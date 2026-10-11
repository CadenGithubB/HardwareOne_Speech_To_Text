#!/usr/bin/env python3
"""Capture the P4 console non-interactively; keep only numeric TL timing lines.

  ~/.espressif/python_env/idf5.5_py3.9_env/bin/python tl_capture.py OUTDIR \
      [--port auto] [--seconds 600] [--until REGEX] [--mode reset|attach]

NOT YET RUN AGAINST THE DEVICE (drafted read-only on 2026-10-09).
  reset  : open with DTR/RTS released (what p4_cli.py does; observed to reset
           the P4 on this Mac), then an explicit esptool HardReset so every run
           starts from a clean boot (run_app.py pattern).
  attach : monitor-style open that should NOT reset (esp_idf_monitor
           serial_reader.open_serial ordering: lines asserted before open,
           then RTS released before DTR). Verify once: the first captured
           ESP log timestamps must be large (uptime), with no ROM boot banner.
Writes OUTDIR/raw.log (0600; may hold transcript text, never printed) and
OUTDIR/tl.txt (numeric TL lines only). Prints only TL lines and a summary.
The port must not be open elsewhere (esptool, idf.py monitor, a terminal).
"""
import argparse, os, re, subprocess, sys, time
from pathlib import Path
import serial

HERE = Path(__file__).resolve().parent
TL = re.compile(rb'(?:I|W) \((\d+)\) STT: (TL [a-z_0-9]+(?: [a-z0-9_]+=-?[0-9]+(?:MHz)?)*)\s*$')
FATAL = re.compile(rb'Guru Meditation|panic\(|abort\(\)|Brownout|Task watchdog got triggered')
BOOT = re.compile(rb'rst:0x')  # ROM banner: up to two per reset-mode start (open + HardReset), none in attach mode

ap = argparse.ArgumentParser()
ap.add_argument('outdir', type=Path)
ap.add_argument('--port', default='auto')
ap.add_argument('--seconds', type=float, default=600)
ap.add_argument('--until', default=None, help='stop when a line matches (bytes regex)')
ap.add_argument('--mode', choices=['reset', 'attach'], default='reset')
a = ap.parse_args()

port = a.port
if port == 'auto':
    port = subprocess.check_output([sys.executable, str(HERE / 'find_p4_port.py')], text=True).strip()
a.outdir.mkdir(parents=True, exist_ok=True, mode=0o700)
raw = os.fdopen(os.open(a.outdir / 'raw.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb')
tl = open(a.outdir / 'tl.txt', 'x')

s = serial.Serial(port=None, baudrate=115200, timeout=0.1)  # baud is ignored by USB-Serial/JTAG
if a.mode == 'attach':
    s.dtr = True; s.rts = True
else:
    s.dtr = False; s.rts = False
s.port = port
s.open()
if a.mode == 'attach':
    s.rts = False   # RTS first, then DTR: never passes through RTS-only (= chip reset)
    s.dtr = False
else:
    from esptool.reset import HardReset
    HardReset(s, uses_usb=True)()

until = re.compile(a.until.encode()) if a.until else None
pending, n_tl, fatal, boots, t0 = b'', 0, 0, 0, time.monotonic()
try:
    while time.monotonic() - t0 < a.seconds:
        chunk = s.read(max(1, min(s.in_waiting, 4096)))   # keep draining: an undrained port stalls/drops device logs
        if not chunk:
            continue
        raw.write(chunk); raw.flush()
        pending += chunk
        *lines, pending = pending.split(b'\n')
        for line in lines:
            m = TL.search(line.rstrip(b'\r'))
            if m:
                rec = f'[{int(m.group(1))}] {m.group(2).decode()}'
                tl.write(rec + '\n'); tl.flush(); n_tl += 1
                print(rec, flush=True)
            if FATAL.search(line):
                fatal += 1
                print(f'FATAL-MARKER at +{time.monotonic() - t0:.1f}s (see raw.log)', flush=True)
            if BOOT.search(line):
                boots += 1
                if boots > (2 if a.mode == 'reset' else 0):  # reset mode: the open itself may reset once, then HardReset
                    fatal += 1
                    print(f'UNEXPECTED-REBOOT at +{time.monotonic() - t0:.1f}s', flush=True)
            if until and until.search(line):
                raise StopIteration
except (StopIteration, KeyboardInterrupt):
    pass
finally:
    s.close(); raw.close(); tl.close()
print(f'summary: tl_lines={n_tl} fatal_markers={fatal} boots={boots} seconds={time.monotonic() - t0:.1f} port={port}')
sys.exit(3 if fatal else 0)
