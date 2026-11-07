"""Phase 5: compare recall variants of G2c under the exact device rule, on AMI validation only.

For each phase directory with an int8 export (export-int8/status.json): run the int8 native graph on
the fixed 2,000-window AMI validation subsample with the device rule (int8 input, 200-frame chunks,
silence padding, softmax, P(two) >= 0.5, drop marked runs shorter than 10 frames, fraction over the
segment's own frames, no collar), choose the segment threshold at <= 2% false alarms on these AMI
negatives, and report the recall it buys. AMI test is never read here.

  variant_eval.py DIR [DIR ...]     evaluate and write DIR/variant-eval.json
  variant_eval.py --summary         table of every evaluated variant, G2c included
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overlap_gate import labels, scorer  # noqa: E402
from overlap_gate import g2_common as g2  # noqa: E402
from overlap_gate.device_rule import DeviceGate  # noqa: E402
from overlap_gate.suppression import drop_short_runs  # noqa: E402

CEILING = 0.02
DIRS = [g2.LABELS / 'phase3c'] + [g2.LABELS / 'phase5' / v for v in ('g2d', 'g2e', 'g2f', 'g2g')]


def evaluate(phase: Path) -> dict:
    gate = DeviceGate(phase / 'export-int8', threshold=0.0)
    bank = g2.Features('ami-sdm-validation')
    lab, r0, r10 = [], [], []
    for r in g2.validation_subsample():
        counts = labels.expand(r['counts'])
        collar = labels.expand(r['collar']).astype(bool)
        p2 = gate.frame_posteriors(bank.slice(r['audio_id']))
        marked = p2 >= scorer.FRAME_THRESHOLD
        lab.append(scorer.segment_label(counts, collar))
        r0.append(float(marked.mean()) if marked.size else 0.0)
        r10.append(float(drop_short_runs(marked, 10).mean()) if marked.size else 0.0)
    lab = np.array(lab)
    out = dict(phase=str(phase), espdl_sha256=gate.status['espdl_sha256'], parameters=gate.status['parameters'],
               espdl_bytes=gate.status['espdl_bytes'], static_activation_peak_bytes=gate.status['static_activation_peak_bytes'],
               validation_frame_roc_auc=gate.status['validation_frame_roc_auc'], cases=int(lab.size), positives=int(lab.sum()), rules={})
    for name, frac in (('R0', np.array(r0)), ('R10', np.array(r10))):
        sel = scorer.select_threshold(frac, lab, CEILING)
        m = sel['metrics']
        out['rules'][name] = dict(threshold=sel['threshold'], recall=m['recall'], false_alarm_rate=m['false_alarm_rate'], precision=m['precision'])
    (phase / 'variant-eval.json').write_text(json.dumps(out, indent=1, default=lambda o: None if o != o else float(o)) + '\n')
    return out


def summary():
    rows = []
    for d in DIRS:
        f = d / 'variant-eval.json'
        if f.exists():
            e = json.loads(f.read_text())
            r = e['rules']['R10']
            rows.append((d.name, e['parameters'], e['espdl_bytes'], e['validation_frame_roc_auc']['int8'], r['threshold'], r['recall'], r['false_alarm_rate']))
        else:
            rows.append((d.name, None, None, None, None, None, None))
    print(f"{'variant':8s} {'params':>7s} {'bytes':>7s} {'int8 AUC':>9s} {'thr':>6s} {'recall@2%':>10s} {'fa':>6s}")
    for name, p, b, auc, thr, rec, fa in rows:
        if p is None:
            print(f'{name:8s} (not evaluated)')
        else:
            print(f'{name:8s} {p:7d} {b:7d} {auc:9.4f} {thr:6.3f} {rec:10.4f} {fa:6.4f}')
    (g2.LABELS / 'phase5').mkdir(exist_ok=True)
    (g2.LABELS / 'phase5' / 'summary.json').write_text(json.dumps([dict(variant=r[0], parameters=r[1], espdl_bytes=r[2], int8_auc=r[3], threshold=r[4],
                                                                         recall=r[5], false_alarm_rate=r[6]) for r in rows], indent=1) + '\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dirs', nargs='*', type=Path)
    ap.add_argument('--summary', action='store_true')
    args = ap.parse_args()
    torch.set_num_threads(1)
    for d in args.dirs:
        e = evaluate(d)
        print(d.name, json.dumps(e['rules']))
    if args.summary:
        summary()


if __name__ == '__main__':
    main()
