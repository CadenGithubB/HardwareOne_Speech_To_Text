#!/usr/bin/env python3
"""Mac mini side of the HW1 heap-tripwire work (driven by Claude over Remote Desktop).

  identify          MAC + partition-table hash check (read-only)
  flash IMAGE       identify, write IMAGE at 0x10000, verify
  restore SLOT      identify, write a full 0x715000-byte slot backup, verify
  timing CLIP [S]   one boot; one STT session per tripwire configuration on the first S
                    seconds (default 100) of the same clip, acknowledging captions as they come;
                    per-phrase speech-model and speaker-NN timings for each
  stack CLIP N S    N sessions, fresh boot each, first S seconds of CLIP; speaker-stack
                    placement and lowest free stack, plus a command right after teardown
  upload WAV DEST   convert WAV to 16 kHz mono PCM and write it to DEST on the SD card
  bench LABEL PCM N N fresh-boot STT sessions reading PCM (an SD path) instead of the mic
  cal               calibration: status, watch on core 0/1, selftest

Everything lands in ~/claude-heaptw/ (not /private/tmp, which a reboot wipes). The device login is read from
device-login (mode 600) and scrubbed from logs. Uses ChatGPT's find_p4_port.py
(USB serial number match) to pick the port; never guesses between ports.
"""
import fcntl, json, os, re, statistics, subprocess, sys, termios, threading, time
from pathlib import Path

import serial

ROOT = Path('/Users/cadbecaimacmini/claude-heaptw')
FIND_PORT = ROOT / 'find_p4_port.py'
EXPECT_MAC = 'e8:f6:0a:e3:a7:68'
EXPECT_PT_SHA = '39b3160f424d886b0939b43d3e127d893a6bb93d843d8e530d8acd8f1a33c5c3'
SLOT_OFFSET, SLOT_SIZE = 0x10000, 0x715000
PANIC = re.compile(r'Guru Meditation|abort\(\) was called|HW1TW heap header changed')


def log(msg):
    line = f'{time.strftime("%H:%M:%S")} {msg}'
    print(line, flush=True)
    with open(ROOT / 'progress.log', 'a') as f:
        f.write(line + '\n')


