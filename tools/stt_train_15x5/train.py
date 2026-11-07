#!/usr/bin/env python3
"""Fine-tune QuartzNet15x5 with the run2 (QuartzNet5x5) recipe, like for like.

Copy of experiments/stt_train/train.py with these deliberate differences:
  * TRAIN_MIX is run2's mix (AMI SDM/IHM + LibriSpeech clean-100), not run3's.
  * The run length is measured in audio hours seen (run2 saw ~175 h) instead
    of wall-clock time, because the 15x5 is ~3x slower per audio second. The
    cosine schedule now follows audio exposure; --schedule legacy-wall retains
    the older max(audio fraction, wall-clock fraction) recipe.
  * Dev evaluations are spaced by audio hours (run2's 30-min cadence was
    ~26 h of audio; its first eval came after ~12.6 h).
  * Gradient accumulation: --max-seconds / --max-items give the effective
    batch per optimizer step (run2: 110 s / 32 items) and --accum splits it
    into micro-batches so the bigger model fits in memory. Loss is normalized
    by the actual total item count across the accumulated micro-batches.
Diagnostics added 2026-11-03: strict dataset audit, immutable input identity,
per-source exposure/loss/gradient health, paired evaluation and deterministic
CPU resume. See docs/STT_TRAINING_DIAGNOSTICS.md for migration and limits.
Options added 2026-09-30 for continued training, all off by default:
--optimizer novograd (NeMo's recipe), --mix broad (+VoxPopuli), --dev g2 and
--g2-prob (simulated glasses mic channel, see lc3codec.py).
Everything else (augmentation, bucketed batch shapes, AdamW 2e-5, warmup 300,
frozen BN stats, step-0 eval, rollback guard, memory restart) is unchanged.
Speed options added 2026-10-09, ON by default, each with an off switch (same
maths; only fp32 rounding differs, so runs are not bit-for-bit the old ones):
--fast-dwconv (QuartzNet: depthwise convs' backward rebuilt from forward convs
on MPS, masks built once per forward), --fused-adamw (one fused AdamW kernel
instead of a per-tensor loop on MPS) and --eval-device mps (dev evals on the
training model on MPS, padded to the training bucket shapes: ~110 s instead
of ~20 min on a CPU copy). general2 recipe, 100 steps: 18.5 -> 55.1 audio-s/s.
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
import platform
import sys
import shutil
import importlib.metadata
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from common import QuartzNet, load_checkpoint, save_checkpoint as _save_checkpoint, BLANK
from citrinet import Citrinet, is_citrinet, load_vocab


def save_checkpoint(model, template, config, directory):
    _save_checkpoint(model, template, config, directory)
    if hasattr(model, 'tokenizer'):  # Citrinet: keep its WordPiece vocabulary beside the weights
        (Path(directory) / 'vocab.txt').write_text('\n'.join(model.tokenizer.vocab) + '\n')
from data import Store, Augmenter, TrainSet, MixedBatchSampler, collate
from evaluate import evaluate_stores
from diagnostics import audit_stores, atomic_json, sha256, digest, paired_changes
from training_state import seed_all, rng_state, restore_rng, save_state, restore_matching, Exposure


TRAIN_MIX = [  # run2's mix: (store, weight, far_field)
    ('ami-sdm-train', 0.35, True),
    ('ami-ihm-train', 0.35, False),
    ('librispeech-train-clean-100', 0.30, False),
]
# --mix broad: run2's sources plus VoxPopuli (parliament speech, many accents;
# already on disk), keeping LibriSpeech near a quarter against clean regression.
BROAD_MIX = [
    ('ami-sdm-train', 0.30, True),
    ('ami-ihm-train', 0.25, False),
    ('librispeech-train-clean-100', 0.25, False),
    ('voxpopuli-train', 0.20, False),
]
# --mix expanded (2026-10-01): adds People's Speech (mostly public meetings and
# interviews; filtered with keep.json), 100 h more LibriSpeech speakers
# (clean-360 subset) and 4 more VoxPopuli shards. AMI stays at 45%, the only
# real meeting-room audio; read speech ~15% to hold clean accuracy.
EXPANDED_MIX = [
    ('ami-sdm-train', 0.25, True),
    ('ami-ihm-train', 0.20, False),
    ('peoples-clean-train', 0.25, False),
    ('librispeech-train-clean-100', 0.08, False),
    ('librispeech-train-clean-360-p28', 0.07, False),
    ('voxpopuli-train', 0.08, False),
    ('voxpopuli-train-b', 0.07, False),
]
# --mix general (2026-10-02): wide everyday use, not only meetings. Varied
# real-world talk 30%, meetings 25%, read speech 20%, accented formal 25%.
GENERAL_MIX = [
    ('peoples-clean-train', 0.30, False),
    ('ami-sdm-train', 0.15, True),
    ('ami-ihm-train', 0.10, False),
    ('librispeech-train-clean-100', 0.10, False),
    ('librispeech-train-clean-360-p28', 0.10, False),
    ('voxpopuli-train', 0.13, False),
    ('voxpopuli-train-b', 0.12, False),
]
# --mix general2 (2026-10-03): the general mix over the bigger pool: 60 more
# People's Speech shards (peoples-clean-train2) and Common Voice English
# (thousands of speakers on their own phones and laptops).
GENERAL2_MIX = [
    ('peoples-clean-train', 0.15, False),
    ('peoples-clean-train2', 0.15, False),
    ('commonvoice-en-train', 0.12, False),
    ('ami-sdm-train', 0.15, True),
    ('ami-ihm-train', 0.10, False),
    ('librispeech-train-clean-100', 0.08, False),
    ('librispeech-train-clean-360-p28', 0.07, False),
    ('voxpopuli-train', 0.10, False),
    ('voxpopuli-train-b', 0.08, False),
]
MIXES = {'run2': TRAIN_MIX, 'broad': BROAD_MIX, 'expanded': EXPANDED_MIX, 'general': GENERAL_MIX,
         'general2': GENERAL2_MIX}
NOISE_ONLY = '__noise_only__'  # mix entry name for data.NoiseOnlyStore


def noise_source(name):
    """--noise-pool / --noise-only-pool value -> the noise store or pool."""
    from data import NoisePool
    musan = Store('musan-noise')
    return NoisePool([musan, Store('demand-noise-train')]) if name == 'musan+demand' else musan
DEV_SETS = [('ami-sdm-validation', 400), ('ami-ihm-validation', 400), ('librispeech-dev-clean', 400)]
# --dev g2 adds the same AMI subsets passed through the simulated glasses
# channel (make_g2_stores.py), so selection also rewards glasses robustness.
G2_DEV_SETS = DEV_SETS + [('ami-sdm-validation-g2', 400), ('ami-ihm-validation-g2', 400)]
# --dev broad: four kinds of speech, each plain and through the simulated
# glasses channel; peoples-dev / voxpopuli-dev are held out of the training
# stores (make_dev_views.py). Scored by broad_score, not a plain mean.
BROAD_DEV_SETS = [(n, 300) for base in ('ami-sdm-validation', 'ami-ihm-validation', 'librispeech-dev-clean',
                                        'peoples-dev', 'voxpopuli-dev') for n in (base, base + '-g2')]


def domain(name):
    for prefix, d in (('ami-', 'meetings'), ('libri', 'read'), ('peoples-', 'varied'), ('vox', 'accented')):
        if name.startswith(prefix):
            return d
    return name


def broad_score(wers):
    """Mean over kinds of speech (meetings, varied talk, read, accented) of the
    mean WER of that kind's sets (plain and glasses-simulated; AMI far and
    headset are one kind). Same formula as BENCHMARK.md's Broad column."""
    groups = {}
    for name, w in wers.items():
        groups.setdefault(domain(name), []).append(w)
    return float(np.mean([np.mean(v) for v in groups.values()]))


