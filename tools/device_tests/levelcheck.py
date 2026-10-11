#!/usr/bin/env python3
"""20 s placement check: play 20 s of the standard playlist (from its first clip) and print the P4's TL level
lines (rms of the mic, noise floor, open threshold) while it plays, plus 4 s of silence before.
Morning reference (b19, same playlist): while a phrase is open the median rms was 16 and the 90th percentile
67; the idle open threshold is 45. Uses the running speaker-test firmware's console; never flashes.
"""
import os
import re
import statistics as st
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import serial  # IDF python env

HERE = Path(__file__).parent
PL = HERE / 'speaker' / 'playlist' / 'playlist.wav'
VPY = os.environ.get('HW1_STT_PYTHON', sys.executable)   # a Python with the export tooling


def main():
    port = subprocess.check_output([VPY, str(HERE / 'find_p4_port.py')], text=True).strip().splitlines()[-1]
    with wave.open(str(PL)) as w:
        r = w.getframerate()
        w.setpos(int(6.0 * r))
        frames = w.readframes(int(20.0 * r))
        params = w.getparams()
    tmp = Path(tempfile.mkdtemp()) / 'level.wav'
    with wave.open(str(tmp), 'wb') as o:
        o.setparams(params)
        o.writeframes(frames)
    ser = serial.Serial(port, 115200, timeout=0.2)
    ser.dtr = False; ser.rts = False
    rows = []

    def read_for(sec, tag):
        end = time.monotonic() + sec
        buf = b''
        while time.monotonic() < end:
            buf += ser.read(4096)
            *lines, buf = buf.split(b'\n')
            for line in lines:
                m = re.search(rb'TL level t=(\d+) rms=(\d+) noise=(\d+) thr=(\d+) open=(\d)', line)
                if m:
                    rows.append((tag, int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))))

    read_for(4.0, 'silence')
    p = subprocess.Popen(['afplay', str(tmp)])
    read_for(21.0, 'speech')
    p.wait()
    ser.close()
    sp = [x[1] for x in rows if x[0] == 'speech']
    si = [x[1] for x in rows if x[0] == 'silence']
    if not sp:
        sys.exit('no TL level lines read: is the speaker-test firmware running?')
    print('rms during speech:', sp)
    print(f'speech median {st.median(sp)}, max {max(sp)}, 90th {sorted(sp)[int(0.9 * len(sp))]}; '
          f'silence median {st.median(si) if si else "?"}; open threshold {rows[-1][3]}; '
          f'windows open during speech {sum(x[4] for x in rows if x[0] == "speech")}/{len(sp)}')
    print('morning reference: median while open 16, 90th 67, idle open threshold 45')


if __name__ == '__main__':
    main()
