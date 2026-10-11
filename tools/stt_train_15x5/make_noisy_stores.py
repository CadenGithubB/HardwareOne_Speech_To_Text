#!/usr/bin/env python3
"""Noisy copies of evaluation stores: <name>-noisy.

  make_noisy_stores.py librispeech-test-clean peoples-clean-test [--noise demand-noise-test]

Each utterance gets held-out everyday noise (DEMAND test portion: never used
in training) at a deterministic random SNR between 0 and 10 dB (loud: a busy
cafe or street), seeded by its index, so every model is scored on identical
audio. Same order, texts and lengths as the source. Mixing happens before the
glasses-channel simulation would, as on the device (the noise is in the room).
"""
import argparse
import json
import os
import hashlib
import random

import numpy as np

from data import STORES, Store


def rms(x):
    return float(np.sqrt(np.mean(np.square(x)) + 1e-12))


def convert(name, noise, snr_min, snr_max):
    out = STORES / f'{name}-noisy'
    if (out / 'index.json').exists():
        print(f'{out.name}: exists, skipped')
        return
    src = Store(name)
    out.mkdir(parents=True, exist_ok=True)
    index = json.loads((STORES / name / 'index.json').read_text())
    offsets, position = [], 0
    sha = hashlib.sha256()  # of exactly what was written; verify_stores.py re-reads it from disk
    with open(out / 'audio.bin.tmp', 'wb') as f:
        for i in range(len(src)):
            rng = random.Random(7919 * i + 3)
            x = src.samples(i)
            n = noise.samples(rng.randrange(len(noise)))
            if len(n) < len(x):
                n = np.tile(n, int(np.ceil(len(x) / len(n))))
            start = rng.randrange(len(n) - len(x) + 1)
            n = n[start:start + len(x)]
            snr = rng.uniform(snr_min, snr_max)
            y = x + n * (rms(x) / rms(n)) / (10 ** (snr / 20))
            peak = float(np.max(np.abs(y))) if len(y) else 0.0
            if peak > 0.99:
                y = y * (0.99 / peak)
            pcm = np.clip(np.round(y * 32767), -32768, 32767).astype('<i2')
            data = pcm.tobytes()
            f.write(data)
            sha.update(data)
            offsets.append(position)
            position += len(pcm)
        f.flush()
        os.fsync(f.fileno())
    (out / 'audio.bin.tmp').replace(out / 'audio.bin')
    index['audio_sha256'] = sha.hexdigest()
    index['offsets'] = offsets
    index['lengths'] = [int(n) for n in src.lengths]
    index['source'] = {'store': name, 'noise': noise.name, 'snr_db': [snr_min, snr_max], 'seed': '7919*i+3'}
    (out / 'index.json.tmp').write_text(json.dumps(index))
    (out / 'index.json.tmp').replace(out / 'index.json')
    print(f'{out.name}: {len(src)} items')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stores', nargs='+')
    ap.add_argument('--noise', default='demand-noise-test')
    ap.add_argument('--snr-min', type=float, default=0.0)
    ap.add_argument('--snr-max', type=float, default=10.0)
    a = ap.parse_args()
    noise = Store(a.noise)
    for name in a.stores:
        convert(name, noise, a.snr_min, a.snr_max)


if __name__ == '__main__':
    main()
