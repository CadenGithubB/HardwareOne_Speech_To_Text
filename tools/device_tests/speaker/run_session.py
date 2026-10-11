#!/usr/bin/env python3
"""Speaker-to-P4-mic STT timing sessions (needs pyserial: use the IDF python).

  PY=~/.espressif/python_env/idf5.5_py3.9_env/bin/python
  $PY run_session.py --label base [--sessions K] [--wav playlist/playlist.wav]
  $PY run_session.py --capture-only 30          # boot capture, no audio
  $PY run_session.py --calibrate-afplay         # silent afplay latency test only

One session:
  1. resolve the test P4's port by its USB serial (= chip MAC) via
     ../find_p4_port.py, without opening anything;
  2. open the port (DTR/RTS released first, the pattern the bench scripts use;
     on this Mac the open resets the P4). If no boot is seen within 3 s, a
     plain esptool-style hard reset (RTS pulse, DTR low = normal boot) is sent;
  3. a reader thread drains the port continuously and stamps every line with
     time.monotonic() and time.time() when its newline arrives;
  4. wait for TL capture_start and TL warm from this boot (--ready), then
     --settle s (default 2);
  5. read (never set) the output volume; refuse to play if it is muted or not
     --expect-volume;
  6. play the WAV with `afplay -d` under a pty, recording the monotonic time
     just before launch, afplay's own 'Buffer Byte Size' line (its last print
     before starting), the CoreAudio output device's IO start, and the exit;
  7. keep reading until --post s after playback ends, then close the port.
Each session gets <root>/<label>/<stamp>_s<k>/ with raw.log (bytes as received),
lines.tsv (mono, wall, line) and session.json (all timings + metadata). raw.log
and lines.tsv hold transcript text (TL txt) and are 0600; this script prints
only status and counts, never transcript text.

Do not run this while anything else holds the port (esptool, a monitor). It
never flashes, never sends CLI commands, never changes system settings.
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path

import serial

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import afplay_timing  # noqa: E402
import coreaudio_probe as cap  # noqa: E402
from tl_parse import FATAL, ROM_BOOT, parse_line  # noqa: E402

FIND_PORT = HERE.parent / 'find_p4_port.py'
DEFAULT_ROOT = HERE / 'sessions'


def resolve_port():
    out = subprocess.run([sys.executable, str(FIND_PORT)], capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise SystemExit(f'P4 port not resolved: {out.stderr.strip() or out.stdout.strip()}')
    return out.stdout.strip()


def private_file(path, mode='wb'):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(fd, mode)


class Reader(threading.Thread):
    """Drains the serial port continuously and timestamps each line."""

    def __init__(self, ser, outdir):
        super().__init__(daemon=True)
        self.ser = ser
        self.raw = private_file(outdir / 'raw.log', 'wb')
        self.tsv = private_file(outdir / 'lines.tsv', 'w')
        self.tsv.write('# mono_s\twall_s\tline (newline arrival time; ANSI codes kept as received)\n')
        self.stop_ev = threading.Event()
        self.lock = threading.Lock()
        self.n_lines = 0
        self.n_bytes = 0
        self.first_byte_mono = None
        self.boot_marks = []        # mono of ROM boot banners
        self.small_tick_mono = None  # first ESP log line with tick < 3000 ms (fresh boot)
        self.fatal = []             # (mono, short marker)
        self.tl_counts = {}
        self.first_tl = {}          # kind -> mono of first occurrence
        self.last_tick = None
        self.tick_offsets = []      # (mono, tick) for ESP log lines
        self.error = None

    def run(self):
        pending = b''
        try:
            while not self.stop_ev.is_set():
                try:
                    n = self.ser.in_waiting
                    data = self.ser.read(max(1, min(n, 65536)))
                except (serial.SerialException, OSError) as exc:
                    self.error = repr(exc)
                    break
                if not data:
                    continue
                mono, wall = time.monotonic(), time.time()
                if self.first_byte_mono is None:
                    self.first_byte_mono = mono
                self.raw.write(data)
                self.n_bytes += len(data)
                pending += data
                *lines, pending = pending.split(b'\n')
                for ln in lines:
                    self._line(mono, wall, ln)
                self.raw.flush()
                self.tsv.flush()
        finally:
            if pending:
                self._line(time.monotonic(), time.time(), pending)
            self.raw.close()
            self.tsv.close()

    def _line(self, mono, wall, ln):
        text = ln.decode('utf-8', 'replace').rstrip('\r')
        self.tsv.write(f'{mono:.6f}\t{wall:.6f}\t{text.replace(chr(9), " ")}\n')
        with self.lock:
            self.n_lines += 1
            if ROM_BOOT.search(text):
                self.boot_marks.append(mono)
            if FATAL.search(text):
                self.fatal.append((mono, FATAL.search(text).group(0)))
            p = parse_line(text)
            if p['tick'] is not None:
                self.tick_offsets.append((mono, p['tick']))
                if p['tick'] < 3000 and self.small_tick_mono is None:
                    self.small_tick_mono = mono
                self.last_tick = p['tick']
            if p['tl']:
                k = p['tl']['kind']
                self.tl_counts[k] = self.tl_counts.get(k, 0) + 1
                self.first_tl.setdefault(k, mono)

    def stop(self):
        self.stop_ev.set()
        self.join(timeout=3)


def wait_for(pred, timeout, step=0.02):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(step)
    return pred()


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def wav_seconds(path):
    import wave
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def open_and_boot(port, reader_dir, force_reset=True):
    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = port, 115200, 0.05
    ser.dtr, ser.rts = False, False
    try:
        ser.exclusive = True
    except Exception:  # noqa: BLE001
        pass
    t_open0 = time.monotonic()
    ser.open()  # on this Mac this resets the P4
    t_open1 = time.monotonic()
    rd = Reader(ser, reader_dir)
    rd.start()
    boot = {'t_open_call': t_open0, 't_open_done': t_open1, 'forced_reset': False}
    seen = wait_for(lambda: rd.boot_marks or rd.small_tick_mono is not None, 3.0)
    if not seen and force_reset:
        # esptool HardReset(uses_usb=True): RTS high with DTR low = chip reset into the app
        boot['forced_reset'] = True
        boot['t_forced_reset'] = time.monotonic()
        ser.dtr = False
        ser.rts = True
        time.sleep(0.2)
        ser.rts = False
        time.sleep(0.2)
        seen = wait_for(lambda: rd.boot_marks or rd.small_tick_mono is not None, 5.0)
    boot['boot_seen'] = bool(seen)
    boot['t_boot_banner'] = rd.boot_marks[0] if rd.boot_marks else None
    boot['t_first_small_tick_line'] = rd.small_tick_mono
    boot['t_first_byte'] = rd.first_byte_mono
    return ser, rd, boot


def allowed_boots(boot):
    """The open-induced reset gives one ROM banner; a forced reset may add one."""
    return 2 if boot.get('forced_reset') else 1


def tick_offset_summary(rd):
    """Lower envelope of (mono_ms - tick): offset + minimum transport delay."""
    with rd.lock:
        pts = list(rd.tick_offsets)
    if not pts:
        return None
    d = sorted(m * 1000.0 - t for m, t in pts)
    return {'n': len(d), 'min_ms': round(d[0], 2), 'p10_ms': round(d[len(d) // 10], 2),
            'median_ms': round(d[len(d) // 2], 2), 'spread_p10_minus_min_ms': round(d[len(d) // 10] - d[0], 2)}


def session(a, k, port, outroot, calib):
    stamp = time.strftime('%Y%m%d-%H%M%S')
    sdir = outroot / f'{stamp}_s{k}'
    sdir.mkdir(parents=True, exist_ok=False, mode=0o700)
    meta = {'label': a.label, 'session_index': k, 'port': port, 'started_wall': time.time(),
            'started_iso': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'host': platform.node(),
            'python': sys.version.split()[0], 'pyserial': serial.__version__, 'mode': a.mode,
            'afplay_calibration': calib, 'status': 'running'}
    if a.mode == 'session':
        meta.update(wav=str(a.wav), wav_sha256=sha256(a.wav), wav_seconds=wav_seconds(a.wav),
                    manifest=str(a.manifest), settle_s=a.settle, post_s=a.post)
    ser = rd = None
    try:
        ser, rd, boot = open_and_boot(port, sdir, force_reset=not a.no_force_reset)
        meta['boot'] = boot
        print(f'[s{k}] port open, boot_seen={boot["boot_seen"]} forced_reset={boot["forced_reset"]}', flush=True)
        if a.mode == 'capture':
            time.sleep(a.capture_only)
            meta['status'] = 'captured'
            return meta, sdir, rd
        t0 = boot['t_open_done']
        need = [x for x in a.ready.split(',') if x]
        ok = wait_for(lambda: all(x in rd.first_tl for x in need), a.warm_timeout)
        meta['ready_kinds'] = need
        meta['t_ready_lines'] = {x: rd.first_tl.get(x) for x in need}
        meta['t_capture_start_line'] = rd.first_tl.get('capture_start')
        meta['t_warm_line'] = rd.first_tl.get('warm')
        if not ok:
            meta['status'] = 'no_warm'
            print(f'[s{k}] no TL {"+".join(need)} within {a.warm_timeout:.0f} s; not playing', flush=True)
            time.sleep(1.0)
            return meta, sdir, rd
        t_ready = max(rd.first_tl[x] for x in need)
        meta['t_ready'] = t_ready
        print(f'[s{k}] warm at +{t_ready - t0:.2f} s after open; settling {a.settle:.1f} s', flush=True)
        vol = cap.read_output_volume()   # read only (osascript, ~0.2 s), done inside the settle window
        meta['volume_read_only'] = vol
        time.sleep(max(0.0, t_ready + a.settle - time.monotonic()))
        if vol.get('output_muted') == 'true' or (a.expect_volume >= 0 and vol.get('output_volume') != str(a.expect_volume)):
            meta['status'] = 'volume_mismatch'
            print(f'[s{k}] output volume is {vol.get("output_volume")} muted={vol.get("output_muted")} '
                  f'(expected {a.expect_volume}); not playing and not changing it', flush=True)
            return meta, sdir, rd
        if rd.fatal or len(rd.boot_marks) > allowed_boots(boot):
            meta['status'] = 'fault_before_play'
            return meta, sdir, rd
        play = afplay_timing.play_timed(a.wav, calib or {})
        meta['afplay'] = play
        meta['afplay_summary'] = afplay_timing.summarize(play)
        if play.get('returncode') != 0:
            meta['status'] = 'afplay_failed'
        end_play = max(play['t_exit'], (play.get('t_audio_start') or play['t_launch']) + meta['wav_seconds'])
        print(f'[s{k}] played: launch->audio {meta["afplay_summary"]["launch_to_audio_ms"]} ms '
              f'({play["audio_start_method"]}); reading {a.post:.0f} s more', flush=True)
        time.sleep(max(0.0, end_play + a.post - time.monotonic()))
        if meta['status'] == 'running':
            meta['status'] = 'ok'
        return meta, sdir, rd
    except serial.SerialException as exc:
        meta['status'] = f'serial_error: {exc}'
        return meta, sdir, rd
    finally:
        if rd is not None:
            rd.stop()
        if ser is not None:
            try:
                ser.close()
            except Exception:  # noqa: BLE001
                pass
        meta['ended_wall'] = time.time()
        meta['t_end'] = time.monotonic()
        if rd is not None:
            meta['reader'] = {'lines': rd.n_lines, 'bytes': rd.n_bytes, 'boot_banners': rd.boot_marks,
                              'fatal_markers': rd.fatal, 'tl_counts': rd.tl_counts, 'first_tl_mono': rd.first_tl,
                              'reader_error': rd.error, 'tick_offset': tick_offset_summary(rd)}
            if (len(rd.boot_marks) > allowed_boots(meta.get('boot') or {}) or rd.fatal) \
                    and meta['status'] in ('ok', 'running', 'captured'):
                meta['status'] = 'fault'
        (sdir / 'session.json').write_text(json.dumps(meta, indent=1, default=str))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--label', default='unlabelled', help='build name, used as the results sub-folder')
    ap.add_argument('--sessions', type=int, default=1)
    ap.add_argument('--wav', type=Path, default=HERE / 'playlist' / 'playlist.wav')
    ap.add_argument('--manifest', type=Path, default=HERE / 'playlist' / 'manifest.json')
    ap.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    ap.add_argument('--port', default='auto', help="'auto' resolves the test P4 by MAC")
    ap.add_argument('--settle', type=float, default=2.0, help='seconds after warm-up before playing')
    ap.add_argument('--post', type=float, default=10.0, help='seconds to keep reading after playback ends')
    ap.add_argument('--warm-timeout', type=float, default=90.0)
    ap.add_argument('--ready', default='capture_start,warm',
                    help='TL line kinds that must all be seen (this boot) before the settle delay')
    ap.add_argument('--between', type=float, default=3.0, help='pause between sessions')
    ap.add_argument('--expect-volume', type=int, default=54, help='-1 skips the check (it is only read)')
    ap.add_argument('--no-force-reset', action='store_true')
    ap.add_argument('--no-analyse', action='store_true', help='skip the per-session analysis printout')
    ap.add_argument('--capture-only', type=float, default=None, metavar='SECONDS',
                    help='open (reboots the P4), capture for SECONDS, no audio')
    ap.add_argument('--calibrate-afplay', action='store_true', help='only run the silent afplay latency test')
    ap.add_argument('--calib-trials', type=int, default=3)
    a = ap.parse_args()
    a.mode = 'capture' if a.capture_only is not None else 'session'

    if a.calibrate_afplay:
        c = afplay_timing.calibrate(a.calib_trials, 0.0, a.root / 'afplay_calibration.json')
        a.root.mkdir(parents=True, exist_ok=True)
        print(json.dumps(c['summary'], indent=1))
        return
    if a.mode == 'session':
        for p in (a.wav, a.manifest):
            if not p.exists():
                raise SystemExit(f'missing {p}; run build_playlist.py first')
    outroot = a.root / (a.label if a.mode == 'session' else f'{a.label}-capture')
    outroot.mkdir(parents=True, exist_ok=True)
    calib = None
    if a.mode == 'session':
        calib_all = afplay_timing.calibrate(a.calib_trials, 0.0, None)
        calib = {k: calib_all[k] for k in ('launch_to_audio_ms', 'dbg_buffer_to_audio_ms', 'summary',
                                           'output_path', 'measured_at_wall') if k in calib_all}
        print(f'afplay launch->audio median {calib.get("launch_to_audio_ms")} ms '
              f'(silent test, {a.calib_trials} trials)', flush=True)
    results = []
    for k in range(1, a.sessions + 1):
        port = resolve_port() if a.port == 'auto' else a.port
        meta, sdir, rd = session(a, k, port, outroot, calib)
        r = meta.get('reader', {})
        print(f'[s{k}] {meta["status"]}: {r.get("lines")} lines, TL {r.get("tl_counts")}, '
              f'fatal={len(r.get("fatal_markers") or [])}, boots={len(r.get("boot_banners") or [])}, '
              f'tick offset {r.get("tick_offset")} -> {sdir}', flush=True)
        results.append({'dir': str(sdir), 'status': meta['status']})
        if meta['status'] == 'ok' and not a.no_analyse:
            try:
                import analyse  # stdlib only; prints numbers, never transcript text
                analyse.analyse_session(sdir)
            except Exception as exc:  # noqa: BLE001
                print(f'[s{k}] analysis failed: {exc!r} (run analyse.py on {sdir})', flush=True)
        if k < a.sessions:
            time.sleep(a.between)
    (outroot / f'run_{time.strftime("%Y%m%d-%H%M%S")}.json').write_text(
        json.dumps({'label': a.label, 'sessions': results, 'afplay_calibration': calib}, indent=1, default=str))
    bad = [r for r in results if r['status'] not in ('ok', 'captured')]
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
