#!/usr/bin/env python3
"""Drop training items whose transcript does not match their audio.

filter_store.py --store peoples-clean-train --ckpt $STT_ROOT/work/run15x5b/full/best
                [--max-cer 0.5] [--dry-run]

Corpora aligned from subtitles (People's Speech) contain clips whose text is
shifted, truncated or for other audio. A model trained on them learns wrong
words. The reference model (the best fine-tuned 15x5) transcribes every item;
an item is kept when its character error rate against the transcript is at
most --max-cer. Clean, in-domain speech scores ~0.1-0.3 CER even on hard
audio, so 0.5 removes gross mismatches, not difficult speech.

Writes <store>/keep.json ({"keep": [indices], ...stats}); data.Store applies
it, the audio and index stay untouched (delete keep.json to undo). Also writes
<store>/cer.json (per-item CER) so the threshold can be revisited without
re-running the model.
"""
import argparse
import json

import numpy as np
import torch

from common import QuartzNet, Frontend, load_checkpoint, greedy_decode
from data import STORES
import os
from pathlib import Path
STT_ROOT = Path(os.environ.get('STT_ROOT', 'stt-data'))  # data root: set STT_ROOT


def edit_distance(a, b):
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        nxt = [i]
        for j, cb in enumerate(b, 1):
            nxt.append(min(nxt[-1] + 1, row[j] + 1, row[j - 1] + (ca != cb)))
        row = nxt
    return row[-1]


@torch.no_grad()
def score(store_dir, ckpt, batch_seconds=200.0):
    index = json.loads((store_dir / 'index.json').read_text())
    offsets, lengths, texts = index['offsets'], index['lengths'], index['texts']
    audio = np.memmap(store_dir / 'audio.bin', dtype='<i2', mode='r')
    config, state = load_checkpoint(ckpt)
    device = torch.device('cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu')
    model = QuartzNet(config).load_nemo(state).to(device).eval()
    frontend = Frontend(state)
    rng = np.random.default_rng(0)
    order = sorted(range(len(lengths)), key=lambda i: lengths[i])
    cer = [None] * len(lengths)
    batch = []

    def flush():
        feats = [frontend(np.asarray(audio[offsets[i]:offsets[i] + lengths[i]], dtype=np.float32) / 32768.0,
                          dither=True, rng=rng) for i in batch]
        n = torch.tensor([f.shape[1] for f in feats])
        x = torch.zeros(len(feats), feats[0].shape[0], int(n.max()))
        for k, f in enumerate(feats):
            x[k, :, :f.shape[1]] = f
        log_probs, out_n = model(x.to(device), n.to(device))
        for i, hyp in zip(batch, greedy_decode(log_probs, out_n)):
            ref = texts[i]
            cer[i] = edit_distance(ref, hyp) / max(len(ref), 1)

    for done, i in enumerate(order):
        if batch and lengths[i] / 16000 * (len(batch) + 1) > batch_seconds:
            flush()
            batch = []
        batch.append(i)
        if done % 5000 == 0:
            print(f'{done}/{len(order)}', flush=True)
    if batch:
        flush()
    return cer, lengths


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--store', required=True)
    p.add_argument('--ckpt', required=True)
    p.add_argument('--max-cer', type=float, default=0.5)
    p.add_argument('--dry-run', action='store_true', help='report only, no keep.json')
    a = p.parse_args()
    store_dir = STORES / a.store
    cer_path = store_dir / 'cer.json'
    if cer_path.exists():
        saved = json.loads(cer_path.read_text())
        cer, lengths = saved['cer'], json.loads((store_dir / 'index.json').read_text())['lengths']
    else:
        cer, lengths = score(store_dir, a.ckpt)
        cer_path.write_text(json.dumps({'ckpt': a.ckpt, 'cer': cer}))
    keep = [i for i, c in enumerate(cer) if c <= a.max_cer]
    hours = lambda ids: sum(lengths[i] for i in ids) / 16000 / 3600
    q = np.percentile(cer, [10, 25, 50, 75, 90, 95])
    stats = {'items': len(cer), 'kept': len(keep), 'hours': round(hours(range(len(cer))), 1),
             'kept_hours': round(hours(keep), 1), 'max_cer': a.max_cer, 'ckpt': a.ckpt,
             'cer_percentiles_10_25_50_75_90_95': [round(float(x), 3) for x in q]}
    print(json.dumps(stats))
    if not a.dry_run:
        (store_dir / 'keep.json').write_text(json.dumps({'keep': keep, **stats}))


if __name__ == '__main__':
    main()