class NovoGrad(torch.optim.Optimizer):
    """NovoGrad as in NeMo (Ginsburg et al. 2019), QuartzNet's own optimizer.

    Per tensor: the second moment is one scalar (EMA of the squared gradient
    norm), the gradient is normalised by it, weight decay is added to the
    normalised gradient, then momentum. With grad_averaging=False (NeMo's
    default) the momentum buffer is a running sum, so lr is the per-tensor step
    size scale; NeMo's fine-tuning examples use lr ~1e-3 with this.
    """

    def __init__(self, params, lr=1e-3, betas=(0.95, 0.5), eps=1e-8, weight_decay=1e-3,
                 grad_averaging=False):
        super().__init__(params, dict(lr=lr, betas=betas, eps=eps, weight_decay=weight_decay,
                                      grad_averaging=grad_averaging))

    @torch.no_grad()
    def step(self, closure=None):
        for group in self.param_groups:
            beta1, beta2 = group['betas']
            for p in group['params']:
                if p.grad is None:
                    continue
                grad = p.grad
                state = self.state[p]
                norm = grad.square().sum()
                if not state:
                    state['exp_avg'] = torch.zeros_like(p)
                    state['exp_avg_sq'] = norm.clone()
                else:
                    state['exp_avg_sq'].mul_(beta2).add_(norm, alpha=1 - beta2)
                g = grad / (state['exp_avg_sq'].sqrt() + group['eps'])
                if group['weight_decay']:
                    g.add_(p, alpha=group['weight_decay'])
                if group['grad_averaging']:
                    g.mul_(1 - beta1)
                state['exp_avg'].mul_(beta1).add_(g)
                p.add_(state['exp_avg'], alpha=-group['lr'])


