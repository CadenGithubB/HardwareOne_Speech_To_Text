#!/usr/bin/env python3
"""Score c13 speaker labels (TL spk) against the conversation playlist's known speakers.

  spkeval.py SESSION_DIR [...]       or   spkeval.py --label b20-c13n

Each labelled phrase is matched to the clip holding the middle of its played span (analysis.json phrases);
its true speaker is that clip's. Accuracy uses the best one-to-one mapping of labels to speakers (labels
left over count as wrong). Also: speakers found vs true, tentative share, timing (median ms per phrase:
features, trunk, pooling, total), and the load line. Numbers only.
"""
import itertools
import json
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).parent / 'sessions'
SPK = re.compile(r'TL spk seq=(\d+) spk=(-?\d+) sim=([-0-9.]+) new=(\d) tent=(\d) samples=(\d+) fe_us=(\d+) '
                 r'nn_us=(\d+) head_us=(\d+) us=(\d+)')
LOAD = re.compile(r'TL spk_load (.*)$')
LOAD2 = re.compile(r'TL spk_load2 (.*)$')
SPKT = re.compile(r'TL spkt seq=(\d+) (.*)$')
STG = re.compile(r'TL spkstg i=(\d+) name=(\S+) n=(\d+) us_mean=(\d+) pct=([0-9.]+)')


def kv(text):
    out = {}
    for tok in text.split():
        if '=' in tok:
            k, v = tok.split('=', 1)
            try:
                out[k] = float(v) if '.' in v else int(v)
            except ValueError:
                out[k] = v
    return out


def best_map(true, pred):
    """Most phrases right under a one-to-one mapping of labels to speakers (either side may be larger)."""
    ts, ps = sorted(set(true)), sorted(set(pred))
    pairs = list(zip(true, pred))
    best = 0
    if len(ps) <= len(ts):
        for perm in itertools.permutations(ts, len(ps)):
            m = dict(zip(ps, perm))
            best = max(best, sum(1 for t, p in pairs if m[p] == t))
    else:
        for perm in itertools.permutations(ps, len(ts)):
            m = dict(zip(ts, perm))
            best = max(best, sum(1 for t, p in pairs if m[t] == p))
    return best


def score(sdir):
    sdir = Path(sdir)
    raw = open(sdir / 'raw.log', errors='replace').read().replace('\r', '')
    a = json.load(open(sdir / 'analysis.json'))
    man = json.load(open(json.load(open(sdir / 'session.json'))['manifest']))
    clips = man['clips']
    load = next((m.group(1) for m in map(LOAD.search, raw.splitlines()) if m), None)
    load2 = next((kv(m.group(1)) for m in map(LOAD2.search, raw.splitlines()) if m), None)
    sections = [kv(m.group(2)) for m in map(SPKT.search, raw.splitlines()) if m]
    stages = [(int(m.group(1)), m.group(2), int(m.group(4)), float(m.group(5))) for m in map(STG.search, raw.splitlines()) if m]
    labels = {}
    for m in SPK.finditer(raw):
        g = m.groups()
        labels[int(g[0])] = {'spk': int(g[1]), 'sim': float(g[2]), 'new': g[3] == '1', 'tent': g[4] == '1',
                             'samples': int(g[5]), 'fe': int(g[6]), 'nn': int(g[7]), 'head': int(g[8]), 'us': int(g[9])}
    true, pred, short = [], [], []
    for p in a['phrases']:
        if not p.get('span_play_s') or p['seq'] not in labels:
            continue
        mid = sum(p['span_play_s']) / 2
        c = next((c for c in clips if c['start_s'] - 0.5 <= mid <= c['end_s'] + 0.5), None)
        if c is None:
            continue
        true.append(c['speaker']); pred.append(labels[p['seq']]['spk'])
        short.append(labels[p['seq']]['samples'] < 32000)
    n = len(true)
    acc = 100 * best_map(true, pred) / n if n else float('nan')
    sh = [i for i in range(n) if short[i]]
    lo = [i for i in range(n) if not short[i]]
    acc_long = 100 * best_map([true[i] for i in lo], [pred[i] for i in lo]) / len(lo) if lo else float('nan')
    L = list(labels.values())
    lags = [int(x) for x in re.findall(r'TL spk seq=\d+ .* lag_ms=(\d+)', raw)]
    med = lambda k: st.median(x[k] for x in L) / 1000 if L else float('nan')
    sec = {}
    if sections:
        for k in ('fft', 'mel', 'norm', 'q', 'nn', 'dq', 'sap', 'pool', 'fc', 'clu'):
            sec[k] = round(st.median(x[k] for x in sections if k in x) / 1000, 2)
        sec['cropped_share'] = round(sum(x.get('crop', 0) for x in sections) / len(sections), 2)
    top = sorted(stages, key=lambda t: -t[3])[:8]
    by_kind = {}
    for i, name, us, pct in stages:
        kind = re.sub(r'.*/', '', name).split('_')[0] if '/' in name else name.split('_')[0]
        by_kind[kind] = round(by_kind.get(kind, 0) + pct, 1)
    return {'session': str(sdir), 'load': load, 'load2': load2, 'sections_ms_median': sec,
            'layers_top8': [{'i': i, 'name': nm, 'us_mean': us, 'pct': p} for i, nm, us, p in top],
            'layer_kinds_pct': dict(sorted(by_kind.items(), key=lambda x: -x[1])[:10]),
            'phrases_scored': n, 'labels_logged': len(labels),
            'label_lag_ms': {'median': st.median(lags), 'max': max(lags)} if lags else None,
            'skipped': raw.count('skipped=1'),
            'accuracy': round(acc, 1), 'accuracy_2s_plus': round(acc_long, 1), 'short_phrases': len(sh),
            'speakers_true': len(set(true)), 'speakers_found': len(set(pred)),
            'tentative': sum(x['tent'] for x in L), 'ms': {'features': round(med('fe'), 1), 'trunk': round(med('nn'), 1),
                                                           'pooling': round(med('head'), 1), 'total': round(med('us'), 1)}}


def main():
    args = sys.argv[1:]
    dirs = []
    if args and args[0] == '--label':
        for lab in args[1:]:
            dirs += sorted((ROOT / lab).glob('2026*'))
    else:
        dirs = [Path(x) for x in args]
    for d in dirs:
        if (d / 'analysis.json').exists():
            print(json.dumps(score(d)))


if __name__ == '__main__':
    main()
