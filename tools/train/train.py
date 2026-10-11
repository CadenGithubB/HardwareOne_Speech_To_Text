#!/usr/bin/env python3
"""Fine-tune QuartzNet5x5 on meetings + read speech with augmentation.

Runs until a wall-clock deadline with a time-based cosine schedule, keeps the
best checkpoint by held-out WER, and can resume after interruption.
"""
import argparse
import copy
import ctypes
import datetime as dt
import functools
import os
import json
import math
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from common import QuartzNet, load_checkpoint, save_checkpoint, BLANK
from data import Store, Augmenter, TrainSet, MixedBatchSampler, collate
from evaluate import evaluate_stores
STT_ROOT = Path(os.environ.get('STT_ROOT', 'stt-data'))  # data root: set STT_ROOT

TRAIN_MIX = [  # (store, weight, far_field); missing stores are skipped
    ('ami-sdm-train', 0.25, True),
    ('ami-ihm-train', 0.25, False),
    ('librispeech-train-clean-100', 0.15, False),
    # Added for run3: more read speech (clean-speech regression in run2)
    # and parliament speech with many accents.
    ('librispeech-train-clean-360', 0.20, False),
    ('voxpopuli-train', 0.15, False),
]
DEV_SETS = [('ami-sdm-validation', 400), ('ami-ihm-validation', 400), ('librispeech-dev-clean', 400)]


RESTART_EXIT = 75  # run_overnight.sh restarts on this without shrinking batches


def footprint_gb():
    """Physical footprint incl. compressed/swapped pages (what top's MEM shows)."""
    try:
        buf = ctypes.create_string_buffer(256)
        libproc = ctypes.CDLL('/usr/lib/libproc.dylib')
        if libproc.proc_pid_rusage(os.getpid(), 2, buf) != 0:  # RUSAGE_INFO_V2
            return 0.0
        return int.from_bytes(buf.raw[72:80], 'little') / 2**30  # ri_phys_footprint
    except OSError:
        return 0.0


