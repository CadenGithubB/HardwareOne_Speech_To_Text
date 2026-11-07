"""G1 gate: dispersion of the existing speaker-trunk frame vectors.

The production speaker path already computes, for one ~3 s crop per final segment, a trunk
output of 75 frame vectors (40 ms each, 128 channels) and SAP attention weights, then pools them
into one embedding. G1 asks whether those frame vectors scatter in a way that betrays two voices.
No new weights are learned by the trunk; the only fitted quantity is a 5-parameter logistic
calibration (phase-two addendum) trained on an AMI *train* subsample, never on validation or test.

Per window (47,840 samples = the production centre-crop span, hop 16,000 samples), on
L2-normalized frame vectors x_t:
  eig    second-eigenvalue share lambda2 / (lambda1 + lambda2) of the frame covariance
  pair   mean pairwise cosine distance, 1 - ||mean_t x_t||^2
  split  two-means along the first principal component: cosine distance between the two centroid
         directions, times 2 * min(cluster share)
  att    normalized entropy of the SAP attention weights
Window statistics are spread onto the 10 ms label frames they cover (mean over covering windows).
Segments shorter than one window are repeat-padded exactly as the production frontend does.

Writes one .npz per panel (per-frame spread statistics plus labels), a window table for
calibration, and the frozen g1-protocol.json. Holds the shared evaluation lock while inferring.
Run from the repository root with the export venv python.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from overlap_gate import labels  # noqa: E402
from overlap_gate.g0_extract import R3, intervals_to_labels, read_pcm, sha  # noqa: E402

WINDOW = 47840
HOP = 16000
TRUNK_FRAMES = 75
STATS = ('eig', 'pair', 'split', 'att')
VALIDATION_SUBSAMPLE = 2000
VALIDATION_SEED = 20261105          # same windows as G0
TRAIN_SUBSAMPLE = 1500
TRAIN_SEED = 20261106
TRAIN_SPEAKER_EXCLUSIONS = ('FIE038', 'MIO036')


class Trunk:
    def __init__(self):
        prior = R3.parent / 'compact16k-round2'
        old = R3.parent / 'overlap-ab'
        sys.path[:0] = [str(R3), str(prior), str(old), str(old / 'deps'), str(ROOT / 'tools/stt_p4'), str(ROOT / 'tools/stt_p4/speaker')]
        os.environ.update(STT_ROOT='/Volumes/Audiodrive/stt', OMP_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        import torch
        from correct_p4_contract import arithmetic_hooks, TorchExecutor, load_native_graph
        import proto
        torch.set_num_threads(1)
        self.torch, self.proto = torch, proto
        self.native = ROOT / 'private/numerical-takeover/speaker.native'
        graph = load_native_graph(str(self.native))
        self.executor = TorchExecutor(graph=graph, device='cpu')
        self.hooks = arithmetic_hooks(graph)
        self.head = proto.load_model().eval()
        self.identity = dict(speaker_native_sha256=sha(self.native.read_bytes()),
                             head_sha256=sha(b''.join(k.encode() + v.detach().cpu().numpy().tobytes() for k, v in sorted(self.head.state_dict().items()))))
        from resources import acquire
        self.lock = acquire('evaluation')

    def frames_and_attention(self, pcm_i16: np.ndarray):
        audio = pcm_i16.astype(np.float32) / 32768
        f = self.proto.features(audio)
        length = f.shape[-1]
        f = f[..., self.torch.arange(300) % length] if length < 300 else f[..., :300]
        with self.torch.inference_mode():
            out = self.executor.forward(inputs=f, hooks=self.hooks)[0].float()      # [1, 128, 75]
            x = out.permute(0, 2, 1)                                                 # [1, 75, 128]
            h = self.torch.tanh(self.head.sap_linear(x))
            w = self.torch.softmax(self.torch.matmul(h, self.head.attention).squeeze(2), dim=1)
        return x[0].numpy().astype(np.float64), w[0].numpy().astype(np.float64)


def window_stats(frames: np.ndarray, attention: np.ndarray) -> dict:
    x = frames / np.maximum(np.linalg.norm(frames, axis=1, keepdims=True), 1e-9)
    mean = x.mean(axis=0)
    pair = float(np.clip(1.0 - mean @ mean, 0.0, 1.0))
    centred = x - mean
    cov = centred.T @ centred / max(1, x.shape[0] - 1)
    eigvals, eigvecs = np.linalg.eigh(cov)
    l1, l2 = float(eigvals[-1]), float(eigvals[-2])
    eig = float(l2 / (l1 + l2)) if l1 + l2 > 0 else 0.0
    proj = centred @ eigvecs[:, -1]
    a, b = x[proj >= 0], x[proj < 0]
    if len(a) and len(b):
        ca, cb = a.mean(axis=0), b.mean(axis=0)
        ca /= max(np.linalg.norm(ca), 1e-9)
        cb /= max(np.linalg.norm(cb), 1e-9)
        split = float(np.clip(1.0 - ca @ cb, 0.0, 2.0) * 2.0 * min(len(a), len(b)) / x.shape[0])
    else:
        split = 0.0
    w = np.clip(attention, 1e-12, 1.0)
    att = float(-(w * np.log(w)).sum() / np.log(len(w)))
    return dict(eig=eig, pair=pair, split=split, att=att)


class Writer:
    def __init__(self):
        self.rows, self.windows = [], []
        self.counts, self.collar = [], []
        self.stats = {s: [] for s in STATS}

    def add_case(self, trunk: Trunk, case_id, group, condition, pcm, counts, collar, **extra):
        n = counts.size
        spread = {s: np.zeros(n) for s in STATS}
        cover = np.zeros(n)
        starts = list(range(0, max(1, pcm.size - WINDOW + 1), HOP))
        if starts[-1] + WINDOW < pcm.size and pcm.size > WINDOW:
            starts.append(pcm.size - WINDOW)      # final window flush with the segment end
        for st in starts:
            piece = pcm[st:st + WINDOW]
            fr, at = trunk.frames_and_attention(piece)
            stats = window_stats(fr, at)
            f0 = st * 100 // labels.SAMPLE_RATE
            f1 = min(n, (st + min(WINDOW, piece.size)) * 100 // labels.SAMPLE_RATE)
            for s in STATS:
                spread[s][f0:f1] += stats[s]
            cover[f0:f1] += 1
            valid = ~collar[f0:f1]
            target = float(np.mean(counts[f0:f1][valid] >= 2)) if valid.any() else None
            self.windows.append(dict(case=case_id, start=int(st), target=target, valid_frames=int(valid.sum()), **stats))
        cover = np.maximum(cover, 1)
        self.rows.append(dict(id=case_id, group=group, condition=condition, frames=int(n), windows=len(starts), **extra))
        self.counts.append(counts.astype(np.int8))
        self.collar.append(collar.astype(bool))
        for s in STATS:
            self.stats[s].append((spread[s] / cover).astype(np.float32))

    def save(self, path: Path, **meta):
        lengths = np.array([r['frames'] for r in self.rows])
        offsets = np.concatenate([[0], np.cumsum(lengths)])
        np.savez_compressed(path.with_suffix('.npz'), counts=np.concatenate(self.counts), collar=np.concatenate(self.collar),
                            offsets=offsets, **{s: np.concatenate(self.stats[s]) for s in STATS})
        path.with_suffix('.json').write_text(json.dumps(dict(meta, cases=len(self.rows), rows=self.rows), indent=1) + '\n')
        path.with_name(path.name + '-windows.json').write_text(json.dumps(self.windows) + '\n')


def panel_synthetic(trunk, w):
    suite = json.loads((R3 / 'eval-suite.json').read_text())
    for c in suite['cases']:
        pcm = read_pcm(c['mixture']['pcm'] if c['mixture']['pcm'].startswith('/') else str(R3 / c['mixture']['pcm']))
        assert sha(pcm.tobytes()) == c['mixture']['sha256']
        seconds = pcm.size / labels.SAMPLE_RATE
        if c['condition'] == 'real-overlap':
            a, b = c['annotation']['utterances']
            intervals = [(a['speaker'], 0.0, a['end'] - a['start']), (b['speaker'], b['start'] - a['start'], b['end'] - a['start'])]
        elif c['condition'] == 'two-speakers':
            s0, s1 = c['sources']
            intervals = [('s0', 0.0, s0['length'] / labels.SAMPLE_RATE),
                         ('s1', c['offset_samples'] / labels.SAMPLE_RATE, (c['offset_samples'] + s1['length']) / labels.SAMPLE_RATE)]
        elif c['condition'].startswith('no-speech'):
            intervals = []
        else:
            intervals = [('s0', 0.0, c['sources'][0]['length'] / labels.SAMPLE_RATE)]
        counts, collar = intervals_to_labels(intervals, seconds)
        w.add_case(trunk, c['id'], c['group'], c['condition'], pcm, counts, collar, partition=c['partition'],
                   overlap_requested=c.get('overlap_requested'), second_db=c.get('second_db'))


def panel_microphone(trunk, w):
    sys.path.insert(0, str(ROOT / 'private/stt-detector-followup'))
    cwd = os.getcwd()
    os.chdir(ROOT)
    from cases import cases  # noqa: E402
    os.chdir(cwd)
    baseline = json.loads((ROOT / 'private/stt-loss-round3-review/baseline.json').read_text())
    clips = {c['id']: c for c in json.loads((ROOT / 'private/training-track/overlap-investigation/annotation-audit.json').read_text())}
    for c, b in zip(cases, baseline['cases']):
        pcm = np.asarray(c['pcm'], dtype='<i2')
        assert b['id'] == c['id'] and sha(pcm.tobytes()) == b['pcm_sha256']
        seconds = pcm.size / labels.SAMPLE_RATE
        if c['group'] == 'overlap':
            clip = clips[c['id']]
            start, end = clip['span']
            intervals = [(clip['target_speaker'], 0.0, end - start)]
            intervals += [(k['speaker_id'], max(0.0, k['begin_time'] - start), min(end - start, k['end_time'] - start)) for k in clip['competitors']]
            condition = 'real-overlap-clip'
        elif c['group'] == 'background':
            intervals, condition = [], 'no-speech'
        else:
            intervals, condition = [('s0', 0.0, seconds)], 'single-speaker'
        counts, collar = intervals_to_labels(intervals, seconds)
        w.add_case(trunk, c['id'], c['group'], condition, pcm, counts, collar)


def panel_store(trunk, w, split, seed, limit, exclude=()):
    frozen = json.loads((ROOT / f'private/training-track/overlap-gate/labels-{split}.json').read_text())
    store = ROOT / f'private/training-baseline-20261103/corrected/stores/ami-sdm-{split}'
    index = json.loads((store / 'index.json').read_text())
    audio = np.memmap(store / 'audio.bin', '<i2', 'r')
    eligible = [r for r in frozen['records'] if r.get('store_sdm') is not None and r['speaker'] not in exclude]
    rng = random.Random(seed)
    rng.shuffle(eligible)
    chosen = eligible[:limit]
    t0 = time.time()
    for n, r in enumerate(chosen, 1):
        i = r['store_sdm']
        pcm = np.asarray(audio[index['offsets'][i]:index['offsets'][i] + index['lengths'][i]])
        w.add_case(trunk, r['audio_id'], r['meeting'], f'ami-{split}', pcm, labels.expand(r['counts']), labels.expand(r['collar']).astype(bool),
                   store_index=i, speaker=r['speaker'])
        if n % 250 == 0:
            print(f'{split} {n}/{len(chosen)} {time.time() - t0:.0f}s', flush=True)
    return dict(eligible=len(eligible), subsample=len(chosen), seed=seed, excluded_speakers=list(exclude))


def write_protocol(out: Path, trunk: Trunk):
    protocol = dict(
        phase='2 G1 addendum', window_samples=WINDOW, hop_samples=HOP, trunk_frames=TRUNK_FRAMES, statistics=list(STATS),
        spread='window statistics averaged onto covered 10 ms frames',
        calibration='logistic regression, 4 statistics + bias, fitted on the AMI train subsample windows with soft target = fraction of valid frames with two or more speakers; applied per frame to the spread statistics',
        train_subsample=dict(seed=TRAIN_SEED, size=TRAIN_SUBSAMPLE, excluded_speakers=list(TRAIN_SPEAKER_EXCLUSIONS)),
        validation_subsample=dict(seed=VALIDATION_SEED, size=VALIDATION_SUBSAMPLE, note='identical windows to G0'),
        then='frozen experiment.json protocol: frame threshold 0.5 on the calibrated posterior, segment fraction, threshold selected once on validation at the 2% ceiling',
        diagnostics='threshold-free ROC area of each raw statistic, outside the protocol',
        identity=trunk.identity, extractor_sha256=sha(Path(__file__).read_bytes()),
    )
    f = out / 'g1-protocol.json'
    if f.exists():
        prior = json.loads(f.read_text())
        assert {k: v for k, v in prior.items() if k != 'extractor_sha256'} == {k: v for k, v in protocol.items() if k != 'extractor_sha256'}, 'G1 protocol drift'
    else:
        f.write_text(json.dumps(protocol, indent=2) + '\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('panel', choices=['synthetic', 'microphone', 'validation', 'train'])
    ap.add_argument('--out', type=Path, default=ROOT / 'private/training-track/overlap-gate/phase2/g1')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    trunk = Trunk()
    write_protocol(args.out, trunk)
    w = Writer()
    meta = dict(panel=args.panel, hop_ms=labels.HOP_MS, collar_ms=labels.COLLAR_MS, statistics=list(STATS), **trunk.identity,
                extractor_sha256=sha(Path(__file__).read_bytes()))
    if args.panel == 'synthetic':
        panel_synthetic(trunk, w)
    elif args.panel == 'microphone':
        panel_microphone(trunk, w)
    elif args.panel == 'validation':
        meta.update(panel_store(trunk, w, 'validation', VALIDATION_SEED, VALIDATION_SUBSAMPLE))
    else:
        meta.update(panel_store(trunk, w, 'train', TRAIN_SEED, TRAIN_SUBSAMPLE, TRAIN_SPEAKER_EXCLUSIONS))
    w.save(args.out / args.panel, **meta)
    print(json.dumps(dict(panel=args.panel, cases=len(w.rows), windows=len(w.windows))))


if __name__ == '__main__':
    main()
