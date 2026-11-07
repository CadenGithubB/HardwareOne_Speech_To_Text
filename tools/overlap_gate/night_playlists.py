"""Build the overnight acoustic-playback playlists for the device overlap-gate A/B.

Clips (all from held-out or evaluation sources, never from the gate's training data):
  ami-val   seeded AMI validation distant-mic utterance windows (1.5-15 s)   label from frozen labels
  ami-test  seeded AMI test distant-mic windows                              label from frozen labels
  real32    the 32 real two-speaker AMI validation pairs, distant mic         label from annotation
  syn-two   seeded synthetic two-speaker qualification mixtures               label from geometry
  syn-ord / syn-quiet  synthetic qualification single-speaker, ordinary and -18 dB
  ls-test   seeded LibriSpeech test-clean single-speaker utterances           label: no overlap
  noise     DEMAND test noise, 10 s                                           label: no speech

Levels: speech clips are scaled to -26 dBFS RMS over the clip (syn-quiet to -44 dBFS, noise to
-40 dBFS), peak-limited to -1 dBFS; the gain is recorded. Each clip is followed by 2.5 s of
silence so the device closes one segment per clip. Clips are shuffled (seeded) into blocks of
about 12 minutes; every block is a 16 kHz mono WAV plus a manifest with each clip's exact start
and end sample in the WAV, its label, reference text and gain.

--set train builds replay *training* material instead (night 2), drawn only from the gate's training
splits so night 1's validation and test blocks stay clean:
  ami-train   seeded AMI train distant-mic windows (1.5-15 s), speakers outside the exclusions
  one-train   one non-AMI training-store utterance, cropped to 2-8 s       label: one speaker throughout
  two-train   two different non-AMI training-store crops (2-6 s each), the second starting 0.3 s to
              the first's end and scaled -6..+6 dB relative, summed in time; counts from the spans
  noise-train DEMAND/MUSAN training noise, 6 s                             label: no speech
Non-AMI stores are the G2b/G2c training stores; voxpopuli-train speakers that also appear in
voxpopuli-validation are excluded, as in G2b.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tools/stt_train_15x5'))
from overlap_gate import labels, scorer  # noqa: E402
from overlap_gate.g0_extract import intervals_to_labels  # noqa: E402

SR = 16000
GAP_S, LEAD_S = 2.5, 3.0
BLOCK_S = 12 * 60
SEED = 20261106
STORES = ROOT / 'private/training-baseline-20261103/corrected/stores'
R3 = ROOT / 'private/training-track/compact16k-loss-round3'
LABELS = ROOT / 'private/training-track/overlap-gate'
COUNTS = dict(ami_val=600, ami_test=400, syn_two=64, syn_ord=32, syn_quiet=32, ls_test=100, noise=10)
TARGET_DBFS = {'syn-quiet': -44.0, 'noise': -40.0}
DEFAULT_DBFS = -26.0


class Store:
    def __init__(self, name):
        d = STORES / name
        self.index = json.loads((d / 'index.json').read_text())
        self.audio = np.memmap(d / 'audio.bin', '<i2', 'r')
        from diagnostics import effective_ids
        self.ids = effective_ids(d, self.index)

    def pcm(self, i):
        o, n = self.index['offsets'][i], self.index['lengths'][i]
        return np.asarray(self.audio[o:o + n]).astype(np.float32) / 32768


def level(x, category):
    target = TARGET_DBFS.get(category, DEFAULT_DBFS)
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) + 1e-9
    gain = 10 ** (target / 20) / rms
    peak = float(np.max(np.abs(x))) * gain
    if peak > 10 ** (-1 / 20):
        gain *= 10 ** (-1 / 20) / peak
    return np.clip(x * gain, -1, 1), 20 * math.log10(gain)


def label_from_counts(counts, collar):
    return bool(scorer.segment_label(counts, collar))


def clips(rng):
    out = []
    for split, n, cat in (('validation', COUNTS['ami_val'], 'ami-val'), ('test', COUNTS['ami_test'], 'ami-test')):
        store = Store(f'ami-sdm-{split}')
        recs = [r for r in json.loads((LABELS / f'labels-{split}.json').read_text())['records']
                if r.get('store_sdm') is not None and 1.5 <= r['end'] - r['begin'] <= 15]
        rng.shuffle(recs)
        for r in recs[:n]:
            counts = labels.expand(r['counts'])
            collar = labels.expand(r['collar']).astype(bool)
            out.append(dict(category=cat, source=f"{split}:{r['audio_id']}", pcm=store.pcm(r['store_sdm']), label=label_from_counts(counts, collar),
                            overlap_frames=int(r['overlap_frames']), reference=r['text'], counts=r['counts'], collar=r['collar']))
    suite = json.loads((R3 / 'eval-suite.json').read_text())
    by = {}
    for c in suite['cases']:
        if c['partition'] == 'qualification' or c['condition'] == 'real-overlap':
            by.setdefault(c['condition'], []).append(c)
    for cond, cat, n in (('two-speakers', 'syn-two', COUNTS['syn_two']), ('ordinary', 'syn-ord', COUNTS['syn_ord']),
                         ('quiet-minus18', 'syn-quiet', COUNTS['syn_quiet']), ('real-overlap', 'real32', 32)):
        cases = list(by[cond])
        rng.shuffle(cases)
        for c in cases[:n]:
            path = c['mixture']['pcm'] if c['mixture']['pcm'].startswith('/') else str(R3 / c['mixture']['pcm'])
            pcm = np.fromfile(path, '<i2').astype(np.float32) / 32768
            seconds = pcm.size / SR
            if cond == 'real-overlap':
                a, b = c['annotation']['utterances']
                intervals = [(a['speaker'], 0.0, a['end'] - a['start']), (b['speaker'], b['start'] - a['start'], b['end'] - a['start'])]
            elif cond == 'two-speakers':
                s0, s1 = c['sources']
                intervals = [('s0', 0.0, s0['length'] / SR), ('s1', c['offset_samples'] / SR, (c['offset_samples'] + s1['length']) / SR)]
            else:
                intervals = [('s0', 0.0, c['sources'][0]['length'] / SR)]
            counts, collar = intervals_to_labels(intervals, seconds)
            ref = ' '.join(c['references'].values()) if isinstance(c['references'], dict) else ' '.join(c['references'])
            out.append(dict(category=cat, source=f"suite:{c['id']}", pcm=pcm, label=label_from_counts(counts, collar),
                            overlap_frames=int(np.sum((counts >= 2) & ~collar)), reference=ref,
                            counts=labels.runs(counts), collar=labels.runs(collar.astype(np.int8)),
                            intervals=[[s, round(b, 4), round(e, 4)] for s, b, e in intervals]))
    ls = Store('librispeech-test-clean')
    ids = list(ls.ids)
    rng.shuffle(ids)
    for i in ids[:COUNTS['ls_test']]:
        pcm = ls.pcm(i)
        out.append(dict(category='ls-test', source=f'librispeech-test-clean:{i}', pcm=pcm, label=False, overlap_frames=0,
                        reference=ls.index['texts'][i], speaker=ls.index['speakers'][i]))
    noise = Store('demand-noise-test')
    ids = list(noise.ids)
    rng.shuffle(ids)
    for i in ids[:COUNTS['noise']]:
        pcm = noise.pcm(i)[:10 * SR]
        out.append(dict(category='noise', source=f'demand-noise-test:{i}', pcm=pcm, label=False, overlap_frames=0, reference=''))
    return out


TRAIN_COUNTS = dict(ami_train=380, one_train=260, two_train=240, noise_train=20)
TRAIN_SEED = 20261107
NON_AMI = ('librispeech-train-clean-100', 'voxpopuli-train', 'commonvoice-en-train', 'peoples-clean-train')


def _span_labels(spans, n_frames):
    """10 ms counts for active spans [(start_frame, end_frame)], collar +-20 frames at every span edge."""
    counts = np.zeros(n_frames, np.int8)
    collar = np.zeros(n_frames, np.int8)
    for a, b in spans:
        counts[a:b] += 1
        for e in (a, b):
            collar[max(0, e - 20):min(n_frames, e + 20)] = 1
    return counts, collar


def train_clips(rng):
    out = []
    store = Store('ami-sdm-train')
    excluded = {'FIE038', 'MIO036'}
    recs = [r for r in json.loads((LABELS / 'labels-train.json').read_text())['records']
            if r.get('store_sdm') is not None and r['speaker'] not in excluded and 1.5 <= r['end'] - r['begin'] <= 15]
    rng.shuffle(recs)
    for r in recs[:TRAIN_COUNTS['ami_train']]:
        counts = labels.expand(r['counts'])
        collar = labels.expand(r['collar']).astype(bool)
        out.append(dict(category='ami-train', source=f"train:{r['audio_id']}", pcm=store.pcm(r['store_sdm']), label=label_from_counts(counts, collar),
                        overlap_frames=int(r['overlap_frames']), reference=r['text'], counts=r['counts'], collar=r['collar']))
    vox_excluded = set(json.loads((LABELS / 'phase3' / 'g2b-voxpopuli-exclusions.json').read_text())['excluded_speakers'])
    pools = []
    for name in NON_AMI:
        st = Store(name)
        ids = [i for i in st.ids if not (name == 'voxpopuli-train' and st.index['speakers'][i] in vox_excluded)
               and st.index['lengths'][i] >= 2 * SR]
        pools.append((name, st, ids))

    def crop(lo, hi):
        name, st, ids = pools[rng.randrange(len(pools))]
        i = rng.choice(ids)
        x = st.pcm(i)
        n = min(x.size, int(rng.uniform(lo, hi) * SR))
        s0 = rng.randrange(x.size - n + 1)
        return x[s0:s0 + n], f'{name}:{i}:{s0}:{n}', st.index['speakers'][i]

    for _ in range(TRAIN_COUNTS['one_train']):
        x, src, spk = crop(2, 8)
        n = (x.size + 159) // 160
        counts, collar = _span_labels([(0, n)], n)
        out.append(dict(category='one-train', source=src, pcm=x, label=False, overlap_frames=0, reference='',
                        counts=labels.runs(counts), collar=labels.runs(collar)))
    for _ in range(TRAIN_COUNTS['two_train']):
        while True:
            (a, sa, ka), (b, sb, kb) = crop(2, 6), crop(2, 6)
            if ka != kb:
                break
        off = int(rng.uniform(0.3, a.size / SR) * SR)
        rel = 10 ** (rng.uniform(-6, 6) / 20)
        mix = np.zeros(max(a.size, off + b.size), np.float32)
        mix[:a.size] += a / (np.sqrt(np.mean(a ** 2)) + 1e-9)
        mix[off:off + b.size] += rel * b / (np.sqrt(np.mean(b ** 2)) + 1e-9)
        n = (mix.size + 159) // 160
        spans = [(0, (a.size + 159) // 160), (off // 160, (off + b.size + 159) // 160)]
        counts, collar = _span_labels(spans, n)
        out.append(dict(category='two-train', source=f'{sa}+{sb}@{off}', pcm=mix, label=bool(np.any((counts >= 2) & (collar == 0))),
                        overlap_frames=int(np.sum((counts >= 2) & (collar == 0))), reference='', relative_db=round(20 * math.log10(rel), 2),
                        counts=labels.runs(counts), collar=labels.runs(collar)))
    for name in ('demand-noise-train', 'musan-noise'):
        st = Store(name)
        ids = [i for i in st.ids if st.index['lengths'][i] >= 6 * SR]
        rng.shuffle(ids)
        for i in ids[:TRAIN_COUNTS['noise_train'] // 2]:
            out.append(dict(category='noise-train', source=f'{name}:{i}', pcm=st.pcm(i)[:6 * SR], label=False, overlap_frames=0, reference='',
                            counts=[[0, 600, 0]], collar=[]))
    return out


def write_wav(path, x):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype('<i2').tobytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', type=Path, default=Path('/Volumes/Audiodrive/stt/overlap-gate/night1'))
    ap.add_argument('--manifests', type=Path, default=LABELS / 'phase4/night1')
    ap.add_argument('--set', choices=('eval', 'train'), default='eval')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    args.manifests.mkdir(parents=True, exist_ok=True)
    rng = random.Random(TRAIN_SEED if args.set == 'train' else SEED)
    allc = train_clips(rng) if args.set == 'train' else clips(rng)
    rng.shuffle(allc)
    blocks, cur, cur_s = [], [], LEAD_S
    for c in allc:
        d = c['pcm'].size / SR + GAP_S
        if cur and cur_s + d > BLOCK_S:
            blocks.append(cur)
            cur, cur_s = [], LEAD_S
        cur.append(c)
        cur_s += d
    if cur:
        blocks.append(cur)
    summary = []
    for b, block in enumerate(blocks, 1):
        parts = [np.zeros(int(LEAD_S * SR), np.float32)]
        pos = int(LEAD_S * SR)
        entries = []
        for k, c in enumerate(block):
            x, gain_db = level(c['pcm'], c['category'])
            entries.append(dict({key: v for key, v in c.items() if key != 'pcm'}, index=k, start_sample=pos, end_sample=pos + x.size,
                                seconds=round(x.size / SR, 3), gain_db=round(gain_db, 2)))
            parts.append(x)
            parts.append(np.zeros(int(GAP_S * SR), np.float32))
            pos += x.size + int(GAP_S * SR)
        audio = np.concatenate(parts)
        wav = args.out / f'block{b:02d}.wav'
        write_wav(wav, audio)
        sha = hashlib.sha256(wav.read_bytes()).hexdigest()
        manifest = dict(block=b, wav=str(wav), wav_sha256=sha, sample_rate=SR, seconds=round(audio.size / SR, 2), lead_s=LEAD_S, gap_s=GAP_S,
                        seed=TRAIN_SEED if args.set == 'train' else SEED, set=args.set, clips=entries)
        (args.manifests / f'block{b:02d}.json').write_text(json.dumps(manifest) + '\n')
        cats = {}
        for e in entries:
            cats[e['category']] = cats.get(e['category'], 0) + 1
        summary.append(dict(block=b, seconds=manifest['seconds'], clips=len(entries), positives=sum(e['label'] for e in entries), categories=cats))
    (args.manifests / 'playlists.json').write_text(json.dumps(dict(set=args.set, blocks=summary, counts=TRAIN_COUNTS if args.set == 'train' else COUNTS, levels=dict(default=DEFAULT_DBFS, **TARGET_DBFS),
                                                                   scope='acoustic playback through the Mac mini speaker at the bench volume into the P4 microphone'), indent=1) + '\n')
    total = sum(s['seconds'] for s in summary)
    print(json.dumps(dict(blocks=len(summary), clips=sum(s['clips'] for s in summary), positives=sum(s['positives'] for s in summary),
                          hours=round(total / 3600, 2)), indent=1))


if __name__ == '__main__':
    main()
