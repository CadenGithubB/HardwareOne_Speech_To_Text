"""G2h comparison: G2c vs G2h under the exact device rule, on clean AMI and on replayed audio.

Panels (test blocks and AMI test are never read here):
  ami      the AMI validation subsample minus clips replayed in training blocks
  replay   replay validation blocks 7, 8, 12: every saved segment (all categories), and the
           AMI-validation-only subset
For each model: device rule (int8, 200-frame chunks, silence pad, R10). The segment threshold is set
at <=2% false alarms on AMI negatives and applied to replay as is (the deployable setting). A second
threshold, set at <=2% on replay-validation negatives, shows what a replay-tuned setting would buy.
Writes phase5/replay-eval.json.
"""
from __future__ import annotations

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

MODELS = {'g2c': g2.LABELS / 'phase3c' / 'export-int8', 'g2h': g2.LABELS / 'phase5' / 'g2h' / 'export-int8',
          'g2i': g2.LABELS / 'phase5' / 'g2i' / 'export-int8'}
CEILING = 0.02


def score(gate, items):
    lab, frac, post, counts, collars, maxp = [], [], [], [], [], []
    for feats, c, k in items:
        p2 = gate.frame_posteriors(feats())
        m = p2 >= scorer.FRAME_THRESHOLD
        lab.append(scorer.segment_label(c, k))
        frac.append(float(drop_short_runs(m, 10).mean()) if m.size else 0.0)
        maxp.append(float(p2.max()) if p2.size else 0.0)
        up = np.repeat(p2, 2)[:c.size]
        up = np.concatenate([up, np.full(c.size - up.size, up[-1] if up.size else 0.0)]) if up.size < c.size else up
        post.append(up)
        counts.append(c)
        collars.append(k)
    return np.array(lab), np.array(frac), np.array(maxp), scorer.frame_roc(np.concatenate(post), np.concatenate(counts), np.concatenate(collars))['auc']


def auc(x, y):
    p, n = x[y], x[~y]
    return float((p[:, None] > n[None]).mean() + 0.5 * (p[:, None] == n[None]).mean()) if p.size and n.size else None


def at(frac, lab, t):
    f = frac >= t
    return dict(recall=float(f[lab].mean()) if lab.any() else None, false_alarm_rate=float(f[~lab].mean()) if (~lab).any() else None,
                flags=int(f.sum()), positives=int(lab.sum()), negatives=int((~lab).sum()))


def main():
    torch.set_num_threads(2)
    bank = g2.Features('ami-sdm-validation')
    ami = [(lambda a=r['audio_id']: bank.slice(a), labels.expand(r['counts']), labels.expand(r['collar']).astype(bool)) for r in g2.reduced_validation_subsample()]
    rb = g2.ReplayBank()
    rep_all = [(lambda k=k: rb.slice(k), *rb.labels(k)) for k in rb.keys('validation')]
    rep_ami = [(lambda k=k: rb.slice(k), *rb.labels(k)) for k in rb.keys('validation', ami_val_only=True)]
    out = dict(panels=dict(ami=len(ami), replay_all=len(rep_all), replay_ami_val=len(rep_ami)), models={})
    for name, d in MODELS.items():
        if not (d / 'status.json').exists():
            print(name, 'not exported')
            continue
        gate = DeviceGate(d, threshold=0.0)
        la, fa, ma, aa = score(gate, ami)
        t_ami = scorer.select_threshold(fa, la, CEILING)['threshold']
        res = dict(espdl_sha256=gate.status['espdl_sha256'], ami=dict(frame_auc=aa, segment_auc=auc(fa, la), threshold=t_ami, **at(fa, la, t_ami)))
        for pname, items in (('replay_all', rep_all), ('replay_ami_val', rep_ami)):
            lr, fr, mr, ar = score(gate, items)
            t_rep = scorer.select_threshold(fr, lr, CEILING)['threshold']
            res[pname] = dict(frame_auc=ar, segment_auc_fraction=auc(fr, lr), segment_auc_max=auc(mr, lr),
                              at_ami_threshold=at(fr, lr, t_ami), replay_tuned=dict(threshold=t_rep, **at(fr, lr, t_rep)))
        out['models'][name] = res
        print(name, json.dumps(res), flush=True)
    (g2.LABELS / 'phase5' / 'replay-eval.json').write_text(json.dumps(out, indent=1, default=lambda o: None if o != o else float(o)) + '\n')
    print(f"{'model':5s} {'AMI rec@2%':>10s} {'AMI fa':>7s} | {'replay AUC':>10s} {'rec@AMI thr':>11s} {'fa':>6s} | {'rec@replay thr':>14s} {'fa':>6s}")
    for name, r in out['models'].items():
        a, p = r['ami'], r['replay_all']
        print(f"{name:5s} {a['recall']:10.3f} {a['false_alarm_rate']:7.3f} | {p['frame_auc']:10.3f} {p['at_ami_threshold']['recall']:11.3f} "
              f"{p['at_ami_threshold']['false_alarm_rate']:6.3f} | {p['replay_tuned']['recall']:14.3f} {p['replay_tuned']['false_alarm_rate']:6.3f}")


if __name__ == '__main__':
    main()
