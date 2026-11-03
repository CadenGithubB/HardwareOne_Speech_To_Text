#!/usr/bin/env python3
"""Draft responsiveness of PCM-file benchmark runs (heaptw_remote.py bench). Numbers only.

  draftlag.py BENCH_DIR [BENCH_DIR ...]

Per phrase (TL seg a0/a1, TL draft audio_ms/e, TL pub t; device milliseconds):
  first_ms   first draft publication minus the phrase's audio start (a0); phrases without a draft are
             counted separately
  shown_lag  time-averaged lag of the displayed text from a0 until the final: at each moment, the audio
             already heard (up to a1) minus the audio the latest draft covers (a0 before any draft)
  final_ms   final publication minus a1 (as benchscore close_ms)
Per directory: medians across runs of each run's median (and of p90 for shown_lag).
"""
import re, statistics, sys
from pathlib import Path


def kv(s):
    return {k: int(v) for k, v in re.findall(r'\b([a-z_0-9]+)=(-?\d+)\b', s)}


def quant(v, q):
    v = sorted(v)
    if not v:
        return None
    x = (len(v) - 1) * q
    i = int(x)
    return v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * (x - i)


def run(log):
    seg, pub, drafts = {}, {}, {}
    for line in log:
        m = re.search(r'TL seg=(\d+) ', line)
        if m:
            seg[int(m.group(1))] = kv(line[m.start():])
        m = re.search(r'TL pub seq=(\d+) t=(\d+)', line)
        if m:
            pub[int(m.group(1))] = int(m.group(2))
        m = re.search(r'TL draft seq=(\d+) ([^\r\n]*)', line)
        if m:
            d = kv(m.group(2))
            if d.get('ok') == 1 and 'e' in d and 'audio_ms' in d:
                drafts.setdefault(int(m.group(1)), []).append((d['e'], d['audio_ms']))
    first, shown, final, nodraft = [], [], [], 0
    for q, s in seg.items():
        if q not in pub or 'a0' not in s or 'a1' not in s:
            continue
        a0, a1, end = s['a0'], s['a1'], pub[q]
        ds = sorted(x for x in drafts.get(q, []) if x[0] <= end)
        final.append(end - a1)
        if ds:
            first.append(ds[0][0] - a0)
        else:
            nodraft += 1
        # integrate lag(t) = min(t, a1) - covered(t) over [a0, end] in 10 ms steps
        covered, k, total, n = a0, 0, 0, 0
        for t in range(a0, end, 10):
            while k < len(ds) and ds[k][0] <= t:
                covered = max(covered, a0 + ds[k][1])
                k += 1
            total += max(0, min(t, a1) - covered)
            n += 1
        if n:
            shown.append(total / n)
    return {'phrases': len(final), 'no_draft': nodraft, 'first_med': quant(first, .5), 'first_p90': quant(first, .9),
            'shown_med': quant(shown, .5), 'shown_p90': quant(shown, .9), 'final_med': quant(final, .5)}


for d in map(Path, sys.argv[1:]):
    rows = [run(p.read_text(errors='replace').splitlines()) for p in sorted(d.glob('serial-*.log'))]
    rows = [r for r in rows if r['phrases'] >= 30]
    med = lambda k: round(statistics.median(r[k] for r in rows if r[k] is not None)) if rows else None
    print(d.name, 'runs', len(rows), ' '.join(f'{k}={med(k)}' for k in
          ('no_draft', 'first_med', 'first_p90', 'shown_med', 'shown_p90', 'final_med')))
