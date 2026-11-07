"""Train the G2 overlap classifier under the frozen phase-three protocol.

Writes g2-protocol.json (refusing to proceed if an existing one differs), measures the fixed
per-bin feature normalization, trains, saves a checkpoint every 1,000 steps with its validation
frame ROC area, and records the selected checkpoint. Deterministic seeds; CPU only.
Run from the repository root with the export venv python.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overlap_gate import labels, scorer  # noqa: E402
from overlap_gate import g2_common as g2  # noqa: E402


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def write_protocol(out: Path, variant: str):
    base = g2.PROTOCOLS[variant]
    protocol = dict(base, code_sha256={n: sha((Path(__file__).parent / n).read_bytes()) for n in ('g2_common.py', 'g2_train.py')})
    f = out / f'{variant}-protocol.json'
    if f.exists():
        prior = json.loads(f.read_text())
        assert {k: v for k, v in prior.items() if k != 'code_sha256'} == base, f'{variant} protocol drift: do not change constants after training started'
    else:
        f.write_text(json.dumps(protocol, indent=2) + '\n')


def normalization(sampler, n=1024):
    feats = []
    for _ in range(n // 64):
        f, _t, _m = sampler.batch(64)
        feats.append(f)
    f = torch.cat(feats)                                  # [N, 64, T]
    mean = f.mean(dim=(0, 2))
    std = f.std(dim=(0, 2)).clamp_min(1e-3)
    return mean, std


def validation_items(variant: str):
    """(feature-slice callable, counts, collar) for the AMI subsample, plus non-AMI dev negatives for g2b."""
    bank = g2.Features('ami-sdm-validation')
    records = g2.reduced_validation_subsample() if variant in ('g2h', 'g2i') else g2.validation_subsample()
    items = [(lambda b=bank, a=r['audio_id']: b.slice(a), labels.expand(r['counts']), labels.expand(r['collar']).astype(bool)) for r in records]
    if variant in ('g2h', 'g2i'):
        rb = g2.ReplayBank()
        replay = [(lambda k=k: rb.slice(k), *rb.labels(k)) for k in rb.keys('validation', ami_val_only=True)]
        return dict(ami=items, replay=replay)
    if variant == 'g2b':
        banks = {}
        for d in g2.dev_negatives():
            banks.setdefault(d['store'], g2.Features(d['store']))
            items.append((lambda b=banks[d['store']], k=d['key']: b.slice(k), d['counts'], d['collar']))
    return items


def validate(model, items):
    if isinstance(items, dict):
        parts = {name: validate(model, v) for name, v in items.items()}
        return dict(roc_auc=float(np.mean([p['roc_auc'] for p in parts.values()])), **{f'{n}_{k}': v for n, p in parts.items() for k, v in p.items()})
    model.eval()
    scores, counts, collars = [], [], []
    with torch.inference_mode():
        for feats, c, k in items:
            logits = model(torch.from_numpy(feats())[None])[0]
            scores.append(g2.overlap_posterior_10ms(logits, c.size))
            counts.append(c)
            collars.append(k)
    model.train()
    s, c, k = map(np.concatenate, (scores, counts, collars))
    return dict(roc_auc=scorer.frame_roc(s, c, k)['auc'], **{m: v for m, v in scorer.frame_rates(s, c, k).items() if m.endswith('rate')})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--variant', choices=sorted(g2.PROTOCOLS), default='g2')
    ap.add_argument('--out', type=Path, default=None, help='default phase3 for g2, phase3b for g2b, phase3c for g2c')
    ap.add_argument('--steps', type=int, default=None)
    ap.add_argument('--smoke', action='store_true', help='few steps, no checkpoints, protocol not written')
    ap.add_argument('--threads', type=int, default=1)
    args = ap.parse_args()
    torch.set_num_threads(args.threads)
    if args.out is None:
        args.out = {'g2': g2.PHASE3, 'g2b': g2.LABELS / 'phase3b', 'g2c': g2.LABELS / 'phase3c'}.get(args.variant, g2.LABELS / 'phase5' / args.variant)
    args.out.mkdir(parents=True, exist_ok=True)
    cfg = g2.PROTOCOLS[args.variant]['training']
    if not args.smoke:
        write_protocol(args.out, args.variant)
    torch.manual_seed(cfg['seed'])
    np.random.seed(cfg['seed'])
    sampler = g2.Sampler(cfg['seed'], args.variant)
    stats_file = args.out / 'normalization.json'
    if stats_file.exists():
        st = json.loads(stats_file.read_text())
        mean, std = torch.tensor(st['mean']), torch.tensor(st['std'])
    else:
        mean, std = normalization(g2.Sampler(cfg['seed'] + 1000, args.variant))
        if not args.smoke:
            stats_file.write_text(json.dumps(dict(mean=mean.tolist(), std=std.tolist(), windows=1024, seed=cfg['seed'] + 1000)) + '\n')
    arch = g2.ARCH.get(args.variant, {})
    model = g2.G2Net(mean, std, **arch)
    n_params = g2.parameter_count(model)
    print(json.dumps(dict(parameters=n_params, train_records=len(sampler.records), hours=round(float(sampler.weights.sum() and sum(r['end'] - r['begin'] for r in sampler.records) / 3600), 1))), flush=True)
    assert n_params <= 50000
    opt = torch.optim.Adam(model.parameters(), lr=cfg['lr'], weight_decay=cfg['weight_decay'])
    steps = 30 if args.smoke else (args.steps or cfg['steps'])
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: (cfg['lr_end'] + 0.5 * (cfg['lr'] - cfg['lr_end']) * (1 + math.cos(math.pi * min(s, steps) / steps))) / cfg['lr'])
    val_items = validation_items(args.variant)
    class_weights = torch.tensor(g2.CLASS_WEIGHTS[args.variant]) if args.variant in g2.CLASS_WEIGHTS else None
    log = (args.out / 'train.log').open('a')
    history = []
    t0 = time.time()
    running = 0.0
    model.train()
    for step in range(1, steps + 1):
        feats, target, mask = sampler.batch(cfg['batch'])
        logits = model(feats)                                   # [B, 3, 100]
        loss = torch.nn.functional.cross_entropy(logits.permute(0, 2, 1)[mask], target[mask], weight=class_weights)
        opt.zero_grad()
        loss.backward()
        opt.step()
        sched.step()
        running += float(loss.detach())
        if step % 100 == 0 or step == steps:
            msg = f'step {step} loss {running / (100 if step % 100 == 0 else step % 100):.4f} lr {sched.get_last_lr()[0]:.2e} {time.time() - t0:.0f}s'
            print(msg, flush=True)
            log.write(msg + '\n')
            log.flush()
            running = 0.0
        if not args.smoke and (step % cfg['checkpoint_every'] == 0 or step == steps):
            metrics = validate(model, val_items)
            ck = args.out / f'{args.variant}-step{step:05d}.pt'
            torch.save(dict(state_dict=model.state_dict(), step=step, mean=mean, std=std, metrics=metrics, arch=dict(arch)), ck)
            history.append(dict(step=step, checkpoint=ck.name, sha256=sha(ck.read_bytes()), **metrics))
            msg = f'checkpoint {step} validation {json.dumps(metrics)}'
            print(msg, flush=True)
            log.write(msg + '\n')
            log.flush()
            (args.out / 'history.json').write_text(json.dumps(history, indent=1) + '\n')
    if args.smoke:
        metrics = validate(model, {k: v[:150] for k, v in val_items.items()} if isinstance(val_items, dict) else val_items[:200] + val_items[-100:])
        print('smoke validation (300 windows)', json.dumps(metrics))
        return
    best = max(history, key=lambda h: (h['roc_auc'], -h['step']))
    rule = g2.PROTOCOLS[args.variant]['selection']
    (args.out / 'selection.json').write_text(json.dumps(dict(variant=args.variant, rule=rule, selected=best, history=history), indent=1) + '\n')
    print('selected', json.dumps(best), flush=True)


if __name__ == '__main__':
    main()
