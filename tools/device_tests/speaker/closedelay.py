#!/usr/bin/env python3
"""Close-detection delay of pause-closed phrases: close time q minus the moment the closing silence was
complete on the capture clock (a0 + samples / 16), i.e. how late the P4 noticed. Numbers only."""
import glob, re, statistics as st, sys
for lab in sys.argv[1:]:
    v = []
    for d in sorted(glob.glob(f'sessions/{lab}/2026*')):
        raw = open(d + '/raw.log', errors='replace').read()
        ends = {int(m.group(1)): int(m.group(2)) for m in re.finditer(r'TL trim seg=(\d+) samples=\d+ inf=\d+ voiced_end=\d+ end=(\d+)', raw)}
        for m in re.finditer(r'TL seg=(\d+) a0=(\d+) a1=(\d+) q=(\d+)', raw):
            seg, a0, a1, q = map(int, m.groups())
            if ends.get(seg) == 0:          # closed on a pause
                v.append(q - a1)            # a1 = phrase end on the capture clock
    print(f'{lab:12} pause closes n={len(v):3}  mean {st.mean(v):5.1f} ms  median {st.median(v):5.1f}  p90 {sorted(v)[int(0.9*(len(v)-1))]:5.1f}  max {max(v)}')
