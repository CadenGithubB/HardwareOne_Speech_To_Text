#!/usr/bin/env python3
"""Conversation playlists with known speakers, for the c13 speaker-label test.

  make_conv_playlist.py --name conv1 --store librispeech-dev-clean --speakers 3 [--seed 1] [--seconds 225]

One conversation per playlist (labels are per session): K speakers from one store take turns of 1-10 s
(the next turn is another speaker 80% of the time), separated by 1.0-1.8 s of silence so each turn is its own
phrase. Same level/fade/lead/tail handling as build_playlist.py; manifest clips carry `speaker`. The int8
calibration clips are excluded. Numbers only.
"""
import argparse
import hashlib
import json
import random
import time
import wave
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

import build_playlist as bp

HERE = Path(__file__).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True)
    ap.add_argument('--store', required=True)
    ap.add_argument('--speakers', type=int, default=3)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--seconds', type=float, default=225.0)
    a = ap.parse_args()
    idx, audio = bp.load_store(a.store)
    calib = bp.calibration_set()
    by = {}
    for i, (s, L) in enumerate(zip(idx['speakers'], idx['lengths'])):
        if 1.0 <= L / bp.SR_STORE <= 10.0 and (a.store, i) not in calib and len(bp.normalize_text(idx['texts'][i]).split()) >= 2:
            by.setdefault(s, []).append(i)
    rng = random.Random(a.seed)
    spks = rng.sample(sorted(s for s, v in by.items() if len(v) >= 12), a.speakers)
    for s in spks:
        rng.shuffle(by[s])
    rate, up = 48000, 3
    parts, pos, clips, last, used = [np.zeros(6 * rate)], 6 * rate, [], None, {s: 0 for s in spks}
    while True:
        s = rng.choice([x for x in spks if x != last]) if last and rng.random() < 0.8 else rng.choice(spks)
        if used[s] >= len(by[s]):
            break
        i = by[s][used[s]]; used[s] += 1
        off, L = idx['offsets'][i], idx['lengths'][i]
        x = np.asarray(audio[off:off + L], dtype=np.float32) / 32768.0
        st = bp.level_stats(x)
        gain = -20.0 - st['active_dbfs']
        backoff = max(0.0, st['peak_dbfs'] + gain + 1.0)
        if backoff > 4.0 or gain > 20.0:
            continue
        y = resample_poly(x.astype(np.float64) * 10 ** ((gain - backoff) / 20), up, 1)
        y = y * bp.fade(len(y), rate)
        pk = float(np.max(np.abs(y)))
        if pk > 10 ** (-1 / 20):
            y *= 10 ** (-1 / 20) / pk
        g = round(rng.uniform(1.0, 1.8), 2)
        dur = (pos + len(y) + g * rate + 2.5 * rate) / rate
        if dur > a.seconds:
            break
        text = bp.normalize_text(idx['texts'][i])
        clips.append({'i': len(clips), 'store': a.store, 'item': i, 'speaker': s, 'bin': 'conv',
                      'dur_s': round(len(y) / rate, 4), 'start_s': round(pos / rate, 4), 'end_s': round((pos + len(y)) / rate, 4),
                      'speech_start_s': round((pos + st['speech_start'] * up) / rate, 4),
                      'speech_end_s': round((pos + st['speech_end'] * up) / rate, 4), 'gap_after_s': g,
                      'gain_db': round(gain - backoff, 2), 'text': text, 'text_norm': text, 'words': len(text.split())})
        parts.append(y); pos += len(y)
        parts.append(np.zeros(int(round(g * rate)))); pos += int(round(g * rate))
        last = s
    clips[-1]['gap_after_s'] = 0.0
    parts.append(np.zeros(int(2.5 * rate)))
    sig = np.concatenate(parts)
    pcm = np.clip(np.round(sig * 32767.0), -32768, 32767).astype('<i2')
    d = HERE / f'playlist-{a.name}'
    d.mkdir(exist_ok=True)
    with wave.open(str(d / 'playlist.wav'), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes())
    sha = hashlib.sha256((d / 'playlist.wav').read_bytes()).hexdigest()
    man = {'created': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'wav': str(d / 'playlist.wav'), 'wav_sha256': sha,
           'sample_rate': rate, 'duration_s': round(len(pcm) / rate, 4), 'seed': a.seed, 'store': a.store,
           'speakers': spks, 'bins': {'conv': {'stores': [a.store]}}, 'reference_words': sum(c['words'] for c in clips),
           'clips': clips}
    (d / 'manifest.json').write_text(json.dumps(man, indent=1))
    turns = {s: sum(1 for c in clips if c['speaker'] == s) for s in spks}
    print(f'{d.name}: {len(clips)} turns, {len(pcm) / rate:.1f} s, speakers {len(spks)} turns each {sorted(turns.values())}')


if __name__ == '__main__':
    main()
