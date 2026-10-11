#!/usr/bin/env python3
"""Build the speaker playlist for on-chip STT timing runs (deterministic).

  export-venv/bin/python build_playlist.py [--out DIR] [--seconds 240] [--seed 20261009]

One mono WAV (48 kHz int16 by default) of public dev-set speech:
  - 6 s of digital silence at the start, ~2.5 s at the end;
  - equal numbers of clips in three length bins, interleaved in a seeded order:
      short 1-3 s   ami-ihm-validation only (conversational replies, >= 3 words)
      mid   4-6 s   librispeech-dev-clean / voxpopuli-dev / ami-ihm-validation
      long  7-15 s  librispeech-dev-clean / peoples-dev / voxpopuli-dev
  - 1.5-2.5 s of digital silence between clips (seeded uniform, 10 ms grid);
  - every clip scaled to the same active-speech level (default -20 dBFS,
    peaks <= -1 dBFS; a clip needing > 4 dB of peak backoff or > 20 dB of
    gain is skipped), with
    10 ms raised-cosine fades so clip edges do not click.
Candidates per store follow evaluate.py's order (random.Random(0).shuffle of the
indices); the 100 int8-calibration clips (export-gen2-25397 manifest) and
*-test stores are never used.

Writes DIR/playlist.wav, DIR/manifest.json (clip index, store, item, bin,
start/end and speech start/end offsets in the WAV, gain, reference text) and
prints only the composition (counts, seconds, words) - never transcript text.
"""
import os
import argparse
import hashlib
import json
import math
import random
import re
import time
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

STORES = Path(os.path.join(os.environ.get('STT_ROOT', 'stt-data'), 'stores'))
CALIB = Path(os.path.join(os.environ.get('STT_ROOT', 'stt-data'), 'work/deploy15/export-gen2-25397/manifest.json'))
HERE = Path(__file__).resolve().parent
SR_STORE = 16000

BINS = {
    'short': {'lo': 1.0, 'hi': 3.0, 'stores': ['ami-ihm-validation'], 'min_words': 3},
    'mid': {'lo': 4.0, 'hi': 6.0, 'stores': ['librispeech-dev-clean', 'voxpopuli-dev', 'ami-ihm-validation'],
            'min_words': 5},
    'long': {'lo': 7.0, 'hi': 15.0, 'stores': ['librispeech-dev-clean', 'peoples-dev', 'voxpopuli-dev'],
             'min_words': 8},
}
DEV_STORES = sorted({s for b in BINS.values() for s in b['stores']})


def normalize_text(text):
    """Same as experiments/stt_train_15x5/common.py normalize_text."""
    text = text.lower().replace('-', ' ')
    text = re.sub(r"[^a-z' ]", ' ', text)
    text = re.sub(r"\s+'|'\s+", ' ', f' {text} ')
    return re.sub(r'\s+', ' ', text).strip()


def db(x):
    return 20.0 * math.log10(max(x, 1e-12))


def level_stats(x):
    """x: float32 in [-1, 1] at 16 kHz. Active-speech level (frames within 25 dB
    of the 95th-percentile frame), speech start/end (first/last frame within
    25 dB of the active level), peak."""
    hop = SR_STORE // 100
    n = len(x) // hop
    fr = x[:n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(fr * fr, axis=1) + 1e-20)
    lv = 20 * np.log10(rms)
    p95 = float(np.percentile(lv, 95))
    act = lv > p95 - 25.0
    active_rms = float(np.sqrt(np.mean((fr[act] ** 2)))) if act.any() else 0.0
    thr = db(active_rms) - 25.0
    on = np.nonzero(lv > thr)[0]
    s0 = (int(on[0]) * hop) if len(on) else 0
    s1 = (int(on[-1]) + 1) * hop if len(on) else len(x)
    return {'active_dbfs': db(active_rms), 'peak_dbfs': db(float(np.max(np.abs(x))) if len(x) else 0.0),
            'speech_start': s0, 'speech_end': min(s1, len(x)), 'active_frac': float(act.mean()) if n else 0.0}


def load_store(name):
    d = json.loads((STORES / name / 'index.json').read_text())
    audio = np.memmap(STORES / name / 'audio.bin', dtype='<i2', mode='r')
    return d, audio


def calibration_set():
    try:
        m = json.loads(CALIB.read_text())
        return {(c['store'], int(c['index'])) for c in m['calibration_stores']['clips']}
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f'cannot read calibration clip list {CALIB}: {exc}')


def fade(n, rate):
    k = max(1, int(0.010 * rate))
    w = np.ones(n, dtype=np.float64)
    r = 0.5 - 0.5 * np.cos(np.linspace(0, math.pi, k))
    w[:k] = r
    w[-k:] = np.minimum(w[-k:], r[::-1])
    return w


