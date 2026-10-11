#!/usr/bin/env python3
"""Make glasses-channel copies of evaluation stores: <name>-g2.

Each utterance goes through the G2 mic channel deterministically (seeded by its
index): slow gain control toward -24 dB, then LC3 at the glasses' settings
(16 kHz, 10 ms, 32 kbps) with 0.2% concealed frame loss. Same order, texts and
speakers as the source, so evaluate.py's fixed subsets pick the same items.

This simulates the channel; it is not a substitute for audio actually recorded
through the glasses (room, distance and the wearer's own voice differ).

  make_g2_stores.py ami-sdm-validation ami-ihm-validation ami-sdm-test ami-ihm-test
"""
import json
import os
import hashlib
import random
import sys

import numpy as np

from data import STORES, Store
from lc3codec import G2Channel, agc


def convert(name):
    src = Store(name)
    out = STORES / f'{name}-g2'
    if (out / 'index.json').exists():
        print(f'{out.name}: exists, skipped')
        return
    out.mkdir(parents=True, exist_ok=True)
    channel = G2Channel()
    index = json.loads((STORES / name / 'index.json').read_text())
    offsets, position = [], 0
    sha = hashlib.sha256()  # of exactly what was written; verify_stores.py re-reads it from disk
    with open(out / 'audio.bin.tmp', 'wb') as f:
        for i in range(len(src)):
            rng = random.Random(1_000_003 * i + 17)
            x = agc(src.samples(i), rng, target_db=-24.0)
            y = channel(np.clip(x, -1, 1), loss_rate=0.002, rng=rng)
            pcm = np.clip(np.round(y * 32767), -32768, 32767).astype('<i2')
            data = pcm.tobytes()
            f.write(data)
            sha.update(data)
            offsets.append(position)
            position += len(pcm)
            if i % 2000 == 0:
                print(f'{out.name}: {i}/{len(src)}', flush=True)
        f.flush()
        os.fsync(f.fileno())
    (out / 'audio.bin.tmp').replace(out / 'audio.bin')
    index['audio_sha256'] = sha.hexdigest()
    index['offsets'] = offsets
    index['lengths'] = [int(n) for n in src.lengths]
    index['source'] = {'store': name, 'channel': 'agc -24 dB + LC3 16k/10ms/40B, 0.2% PLC',
                       'seed': '1000003*i+17'}
    (out / 'index.json.tmp').write_text(json.dumps(index))
    (out / 'index.json.tmp').replace(out / 'index.json')
    print(f'{out.name}: done, {len(src)} items')


if __name__ == '__main__':
    for name in sys.argv[1:]:
        convert(name)
