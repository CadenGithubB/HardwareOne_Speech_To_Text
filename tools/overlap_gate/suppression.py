"""Phase four, step 0b: label-free boundary suppression on the device decision rule.

The protocol excluded +-200 ms around speaker boundaries from scoring; the device cannot. These
rules try to remove the same isolated boundary flickers without labels, on the 20 ms device
posteriors saved by device_rule.py:

  R0      fraction of frames with P(two) >= 0.5                            (the plain device rule)
  Rk      as R0, but marked runs shorter than k frames are dropped first      k in 3, 5, 10
  Sk      P(two) smoothed by a centred k-frame moving average, then >= 0.5    k in 3, 5

Selection: for each rule, the segment threshold is chosen on the AMI validation subsample at the
frozen 2% false-alarm ceiling; the rule with the highest validation recall wins (ties: the plainer
rule). Only the winner is then scored on AMI test, the saved microphone panel and the synthetic
suite. Writes phase4/suppression-rules.json and adds the winner's decision to answer-key.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overlap_gate import scorer  # noqa: E402
from overlap_gate import g2_common as g2  # noqa: E402

PHASE4 = g2.LABELS / 'phase4'
CEILING = 0.02


def load(name):
    with np.load(PHASE4 / 'posteriors' / f'{name}.npz') as d:   # read each array once; NpzFile re-decompresses on every access
        p2, p2_off, counts, collar, off = d['p2'].astype(np.float64), d['p2_offsets'], d['counts'], d['collar'], d['offsets']
    rows = json.loads((PHASE4 / 'posteriors' / f'{name}.json').read_text())
    cases = []
    for i, r in enumerate(rows):
        a, b = int(p2_off[i]), int(p2_off[i + 1])
        s, e = int(off[i]), int(off[i + 1])
        cases.append(dict(r, p2=p2[a:b], counts=counts[s:e], collar=collar[s:e]))
    return cases


def drop_short_runs(marked: np.ndarray, k: int) -> np.ndarray:
    """Clear every run of True shorter than k frames (vectorized run-length pass)."""
    if k <= 1 or marked.size == 0:
        return marked
    m = marked.astype(np.int8)
    edges = np.flatnonzero(np.diff(np.concatenate([[0], m, [0]])))
    starts, ends = edges[0::2], edges[1::2]
    out = marked.copy()
    for s, e in zip(starts, ends):
        if e - s < k:
            out[s:e] = False
    return out


def smooth(p2: np.ndarray, k: int) -> np.ndarray:
    if k <= 1 or p2.size == 0:
        return p2
    pad = k // 2
    x = np.concatenate([np.full(pad, p2[0]), p2, np.full(pad, p2[-1])])
    return np.convolve(x, np.ones(k) / k, mode='valid')[:p2.size]


RULES = {
    'R0': lambda p2: p2 >= scorer.FRAME_THRESHOLD,
    'R3': lambda p2: drop_short_runs(p2 >= scorer.FRAME_THRESHOLD, 3),
    'R5': lambda p2: drop_short_runs(p2 >= scorer.FRAME_THRESHOLD, 5),
    'R10': lambda p2: drop_short_runs(p2 >= scorer.FRAME_THRESHOLD, 10),
    'S3': lambda p2: smooth(p2, 3) >= scorer.FRAME_THRESHOLD,
    'S5': lambda p2: smooth(p2, 5) >= scorer.FRAME_THRESHOLD,
}
ORDER = list(RULES)   # plainer first; used for tie-breaking


def fractions(cases, rule):
    return np.array([float(RULES[rule](c['p2']).mean()) if c['p2'].size else 0.0 for c in cases])


def labels_of(cases):
    return np.array([scorer.segment_label(c['counts'], c['collar']) for c in cases])


def main():
    val = load('validation')
    lab_v = labels_of(val)
    table = {}
    for rule in ORDER:
        sel = scorer.select_threshold(fractions(val, rule), lab_v, CEILING)
        table[rule] = dict(threshold=sel['threshold'], recall=sel['metrics']['recall'], false_alarm_rate=sel['metrics']['false_alarm_rate'],
                           precision=sel['metrics']['precision'])
    best = max(ORDER, key=lambda r: (round(table[r]['recall'], 6), -ORDER.index(r)))
    threshold = table[best]['threshold']
    report = dict(ceiling=CEILING, validation=table, chosen=dict(rule=best, threshold=threshold), once={})
    for name in ('test', 'microphone', 'synthetic'):
        cases = load(name)
        lab = labels_of(cases)
        frac = fractions(cases, best)
        flags = frac >= threshold
        entry = dict(cases=len(cases), positives=int(lab.sum()), segment=scorer.segment_metrics(flags, lab), by_condition={})
        for cond in sorted({(c['partition'], c['condition']) for c in cases}):
            idx = np.array([i for i, c in enumerate(cases) if (c['partition'], c['condition']) == cond])
            entry['by_condition']['/'.join(cond)] = scorer.segment_metrics(flags[idx], lab[idx])
        if name == 'microphone':
            neg = np.array([c['group'] != 'overlap' for c in cases])
            entry['adoption_gate'] = dict(negatives=int(neg.sum()), flagged_negatives=int(np.sum(flags & neg)), passes=bool(np.sum(flags & neg) / neg.sum() <= CEILING))
            key_file = PHASE4 / 'answer-key.json'
            key = json.loads(key_file.read_text())
            by_id = {c['id']: (float(f), bool(fl)) for c, f, fl in zip(cases, frac, flags)}
            for clip in key['clips']:
                clip['fraction_at_suppression_rule'], clip['flag_at_suppression_rule'] = by_id[clip['id']]
            key['suppression_rule'] = dict(rule=best, threshold=threshold)
            key_file.write_text(json.dumps(key, indent=1) + '\n')
        report['once'][name] = json.loads(json.dumps(entry, default=lambda o: None if isinstance(o, float) and o != o else float(o)))
    (PHASE4 / 'suppression-rules.json').write_text(json.dumps(report, indent=1) + '\n')
    print('validation (AMI only), threshold at 2% FA and the recall it buys:')
    for rule, t in table.items():
        print(f"  {rule:4s} thr {t['threshold']:.4f} recall {t['recall']:.4f} fa {t['false_alarm_rate']:.4f}")
    print('chosen', best, 'thr', round(threshold, 4))
    for name, e in report['once'].items():
        s = e['segment']
        print(f"  {name:10s} recall {s['recall']} fa {s['false_alarm_rate']} precision {s['precision']} ({s['positives']} pos / {s['negatives']} neg)", e.get('adoption_gate', ''))


if __name__ == '__main__':
    main()
