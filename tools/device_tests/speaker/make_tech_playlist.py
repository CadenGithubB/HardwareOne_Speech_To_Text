#!/usr/bin/env python3
"""Tech-speech test playlists from the TTS test sentences (analysis/techvocab/test_sentences.jsonl).

  make_tech_playlist.py [--parts 5]     writes playlist-tech1 .. playlist-techN (playlist.wav + manifest.json)

Each sentence is spoken by a macOS voice (13 natural English voices, rotating), at 16 kHz, scaled to the
same -20 dBFS active level as the standard playlist, with 1.5-2.5 s of silence between clips, 6 s lead and
2.5 s tail, resampled to 48 kHz. The reference is the sentence's normalized `ref`. Parts are sized to stay
under ~235 s so the c12 probe dump (262 s after capture start) comes after the last clip. Numbers only.
"""
import os
import argparse
import hashlib
import json
import random
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

import build_playlist as bp

HERE = Path(__file__).parent
SRC = Path(os.path.join(os.environ.get('STT_ROOT', 'stt-data'), 'hw1-work/analysis/techvocab/test_sentences.jsonl'))
VOICES = ['Samantha', 'Daniel', 'Karen', 'Moira', 'Kathy', 'Tessa', 'Rishi', 'Eddy (English (US))',
          'Flo (English (UK))', 'Reed (English (US))', 'Sandy (English (UK))', 'Shelley (English (US))',
          'Rocko (English (UK))']


def tts(text, voice):
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / 'a.wav'
        subprocess.run(['say', '-v', voice, '-o', str(out), '--file-format=WAVE', '--data-format=LEI16@16000', text],
                       check=True)
        with wave.open(str(out)) as w:
            assert w.getframerate() == 16000 and w.getnchannels() == 1
            return np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(np.float32) / 32768.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parts', type=int, default=5)
    ap.add_argument('--max-seconds', type=float, default=235.0)
    ap.add_argument('--seed', type=int, default=20261011)
    a = ap.parse_args()
    items = [json.loads(l) for l in open(SRC)]
    rng = random.Random(a.seed)
    clips = []
    for k, it in enumerate(items):
        voice = VOICES[k % len(VOICES)]
        x = tts(it['tts'], voice)
        st = bp.level_stats(x)
        gain = -20.0 - st['active_dbfs']
        backoff = max(0.0, st['peak_dbfs'] + gain - (-1.0))
        clips.append({'k': k, 'voice': voice, 'x16': x, 'stats': st, 'gain_db': gain - backoff, 'backoff_db': backoff,
                      'ref': bp.normalize_text(it['ref'])})
    per = (len(clips) + a.parts - 1) // a.parts
    for p in range(a.parts):
        part = clips[p * per:(p + 1) * per]
        rate, up = 48000, 3
        parts = [np.zeros(6 * rate)]
        pos = len(parts[0])
        out = []
        for i, c in enumerate(part):
            y = resample_poly(c['x16'].astype(np.float64) * 10 ** (c['gain_db'] / 20), up, 1)
            y = y * bp.fade(len(y), rate)
            pk = float(np.max(np.abs(y)))
            if pk > 10 ** (-1 / 20):
                y *= 10 ** (-1 / 20) / pk
            g = round(rng.uniform(1.5, 2.5), 2) if i < len(part) - 1 else 0.0
            st = c['stats']
            out.append({'i': i, 'store': 'tech-tts', 'item': c['k'], 'bin': 'tech', 'voice': c['voice'],
                        'dur_s': round(len(y) / rate, 4), 'start_s': round(pos / rate, 4), 'end_s': round((pos + len(y)) / rate, 4),
                        'speech_start_s': round((pos + st['speech_start'] * up) / rate, 4),
                        'speech_end_s': round((pos + st['speech_end'] * up) / rate, 4), 'gap_after_s': g,
                        'gain_db': round(c['gain_db'], 2), 'backoff_db': round(c['backoff_db'], 2),
                        'text': c['ref'], 'text_norm': c['ref'], 'words': len(c['ref'].split())})
            parts.append(y)
            pos += len(y)
            if g:
                parts.append(np.zeros(int(round(g * rate))))
                pos += int(round(g * rate))
        parts.append(np.zeros(int(2.5 * rate)))
        sig = np.concatenate(parts)
        dur = len(sig) / rate
        if dur > a.max_seconds:
            raise SystemExit(f'part {p + 1}: {dur:.1f} s > {a.max_seconds} s; use more --parts')
        pcm = np.clip(np.round(sig * 32767.0), -32768, 32767).astype('<i2')
        d = HERE / f'playlist-tech{p + 1}'
        d.mkdir(exist_ok=True)
        with wave.open(str(d / 'playlist.wav'), 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes())
        sha = hashlib.sha256((d / 'playlist.wav').read_bytes()).hexdigest()
        man = {'created': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'wav': str(d / 'playlist.wav'), 'wav_sha256': sha,
               'sample_rate': rate, 'duration_s': round(dur, 4), 'seed': a.seed, 'lead_s': 6.0, 'tail_s': 2.5,
               'gap_range_s': [1.5, 2.5], 'level_dbfs': -20.0, 'source': str(SRC), 'voices': VOICES,
               'bins': {'tech': {'stores': ['tech-tts']}}, 'reference_words': sum(c['words'] for c in out), 'clips': out}
        (d / 'manifest.json').write_text(json.dumps(man, indent=1))
        print(f'{d.name}: {len(out)} clips, {dur:.1f} s, {man["reference_words"]} words')


if __name__ == '__main__':
    main()