def parse_deadline(text):
    now = dt.datetime.now()
    hh, mm = map(int, text.split(':'))
    deadline = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if deadline <= now:
        deadline += dt.timedelta(days=1)
    return deadline.timestamp()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--init', required=True, help='NeMo-format checkpoint dir to start from')
    p.add_argument('--out', required=True)
    p.add_argument('--deadline', required=True, help='HH:MM local time to stop')
    # 2e-4 destroyed the pretrained weights in run1 (conv weight RMS is only
    # ~0.05, and Adam moves each weight ~lr per step): keep fine-tuning gentle.
    p.add_argument('--lr', type=float, default=2e-5)
    p.add_argument('--warmup', type=int, default=300)
    p.add_argument('--max-seconds', type=float, default=110.0, help='padded audio seconds per batch')
    p.add_argument('--max-items', type=int, default=32)
    p.add_argument('--workers', type=int, default=5)
    p.add_argument('--eval-minutes', type=float, default=30.0)
    p.add_argument('--first-eval-minutes', type=float, default=15.0)
    p.add_argument('--save-steps', type=int, default=250)
    p.add_argument('--max-footprint-gb', type=float, default=6.0,
                   help='save and exit with code 75 (restart) above this memory footprint')
    p.add_argument('--patience', type=int, default=2, help='worse evals before rolling back to best')
    p.add_argument('--benchmark-steps', type=int, default=0, help='run N steps, report speed, exit')
    a = p.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / 'train.jsonl', 'a')

    def emit(**kw):
        kw['time'] = dt.datetime.now().strftime('%H:%M:%S')
        line = json.dumps(kw)
        print(line, flush=True)
        log.write(line + '\n')
        log.flush()

    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    config, template = load_checkpoint(a.init)
    model = QuartzNet(config).load_nemo(template).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-3)

    step, best = 0, None
    # Rollback guard: after `patience` evals worse than the best, restore the
    # best weights and halve the learning rate instead of drifting further.
    guard = {'bad': 0, 'lr_scale': 1.0}
    resume = out / 'resume.pt'
    if resume.exists() and not a.benchmark_steps:
        blob = torch.load(resume, weights_only=False, map_location='cpu')
        model.load_state_dict(blob['model'])
        optimizer.load_state_dict(blob['optimizer'])
        step, best = blob['step'], blob.get('best')
        guard.update(blob.get('guard', {}))
        emit(event='resumed', step=step, best=best, guard=guard)

    def save_resume():
        torch.save({'model': model.state_dict(), 'optimizer': optimizer.state_dict(),
                    'step': step, 'best': best, 'guard': guard}, out / 'resume.pt.tmp')
        (out / 'resume.pt.tmp').replace(resume)

    def optional(name):
        try:
            return Store(name)
        except FileNotFoundError:
            emit(event='missing_store', store=name)
            return None
    augmenter = Augmenter(optional('musan-noise'), optional('musan-speech'), optional('rirs'))
    present = [(n, w, f) for n, w, f in TRAIN_MIX if ((STT_ROOT / 'stores') / n / 'index.json').exists()]
    pending = [n for n, _, _ in TRAIN_MIX if n not in {m for m, _, _ in present}]
    if pending:
        emit(event='missing_train_stores', using=[n for n, _, _ in present], pending=pending)
    TRAIN_MIX[:] = present
    stores = [Store(name) for name, _, _ in TRAIN_MIX]
    dataset = TrainSet(stores, [f for _, _, f in TRAIN_MIX], template, augmenter, seed=step + 1)
    total_steps = a.benchmark_steps or 10 ** 9
    sampler = MixedBatchSampler(stores, [w for _, w, _ in TRAIN_MIX], a.max_seconds, a.max_items,
                                total_steps, seed=step + 17)
    loader = torch.utils.data.DataLoader(dataset, batch_sampler=sampler, collate_fn=functools.partial(collate, max_seconds=a.max_seconds,
                                                                      max_items=a.max_items),
                                         num_workers=a.workers, persistent_workers=True,
                                         prefetch_factor=4)

    start = time.time()
    deadline = parse_deadline(a.deadline) if not a.benchmark_steps else start + 1e9
    if not a.benchmark_steps:
        # The cosine schedule and eval timer span the whole run, not each
        # process: memory restarts must not reset the LR to its peak.
        first = getattr(os.stat(out / 'train.jsonl'), 'st_birthtime', start)
        start = guard.setdefault('sched_start', min(first, start))
    span = max(deadline - start, 1.0)
    # Score the starting point first so "best" can never be worse than it.
    if best is None and not a.benchmark_steps:
        best = run_eval(model, template, config, out, step, best, emit, device, guard, a.patience)
        guard['last_eval'] = time.time() - (a.eval_minutes - a.first_eval_minutes) * 60
        save_resume()
    last_eval = guard.setdefault('last_eval', time.time())
    audio_seconds = 0.0
    window_loss, window_n, t_window = 0.0, 0, time.time()
    train_mode(model)

    for feats, lengths, labels, label_lengths in loader:
        now = time.time()
        if now >= deadline:
            break
        # Linear warmup, then cosine decay over the remaining wall-clock time.
        progress = min(1.0, (now - start) / span)
        lr = a.lr * guard['lr_scale'] * min(1.0, (step + 1) / a.warmup) * (0.05 + 0.95 * 0.5 * (1 + math.cos(math.pi * progress)))
        for g in optimizer.param_groups:
            g['lr'] = lr

        log_probs, out_lengths = model(feats.to(device), lengths.to(device))
        log_probs = F.log_softmax(log_probs.float(), dim=-1)
        loss = F.ctc_loss(log_probs.transpose(0, 1).cpu(), labels, out_lengths.cpu(), label_lengths,
                          blank=BLANK, reduction='mean', zero_infinity=True)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        optimizer.step()
        step += 1
        audio_seconds += float(lengths.sum()) * 0.01
        window_loss += loss.item()
        window_n += 1

        if step % 50 == 0:
            elapsed = time.time() - t_window
            emit(event='train', step=step, loss=round(window_loss / window_n, 4), lr=f'{lr:.2e}',
                 audio_hours=round(audio_seconds / 3600, 2),
                 steps_per_s=round(window_n / elapsed, 3), batch=int(len(lengths)),
                 mem_gb=round(footprint_gb(), 2))
            window_loss, window_n, t_window = 0.0, 0, time.time()
            if not a.benchmark_steps and footprint_gb() > a.max_footprint_gb:
                save_resume()
                emit(event='memory_restart', step=step, mem_gb=round(footprint_gb(), 2))
                log.close()
                os._exit(RESTART_EXIT)

        if a.benchmark_steps:
            if step >= a.benchmark_steps:
                rate = audio_seconds / (time.time() - start)
                emit(event='benchmark', audio_seconds_per_second=round(rate, 1),
                     peak_mps_mb=round(torch.mps.driver_allocated_memory() / 2**20) if device.type == 'mps' else None)
                return
            continue

        if step % a.save_steps == 0:
            save_resume()

        if time.time() - last_eval >= a.eval_minutes * 60:
            best = run_eval(model, template, config, out, step, best, emit, device, guard, a.patience)
            last_eval = guard['last_eval'] = time.time()
            save_resume()
            train_mode(model)
            arrived = [n for n in pending if ((STT_ROOT / 'stores') / n / 'index.json').exists()]
            if arrived:  # restart so the new corpora join the mix
                emit(event='data_restart', step=step, arrived=arrived)
                log.close()
                os._exit(RESTART_EXIT)

    save_checkpoint(model, template, config, out / 'last')
    best = run_eval(model, template, config, out, step, best, emit, device, guard, a.patience)
    save_resume()
    emit(event='finished', step=step, best=best, audio_hours=round(audio_seconds / 3600, 2))


