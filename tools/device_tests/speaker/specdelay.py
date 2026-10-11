#!/usr/bin/env python3
"""Head-start trigger delay per speculative run: run start - the moment the snapshot's last sample
was captured (a0 + samples / 16 on the TL clock). Only runs that were later promoted count, so the
delay is the one on the critical path of a caption. Numbers only."""
import glob, re, statistics as st, sys
for lab in sys.argv[1:]:
    allv, prom = [], []
    for d in sorted(glob.glob(f'sessions/{lab}/2026*')):
        raw = open(d + '/raw.log', errors='replace').read()
        promoted = {int(m.group(1)) for m in re.finditer(r'TL spec_promote seg=\d+ id=(\d+)', raw)}
        for m in re.finditer(r'TL spec_start seq=\d+ id=(\d+) a0=(\d+) samples=(\d+) t=(\d+)', raw):
            i, a0, n, t = map(int, m.groups())
            v = t - (a0 + n / 16)
            allv.append(v)
            if i in promoted: prom.append(v)
    def s(v): return f'n={len(v):3} mean {st.mean(v):5.1f} ms  median {st.median(v):5.1f}  p90 {sorted(v)[int(0.9*(len(v)-1))]:5.1f}  max {max(v):5.1f}' if v else 'n=0'
    print(f'{lab:12} all runs: {s(allv)}\n{"":12} promoted: {s(prom)}')
