#!/usr/bin/env python3
"""Where does the device's LM decode time go? From lmprobe.json of c12 sessions:

  lmtiming.py LABEL [...]

- live vs idle replay (cache evicted = cold, then warm) for the identical logits: if live ~ cold, the session
  load is not what makes decodes slow; cold - warm is the cost of fetching the LM from PSRAM;
- decoder work per frame (nodes, scored candidates, word-LM completions) and a least-squares fit of the cold
  time on it, so host counts for other beams / LMs can be turned into device milliseconds.
Numbers only.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent / 'sessions'


def med(v):
    return float(np.median(v)) if len(v) else float('nan')


def main():
    caps = []
    for lab in sys.argv[1:]:
        for d in sorted((ROOT / lab).glob('2026*')):
            p = d / 'lmprobe.json'
            if p.exists():
                caps += [c for c in json.load(open(p))['captions'] if c['status'] == 0]
    if not caps:
        sys.exit('no probe captions')
    print(f'{len(caps)} captions; idle replay text identical: {sum(c["replay_exact"] for c in caps)}/{len(caps)}')
    print(f'{"audio":>9s} {"n":>4s} {"live ms":>8s} {"cold ms":>8s} {"warm ms":>8s} {"live/cold":>9s} '
          f'{"nodes/fr":>8s} {"cand/fr":>8s} {"comp/fr":>8s}')
    bins = [(0, 3), (3, 6), (6, 10.5)]
    for lo, hi in bins:
        cs = [c for c in caps if lo <= c['frames'] * 0.02 < hi]   # 20 ms per output frame
        if not cs:
            continue
        print(f'{lo:>3d}-{hi:<4g}s {len(cs):4d} {med([c["live_us"] for c in cs]) / 1000:8.1f} '
              f'{med([c["cold_us"] for c in cs]) / 1000:8.1f} {med([c["warm_us"] for c in cs]) / 1000:8.1f} '
              f'{med([c["live_us"] / c["cold_us"] for c in cs]):9.2f} '
              f'{med([c["nodes"] / c["frames"] for c in cs]):8.1f} {med([c["cand"] / c["frames"] for c in cs]):8.1f} '
              f'{med([c["comp"] / c["frames"] for c in cs]):8.1f}')
    X = np.array([[c['frames'], c['nodes'], c['cand'], c['comp'], 1.0] for c in caps], dtype=float)
    for key in ('cold_us', 'warm_us', 'live_us'):
        y = np.array([c[key] for c in caps], dtype=float)
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        pred = X @ coef
        r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
        print(f'{key:8s} ~ {coef[0]:.2f}*frames + {coef[1]:.3f}*nodes + {coef[2]:.4f}*cand + {coef[3]:.3f}*comp '
              f'+ {coef[4]:.0f} us   (R^2 {r2:.3f})')
    tot = {k: sum(c[k] for c in caps) / 1000 for k in ('live_us', 'cold_us', 'warm_us')}
    print(f'total over these captions: live {tot["live_us"]:.0f} ms, cold {tot["cold_us"]:.0f} ms, '
          f'warm {tot["warm_us"]:.0f} ms')


if __name__ == '__main__':
    main()