def sha(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def port():
    out = subprocess.run([sys.executable, str(FIND_PORT)], capture_output=True, text=True, timeout=30,
                         env={**os.environ, 'UNIT_MAC': EXPECT_MAC})
    p = out.stdout.strip()
    if out.returncode or not p.startswith('/dev/'):
        sys.exit(f'P4 port not resolved: {out.stderr.strip() or p}')
    return p


def esptool(*args):
    cmd = [sys.executable, '-m', 'esptool', '--chip', 'esp32p4', '--port', port(), '--baud', '921600', *args]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    with open(ROOT / 'esptool.log', 'a') as f:
        f.write('$ ' + ' '.join(cmd[2:]) + '\n' + out.stdout + out.stderr)
    if out.returncode:
        sys.exit(f'esptool {args[0]} failed (see esptool.log)')
    return out.stdout + out.stderr


def identify():
    if EXPECT_MAC not in esptool('read_mac').lower():
        sys.exit('MAC mismatch')
    pt = ROOT / 'partition-table-read.bin'
    esptool('read_flash', '0x8000', '0xc00', str(pt))
    if sha(pt) != EXPECT_PT_SHA:
        sys.exit('partition table differs from the recorded table: stop')
    log(f'identity ok: mac {EXPECT_MAC}, partition table {EXPECT_PT_SHA[:8]}')


def credentials():
    f = ROOT / 'device-login'
    if f.stat().st_mode & 0o077:
        sys.exit('device-login must be mode 600')
    user, pw = f.read_text().split()[:2]
    return user, pw


class Console:
    def __init__(self, logpath):
        self.lines, self.lock, self.stop_flag, self.ser = [], threading.Lock(), False, None
        self.logpath = logpath
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    @staticmethod
    def _scrub(s):
        return re.sub(r'(login\s+)\S+(\s+)\S+', r'\1***\2***', s)

    def _open(self):
        p = port()
        while not self.stop_flag:
            try:
                s = serial.Serial()
                s.port, s.baudrate, s.timeout = p, 115200, 0.1
                s.dtr = s.rts = False
                s.open()
                # Exclusive tty: another program's open (e.g. an esptool probe, whose
                # connect sequence resets the P4 into download mode) fails with EBUSY.
                fcntl.ioctl(s.fileno(), getattr(termios, 'TIOCEXCL', 0x2000740d))
                return s
            except (serial.SerialException, OSError):
                time.sleep(0.5)

    def close(self):
        self.stop_flag = True
        self.thread.join(timeout=5)

    def _run(self):
        buf = b''
        with open(self.logpath, 'a') as out:
            self._loop(out, buf)
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:  # noqa: BLE001
                pass

    def _loop(self, out, buf):
        while not self.stop_flag:
            if self.ser is None:
                self.ser = self._open()
                if self.ser is None:   # stopped while waiting for the port
                    return
            try:
                buf += self.ser.read(4096)
            except (serial.SerialException, OSError):
                try:
                    self.ser.close()
                except Exception:  # noqa: BLE001
                    pass
                self.ser = None
                continue
            while b'\n' in buf:
                raw, buf = buf.split(b'\n', 1)
                line = self._scrub(raw.decode('utf-8', 'replace').rstrip('\r'))
                out.write(f'{time.time():.3f} {line}\n')
                out.flush()
                with self.lock:
                    self.lines.append(line)

    def mark(self):
        with self.lock:
            return len(self.lines)

    def since(self, start):
        with self.lock:
            return self.lines[start:]

    def wait(self, pattern, start, timeout):
        rx, end = re.compile(pattern), time.monotonic() + timeout
        while time.monotonic() < end:
            for line in self.since(start):
                m = rx.search(line)
                if m:
                    return m
            time.sleep(0.05)
        return None

    def send(self, cmd):
        for _ in range(40):
            if self.ser is not None:
                try:
                    self.ser.write((cmd + '\n').encode())
                    return
                except (serial.SerialException, OSError):
                    pass
            time.sleep(0.25)
        raise RuntimeError('serial port unavailable')

    def command(self, cmd, pattern, timeout=20):
        start = self.mark()
        self.send(cmd)
        m = self.wait(pattern, start, timeout)
        if not m:
            raise RuntimeError(f'no reply to {cmd.split()[0]} {cmd.split()[1] if cmd.startswith("sttperf") else ""}')
        return m


def ready(con):
    user, pw = credentials()
    con.wait(r'HW1TW', con.mark(), 25)
    time.sleep(8)
    for attempt in range(10):
        try:
            con.command(f'login {user} {pw}', r'Login successful', 10)
            break
        except RuntimeError:
            if attempt == 9:
                raise
            time.sleep(5)
    con.command('loglink on', r'loglink ON', 20)
    con.command('sttperf log on', r'STT perf live log: ON', 20)
    return con.command('sttperf heaptw status', r'TL heaptw status .*end', 20).group(0)


def kv(line):
    return {k: int(v) for k, v in re.findall(r'\b([a-z_0-9]+)=(-?\d+)\b', line)}


def drain_once(con, tok):
    """Acknowledge at most one waiting caption, as the production runner does."""
    nxt = json.loads(con.command(f'stt next {tok}', r'\{[^\r\n]*"available":(?:true|false)[^\r\n]*\}').group(0))
    if nxt.get('available'):
        con.command(f'stt ack {tok} {nxt["sequence"]}', r'STT chunk acknowledged', 20)
        return 1
    return 0


def stt_session(con, clip, seconds):
    start = con.mark()
    tok = con.command('stt start', r'"accepted":true,"id":"([0-9a-f]{16})"', 30).group(1)
    end = time.monotonic() + 120
    while time.monotonic() < end:
        st = json.loads(con.command(f'stt status {tok}', r'\{[^\r\n]*"state":[^\r\n]*\}').group(0))
        if st.get('state') == 'recording' and st.get('captureActive'):
            break
        time.sleep(1)
    time.sleep(2)
    # Keep acknowledging captions while the clip plays and for 10 s after it:
    # an unacknowledged backlog ends the session early.
    play = subprocess.Popen(['afplay', '-t', str(seconds), str(clip)])
    acked, post_end = 0, None
    while True:
        acked += drain_once(con, tok)
        if play.poll() is not None:
            post_end = post_end or time.monotonic() + 10
            if time.monotonic() >= post_end:
                break
        time.sleep(0.5)
    stop = con.command(f'stt stop {tok}', r'STT request accepted|no matching STT run', 20).group(0)
    ended_early = 'no matching' in stop
    state, end = None, time.monotonic() + 240
    while time.monotonic() < end:
        n = drain_once(con, tok)
        acked += n
        if n:
            continue
        state = json.loads(con.command(f'stt status {tok}', r'\{[^\r\n]*"state":[^\r\n]*\}').group(0))
        if state.get('state') in ('done', 'failed', 'cancelled'):
            break
        time.sleep(0.5)
    time.sleep(3)   # let late speaker lines arrive
    lines = con.since(start)
    seg = [kv(l) for l in lines if 'TL seg=' in l]
    spk = [kv(l) for l in lines if 'TL spk seq=' in l]
    ratio = [s['n'] / (s['a1'] - s['a0']) for s in seg if s.get('a1', 0) > s.get('a0', 0) and 'n' in s]
    nn = [s['nn_us'] / 1000 for s in spk if 'nn_us' in s]
    med = lambda v: round(statistics.median(v), 3) if v else None
    spk_end = [kv(l) for l in lines if 'TL spk_end' in l]
    return {'state': (state or {}).get('state'), 'error': (state or {}).get('error'), 'ended_early': ended_early,
            'overruns': (state or {}).get('audioOverruns'), 'acked': acked,
            'phrases': len(seg), 'model_ms_per_audio_ms': med(ratio), 'speaker_nn_ms_median': med(nn),
            'speaker_nn_ms_max': round(max(nn), 1) if nn else None, 'speaker_jobs': len(nn),
            'speaker_skipped': spk_end[-1].get('skipped') if spk_end else None,
            'watchdog': sum('Task watchdog got triggered' in l for l in lines),
            'panic': any(PANIC.search(l) for l in lines)}


CONFIGS = [  # name, watch, timer Hz, hooks
    ('all-off', 'off', '0', 'off'),
    ('watch-on', 'on', '0', 'off'),
    ('timer-1000', 'off', '1000', 'off'),
    ('hooks-on', 'off', '0', 'on'),
    ('v2-default', 'auto', '100', 'on'),
]


def cmd_timing(clip, seconds):
    run = ROOT / time.strftime('timing-%Y%m%d-%H%M%S')
    run.mkdir(mode=0o700)
    subprocess.run(['osascript', '-e', 'set volume output volume 50 without output muted'], check=True)
    con = Console(run / 'serial.log')
    status = ready(con)
    log(f'ready ({clip.name}, {seconds}s per config): ' + status)
    results = []
    try:
        for name, watch, timer, hooks in CONFIGS:
            con.command(f'sttperf heaptw watch {watch}', r'OK: heaptw watch set')
            con.command(f'sttperf heaptw timer {timer}', r'OK: heaptw timer set')
            con.command(f'sttperf heaptw hooks {hooks}', r'OK: heaptw hooks set')
            st = con.command('sttperf heaptw status', r'TL heaptw status .*end').group(0)
            log(f'{name}: {st[st.index("watch="):st.index(" heap=")]}')
            r = stt_session(con, clip, seconds)
            r['config'] = name
            results.append(r)
            (run / 'timing.json').write_text(json.dumps(results, indent=2))
            log(f'{name}: {json.dumps(r)}')
            if r['panic']:
                log('panic seen: stopping; read the record before anything else')
                return
            time.sleep(5)
    finally:
        if not any(r.get('panic') for r in results):
            for cmd, rx in (('watch auto', 'watch set'), ('timer 100', 'timer set'), ('hooks on', 'hooks set')):
                try:
                    con.command(f'sttperf heaptw {cmd}', 'OK: heaptw ' + rx)
                except RuntimeError as exc:
                    log(f'could not restore {cmd}: {exc}')
        con.close()
        log('timing finished: ' + str(run))


def cmd_stack(clip, sessions, seconds, uncached=False):
    run = ROOT / time.strftime('stack-%Y%m%d-%H%M%S')
    run.mkdir(mode=0o700)
    subprocess.run(['osascript', '-e', 'set volume output volume 50 without output muted'], check=True)
    summary = []
    for k in range(sessions):
        con = Console(run / f'serial-{k}.log')   # opening the port reboots the board: fresh boot per session
        try:
            status = ready(con)
            if k == 0 and 'saved=1' in status:
                # An earlier capture is still retained; it was already copied off.
                con.command('sttperf heaptw clear', r'OK: heaptw cleared')
            if uncached:
                # Write the header's cache line back to PSRAM and compare both views
                # from here on: separates DMA, cached CPU stores and invalidation.
                con.command('sttperf heaptw uncached', r'OK: heaptw uncached compare on')
                status = con.command('sttperf heaptw status', r'TL heaptw status .*end').group(0)
            log(f'session {k} ready: ' + status)
            start = con.mark()
            r = stt_session(con, clip, seconds)
            # The old faults surfaced on the first command after teardown.
            r['status_after'] = con.command('sttperf heaptw status', r'TL heaptw status .*end').group(0)
            lines = con.since(start)
            creates = [kv(l) for l in lines if 'TL spkstack create' in l]
            jobs = [kv(l) for l in lines if 'TL spkstack job' in l or 'TL spkstack end' in l]
            r['stack_off'] = [c.get('off') for c in creates]
            r['stack_free_min'] = min((j['free_min'] for j in jobs if 'free_min' in j), default=None)
            r['stack_free_trace'] = [j.get('free_min') for j in jobs]
            r['session'] = k
            summary.append(r)
            (run / 'stack.json').write_text(json.dumps(summary, indent=2))
            log(f'session {k}: off={r["stack_off"]} free_min={r["stack_free_min"]} watchdog={r["watchdog"]} '
                f'panic={r["panic"]} state={r["state"]} acked={r["acked"]} {r["status_after"][-40:]}')
            if r['panic'] or 'saved=1' in r['status_after']:
                time.sleep(3)
                ready(con)
                s2 = con.mark()
                con.command('sttperf heaptw read', r'OK: heaptw (read|no saved record)', 60)
                (run / f'capture-{k}.txt').write_text('\n'.join(l for l in con.since(s2) if 'TL heaptw saved' in l) + '\n')
                log(f'session {k}: capture saved; stopping (record not cleared)')
                return
        except Exception as exc:  # noqa: BLE001
            # A crash mid-session shows up as a command timeout. Read the black
            # box before anything else touches the board, then stop.
            log(f'session {k}: error {exc}; reading the record, then stopping')
            try:
                time.sleep(3)
                ready(con)
                s2 = con.mark()
                con.command('sttperf heaptw read', r'OK: heaptw (read|no saved record)', 60)
                rec = [l for l in con.since(s2) if 'TL heaptw saved' in l]
                (run / f'capture-{k}.txt').write_text('\n'.join(rec) + '\n')
                log(f'session {k}: record lines {len(rec)} (not cleared)')
            except Exception as exc2:  # noqa: BLE001
                log(f'session {k}: record read failed: {exc2}')
            return
        finally:
            con.close()
            time.sleep(2)
    log('stack sessions done: ' + str(run))


def ready_plain(con):
    """Log in on a build without the tripwire."""
    user, pw = credentials()
    time.sleep(25)
    for attempt in range(10):
        try:
            con.command(f'login {user} {pw}', r'Login successful', 10)
            break
        except RuntimeError:
            if attempt == 9:
                raise
            time.sleep(5)
    con.command('loglink on', r'loglink ON', 20)
    con.command('sttperf log on', r'STT perf live log: ON', 20)


def cmd_upload(wav, dest):
    """Convert a WAV to 16 kHz mono int16 PCM and append it to an SD file in base64 chunks."""
    import base64, wave
    tmp = ROOT / 'upload-16k.wav'
    subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', str(wav), str(tmp)], check=True)
    with wave.open(str(tmp), 'rb') as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
        pcm = w.readframes(w.getnframes())
    (ROOT / 'upload.pcm').write_bytes(pcm)
    log(f'upload: {len(pcm)} bytes ({len(pcm) / 32000:.1f} s) sha256 {sha(ROOT / "upload.pcm")} -> {dest}')
    run = ROOT / time.strftime('upload-%Y%m%d-%H%M%S')
    run.mkdir(mode=0o700)
    con = Console(run / 'serial.log')
    try:
        ready_plain(con)
        chunk = 1400
        for off in range(0, len(pcm), chunk):
            b64 = base64.b64encode(pcm[off:off + chunk]).decode()
            for attempt in range(3):
                try:
                    con.command(f'filewrite "{dest}" {off} {b64}', r'"success":true', 20)
                    break
                except RuntimeError:
                    if attempt == 2:
                        raise
            if off % (chunk * 500) == 0:
                log(f'upload: {off}/{len(pcm)}')
        log(f'upload done: {len(pcm)} bytes')
    finally:
        con.close()


def bench_session(con, tok_timeout=300, probes=()):
    start = con.mark()
    tok = con.command('stt start', r'"accepted":true,"id":"([0-9a-f]{16})"', 30).group(1)
    acked, state, captions = 0, None, []
    t0 = time.monotonic()
    end = t0 + tok_timeout
    pending = sorted(probes)
    while time.monotonic() < end:
        if pending and time.monotonic() - t0 >= pending[0]:
            pending.pop(0)
            con.command('sttperf stacks', r'OK: stacks', 20)
        nxt = json.loads(con.command(f'stt next {tok}', r'\{[^\r\n]*"available":(?:true|false)[^\r\n]*\}').group(0))
        if nxt.get('available'):
            captions.append(nxt)
            con.command(f'stt ack {tok} {nxt["sequence"]}', r'STT chunk acknowledged', 20)
            acked += 1
            continue
        state = json.loads(con.command(f'stt status {tok}', r'\{[^\r\n]*"state":[^\r\n]*\}').group(0))
        if state.get('state') in ('done', 'failed', 'cancelled'):
            break
        time.sleep(0.5)
    time.sleep(3)
    lines = con.since(start)
    seg = [kv(l) for l in lines if 'TL seg=' in l]
    spk = [kv(l) for l in lines if 'TL spk seq=' in l]
    ratio = [x['n'] / (x['a1'] - x['a0']) for x in seg if x.get('a1', 0) > x.get('a0', 0) and 'n' in x]
    nn = [x['nn_us'] / 1000 for x in spk if 'nn_us' in x]
    med = lambda v: round(statistics.median(v), 4) if v else None
    return {'state': (state or {}).get('state'), 'error': (state or {}).get('error'), 'acked': acked,
            'phrases': len(seg), 'model_ms_per_audio_ms': med(ratio), 'speaker_nn_ms_median': med(nn),
            'speaker_jobs': len(nn), 'watchdog': sum('Task watchdog got triggered' in l for l in lines),
            'panic': any(PANIC.search(l) for l in lines), 'captions': captions}


def cmd_bench(label, pcm_path, runs, probes=()):
    """Fresh boot per run; the board reads pcm_path instead of the microphone."""
    run = ROOT / time.strftime(f'bench-{label}-%Y%m%d-%H%M%S')
    run.mkdir(mode=0o700)
    results = []
    for k in range(runs):
        con = Console(run / f'serial-{k}.log')
        try:
            ready_plain(con)
            con.command(f'sttperf pcmsrc "{pcm_path}"', r'OK: STT input is the benchmark PCM file')
            if label.endswith('wp'):
                con.command('sttperf watchhdr', r'OK: watchhdr armed', 20)
            if 'mm' in label:
                save_mmlog(con, run / f'mmlog-before-{k}.txt')
                con.command('sttperf mmlog clear', r'OK: mmlog armed', 20)
            r = bench_session(con, probes=probes)
            if 'mm' in label:
                r['mmlog_lines'] = save_mmlog(con, run / f'mmlog-{k}.txt')
            try:   # per-layer model time, slowest 40 (lands in the serial log)
                con.command('sttperf stages', r'STT stage profile', 20)
                time.sleep(1)
            except RuntimeError:
                pass
            r['run'] = k
            results.append(r)
            (run / 'bench.json').write_text(json.dumps(results, indent=2))
            log(f'bench {label} run {k}: state={r["state"]} phrases={r["phrases"]} acked={r["acked"]} '
                f'model={r["model_ms_per_audio_ms"]} spk_nn={r["speaker_nn_ms_median"]} '
                f'wd={r["watchdog"]} panic={r["panic"]}')
        except Exception as exc:  # noqa: BLE001
            log(f'bench {label} run {k}: error {exc}')
            if 'mm' in label:
                # The panic disarmed the ring; read it on the same port after the reboot.
                try:
                    time.sleep(3)
                    ready_plain(con)
                    n = save_mmlog(con, run / f'mmlog-crash-{k}.txt')
                    log(f'bench {label} run {k}: mmlog lines {n}')
                except Exception as exc2:  # noqa: BLE001
                    log(f'bench {label} run {k}: mmlog read failed: {exc2}')
        finally:
            con.close()
            time.sleep(2)
    log(f'bench {label} done: {run}')


def save_mmlog(con, path):
    s2 = con.mark()
    con.command('sttperf mmlog', r'OK: mmlog', 60)
    lines = [l for l in con.since(s2) if 'TL mm' in l]
    if lines:
        path.write_text('\n'.join(lines) + '\n')
    return len(lines)


def read_record(con, path):
    """Save the retained tripwire record (if any) to path; returns its line count."""
    s2 = con.mark()
    con.command('sttperf heaptw read', r'OK: heaptw (read|no saved record)', 90)
    rec = [l for l in con.since(s2) if 'TL heaptw saved' in l]
    if rec:
        path.write_text('\n'.join(rec) + '\n')
    return len(rec)


def cmd_twbench(label, pcm_path, runs, victim=None):
    """bench on a tripwire build: read and clear any retained record first, optionally
    watch one spinlock (sttperf heaptw victim), and read the record after a crash."""
    run = ROOT / time.strftime(f'twbench-{label}-%Y%m%d-%H%M%S')
    run.mkdir(mode=0o700)
    results = []
    for k in range(runs):
        con = Console(run / f'serial-{k}.log')
        try:
            status = ready(con)
            if 'saved=1' in status:
                n = read_record(con, run / f'record-before-{k}.txt')
                log(f'twbench {label} run {k}: earlier record lines {n}')
                con.command('sttperf heaptw clear', r'OK: heaptw cleared')
            if victim:
                con.command(f'sttperf heaptw victim {victim}', r'OK: heaptw victim set')
            con.command(f'sttperf pcmsrc "{pcm_path}"', r'OK: STT input is the benchmark PCM file')
            r = bench_session(con)
            r['run'] = k
            r['status_after'] = con.command('sttperf heaptw status', r'TL heaptw status .*end').group(0)
            s2 = con.mark()
            con.command('sttperf heaptw live', r'OK: heaptw live', 90)
            (run / f'live-{k}.txt').write_text('\n'.join(l for l in con.since(s2) if 'TL heaptw live' in l) + '\n')
            results.append(r)
            (run / 'bench.json').write_text(json.dumps(results, indent=2))
            log(f'twbench {label} run {k}: state={r["state"]} phrases={r["phrases"]} panic={r["panic"]} '
                f'{r["status_after"][-30:]}')
        except Exception as exc:  # noqa: BLE001
            log(f'twbench {label} run {k}: error {exc}; reading the record')
            try:
                # Same port, as cmd_stack does: the panic already rebooted the board.
                time.sleep(3)
                ready(con)
                n = read_record(con, run / f'capture-{k}.txt')
                log(f'twbench {label} run {k}: record lines {n} (not cleared)')
            except Exception as exc2:  # noqa: BLE001
                log(f'twbench {label} run {k}: record read failed: {exc2}')
        finally:
            con.close()
            time.sleep(2)
    log(f'twbench {label} done: {run}')


def cmd_startloop(label, pcm_path, trials):
    """Session start only: fresh boot, stt start on the benchmark file, wait for the session's first
    model load (TL warm) plus 3 s, next trial. Outcome: ok, warm_fail, crash (panic, abort,
    CORRUPT HEAP or a reset line), timeout (nothing within 25 s), error (harness)."""
    import collections
    run = ROOT / time.strftime(f'start-{label}-%Y%m%d-%H%M%S')
    run.mkdir(mode=0o700)
    crash_rx = r'Guru Meditation|abort\(\) was called|CORRUPT HEAP|rst:0x'
    counts = collections.Counter()
    for k in range(trials):
        con = Console(run / f'serial-{k}.log')
        outcome = 'error'
        try:
            ready_plain(con)
            if pcm_path != 'mic':   # 'mic': production builds without sttperf pcmsrc
                con.command(f'sttperf pcmsrc "{pcm_path}"', r'OK: STT input is the benchmark PCM file')
            start = con.mark()
            con.send('stt start')
            m = con.wait(r'TL warm .*?ok=(\d)|' + crash_rx, start, 25)
            if not m:
                outcome = 'timeout'
            elif m.group(0).startswith('TL warm'):
                outcome = 'ok' if m.group(1) == '1' else 'warm_fail'
            else:
                outcome = 'crash'
            if outcome in ('ok', 'warm_fail') and con.wait(crash_rx, start, 3):
                outcome = 'crash'
        except Exception as exc:  # noqa: BLE001
            outcome = f'error {exc}'
        finally:
            con.close()
            time.sleep(2)
        counts[outcome.split()[0]] += 1
        log(f'startloop {label} trial {k}: {outcome}')
    log(f'startloop {label} done: {dict(counts)} {run}')


def cmd_soak(label, clip, pcm_path, sessions, seconds):
    """Production soak (no tripwire): fresh boot per session; even sessions live (clip through the
    mini's speaker at 50%), odd sessions on the benchmark file (silent; pcm_path 'none': all live,
    for builds without sttperf pcmsrc). Never stops on a failure:
    each session is recorded as done, crash (panic/abort/CORRUPT HEAP/reset line in its log) or
    error (no reply), then the next one starts on a fresh boot."""
    import collections
    run = ROOT / time.strftime(f'soak-{label}-%Y%m%d-%H%M%S')
    run.mkdir(mode=0o700)
    subprocess.run(['osascript', '-e', 'set volume output volume 50 without output muted'], check=True)
    crash_rx = re.compile(r'Guru Meditation|abort\(\) was called|CORRUPT HEAP|rst:0x')
    counts = collections.Counter()
    results = []
    for k in range(sessions):
        mode = 'live' if k % 2 == 0 or pcm_path == 'none' else 'file'
        con = Console(run / f'serial-{k}-{mode}.log')
        r = {'session': k, 'mode': mode}
        try:
            ready_plain(con)
            start = con.mark()
            if mode == 'file':
                con.command(f'sttperf pcmsrc "{pcm_path}"', r'OK: STT input is the benchmark PCM file')
                r.update(bench_session(con))
            else:
                r.update(stt_session(con, clip, seconds))
            r.pop('captions', None)
            crashed = any(crash_rx.search(l) for l in con.since(start))
            r['outcome'] = 'crash' if crashed else ('done' if r.get('state') == 'done' else 'ended:' + str(r.get('state')))
        except Exception as exc:  # noqa: BLE001
            subprocess.run(['pkill', '-x', 'afplay'])   # a live clip must not play over the next session
            time.sleep(5)
            crashed = any(crash_rx.search(l) for l in con.since(0))
            r['outcome'] = 'crash' if crashed else 'error'
            r['error'] = str(exc)
        finally:
            con.close()
            time.sleep(2)
        counts[r['outcome']] += 1
        results.append(r)
        (run / 'soak.json').write_text(json.dumps(results, indent=2))
        log(f'soak {label} session {k} {mode}: {r["outcome"]} state={r.get("state")} acked={r.get("acked")} '
            f'model={r.get("model_ms_per_audio_ms")} wd={r.get("watchdog")} {r.get("error", "")[:60]}')
    log(f'soak {label} done: {dict(counts)} {run}')


def cmd_cal():
    run = ROOT / time.strftime('cal-%Y%m%d-%H%M%S')
    run.mkdir(mode=0o700)
    con = Console(run / 'serial.log')
    status = ready(con)
    log('ready: ' + status)
    if 'armed=1' not in status:
        sys.exit('guard not armed')
    con.command('sttperf heaptw clear', r'OK: heaptw cleared')
    for test in ('watchtest0', 'watchtest1', 'selftest'):
        if test != 'selftest':
            con.command('sttperf heaptw watch on', r'OK: heaptw watch set')
        start = con.mark()
        con.send(f'sttperf heaptw {test}')
        if not con.wait(r'Guru Meditation|abort\(\) was called|Rebooting', start, 15):
            sys.exit(f'{test}: no panic')
        ready(con)
        start = con.mark()
        con.command('sttperf heaptw read', r'OK: heaptw (read|no saved record)', 60)
        rec = [l for l in con.since(start) if 'TL heaptw saved' in l]
        (run / f'{test}.txt').write_text('\n'.join(rec) + '\n')
        log(f'{test}: ' + (rec[0] if rec else 'NO RECORD'))
        con.command('sttperf heaptw clear', r'OK: heaptw cleared')
    con.close()
    log('cal done: ' + str(run))


def main():
    ROOT.mkdir(mode=0o700, exist_ok=True)
    op = sys.argv[1]
    if op == 'identify':
        identify()
    elif op in ('flash', 'restore'):
        img = Path(sys.argv[2])
        if op == 'restore' and img.stat().st_size != SLOT_SIZE:
            sys.exit('restore needs a full slot backup')
        identify()
        esptool('write_flash', hex(SLOT_OFFSET), str(img))
        esptool('verify_flash', hex(SLOT_OFFSET), str(img))
        log(f'{op} written and verified: {sha(img)}')
    elif op == 'timing':
        cmd_timing(Path(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 100)
    elif op == 'stack':
        cmd_stack(Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), 'uncached' in sys.argv[5:])
    elif op == 'upload':
        cmd_upload(Path(sys.argv[2]), sys.argv[3])
    elif op == 'bench':
        cmd_bench(sys.argv[2], sys.argv[3], int(sys.argv[4]),
                  [float(x) for x in sys.argv[5].split(',')] if len(sys.argv) > 5 else ())
    elif op == 'twbench':
        cmd_twbench(sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5] if len(sys.argv) > 5 else None)
    elif op == 'startloop':
        cmd_startloop(sys.argv[2], sys.argv[3], int(sys.argv[4]))
    elif op == 'soak':
        cmd_soak(sys.argv[2], Path(sys.argv[3]), sys.argv[4], int(sys.argv[5]), int(sys.argv[6]))
    elif op == 'cal':
        cmd_cal()
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