RESTART_EXIT = 75  # run_15x5.sh restarts on this without shrinking batches
MEMORY_EXIT = 3    # benchmark exceeded the footprint limit


# Characters an empty-transcript item counts as, per output frame (~15 letters/s
# at 50 frames/s). See ctc_divisor.
EMPTY_CHARS_PER_FRAME = 0.3


def ctc_divisor(label_lengths, out_lengths):
    """Per-item divisor of the CTC loss: the transcript length, as in PyTorch's
    reduction='mean'. That reduction divides an EMPTY transcript (noise-only clip)
    by 1, so one clip's whole-sequence loss outweighed ~100 speech items and the
    noise-only clips made up ~90% of the loss (2026-10-05). An empty item is
    divided by the letters speech of its duration would hold instead."""
    n = label_lengths.float()
    return torch.where(n > 0, n, (out_lengths.float() * EMPTY_CHARS_PER_FRAME).clamp(min=1.0))


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
    if text.startswith('+'):  # '+30h': runs longer than a day (HH:MM is at most 24 h ahead)
        return time.time() + float(text[1:].rstrip('h')) * 3600
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
    p.add_argument('--deadline', required=True, help="HH:MM local time to stop at the latest, or '+30h'")
    p.add_argument('--target-hours', type=float, default=175.0,
                   help='stop after this many hours of (augmented) training audio; run2 saw ~175 h')
    p.add_argument('--lr', type=float, default=2e-5)
    p.add_argument('--optimizer', choices=['adamw', 'novograd'], default='adamw',
                   help='novograd: NeMo-style, use with --lr ~1e-3')
    p.add_argument('--betas', type=float, nargs=2, help='default: AdamW (0.9, 0.999), NovoGrad (0.95, 0.5)')
    p.add_argument('--weight-decay', type=float, default=1e-3)
    p.add_argument('--mix', choices=sorted(MIXES), default='run2')
    p.add_argument('--dev', choices=['default', 'g2', 'broad'], default='default')
    p.add_argument('--g2-prob', type=float, default=0.0,
                   help='fraction of training items passed through the simulated glasses channel '
                        '(slow AGC + LC3 16k/10ms/32kbps with occasional PLC)')
    p.add_argument('--warmup', type=int, default=300)
    p.add_argument('--max-seconds', type=float, default=110.0,
                   help='padded audio seconds per optimizer step (split over --accum micro-batches)')
    p.add_argument('--max-items', type=int, default=32, help='items per optimizer step')
    p.add_argument('--accum', type=int, default=1, help='micro-batches per optimizer step')
    p.add_argument('--workers', type=int, default=5,
                   help='DataLoader workers; 2 measured the same speed as 5 with ~1 GB less memory '
                        '(general2 recipe, 2026-10-09), below 2 the loader can fall behind')
    p.add_argument('--eval-hours', type=float, default=26.2, help='audio hours between dev evals')
    p.add_argument('--first-eval-hours', type=float, default=12.6)
    p.add_argument('--save-steps', type=int, default=250)
    p.add_argument('--max-footprint-gb', type=float, default=6.0,
                   help='save and exit with code 75 (restart) above this memory footprint')
    p.add_argument('--patience', type=int, default=2, help='worse evals before rolling back to best')
    p.add_argument('--benchmark-steps', type=int, default=0, help='run N steps, report speed, exit')
    p.add_argument('--device', default='cuda' if torch.cuda.is_available() else
                   'mps' if torch.backends.mps.is_available() else 'cpu', help='cpu only for tiny smoke tests')
    p.add_argument('--rollback', choices=['on', 'off'], default='on',
                   help="off: never revert to the best checkpoint or halve the LR on a worse eval "
                        "(every eval is still saved and the best one kept)")
    p.add_argument('--amp', action='store_true', help='CUDA only: bfloat16 autocast for the model forward pass')
    p.add_argument('--noise-pool', choices=['musan', 'musan+demand'], default='musan',
                   help='background noise for augmentation; +demand adds DEMAND everyday ambiences')
    p.add_argument('--noise-only-share', type=float, default=0.0,
                   help='share of training items that are pure noise with an EMPTY transcript (e.g. 0.04)')
    p.add_argument('--noise-only-pool', choices=['same', 'musan', 'musan+demand'], default='same',
                   help='noise the noise-only clips are cut from; same = --noise-pool')
    p.add_argument('--fast-dwconv', choices=['on', 'off'], default='on',
                   help='QuartzNet: custom backward for the stride-1 depthwise convs on MPS (~2.8x faster '
                        'steps) and masks built once per forward; off = the stock autograd path')
    p.add_argument('--fused-adamw', choices=['on', 'off'], default='on',
                   help='AdamW as one fused kernel (MPS runs a per-tensor loop otherwise)')
    p.add_argument('--eval-device', choices=['mps', 'cpu'], default='mps',
                   help='--device mps only: mps = dev eval of the training model on MPS, padded to the '
                        'training bucket shapes (~110 s); cpu = a CPU copy (~20 min). Citrinet always uses cpu')
    p.add_argument('--stop-after-steps', type=int, default=0,
                   help='Checkpoint and stop at this absolute step without a new evaluation; safe to resume')
    p.add_argument('--seed', type=int, default=2026)
    p.add_argument('--gradient-diagnostics-every', type=int, default=50,
                   help='per-source microbatch gradient norms; 0 disables the expensive diagnostic')
    p.add_argument('--diagnostic-sets', nargs='*', default=[],
                   help='Additional DEVELOPMENT stores (e.g. noise-only/noisy speech); reported but not selected on')
    p.add_argument('--audit-test-stores', nargs='*', default=[],
                   help='reserved test stores to check for overlap, never evaluated during training')
    p.add_argument('--fingerprint-audio', choices=['sha256', 'metadata'], default='sha256')
    p.add_argument('--schedule', choices=['audio', 'legacy-wall'], default='audio')
    a = p.parse_args()
    if a.accum < 1 or a.workers < 0 or a.warmup < 1 or a.target_hours <= 0:
        p.error('accum/warmup/target-hours must be positive and workers nonnegative')
    seed_all(a.seed)
    train_mix = MIXES[a.mix]
    if any('test' in name.split('-') for name in a.diagnostic_sets):
        p.error('Use reserved development stores for diagnostic evaluations, not test stores')
    dev_sets = {'g2': G2_DEV_SETS, 'broad': BROAD_DEV_SETS}.get(a.dev, DEV_SETS)
    micro_seconds = a.max_seconds / a.accum
    micro_items = max(1, a.max_items // a.accum)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / 'train.jsonl', 'a')

    def emit(**kw):
        kw['time'] = dt.datetime.now().strftime('%H:%M:%S')
        line = json.dumps(kw)
        print(line, flush=True)
        log.write(line + '\n')
        log.flush()

    # Hash inputs before loading weights or launching workers. No source data is changed.
    from data import STORES
    noise_names = ['musan-noise', 'musan-speech', 'rirs']
    if 'demand' in a.noise_pool or 'demand' in a.noise_only_pool:
        noise_names.append('demand-noise-train')
    partitions = {'train': [n for n, _, _ in train_mix], 'dev': list(dict.fromkeys([n for n, _ in dev_sets] + a.diagnostic_sets)),
                  'test': a.audit_test_stores, 'augmentation': noise_names}
    emit(event='audit_start', audio_verification=a.fingerprint_audio)
    audit = audit_stores(STORES, partitions, a.fingerprint_audio == 'sha256')
    atomic_json(out / 'dataset-audit.json', audit)
    if audit['issues']:
        raise ValueError('Dataset integrity audit failed; see dataset-audit.json')
    recipe = {k:v for k,v in vars(a).items() if k not in
              ('deadline', 'out', 'init', 'max_footprint_gb', 'save_steps', 'workers', 'benchmark_steps', 'stop_after_steps')}
    identity = {'recipe': recipe, 'datasets': audit['fingerprint'],
                'code': {p.name: sha256(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
                'initial_weights': sha256(Path(a.init)/'model_weights.ckpt'),
                'initial_config': sha256(Path(a.init)/'model_config.yaml'),
                'runtime': {'python': sys.version, 'torch': torch.__version__, 'numpy': np.__version__,
                            'platform': platform.platform(),
                            'packages': {n:importlib.metadata.version(n) for n in ('scipy','PyYAML')},
                            'mps_fallback': os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK'),
                            'threads': torch.get_num_threads()}}
    vocab_path = Path(a.init) / 'vocab.txt'
    if vocab_path.exists():
        identity['tokenizer_sha256'] = sha256(vocab_path)
    identity['fingerprint'] = digest(identity)
    manifest_path = out / 'run-manifest.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != identity:
        raise ValueError('Run inputs changed; start a new output directory instead of resuming')
    atomic_json(manifest_path, identity)
    device = torch.device(a.device)
    config, template = load_checkpoint(a.init)
    if is_citrinet(config):
        model = Citrinet(config, load_vocab(a.init)).load_nemo(template).to(device)
        # The tokenizer alone goes to the DataLoader workers (never the MPS model).
        encoder, blank, reduction = model.tokenizer.encode, model.blank, 8
    else:
        model = QuartzNet(config).load_nemo(template).to(device)
        encoder, blank, reduction = None, BLANK, 2
    # Citrinet keeps its own plain blocks, and its MPS eval parity is unchecked.
    quartznet = isinstance(model, QuartzNet)
    custom_dw = model.set_fast(a.fast_dwconv == 'on') if quartznet else 0
    eval_bucket = (micro_seconds, micro_items) if device.type == 'mps' and a.eval_device == 'mps' \
        and quartznet else None
    fused = True if a.fused_adamw == 'on' else None  # None: torch's default (a per-tensor loop on MPS)
    if a.optimizer == 'novograd':
        optimizer = NovoGrad(model.parameters(), lr=a.lr, betas=tuple(a.betas or (0.95, 0.5)),
                             weight_decay=a.weight_decay)
    else:
        optimizer = torch.optim.AdamW(model.parameters(), lr=a.lr, betas=tuple(a.betas or (0.9, 0.999)),
                                      weight_decay=a.weight_decay, fused=fused)

    step, best = 0, None
    exposure = Exposure()
    pending_rng = None
    # Rollback guard: after `patience` evals worse than the best, restore the
    # best weights and halve the learning rate instead of drifting further.
    guard = {'bad': 0, 'lr_scale': 1.0, 'audio_seconds': 0.0}
    resume = out / 'resume.pt'
    if resume.exists() and not a.benchmark_steps:
        blob = restore_matching(resume, model, optimizer)
        if blob.get('identity') != identity['fingerprint']:
            raise ValueError('Resume identity differs')
        exposure = Exposure(blob.get('exposure'))
        pending_rng = blob['rng']
        if a.optimizer == 'adamw':
            set_fused(optimizer, fused)
        step, best = blob['step'], blob.get('best')
        guard.update(blob.get('guard', {}))
        if 'last_eval_step' in guard:
            previous = out / 'evals' / f"step_{guard['last_eval_step']:06d}" / 'utterances.json'
            atomic_json(out / 'previous-evaluation.json', json.loads(previous.read_text()))
        if best is not None:
            selected = out / 'evals' / f"step_{best['step']:06d}"
            for name in ('model_weights.ckpt', 'model_config.yaml', 'metrics.json', 'vocab.txt'):
                if (selected / name).exists():
                    shutil.copy2(selected / name, out / 'best' / name)
        emit(event='resumed', step=step, best=best, guard=guard)
    emit(event='config', accum=a.accum, micro_seconds=micro_seconds, micro_items=micro_items,
         target_hours=a.target_hours, lr=a.lr, optimizer=a.optimizer, betas=a.betas,
         weight_decay=a.weight_decay, mix=train_mix, dev=dev_sets, g2_prob=a.g2_prob,
         rollback=a.rollback, amp=a.amp, noise_pool=a.noise_pool, noise_only_share=a.noise_only_share,
         noise_only_pool=a.noise_only_pool, empty_chars_per_frame=EMPTY_CHARS_PER_FRAME,
         device=str(device), fast_dwconv=a.fast_dwconv, custom_dw_convs=custom_dw,
         fused_adamw=a.fused_adamw, adamw_fused=optimizer.param_groups[0].get('fused'),
         eval_device=('mps' if eval_bucket else 'cpu') if device.type == 'mps' else str(device),
         eval_bucket=eval_bucket, workers=a.workers, seed=a.seed, schedule=a.schedule,
         identity=identity['fingerprint'], gradient_diagnostics_every=a.gradient_diagnostics_every)

    def save_resume():
        save_state(resume, model, optimizer, step=step, best=best, guard=guard,
                   exposure=exposure.state(), identity=identity['fingerprint'])

    from data import NoiseOnlyStore
    if a.g2_prob:  # build the LC3 library once here, not in every DataLoader worker
        import lc3codec
        lc3codec._load()
    noise = noise_source(a.noise_pool)
    augmenter = Augmenter(noise, Store('musan-speech'), Store('rirs'), g2_prob=a.g2_prob)
    only_noise = noise if a.noise_only_pool == 'same' else noise_source(a.noise_only_pool)
    if a.noise_only_share > 0:
        train_mix = train_mix + [(NOISE_ONLY, a.noise_only_share, False)]
    stores = [NoiseOnlyStore(only_noise) if name == NOISE_ONLY else Store(name) for name, _, _ in train_mix]
    dataset = TrainSet(stores, [f for _, _, f in train_mix], template, augmenter, seed=a.seed,
                       **({'encoder': encoder} if encoder else {}))
    total_steps = (a.benchmark_steps * a.accum) or 10 ** 9
    sampler = MixedBatchSampler(stores, [w for _, w, _ in train_mix], micro_seconds, micro_items,
                                total_steps, seed=a.seed + 17, start_batch=guard.get('consumed_batches', 0))
    loader = torch.utils.data.DataLoader(dataset, batch_sampler=sampler,
                                         collate_fn=functools.partial(collate, max_seconds=micro_seconds,
                                                                      max_items=micro_items, reduction=reduction),
                                         num_workers=a.workers,
                                         generator=torch.Generator().manual_seed(a.seed),
                                         **({'persistent_workers': True, 'prefetch_factor': 4} if a.workers else {}))

    start = time.time()
    deadline = parse_deadline(a.deadline) if not a.benchmark_steps else start + 1e9
    target = a.target_hours * 3600
    if not a.benchmark_steps:
        # The schedule spans the whole run, not each process: memory restarts
        # must not reset the LR to its peak.
        first = getattr(os.stat(out / 'train.jsonl'), 'st_birthtime', start)
        start = guard.setdefault('sched_start', min(first, start))
    span = max(deadline - start, 1.0)
    # Score the starting point first so "best" can never be worse than it.
    if best is None and not a.benchmark_steps:
        best = run_eval(model, template, config, out, step, best, emit, device, guard, a.patience, dev_sets,
                        rollback=a.rollback == 'on', bucket=eval_bucket, optimizer=optimizer, diagnostic_sets=a.diagnostic_sets)
        guard['last_eval_audio'] = -(a.eval_hours - a.first_eval_hours) * 3600
        save_resume()
    guard.setdefault('last_eval_audio', 0.0)
    process_audio, t_process = 0.0, time.time()
    window_loss, window_n, t_window = 0.0, 0, time.time()
    micro, micro_loss = 0, 0.0
    train_mode(model)

    if pending_rng is not None:
        restore_rng(pending_rng)
    for feats, lengths, labels, label_lengths, metadata, batch_stats in loader:
        if micro == 0:
            now = time.time()
            if now >= deadline:
                emit(event='deadline', step=step, audio_hours=round(guard['audio_seconds'] / 3600, 2))
                break
            if guard['audio_seconds'] >= target and not a.benchmark_steps:
                emit(event='target_reached', step=step, audio_hours=round(guard['audio_seconds'] / 3600, 2))
                break
            # Linear warmup, then cosine decay over the audio budget (or the
            # remaining wall-clock time, whichever runs out first).
            progress = min(1.0, guard['audio_seconds'] / target)
            if a.schedule == 'legacy-wall':
                progress = min(1.0, max(progress, (now-start)/span))
            lr = a.lr * guard['lr_scale'] * min(1.0, (step + 1) / a.warmup) * \
                (0.05 + 0.95 * 0.5 * (1 + math.cos(math.pi * progress)))
            for g in optimizer.param_groups:
                g['lr'] = lr
            optimizer.zero_grad(set_to_none=True)
            micro_loss = 0.0
            effective_items = 0

        if a.amp and device.type == 'cuda':
            with torch.autocast('cuda', dtype=torch.bfloat16):
                log_probs, out_lengths = model(feats.to(device), lengths.to(device))
        else:
            log_probs, out_lengths = model(feats.to(device), lengths.to(device))
        log_probs = F.log_softmax(log_probs.float(), dim=-1)
        if device.type == 'mps':  # no CTC on MPS: compute the loss on the CPU
            log_probs, out_lengths = log_probs.cpu(), out_lengths.cpu()
        else:
            labels, label_lengths = labels.to(device), label_lengths.to(device)
        nll = F.ctc_loss(log_probs.transpose(0, 1), labels, out_lengths, label_lengths,
                         blank=blank, reduction='none', zero_infinity=False)
        per_item = nll / ctc_divisor(label_lengths, out_lengths)
        invalid = int((~torch.isfinite(per_item)).sum())
        if invalid:
            emit(event='nonfinite_ctc', step=step, count=invalid,
                 items=[m for m, bad in zip(metadata, (~torch.isfinite(per_item)).tolist()) if bad])
            raise FloatingPointError('Nonfinite CTC loss; optimizer was not stepped')
        if a.gradient_diagnostics_every and step % a.gradient_diagnostics_every == 0:
            norms = {}
            for source in sorted({m['source'] for m in metadata}):
                indices = [i for i,m in enumerate(metadata) if m['source'] == source]
                grads = torch.autograd.grad(per_item[indices].mean(), tuple(model.parameters()),
                                            retain_graph=True, allow_unused=True)
                norms[source] = float(torch.stack([g.detach().float().square().sum()
                                                   for g in grads if g is not None]).sum().sqrt())
            if not all(math.isfinite(n) for n in norms.values()):
                emit(event='nonfinite_source_gradient', step=step)
                raise FloatingPointError('Nonfinite per-source gradient')
            emit(event='source_gradient', step=step, microbatch=micro, mean_loss_gradient_norm=norms)
        # Accumulate sums, then divide ALL gradients by actual effective item count.
        per_item.sum().backward()
        effective_items += len(metadata)
        micro_loss += float(per_item.detach().sum())
        exposure.add(metadata, lengths.tolist(), per_item.detach().tolist(), batch_stats)
        guard['consumed_batches'] = guard.get('consumed_batches', 0) + 1
        seconds = float(lengths.sum()) * 0.01
        guard['audio_seconds'] += seconds
        process_audio += seconds
        micro += 1
        if micro < a.accum:
            continue
        micro = 0
        for parameter in model.parameters():
            if parameter.grad is not None:
                parameter.grad.div_(effective_items)
        try:
            norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0, error_if_nonfinite=True)
        except RuntimeError:
            emit(event='nonfinite_gradient', step=step, effective_items=effective_items)
            raise
        guard['optimizer_steps_observed'] = guard.get('optimizer_steps_observed', 0) + 1
        guard['clipped_steps'] = guard.get('clipped_steps', 0) + int(float(norm) > 5.0)
        micro_loss /= effective_items
        if step % 50 == 0:
            emit(event='health', step=step, gradient_norm=float(norm), clipped=float(norm) > 5.0,
                 effective_items=effective_items, sources=exposure.report(), nonfinite_ctc=0,
                 clipped_steps=guard['clipped_steps'], optimizer_steps_observed=guard['optimizer_steps_observed'])
        optimizer.step()
        step += 1
        window_loss += micro_loss
        window_n += 1

        if a.stop_after_steps and step >= a.stop_after_steps:
            save_resume()
            emit(event='requested_stop', step=step, sources=exposure.report())
            log.close()
            os._exit(0)

        if a.benchmark_steps and step % 10 == 0 and footprint_gb() > a.max_footprint_gb:
            emit(event='benchmark_memory', step=step, mem_gb=round(footprint_gb(), 2))
            log.close()
            os._exit(MEMORY_EXIT)

        if step % 50 == 0:
            elapsed = time.time() - t_window
            emit(event='train', step=step, loss=round(window_loss / window_n, 4), lr=f'{lr:.2e}',
                 audio_hours=round(guard['audio_seconds'] / 3600, 2),
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
                rate = process_audio / (time.time() - t_process)
                emit(event='benchmark', accum=a.accum, audio_seconds_per_second=round(rate, 2),
                     mem_gb=round(footprint_gb(), 2),
                     peak_mps_mb=round(torch.mps.driver_allocated_memory() / 2**20) if device.type == 'mps' else None,
                     peak_cuda_mb=round(torch.cuda.max_memory_allocated() / 2**20) if device.type == 'cuda' else None)
                log.close()
                os._exit(0)  # skip slow DataLoader worker teardown
            continue

        if step % a.save_steps == 0:
            save_resume()

        if guard['audio_seconds'] - guard['last_eval_audio'] >= a.eval_hours * 3600:
            best = run_eval(model, template, config, out, step, best, emit, device, guard, a.patience, dev_sets,
                            rollback=a.rollback == 'on', bucket=eval_bucket, optimizer=optimizer, diagnostic_sets=a.diagnostic_sets)
            guard['last_eval_audio'] = guard['audio_seconds']
            save_resume()
            train_mode(model)

    save_checkpoint(model, template, config, out / 'last')
    best = run_eval(model, template, config, out, step, best, emit, device, guard, a.patience, dev_sets,
                    rollback=a.rollback == 'on', bucket=eval_bucket, optimizer=optimizer, diagnostic_sets=a.diagnostic_sets)
    save_resume()
    emit(event='finished', step=step, best=best, audio_hours=round(guard['audio_seconds'] / 3600, 2),
         sources=exposure.report())
    log.close()
    os._exit(0)


def set_fused(optimizer, fused):
    """resume.pt brings back the param groups it was saved with, so a run saved
    before --fused-adamw (or with the other setting) would silently keep its
    old AdamW kernel. Re-apply the flag and keep each state['step'] where that
    kernel wants it: fused float32 on the parameter's device, the per-tensor
    loop on the CPU (it reads the step back every update)."""
    for group in optimizer.param_groups:
        group['fused'] = fused
        for p in group['params']:
            state = optimizer.state.get(p, {})
            if 'step' in state:
                state['step'] = state['step'].to(device=p.device if fused else 'cpu', dtype=torch.float32)


def train_mode(model):
    """Train weights but keep the pretrained BatchNorm statistics: augmented,
    padded fine-tuning batches would otherwise drag them off the real-audio
    distribution."""
    model.train()
    for m in model.modules():
        if isinstance(m, torch.nn.modules.batchnorm._BatchNorm):
            m.eval()


def run_eval(model, template, config, out, step, best, emit, device, guard, patience, dev_sets=DEV_SETS,
             rollback=True, bucket=None, optimizer=None, diagnostic_sets=()):
    selection_sets = dev_sets
    dev_sets = list(dev_sets) + [(name, 300) for name in diagnostic_sets
                                 if name not in {n for n, _ in dev_sets}]
    model.eval()
    t0 = time.time()
    if device.type == 'mps' and bucket:
        # --eval-device mps: the training model itself, with the dev items
        # batched and padded to the training micro-batch shapes, so MPS only
        # sees graphs training has already cached (~110 s vs ~20 min on CPU).
        # Same items and dither stream; per-set WER was bit-identical at step 0
        # and within one near-tie word per set on trained weights. No
        # torch.mps.empty_cache() afterwards: the eval fits in training's pool,
        # and emptying it only made training regrow it (+0.4 GB that stayed).
        results = evaluate_stores(model, template, dev_sets, device, bucket=bucket)
    elif device.type == 'mps':
        # Evaluate a CPU copy: eval batches have many distinct shapes, each of
        # which would otherwise leave a cached graph behind on MPS. 30 s batches
        # instead of 200 s: identical WER (padding is masked), ~3x faster on CPU.
        cpu_model = copy.deepcopy(model).cpu().eval()
        results = evaluate_stores(cpu_model, template, dev_sets, torch.device('cpu'), batch_seconds=30.0)
        del cpu_model
    else:
        results = evaluate_stores(model, template, dev_sets, device)
    if set(results) != {name for name, _ in dev_sets} or any(results[name]['wer'] is None for name, _ in selection_sets):
        raise ValueError('Incomplete or empty-word selection evaluation')
    wers = {name: results[name]['wer'] for name, _ in selection_sets}
    score = broad_score(wers) if selection_sets is BROAD_DEV_SETS else float(np.mean(list(wers.values())))
    metrics = {'score': score, 'step': step, 'audio_hours': round(guard['audio_seconds'] / 3600, 2),
               'sets': {k: v['wer'] for k, v in results.items()}}
    emit(event='eval', step=step, score=round(score, 4), eval_s=round(time.time() - t0),
         audio_hours=metrics['audio_hours'], mem_gb=round(footprint_gb(), 2),
         **{k: round(v['wer'], 4) if v['wer'] is not None else None for k, v in results.items()},
         diagnostics={k: {x: v[x] for x in ('wer','errors','words','phantom_words_per_minute')}
                      for k,v in results.items() if k in diagnostic_sets})
    # Every evaluated point is kept (~76 MB each for the 15x5).
    snapshot = out / 'evals' / f'step_{step:06d}'
    save_checkpoint(model, template, config, snapshot)
    (snapshot / 'metrics.json').write_text(json.dumps(metrics, indent=2))
    previous_path = out / 'previous-evaluation.json'
    if previous_path.exists():
        previous = json.loads(previous_path.read_text())
        for name, result in results.items():
            result['paired'] = paired_changes(previous[name]['records'], result['records'])
    atomic_json(snapshot / 'utterances.json', results)
    atomic_json(previous_path, results)
    guard['last_eval_step'] = step
    if best is None or score < best['score']:
        best = metrics
        guard['bad'] = 0
        save_checkpoint(model, template, config, out / 'best')
        (out / 'best' / 'metrics.json').write_text(json.dumps(best, indent=2))
        if optimizer is not None:
            save_state(snapshot / 'training.pt', model, optimizer, step=step)
        emit(event='new_best', step=step, score=round(score, 4))
        return best
    if not rollback:  # --rollback off: keep training straight through
        return best
    # Noise on the dev subsets is ~0.3% absolute: only a clear loss counts,
    # and a big one rolls back immediately.
    if score > best['score'] * 1.01:
        guard['bad'] += 1
    if (guard['bad'] >= patience or score > best['score'] * 1.05) and step != best['step']:
        if optimizer is None:
            raise ValueError('Rollback requires matching optimizer state')
        fused = optimizer.param_groups[0].get('fused')
        restore_matching(out / 'evals' / f"step_{best['step']:06d}" / 'training.pt', model, optimizer)
        if isinstance(optimizer, torch.optim.AdamW):
            set_fused(optimizer, fused)
        guard['bad'] = 0
        guard['lr_scale'] *= 0.5
        emit(event='rollback', to_step=best['step'], score=round(best['score'], 4),
             lr_scale=guard['lr_scale'])
    return best


if __name__ == '__main__':
    main()
