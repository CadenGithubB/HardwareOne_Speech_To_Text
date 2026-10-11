#!/usr/bin/env python3
"""DEMAND everyday noise -> training and held-out test noise stores.

  prepare_noise.py [--src $STT_ROOT/demand]

DEMAND (Thiemann et al. 2013, CC-BY 4.0, zenodo 1227121): 17 real
environments (kitchen, living room, washing, field, park, river, hallway,
meeting, office, cafeteria, restaurant, station, square, traffic, bus, car,
metro), ~5 min each from a 16-mic array at 16 kHz.

Split by TIME, not by channel (the channels are simultaneous recordings of
the same sounds): the first 80% of each environment trains, the last 20% is
held out. Writes, in the usual store format (audio.bin int16 + index.json):
  demand-noise-train  ch01 and ch09 of the first 80% (2 items per environment)
  demand-noise-test   last 20% of ch01, cut into 10 s clips, empty texts:
                      noise the model never trained on, for the phantom-word
                      and noisy-speech benchmarks
"""
import argparse
import io
import json
import os
import hashlib
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf

from data import STORES

TRAIN_SHARE = 0.8
CLIP = 10 * 16000


def write_store(name, items):
    out = STORES / name
    if (out / 'index.json').exists():
        print(f'{name}: exists, skipped')
        return
    out.mkdir(parents=True, exist_ok=True)
    offsets, lengths, texts, speakers, position = [], [], [], [], 0
    sha = hashlib.sha256()  # of exactly what was written; verify_stores.py re-reads it from disk
    with open(out / 'audio.bin.tmp', 'wb') as f:
        for env, audio in items:
            pcm = np.clip(np.round(audio * 32767), -32768, 32767).astype('<i2')
            data = pcm.tobytes()
            f.write(data)
            sha.update(data)
            offsets.append(position); lengths.append(len(pcm)); texts.append(''); speakers.append(env)
            position += len(pcm)
        f.flush()
        os.fsync(f.fileno())
    (out / 'audio.bin.tmp').replace(out / 'audio.bin')
    (out / 'index.json').write_text(json.dumps({'offsets': offsets, 'lengths': lengths, 'texts': texts,
                                                 'speakers': speakers, 'source': 'DEMAND 16 kHz, CC-BY 4.0',
                                                 'audio_sha256': sha.hexdigest()}))
    print(f'{name}: {len(items)} items, {position / 16000 / 60:.1f} min')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=str(STORES.parent / 'demand'))
    a = ap.parse_args()
    train, test = [], []
    for z in sorted(Path(a.src).glob('*_16k.zip')):
        env = z.name[:-len('_16k.zip')]
        with zipfile.ZipFile(z) as zf:
            def channel(n):
                name = next(m for m in zf.namelist() if m.endswith(f'ch{n:02d}.wav'))
                audio, rate = sf.read(io.BytesIO(zf.read(name)), dtype='float32')
                assert rate == 16000 and audio.ndim == 1, (z, name, rate)
                return audio
            ch1, ch9 = channel(1), channel(9)
        cut = int(len(ch1) * TRAIN_SHARE)
        train += [(env, ch1[:cut]), (env, ch9[:cut])]
        held = ch1[cut:]
        test += [(env, held[i:i + CLIP]) for i in range(0, len(held) - CLIP + 1, CLIP)]
    write_store('demand-noise-train', train)
    write_store('demand-noise-test', test)


if __name__ == '__main__':
    main()
