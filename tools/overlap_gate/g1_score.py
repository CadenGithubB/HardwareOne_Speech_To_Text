"""Score the G1 speaker-trunk dispersion gate under the frozen protocol.

1. Fit the declared logistic calibration on the AMI train subsample windows (soft targets).
2. Apply it per frame to the spread statistics of every panel -> posterior in [0, 1].
3. Frozen protocol: frame rates and ROC at threshold 0.5; segment labels and fractions; the
   segment threshold selected once on the validation subsample at the 2% ceiling; segment
   metrics on every panel; the adoption gate on the saved-microphone negatives.
4. Diagnostics outside the protocol: threshold-free ROC area of each raw statistic.
"""
from __future__ import annotations

import collections
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from overlap_gate import scorer  # noqa: E402
from overlap_gate.g1_extract import STATS  # noqa: E402
from overlap_gate.g0_score import clean, groupby, partition_key  # noqa: E402

G1 = ROOT / 'private/training-track/overlap-gate/phase2/g1'
OUT = ROOT / 'private/training-track/overlap-gate/phase2/g1-results.json'


def load(name):
    path = G1 / name
    if not path.with_suffix('.npz').exists():
        return None
    data = np.load(path.with_suffix('.npz'))
    meta = json.loads(path.with_suffix('.json').read_text())
    offsets = data['offsets']
    cases = []
    for i, row in enumerate(meta['rows']):
        s, e = int(offsets[i]), int(offsets[i + 1])
        cases.append(dict(row, counts=data['counts'][s:e], collar=data['collar'][s:e], **{k: data[k][s:e].astype(np.float64) for k in STATS}))
    windows = json.loads(path.with_name(name + '-windows.json').read_text())
    return dict(meta=meta, cases=cases, windows=windows)


def fit_logistic(X, y, l2=1e-3, iters=500):
    """Deterministic Newton fit of a logistic regression with soft targets and small ridge."""
    Xb = np.hstack([X, np.ones((len(X), 1))])
    w = np.zeros(Xb.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xb @ w))
        grad = Xb.T @ (p - y) / len(y) + l2 * np.r_[w[:-1], 0]
        H = (Xb * (p * (1 - p))[:, None]).T @ Xb / len(y) + l2 * np.diag(np.r_[np.ones(Xb.shape[1] - 1), 0])
        step = np.linalg.solve(H, grad)
        w -= step
        if np.max(np.abs(step)) < 1e-9:
            break
    return w


def posterior(case, w):
    X = np.stack([case[s] for s in STATS], axis=1)
    return 1 / (1 + np.exp(-(X @ w[:-1] + w[-1])))