def predict_segments(clips, preroll=0.3, end_sil=0.6, min_seg=4.0, cap=20.0):
    """Simplified deployed segmenter on clip speech intervals (ignores pauses
    inside clips and the noise threshold): phrase opens preroll before speech,
    closes at max(speech_end + end_sil, open + min_seg) unless the next clip's
    speech starts first; 20 s cap -> cut. Returns list of lists of clip ids."""
    iv = [(c['speech_start_s'], c['speech_end_s'], c['i']) for c in clips]
    out, i = [], 0
    while i < len(iv):
        op = iv[i][0] - preroll
        members = [iv[i][2]]
        end = iv[i][1]
        j = i
        while True:
            close = max(end + end_sil, op + min_seg)
            if close - op > cap:
                break
            if j + 1 < len(iv) and iv[j + 1][0] - preroll < close:
                j += 1
                end = iv[j][1]
                members.append(iv[j][2])
                continue
            break
        out.append(members)
        i = j + 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=HERE / 'playlist')
    ap.add_argument('--seconds', type=float, default=240.0, help='target total WAV length')
    ap.add_argument('--seed', type=int, default=20261009, help='bin order + gap lengths')
    ap.add_argument('--long-only', action='store_true',
                    help='one bin of 12-30 s single utterances (phrase-cap tests)')
    ap.add_argument('--rate', type=int, choices=[16000, 48000], default=48000)
    ap.add_argument('--lead', type=float, default=6.0)
    ap.add_argument('--tail', type=float, default=2.5)
    ap.add_argument('--gap-min', type=float, default=1.5)
    ap.add_argument('--gap-max', type=float, default=2.5)
    ap.add_argument('--level-dbfs', type=float, default=-20.0, help='active-speech level')
    ap.add_argument('--peak-dbfs', type=float, default=-1.0)
    ap.add_argument('--max-backoff-db', type=float, default=4.0)
    ap.add_argument('--max-gain-db', type=float, default=20.0,
                    help='skip clips recorded so quietly that reaching the level would lift their noise floor more')
    a = ap.parse_args()

    global BINS, DEV_STORES
    if a.long_only:
        BINS = {'long': {'lo': 12.0, 'hi': 30.0, 'stores': ['librispeech-dev-clean', 'peoples-dev', 'voxpopuli-dev'],
                         'min_words': 20}}
        DEV_STORES = sorted({s for b in BINS.values() for s in b['stores']})
    first = next(iter(BINS))
    calib = calibration_set()
    stores = {n: load_store(n) for n in DEV_STORES}
    # candidate iterators per (bin, store), evaluate.py order
    cands = {}
    for bname, b in BINS.items():
        for s in b['stores']:
            idx, _ = stores[s]
            order = list(range(len(idx['lengths'])))
            random.Random(0).shuffle(order)
            cands[(bname, s)] = iter([i for i in order
                                      if b['lo'] <= idx['lengths'][i] / SR_STORE <= b['hi']
                                      and (s, i) not in calib
                                      and len(normalize_text(idx['texts'][i]).split()) >= b['min_words']])
    rot = {b: 0 for b in BINS}
    skipped = {'level': 0}

    def take(bname):
        b = BINS[bname]
        for _ in range(10000):
            s = b['stores'][rot[bname] % len(b['stores'])]
            rot[bname] += 1
            try:
                i = next(cands[(bname, s)])
            except StopIteration:
                continue
            idx, audio = stores[s]
            off, n = idx['offsets'][i], idx['lengths'][i]
            x = np.asarray(audio[off:off + n], dtype=np.float32) / 32768.0
            st = level_stats(x)
            gain_db = a.level_dbfs - st['active_dbfs']
            backoff = max(0.0, st['peak_dbfs'] + gain_db - a.peak_dbfs)
            if backoff > a.max_backoff_db or gain_db > a.max_gain_db or not math.isfinite(gain_db):
                skipped['level'] += 1
                rot[bname] -= 1  # retry the same store next
                continue
            return {'store': s, 'item': i, 'bin': bname, 'x16': x, 'gain_db': gain_db - backoff,
                    'backoff_db': backoff, 'stats': st, 'text': idx['texts'][i]}
        raise SystemExit(f'ran out of candidates for bin {bname}')

    rng = random.Random(a.seed)
    picked = {b: [] for b in BINS}
    total = a.lead + a.tail
    while True:
        trial = [take(b) for b in BINS]
        add = sum(len(c['x16']) / SR_STORE for c in trial) + 3 * (a.gap_min + a.gap_max) / 2
        if picked[first] and total + add > a.seconds + 4.0:
            break
        for c in trial:
            picked[c['bin']].append(c)
        total += add
        if total >= a.seconds - 4.0:
            break
    n_per = len(picked[first])
    # seeded interleave: no more than two clips of the same bin in a row
    seq = None
    for _ in range(10000):
        cand = [b for b in BINS for _ in range(n_per)]
        rng.shuffle(cand)
        if len(BINS) == 1 or all(not (cand[k] == cand[k + 1] == cand[k + 2]) for k in range(len(cand) - 2)):
            seq = cand
            break
    seq = seq or cand
    pools = {b: list(picked[b]) for b in BINS}
    ordered = [pools[b].pop(0) for b in seq]
    gaps = [round(rng.uniform(a.gap_min, a.gap_max), 2) for _ in ordered[:-1]] + [0.0]

    rate = a.rate
    up = rate // SR_STORE
    parts = [np.zeros(int(round(a.lead * rate)), dtype=np.float64)]
    pos = len(parts[0])
    clips = []
    for k, (c, g) in enumerate(zip(ordered, gaps)):
        x = c['x16'].astype(np.float64) * (10 ** (c['gain_db'] / 20))
        y = resample_poly(x, up, 1) if up > 1 else x
        y = y * fade(len(y), rate)
        pk = float(np.max(np.abs(y)))
        lim = 10 ** (a.peak_dbfs / 20)
        if pk > lim:  # inter-sample overshoot after resampling
            y *= lim / pk
            c['gain_db'] += db(lim / pk)
        st = c['stats']
        start = pos
        end = pos + len(y)
        clips.append({
            'i': k, 'store': c['store'], 'item': c['item'], 'bin': c['bin'],
            'dur_s': round(len(y) / rate, 4),
            'start_s': round(start / rate, 4), 'end_s': round(end / rate, 4),
            'speech_start_s': round((start + st['speech_start'] * up) / rate, 4),
            'speech_end_s': round((start + st['speech_end'] * up) / rate, 4),
            'gap_after_s': g,
            'gain_db': round(c['gain_db'], 2), 'backoff_db': round(c['backoff_db'], 2),
            'src_active_dbfs': round(st['active_dbfs'], 2), 'src_peak_dbfs': round(st['peak_dbfs'], 2),
            'text': c['text'], 'text_norm': normalize_text(c['text']),
            'words': len(normalize_text(c['text']).split()),
        })
        parts.append(y)
        pos = end
        if g:
            z = np.zeros(int(round(g * rate)), dtype=np.float64)
            parts.append(z)
            pos += len(z)
    parts.append(np.zeros(int(round(a.tail * rate)), dtype=np.float64))
    sig = np.concatenate(parts)
    pcm = np.clip(np.round(sig * 32767.0), -32768, 32767).astype('<i2')

    a.out.mkdir(parents=True, exist_ok=True)
    wav = a.out / 'playlist.wav'
    import wave
    with wave.open(str(wav), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    sha = hashlib.sha256(wav.read_bytes()).hexdigest()

    comp = {}
    for b in BINS:
        cs = [c for c in clips if c['bin'] == b]
        comp[b] = {'clips': len(cs), 'speech_seconds': round(sum(c['dur_s'] for c in cs), 2),
                   'words': sum(c['words'] for c in cs),
                   'min_s': round(min(c['dur_s'] for c in cs), 2), 'max_s': round(max(c['dur_s'] for c in cs), 2),
                   'stores': {s: sum(1 for c in cs if c['store'] == s) for s in BINS[b]['stores']}}
    segs = predict_segments(clips)
    pred = {'phrases': len(segs), 'multi_clip_phrases': sum(1 for s in segs if len(s) > 1),
            'clips_merged_into_previous': sum(len(s) - 1 for s in segs),
            'note': 'simplified deployed segmenter (4 s floor, 600 ms end silence, 300 ms pre-roll); '
                    'ignores pauses inside clips, so long clips may still split on device'}
    manifest = {
        'created': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'wav': str(wav), 'wav_sha256': sha,
        'sample_rate': rate, 'duration_s': round(len(pcm) / rate, 4), 'seed': a.seed,
        'store_order': 'random.Random(0).shuffle(range(n)) per store (evaluate.py _subset order)',
        'lead_s': a.lead, 'tail_s': a.tail, 'gap_range_s': [a.gap_min, a.gap_max],
        'level_dbfs': a.level_dbfs, 'peak_dbfs': a.peak_dbfs, 'max_backoff_db': a.max_backoff_db,
        'max_gain_db': a.max_gain_db,
        'bins': BINS, 'excluded': 'int8 calibration clips from ' + str(CALIB),
        'skipped_for_level': skipped['level'],
        'composition': comp, 'predicted_segmentation_4s_floor': pred,
        'reference_words': sum(c['words'] for c in clips),
        'clips': clips,
    }
    (a.out / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    print(f'wrote {wav} ({manifest["duration_s"]:.1f} s, {rate} Hz, sha256 {sha[:16]})')
    print(f'wrote {a.out / "manifest.json"}  clips={len(clips)} reference_words={manifest["reference_words"]} '
          f'skipped_for_level={skipped["level"]}')
    for b, v in comp.items():
        print(f'  {b:5s}: {v["clips"]} clips, {v["speech_seconds"]:.1f} s ({v["min_s"]}-{v["max_s"]} s), '
              f'{v["words"]} words, stores {v["stores"]}')
    print(f'  predicted phrases (4 s floor): {pred["phrases"]}, multi-clip {pred["multi_clip_phrases"]}, '
          f'clips merged into a previous phrase {pred["clips_merged_into_previous"]}')


if __name__ == '__main__':
    main()
