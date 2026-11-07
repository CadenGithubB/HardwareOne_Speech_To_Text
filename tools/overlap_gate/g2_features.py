"""One sequential pass per store: raw log-mel features (pre-CMVN, dither off) to local float16 files.

The store audio lives on a USB drive, and random 2 s reads from it made training seek-bound.
Reading each store once in offset order is fast there; training then takes random slices from
these local files. Features are exactly what g2_common.RawFrontend computes, so nothing about the
model input changes. Per item: start frame, frame count and, for noise stores, the waveform RMS
(so level augmentation can be applied as a log-domain offset).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overlap_gate import g2_common as g2  # noqa: E402

FEATURES = g2.PHASE3 / 'features'


def items_for(store_name: str, max_hours: float | None = None, seed: int = 20261106):
    """(key, store_index) pairs to featurize for a store; large stores take a seeded subset by hours."""
    if store_name.startswith('ami-'):
        mic, split = store_name.split('-')[1], store_name.split('-')[2]
        frozen = json.loads((g2.LABELS / f'labels-{split}.json').read_text())
        key = f'store_{mic}'
        return [(r['audio_id'], r[key]) for r in frozen['records'] if r.get(key) is not None]
    store = g2.Store(store_name)
    sys.path.insert(0, str(g2.ROOT / 'tools/stt_train_15x5'))
    from diagnostics import effective_ids  # honours the stores' keep/excluded lists
    ids = effective_ids(g2.STORES / store_name, store.index)
    if max_hours is not None:
        import random
        rng = random.Random(seed)
        rng.shuffle(ids)
        budget, kept = max_hours * 3600 * g2.SAMPLE_RATE, []
        for i in ids:
            if budget <= 0:
                break
            kept.append(i)
            budget -= store.index['lengths'][i]
        ids = kept
    return [(str(i), i) for i in ids]


def run(store_name: str, frontend: g2.RawFrontend, out: Path, max_hours: float | None = None):
    store = g2.Store(store_name)
    items = sorted(items_for(store_name, max_hours), key=lambda kv: store.index['offsets'][kv[1]])
    total = sum(math.ceil(store.index['lengths'][i] / g2.HOP) for _k, i in items)
    feat_file = out / f'{store_name}.f16'
    feats = np.memmap(feat_file, np.float16, 'w+', shape=(total, g2.MELS))
    index, pos, t0 = {}, 0, time.time()
    with torch.inference_mode():
        for n, (key, i) in enumerate(items, 1):
            pcm = store.pcm(i).astype(np.float32) / 32768
            f = frontend(pcm).numpy().T                                   # [T, 64]
            feats[pos:pos + f.shape[0]] = f.astype(np.float16)
            entry = dict(start=pos, frames=int(f.shape[0]), store_index=int(i))
            if not store_name.startswith('ami-'):
                entry['rms'] = float(np.sqrt(np.mean(pcm ** 2)) + 1e-9)
            index[key] = entry
            pos += f.shape[0]
            if n % 5000 == 0:
                print(f'{store_name} {n}/{len(items)} {time.time() - t0:.0f}s', flush=True)
    feats.flush()
    assert pos == total
    (out / f'{store_name}.json').write_text(json.dumps(dict(store=store_name, frames=total, mels=g2.MELS, dtype='float16', max_hours=max_hours, items=index)) + '\n')
    print(json.dumps(dict(store=store_name, items=len(items), frames=total, gigabytes=round(total * g2.MELS * 2 / 1e9, 2), seconds=round(time.time() - t0))), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stores', nargs='+')
    ap.add_argument('--out', type=Path, default=FEATURES)
    ap.add_argument('--max-hours', type=float, default=None, help='seeded subset cap for large non-AMI stores')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(2)
    frontend = g2.RawFrontend()
    silence = frontend(np.zeros(g2.WINDOW_SAMPLES, np.float32)).numpy()
    (args.out / 'silence-feature.json').write_text(json.dumps(dict(per_bin_mean=silence.mean(axis=1).tolist(), note='raw log-mel of digital silence; used to pad short utterances')) + '\n')
    for s in args.stores:
        if (args.out / f'{s}.json').exists():
            print('exists', s)
            continue
        run(s, frontend, args.out, args.max_hours)


if __name__ == '__main__':
    main()