def main():
    exp = json.loads((ROOT / 'private/training-track/overlap-gate/experiment.json').read_text())
    ceiling = exp['operating_point']['false_alarm_ceiling']
    panels = {n: load(n) for n in ('train', 'synthetic', 'microphone', 'validation')}
    assert panels['train'], 'train subsample required for calibration'
    tw = [x for x in panels['train']['windows'] if x['target'] is not None and x['valid_frames'] > 0]
    X = np.array([[x[s] for s in STATS] for x in tw])
    y = np.array([x['target'] for x in tw])
    w = fit_logistic(X, y)
    report = dict(ceiling=ceiling, calibration=dict(windows=len(tw), mean_target=float(y.mean()), weights={**dict(zip(STATS, w[:-1].round(4).tolist())), 'bias': round(float(w[-1]), 4)}),
                  frame={}, raw_statistic_roc_auc={}, selection=None, segment={})
    for name, panel in panels.items():
        if not panel or name == 'train':
            continue
        for c in panel['cases']:
            c['post'] = posterior(c, w)
        for part, group in groupby(panel['cases'], partition_key).items():
            post = np.concatenate([c['post'] for c in group])
            counts = np.concatenate([c['counts'] for c in group])
            collar = np.concatenate([c['collar'] for c in group])
            report['frame'][f'{name}/{part}'] = clean(dict(cases=len(group), **scorer.frame_rates(post, counts, collar), roc_auc=scorer.frame_roc(post, counts, collar)['auc']))
            report['raw_statistic_roc_auc'][f'{name}/{part}'] = {s: clean(dict(auc=scorer.frame_roc(np.concatenate([c[s] for c in group]), counts, collar)['auc']))['auc'] for s in STATS}
    val = panels['validation']
    labels_v = np.array([scorer.segment_label(c['counts'], c['collar']) for c in val['cases']])
    scores_v = np.array([scorer.segment_fraction(c['post'], c['collar']) for c in val['cases']])
    sel = scorer.select_threshold(scores_v, labels_v, ceiling)
    threshold = sel['threshold']
    report['selection'] = dict(panel='ami-validation subsample', cases=int(labels_v.size), positives=int(labels_v.sum()), threshold=threshold, metrics=clean(sel['metrics']))
    for name, panel in panels.items():
        if not panel or name == 'train':
            continue
        labels_ = np.array([scorer.segment_label(c['counts'], c['collar']) for c in panel['cases']])
        scores_ = np.array([scorer.segment_fraction(c['post'], c['collar']) for c in panel['cases']])
        flags = scores_ >= threshold
        seg = dict(cases=int(labels_.size), positives=int(labels_.sum()), at_selected_threshold=clean(scorer.segment_metrics(flags, labels_)))
        by = {}
        for key, idx in groupby(list(range(len(panel['cases']))), lambda i: (partition_key(panel['cases'][i]), panel['cases'][i]['condition'])).items():
            idx = np.array(idx)
            by['/'.join(key)] = clean(scorer.segment_metrics(flags[idx], labels_[idx]))
        seg['by_partition_condition'] = by
        if 0 < labels_.sum() < labels_.size:
            means = np.array([float(np.mean(c['post'][~c['collar']])) if np.any(~c['collar']) else 0.0 for c in panel['cases']])
            seg['diagnostic_mean_posterior_roc_auc'] = scorer.frame_roc(means, np.where(labels_, 2, 1), np.zeros(labels_.size, dtype=bool))['auc']
        if name == 'microphone':
            neg = np.array([c['group'] != 'overlap' for c in panel['cases']])
            bg = np.array([c['group'] == 'background' for c in panel['cases']])
            seg['adoption_gate'] = dict(negatives=int(neg.sum()), flagged_negatives=int(np.sum(flags & neg)), flagged_fraction=float(np.sum(flags & neg) / neg.sum()),
                                        no_speech_flags=int(np.sum(flags & bg)), passes=bool(np.sum(flags & neg) / neg.sum() <= ceiling))
        if name == 'synthetic':
            seg['no_speech_fixture_flags'] = int(np.sum(flags & np.array([c['condition'].startswith('no-speech') for c in panel['cases']])))
        report['segment'][name] = seg
    OUT.write_text(json.dumps(report, indent=1) + '\n')
    print('calibration', report['calibration'])
    for k, v in report['frame'].items():
        print(f"frame {k:28s} miss {v['miss_rate']!s:>8.6} fa {v['false_alarm_rate']!s:>8.6} auc {v['roc_auc']!s:>8.6}  raw", {s: round(a, 3) if a is not None else None for s, a in report['raw_statistic_roc_auc'][k].items()})
    m = report['selection']['metrics']
    print(f"selected threshold {threshold} on validation: recall {m['recall']} fa {m['false_alarm_rate']}")
    for name, seg in report['segment'].items():
        m = seg['at_selected_threshold']
        print(f"segment {name:10s} precision {m['precision']} recall {m['recall']} fa {m['false_alarm_rate']} ({m['positives']} pos / {m['negatives']} neg) diag-auc {seg.get('diagnostic_mean_posterior_roc_auc')}")
        if 'adoption_gate' in seg:
            print('adoption gate', seg['adoption_gate'])


if __name__ == '__main__':
    main()
