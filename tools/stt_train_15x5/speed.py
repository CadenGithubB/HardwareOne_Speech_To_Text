#!/usr/bin/env python3
"""CPU cost per audio second for each checkpoint (a rough hint of device cost).

speed.py --ckpt NAME=DIR [NAME=DIR ...] [--threads 1 0] [--out speed.json]

Runs the acoustic model only (features precomputed) one utterance at a time,
as the device does, on a fixed set of dev utterances. --threads 0 = torch's
default thread count. Also reports parameter counts and an int8 size estimate
scaled from the deployed 5x5 file (weights after BatchNorm folding).
"""
import argparse
import json
import random
import time

import torch

from common import QuartzNet, Frontend, load_checkpoint
from data import Store

DEPLOYED_5X5_BYTES = 5487504  # deploy/export-run2/quartznet5x5.p4.stt


def folded_params(model):
    """Weights + one bias per output channel once BN is folded into the convs."""
    n = 0
    for m in model.modules():
        if isinstance(m, torch.nn.Conv1d):
            n += m.weight.numel() + (m.out_channels if m.groups == 1 else 0)
    return n


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--ckpt', nargs='+', required=True, help='NAME=DIR')
    p.add_argument('--threads', type=int, nargs='+', default=[1, 0])
    p.add_argument('--per-set', type=int, default=20)
    p.add_argument('--out')
    a = p.parse_args()

    items = []
    for name in ('ami-sdm-validation', 'ami-ihm-validation', 'librispeech-dev-clean'):
        store = Store(name)
        order = list(range(len(store)))
        random.Random(1).shuffle(order)
        items += [(store, i) for i in order[:a.per_set]]
    audio_s = sum(s.lengths[i] for s, i in items) / 16000

    results = {'audio_seconds': round(audio_s, 1), 'utterances': len(items), 'models': {}}
    default_threads = torch.get_num_threads()
    for spec in a.ckpt:
        name, path = spec.split('=', 1)
        config, state = load_checkpoint(path)
        model = QuartzNet(config).load_nemo(state).eval()
        frontend = Frontend(state)
        feats = [frontend(s.samples(i), dither=False) for s, i in items]
        entry = {'params': sum(p.numel() for p in model.parameters()),
                 'folded_params': folded_params(model)}
        for threads in a.threads:
            torch.set_num_threads(threads or default_threads)
            with torch.no_grad():
                model(feats[0][None], torch.tensor([feats[0].shape[1]]))  # warm-up
                t0, c0 = time.perf_counter(), time.process_time()
                for f in feats:
                    model(f[None], torch.tensor([f.shape[1]]))
                wall, cpu = time.perf_counter() - t0, time.process_time() - c0
            entry[f'threads_{threads or default_threads}'] = {
                'wall_s_per_audio_s': round(wall / audio_s, 4),
                'cpu_s_per_audio_s': round(cpu / audio_s, 4)}
        results['models'][name] = entry
        print(name, json.dumps(entry), flush=True)
    base = next((m['folded_params'] for n, m in results['models'].items() if '5x5' in n and '15x5' not in n), None)
    if base:
        for m in results['models'].values():
            m['int8_bytes_estimate'] = int(DEPLOYED_5X5_BYTES * m['folded_params'] / base)
    if a.out:
        with open(a.out, 'w') as f:
            json.dump(results, f, indent=2)


if __name__ == '__main__':
    main()
