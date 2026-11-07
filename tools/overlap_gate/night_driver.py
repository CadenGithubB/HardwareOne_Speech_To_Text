"""Overnight device A/B driver for the overlap gate (standalone p4_eye_captions build).

For each playlist block, two runs with a fresh boot each: gate ON and gate OFF, order alternating
by block (ON/OFF, OFF/ON, ...). Per run:
  1. esptool chip_id with reset (also re-verifies the board MAC), then wait for "Listening".
  2. USB commands: "overlap on|off", "pcm save on", "overlap status", "perf dump".
  3. Play the block WAV through the Mac speaker with afplay at the bench volume (50).
  4. Wait for the last segments and speaker labels, "perf dump" again.
Every serial line of every run is recorded with host wall and monotonic time (runs/<run>/serial.log).
Run events go to events.jsonl. After the schedule, or at the deadline, the production backup is
restored app-only (MAC and partition-table checks, hash verified) and its boot is recorded.

A busy.lock in ~/claude-heaptw keeps the other bench chains off the board while this runs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import serial

ROOT = Path(__file__).resolve().parents[2]
PHASE4 = ROOT / 'private/training-track/overlap-gate/phase4'
BOARD = PHASE4 / 'board'
MAC = 'e8:f6:0a:e3:a7:68'
PORT = '/dev/cu.usbmodem101'
HEAPTW_LOCK = Path.home() / 'claude-heaptw/busy.lock'
IDF_PY = Path.home() / '.espressif/python_env/idf5.5_py3.9_env/bin/python'
VOLUME = 70   # user choice 6 Nov 2026: Mac mini built-in speaker, P4 about 1 ft away, mic facing it


def now():
    return dt.datetime.now().astimezone().isoformat(timespec='seconds')


class Night:
    def __init__(self, out: Path):
        self.out = out
        self.out.mkdir(parents=True, exist_ok=True)
        self.events = (out / 'events.jsonl').open('a')

    def event(self, **kw):
        kw = dict(time=now(), mono=round(time.monotonic(), 3), **kw)
        self.events.write(json.dumps(kw) + '\n')
        self.events.flush()
        print(json.dumps(kw), flush=True)


def esptool(*args, timeout=300):
    return subprocess.run([str(IDF_PY), '-m', 'esptool', '--chip', 'esp32p4', '-p', PORT, '-b', '921600', *args],
                          capture_output=True, text=True, timeout=timeout)


def reset_board():
    r = esptool('--before', 'default_reset', '--after', 'hard_reset', 'chip_id', timeout=60)
    ok = re.search(r'MAC:\s*' + re.escape(MAC), r.stdout + r.stderr, re.I) is not None
    return ok, (r.stdout + r.stderr)[-400:]


class Console:
    """Serial reader that records every line; never toggles DTR/RTS after open."""

    def __init__(self, log_path: Path):
        self.log = log_path.open('a', buffering=1)
        self.ser = serial.Serial()
        self.ser.port = PORT
        self.ser.baudrate = 115200
        self.ser.timeout = 0.2
        self.ser.dtr = False
        self.ser.rts = False
        self.ser.exclusive = True
        self.ser.open()
        self.lines = []
        self.lock = threading.Lock()
        self.stop = False
        self.t = threading.Thread(target=self._read, daemon=True)
        self.t.start()

    def _read(self):
        buf = b''
        while not self.stop:
            try:
                chunk = self.ser.read(8192)
            except Exception as e:  # port vanished (reset) or closed
                self.log.write(f'{time.time():.3f}\t{time.monotonic():.3f}\t#READ-ERROR {e!r}\n')
                time.sleep(0.5)
                continue
            if not chunk:
                continue
            buf += chunk
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                text = line.decode('utf-8', 'replace').rstrip('\r')
                self.log.write(f'{time.time():.3f}\t{time.monotonic():.3f}\t{text}\n')
                with self.lock:
                    self.lines.append(text)

    def send(self, cmd: str):
        self.log.write(f'{time.time():.3f}\t{time.monotonic():.3f}\t#SEND {cmd}\n')
        self.ser.write((cmd + '\n').encode())
        self.ser.flush()

    def wait_for(self, pattern: str, timeout: float, since: int = 0):
        rx = re.compile(pattern)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                for i in range(since, len(self.lines)):
                    if rx.search(self.lines[i]):
                        return self.lines[i], i + 1
            time.sleep(0.2)
        return None, since

    def count(self, pattern: str, since: int = 0):
        rx = re.compile(pattern)
        with self.lock:
            return sum(1 for l in self.lines[since:] if rx.search(l))

    def close(self):
        self.stop = True
        self.t.join(timeout=2)
        try:
            self.ser.close()
        except Exception:
            pass
        self.log.close()


FAIL = r'Guru Meditation|abort\(\)|rst:0x|Model load failed|No microSD card|Card mount failed|halt'


def run_once(night: Night, block: dict, arm: str, run_name: str, post_s: float, volume: int = VOLUME):
    rdir = night.out / 'runs' / run_name
    rdir.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, 4):
        ok, tail = reset_board()
        if not ok:
            night.event(kind='reset-failed', run=run_name, attempt=attempt, tail=tail)
            time.sleep(10)
            continue
        con = Console(rdir / 'serial.log')
        line, pos = con.wait_for(r'Listening \(noise floor', 180)
        if line:
            break
        night.event(kind='boot-timeout', run=run_name, attempt=attempt, failures=con.count(FAIL))
        con.close()
        time.sleep(5)
    else:
        night.event(kind='run-skipped', run=run_name, reason='board did not reach Listening after 3 attempts')
        return False
    night.event(kind='listening', run=run_name, line=line)
    con.send(f'overlap {arm}')
    ack, pos = con.wait_for(r'Overlap gate (on|off)', 10, pos)
    con.send('pcm save on')
    pcm_ack, pos = con.wait_for(r'PCM save', 10, pos)
    con.send('perf dump')
    time.sleep(3)
    subprocess.run(['osascript', '-e', f'set volume output volume {volume} without output muted'], check=False)
    mark = len(con.lines)
    t0w, t0m = time.time(), time.monotonic()
    play = subprocess.run(['afplay', block['wav']])
    t1w, t1m = time.time(), time.monotonic()
    time.sleep(post_s)
    con.send('perf dump')
    time.sleep(5)
    counts = dict(finals=con.count(r'"type":"final"', mark), overlap_events=con.count(r'"type":"overlap"', mark),
                  overlap_flags=con.count(r'"type":"overlap".*"overlap":true', mark), frame_logs=con.count(r'^STT_OVERLAP ', mark),
                  pcm_saved=con.count(r'^STT_PCM .*"ok":true', mark), pcm_failed=con.count(r'^STT_PCM .*"ok":false', mark),
                  speaker=con.count(r'"type":"speaker"', mark), kbind=con.count(r'TL kbind'), failures=con.count(FAIL, mark),
                  perf=con.count(r'STT_PERF'))
    night.event(kind='run-done', run=run_name, block=block['block'], arm=arm, volume=volume, wav=block['wav'], wav_sha256=block['wav_sha256'],
                ack=ack, pcm_ack=pcm_ack, play_start_wall=round(t0w, 3), play_start_mono=round(t0m, 3), play_end_wall=round(t1w, 3),
                play_end_mono=round(t1m, 3), afplay_rc=play.returncode, counts=counts)
    con.close()
    return True


def restore(night: Night, write: bool = True, image: Path | None = None, want: str | None = None, boot_pattern: str = r'App version:\s+0\.99\.99',
            label: str = 'restore'):
    """App-only write at 0x10000, by default of the production backup. Enters download mode once (chip_id,
    no reset after), re-verifies MAC and partition table in that session, then writes and hard-resets.
    write=False runs every check and reads, without the write (used to test this path). With image/want
    the same checks write another app (the night test build) instead."""
    backup = image or BOARD / 'app-slot-backup.bin'
    want = want or (BOARD / 'app-slot-backup.sha256').read_text().split()[0]
    got = hashlib.sha256(backup.read_bytes()).hexdigest()
    if got != want:
        night.event(kind=f'{label}-aborted', reason='image hash mismatch')
        return False
    pt = night.out / 'pt-at-restore.bin'
    for attempt in range(1, 4):
        r = esptool('--before', 'default_reset', '--after', 'no_reset', 'chip_id', timeout=60)
        if not re.search(r'MAC:\s*' + re.escape(MAC), r.stdout + r.stderr, re.I):
            night.event(kind='restore-retry', attempt=attempt, reason='MAC check failed', tail=(r.stdout + r.stderr)[-300:])
            time.sleep(5)
            continue
        pt.unlink(missing_ok=True)
        r = esptool('--before', 'no_reset', '--after', 'no_reset', 'read_flash', '0x8000', '0xc00', str(pt))
        if pt.exists():
            break
        night.event(kind='restore-retry', attempt=attempt, reason='partition table read failed', tail=(r.stdout + r.stderr)[-300:])
        time.sleep(5)
    else:
        night.event(kind='restore-aborted', reason='could not enter download mode and read the partition table')
        return False
    if pt.read_bytes() != (BOARD / 'partition-table.bin').read_bytes():
        night.event(kind='restore-aborted', reason='partition table changed')
        return False
    if not write:
        esptool('--before', 'no_reset', '--after', 'hard_reset', 'chip_id', timeout=60)
        night.event(kind='restore-check-ok', reason='MAC, partition table and backup hash verified; nothing written')
        return True
    r = esptool('--before', 'no_reset', '--after', 'hard_reset', 'write_flash', '0x10000', str(backup), timeout=900)
    verified = 'Hash of data verified' in (r.stdout + r.stderr)
    night.event(kind=f'{label}-written', image=str(backup), sha256=got, verified=verified, tail=(r.stdout + r.stderr)[-300:])
    con = Console(night.out / f'{label}-boot.log')
    line, _ = con.wait_for(boot_pattern, 60)
    con.close()
    night.event(kind=f'{label}-booted', expected_boot_seen=bool(line), line=line)
    return verified and bool(line)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--manifests', type=Path, default=PHASE4 / 'night1')
    ap.add_argument('--out', type=Path, default=PHASE4 / 'night1-runs')
    ap.add_argument('--deadline', default='08:30', help='local HH:MM: no run starts if it would end after this')
    ap.add_argument('--post', type=float, default=20.0, help='seconds to keep listening after playback')
    ap.add_argument('--blocks', default='all', help='comma list of block numbers, or all')
    ap.add_argument('--dry-wav', type=Path, default=None, help='dry run: play this WAV once with the gate on, no restore')
    ap.add_argument('--no-restore', action='store_true')
    ap.add_argument('--volume', type=int, default=VOLUME)
    ap.add_argument('--check-restore', action='store_true', help='run the restore checks without writing, then exit')
    ap.add_argument('--arms', default='on,off', help='arms per block: "on,off" (A/B, alternating order) or one arm, e.g. "on"')
    ap.add_argument('--flash-app', type=Path, default=None, help='first write this test app at 0x10000 (same checks as restore)')
    ap.add_argument('--flash-sha256', default=None, help='expected SHA-256 of --flash-app')
    args = ap.parse_args()
    if HEAPTW_LOCK.exists():
        sys.exit(f'{HEAPTW_LOCK} exists: another bench chain owns the board')
    HEAPTW_LOCK.write_text(f'overlap-gate night driver pid {os.getpid()} since {now()}\n')
    night = Night(args.out)
    try:
        today = dt.datetime.now()
        hh, mm = map(int, args.deadline.split(':'))
        deadline = today.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if deadline < today:
            deadline += dt.timedelta(days=1)
        if args.check_restore:
            restore(night, write=False)
            return
        if args.flash_app:
            if not restore(night, image=args.flash_app, want=args.flash_sha256, boot_pattern=r'Listening \(noise floor', label='flash-test-app'):
                night.event(kind='night-aborted', reason='test app flash or boot failed')
                return
        if args.dry_wav:
            block = dict(block=0, wav=str(args.dry_wav), wav_sha256=hashlib.sha256(args.dry_wav.read_bytes()).hexdigest(), seconds=0)
            night.event(kind='dry-run-start', wav=str(args.dry_wav))
            run_once(night, block, 'on', f'dry-on-v{args.volume}', args.post, args.volume)
            night.event(kind='dry-run-end')
            return
        blocks = sorted((json.loads(p.read_text()) for p in args.manifests.glob('block*.json')), key=lambda b: b['block'])
        if args.blocks != 'all':
            keep = {int(x) for x in args.blocks.split(',')}
            blocks = [b for b in blocks if b['block'] in keep]
        schedule = []
        for b in blocks:
            arms = args.arms.split(',')
            if len(arms) == 2 and b['block'] % 2 == 0:
                arms = arms[::-1]
            schedule += [(b, a) for a in arms]
        night.event(kind='night-start', runs=len(schedule), deadline=deadline.isoformat(timespec='minutes'),
                    manifests=str(args.manifests))
        for i, (b, arm) in enumerate(schedule, 1):
            expected = b['seconds'] + args.post + 90
            if dt.datetime.now() + dt.timedelta(seconds=expected) > deadline:
                night.event(kind='deadline-stop', remaining=len(schedule) - i + 1)
                break
            run_once(night, b, arm, f'b{b["block"]:02d}-{arm}', args.post, args.volume)
        night.event(kind='night-end')
    finally:
        try:
            if not args.dry_wav and not args.no_restore and not args.check_restore:
                restore(night)
        finally:
            HEAPTW_LOCK.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