def train_mode(model):
    """Train weights but keep the pretrained BatchNorm statistics: augmented,
    padded fine-tuning batches would otherwise drag them off the real-audio
    distribution."""
    model.train()
    for m in model.modules():
        if isinstance(m, torch.nn.modules.batchnorm._BatchNorm):
            m.eval()


def run_eval(model, template, config, out, step, best, emit, device, guard, patience):
    model.eval()
    # Evaluate a CPU copy: eval batches have many distinct shapes, each of
    # which would otherwise leave a cached graph behind on MPS.
    cpu_model = copy.deepcopy(model).cpu().eval()
    results = evaluate_stores(cpu_model, template, DEV_SETS, torch.device('cpu'))
    del cpu_model
    score = float(np.mean([r['wer'] for r in results.values()]))
    metrics = {'score': score, 'step': step, 'sets': {k: v['wer'] for k, v in results.items()}}
    emit(event='eval', step=step, score=round(score, 4), **{k: round(v['wer'], 4) for k, v in results.items()})
    # Every evaluated point is kept (~27 MB each) so any of them can be
    # exported or resumed from later without retraining.
    snapshot = out / 'evals' / f'step_{step:06d}'
    save_checkpoint(model, template, config, snapshot)
    (snapshot / 'metrics.json').write_text(json.dumps(metrics, indent=2))
    if best is None or score < best['score']:
        best = metrics
        guard['bad'] = 0
        save_checkpoint(model, template, config, out / 'best')
        (out / 'best' / 'metrics.json').write_text(json.dumps(best, indent=2))
        emit(event='new_best', step=step, score=round(score, 4))
        return best
    # Noise on the dev subsets is ~0.3% absolute: only a clear loss counts,
    # and a big one rolls back immediately.
    if score > best['score'] * 1.01:
        guard['bad'] += 1
    if (guard['bad'] >= patience or score > best['score'] * 1.05) and step != best['step']:
        _, state = load_checkpoint(out / 'best')
        model.load_nemo(state)
        guard['bad'] = 0
        guard['lr_scale'] *= 0.5
        emit(event='rollback', to_step=best['step'], score=round(best['score'], 4),
             lr_scale=guard['lr_scale'])
    return best


if __name__ == '__main__':
    main()
