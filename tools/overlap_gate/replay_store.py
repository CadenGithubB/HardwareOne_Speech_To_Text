"""Labelled replay store from overnight run 1: the P4's saved segments with frame labels from the playlist.

Every final segment the P4 saved (both arms) is aligned to the block WAV: the run's clock offset from
segment/clip time matching (night_rescore.align), refined by the median cross-correlation lag of up
to 15 segments per run. Each 10 ms frame then takes the count of the playlist clip under it (0 between
clips) and the clip's collar; frames within 200 ms of any clip edge are collar too (alignment error,
room reverberation tail). The run lag is the centre of the largest cluster of per-segment lags;
segments whose own lag is more than 40 ms from it are left out.

Split by block, seeded, before any training: 8 train, 3 validation, 3 test blocks. Both arms of a
block stay together, so no clip is heard in two splits. Only replayed AMI-validation clips may train:
AMI test, the LibriSpeech test clips, the synthetic qualification suite, the 32 saved-microphone
windows and the test noise are frozen evaluation material. AMI-validation clips used in training are
listed so the AMI validation subsample can drop them.

Writes features to /Volumes/Audiodrive/stt/overlap-gate/replay1/replay.f16 (float16 [frames, 64]) and
replay.json (items: key, run, block, split, trainable, frames, start, counts and collar as runs) and
the split to phase5/replay-split.json.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overlap_gate import labels  # noqa: E402
from overlap_gate import g2_common as g2  # noqa: E402
from overlap_gate import night_rescore as nr  # noqa: E402

OUT = Path('/Volumes/Audiodrive/stt/overlap-gate/replay1')
SPLIT_SEED = 20261106
TRAINABLE = ('ami-val',)
# Night 2 (6 Nov 2026, daytime session): training-split material only, every block and category trains.
NIGHT2 = dict(out=Path('/Volumes/Audiodrive/stt/overlap-gate/replay2'), runs=nr.P4 / 'night2-runs', card=nr.P4 / 'night2-card' / 'pcm',
              manifests=nr.P4 / 'night2', trainable=('ami-train', 'one-train', 'two-train', 'noise-train'))
EDGE_COLLAR = 20


def split_blocks():
    blocks = list(range(1, 15))
    random.Random(SPLIT_SEED).shuffle(blocks)
    return dict(validation=sorted(blocks[:3]), test=sorted(blocks[3:6]), train=sorted(blocks[6:]))


def runs_to_array(runs, n):
    a = np.zeros(n, np.int8)
    for f0, f1, v in runs:
        a[f0:f1] = v
    return a


def array_to_runs(a):
    edges = np.flatnonzero(np.diff(a)) + 1
    starts = np.concatenate([[0], edges])
    ends = np.concatenate([edges, [a.size]])
    return [[int(s), int(e), int(a[s])] for s, e in zip(starts, ends)]


def xcorr_lag(src, pcm, a0, W=8000):
    lo = max(0, a0 - W)
    ref = src[lo:a0 + pcm.size + W]
    if ref.size < pcm.size or a0 + pcm.size + W <= 0:
        return 10 ** 9                    # segment outside the playlist (stray sound): never labelled
    n = 1 << int(np.ceil(np.log2(ref.size + pcm.size)))
    c = np.fft.irfft(np.fft.rfft(ref, n) * np.conj(np.fft.rfft(pcm, n)), n)
    return int(np.argmax(c[:ref.size])) - (a0 - lo)


def main():
    global OUT, TRAINABLE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--night', type=int, choices=(1, 2), default=1)
    night = ap.parse_args().night
    runs_dir, card, manifests = nr.RUNS, nr.CARD, nr.P4 / 'night1'
    if night == 2:
        OUT, TRAINABLE = NIGHT2['out'], NIGHT2['trainable']
        runs_dir, card, manifests = NIGHT2['runs'], NIGHT2['card'], NIGHT2['manifests']
    OUT.mkdir(parents=True, exist_ok=True)
    events = list(nr.runs(runs_dir))
    split = split_blocks() if night == 1 else dict(train=sorted({e['block'] for e in events}), validation=[], test=[])
    split_of = {b: s for s, bs in split.items() for b in bs}
    fe = g2.RawFrontend()
    items, chunks, start = {}, [], 0
    trained_ami_val = set()
    lags = {}
    for e in events:
        lines = (runs_dir / 'runs' / e['run'] / 'serial.log').read_text(errors='replace').splitlines()
        segs = []
        for l in lines:
            i = l.find('STT_PCM ')
            if i >= 0:
                try:
                    j = json.loads(l[i + 8:])
                except json.JSONDecodeError:
                    continue
                if j['ok']:
                    segs.append(dict(run=e['run'], seq=j['stream_sequence'], start_sample=j['start_sample'], samples=j['samples']))
        m = json.loads((manifests / f"block{e['block']:02d}.json").read_text())
        with wave.open(m['wav']) as w:
            src = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(np.float64)
        aligned = nr.align(segs, [e], manifests)
        if not aligned:
            continue
        off = aligned[0]['offset']
        # Lag of every segment against the source; the run's lag is the centre of the largest cluster
        # (lags within 20 ms of each other). Segments more than 40 ms from it keep no labels.
        own = {x['seq']: xcorr_lag(src, np.fromfile(card / e['folder'] / f"s{x['seq']:06d}.pcm", dtype='<i2').astype(np.float64),
                                   x['start_sample'] - off) for x in segs}
        v = np.array(list(own.values()))
        support = np.array([np.sum(np.abs(v - a) <= 320) for a in v])
        centre = v[support == support.max()]
        lag = int(np.median(v[np.abs(v - np.median(centre)) <= 320]))
        within = float(np.mean(np.abs(v - lag) <= 320))
        lags[e['run']] = dict(offset=off, lag=lag, segments=int(v.size), within_20ms=within,
                              dropped_over_40ms=int(np.sum(np.abs(v - lag) > 640)))
        segs = [x for x in segs if abs(own[x['seq']] - lag) <= 640]
        clips = m['clips']
        for x in segs:
            pcm = np.fromfile(card / e['folder'] / f"s{x['seq']:06d}.pcm", dtype='<i2')
            if pcm.size != x['samples']:
                continue
            feats = fe(pcm.astype(np.float32) / 32768).numpy()            # [64, T]
            T = feats.shape[1]
            w0 = x['start_sample'] - off + lag                             # WAV sample of segment sample 0
            counts = np.zeros(T, np.int8)
            collar = np.zeros(T, bool)
            cats, trainable = set(), True
            for c in clips:
                c0 = (c['start_sample'] - w0) / g2.HOP                     # clip start in segment frames
                c1 = (c['end_sample'] - w0) / g2.HOP
                if c1 <= 0 or c0 >= T:
                    continue
                cats.add(c['category'])
                if c['category'] not in TRAINABLE:
                    trainable = False
                elif split_of[e['block']] == 'train' and c['category'] == 'ami-val':
                    trained_ami_val.add(c['source'].split(':', 1)[1])
                k0 = int(round(c0))
                n = int(round(c1)) - k0
                # LibriSpeech test clips are one speaker throughout; test noise has none.
                default = 1 if c['category'] in ('ls-test', 'one-train') else 0
                cc = runs_to_array(c.get('counts', [[0, n, default]]), n)
                kc = runs_to_array(c.get('collar', []), n).astype(bool)
                lo, hi = max(0, k0), min(T, k0 + n)
                counts[lo:hi] = cc[lo - k0:hi - k0]
                collar[lo:hi] = kc[lo - k0:hi - k0]
                for edge in (k0, k0 + n):
                    collar[max(0, edge - EDGE_COLLAR):max(0, min(T, edge + EDGE_COLLAR))] = True
            if not cats:
                continue
            key = f"{e['run']}:{x['seq']}"
            items[key] = dict(run=e['run'], arm=e['arm'], block=e['block'], split=split_of[e['block']], categories=sorted(cats),
                              trainable=bool(trainable and split_of[e['block']] == 'train'), frames=T, start=start,
                              counts=array_to_runs(counts), collar=array_to_runs(collar.astype(np.int8)))
            chunks.append(feats.T.astype(np.float16))
            start += T
        print(e['run'], 'lag_ms', lag / 16, 'within_20ms', round(within, 3), 'segments', sum(1 for v in items.values() if v['run'] == e['run']), flush=True)
    data = np.concatenate(chunks)
    data.tofile(OUT / 'replay.f16')
    (OUT / 'replay.json').write_text(json.dumps(dict(frames=int(data.shape[0]), items=items)) + '\n')
    by = {}
    for v in items.values():
        k = (v['split'], v['trainable'])
        by.setdefault(f'{k[0]}/{"trainable" if k[1] else "eval-only"}', 0)
        by[f'{k[0]}/{"trainable" if k[1] else "eval-only"}'] += 1
    (g2.LABELS / 'phase5').mkdir(exist_ok=True)
    split_file = g2.LABELS / 'phase5' / ('replay-split.json' if night == 1 else 'replay2-split.json')
    split_file.write_text(json.dumps(dict(
        seed=SPLIT_SEED, blocks=split, trainable_categories=list(TRAINABLE), items_by_split=by, frames=int(data.shape[0]),
        ami_validation_ids_in_training=sorted(trained_ami_val), alignment=lags), indent=1) + '\n')
    print(json.dumps(dict(blocks=split, items=by, frames=int(data.shape[0]), ami_val_ids_in_training=len(trained_ami_val))))


if __name__ == '__main__':
    main()
