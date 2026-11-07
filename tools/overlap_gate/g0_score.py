"""Score the G0 heuristic gate on the extracted panels under the frozen protocol.

For each frame score (entropy, nonblank): frame miss/false-alarm at the fixed frame threshold and
ROC area per panel partition; segment labels and segment scores per the frozen definitions; the
segment threshold selected once on the AMI validation subsample at the frozen false-alarm
ceiling; segment precision/recall/false-alarm on every panel at that threshold; and the adoption
gate on the saved-microphone negatives and the no-speech fixtures.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from overlap_gate import scorer  # noqa: E402

SCORES = ('entropy', 'nonblank')


def load_panel(path: Path):
    if not path.with_suffix('.npz').exists():
        return None
    data = np.load(path.with_suffix('.npz'))
    meta = json.loads(path.with_suffix('.json').read_text())
    offsets = data['offsets']
    cases = []
    for i, row in enumerate(meta['rows']):
        s, e = int(offsets[i]), int(offsets[i + 1])
        cases.append(dict(row, counts=data['counts'][s:e], collar=data['collar'][s:e],
                          entropy=data['entropy'][s:e].astype(np.float64), nonblank=data['nonblank'][s:e].astype(np.float64)))
    return dict(meta=meta, cases=cases)


def partition_key(case):
    if case.get('partition'):
        return case['partition']
    if case['condition'] == 'ami-validation':
        return 'ami-validation'
    return 'saved-microphone'


def frame_summary(cases, score):
    out = {}
    for part, group in groupby(cases, partition_key).items():
        s = np.concatenate([c[score] for c in group])
        counts = np.concatenate([c['counts'] for c in group])
        collar = np.concatenate([c['collar'] for c in group])
        rates = scorer.frame_rates(s, counts, collar)
        roc = scorer.frame_roc(s, counts, collar)
        out[part] = dict(cases=len(group), **{k: v for k, v in rates.items()}, roc_auc=roc['auc'])
    return out


def groupby(cases, key):
    out = collections.OrderedDict()
    for c in cases:
        out.setdefault(key(c), []).append(c)
    return out


def segment_table(cases, score):
    labels_ = np.array([scorer.segment_label(c['counts'], c['collar']) for c in cases])
    scores_ = np.array([scorer.segment_fraction(c[score], c['collar']) for c in cases])
    return labels_, scores_


def clean(d):
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in d.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--g0', type=Path, default=ROOT / 'private/training-track/overlap-gate/phase1/g0')
    ap.add_argument('--experiment', type=Path, default=ROOT / 'private/training-track/overlap-gate/experiment.json')
    ap.add_argument('--out', type=Path, default=ROOT / 'private/training-track/overlap-gate/phase1/g0-results.json')
    args = ap.parse_args()
    exp = json.loads(args.experiment.read_text())
    ceiling = exp['operating_point']['false_alarm_ceiling']
    panels = {name: load_panel(args.g0 / name) for name in ('synthetic', 'microphone', 'validation')}
    report = dict(ceiling=ceiling, frame_threshold=scorer.FRAME_THRESHOLD, min_overlap_frames=scorer.MIN_OVERLAP_FRAMES,
                  panels_present={k: (v is not None and len(v['cases'])) for k, v in panels.items()}, scores={})
    for score in SCORES:
        entry = dict(frame={}, selection=None, segment={})
        for name, panel in panels.items():
            if panel:
                entry['frame'][name] = {k: clean(v) for k, v in frame_summary(panel['cases'], score).items()}
        if panels['validation']:
            labels_, scores_ = segment_table(panels['validation']['cases'], score)
            sel = scorer.select_threshold(scores_, labels_, ceiling)
            entry['selection'] = dict(panel='ami-validation subsample', cases=int(labels_.size), positives=int(labels_.sum()),
                                      threshold=sel['threshold'], metrics=clean(sel['metrics']))
            threshold = sel['threshold']
        else:
            threshold = None
        for name, panel in panels.items():
            if not panel:
                continue
            labels_, scores_ = segment_table(panel['cases'], score)
            seg = dict(cases=int(labels_.size), positives=int(labels_.sum()))
            # Diagnostic only, outside the frozen protocol: threshold-free separability of segments
            # by their mean frame score. Shows the ceiling of this heuristic, not an operating point.
            if 0 < labels_.sum() < labels_.size:
                means = np.array([float(np.mean(c[score][~c['collar']])) if np.any(~c['collar']) else 0.0 for c in panel['cases']])
                seg['diagnostic_mean_score_roc_auc'] = scorer.frame_roc(means, np.where(labels_, 2, 1), np.zeros(labels_.size, dtype=bool))['auc']
            if threshold is not None:
                flags = scores_ >= threshold
                seg['at_selected_threshold'] = clean(scorer.segment_metrics(flags, labels_))
                by = {}
                for key, idx in groupby(list(range(len(panel['cases']))), lambda i: (partition_key(panel['cases'][i]), panel['cases'][i]['condition'])).items():
                    idx = np.array(idx)
                    by['/'.join(key)] = clean(scorer.segment_metrics(flags[idx], labels_[idx]))
                seg['by_partition_condition'] = by
                if name == 'microphone':
                    neg = np.array([c['group'] != 'overlap' for c in panel['cases']])
                    seg['adoption_gate'] = dict(
                        negatives=int(neg.sum()), flagged_negatives=int(np.sum(flags & neg)),
                        flagged_fraction=float(np.sum(flags & neg) / neg.sum()),
                        no_speech_flags=int(np.sum(flags & np.array([c['group'] == 'background' for c in panel['cases']]))),
                        passes=bool(np.sum(flags & neg) / neg.sum() <= ceiling))
                if name == 'synthetic':
                    fixtures = np.array([c['condition'].startswith('no-speech') for c in panel['cases']])
                    seg['no_speech_fixture_flags'] = int(np.sum(flags & fixtures))
            entry['segment'][name] = seg
        report['scores'][score] = entry
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1) + '\n')
    for score, entry in report['scores'].items():
        print(f'== {score}')
        for name, parts in entry['frame'].items():
            for part, v in parts.items():
                print(f'   frame {name:10s} {part:16s} miss {v["miss_rate"]!s:>8.6} fa {v["false_alarm_rate"]!s:>8.6} auc {v["roc_auc"]!s:>8.6}')
        if entry['selection']:
            m = entry['selection']['metrics']
            print(f"   selected threshold {entry['selection']['threshold']:.4f} on validation: recall {m['recall']} fa {m['false_alarm_rate']}")
        for name, seg in entry['segment'].items():
            if 'at_selected_threshold' in seg:
                m = seg['at_selected_threshold']
                print(f"   segment {name:10s} precision {m['precision']} recall {m['recall']} fa {m['false_alarm_rate']} ({m['positives']} pos / {m['negatives']} neg)")
            if 'adoption_gate' in seg:
                print('   adoption gate', seg['adoption_gate'])


if __name__ == '__main__':
    main()
