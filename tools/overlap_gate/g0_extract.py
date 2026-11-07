"""G0 heuristic gate: per-frame scores from the deployed recognizer's int8 CTC logits.

Two frame scores, both in [0, 1], computed from the same logits the decoder already receives:
  entropy   normalized Shannon entropy of the 29-class posterior (H / ln 29)
  nonblank  1 - p(blank)
Logits are at 20 ms (stride-2); each is repeated twice to the 10 ms label grid.

Panels are written as one .npz per panel holding concatenated per-frame arrays plus offsets, and
an index json. Round-three mixture logits are reused from its recognition cache where present;
other audio is transcribed with the identical frozen frontend binary and exported recognizer.
No model is trained; no settings change; the shared evaluation lock is held while inferring.

Run from the repository root with the export venv python.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from overlap_gate import labels  # noqa: E402

R3 = ROOT / 'private/training-track/compact16k-loss-round3'
R3_CACHE = R3 / 'recognition-cache/792cfab058ea81447d0c871253d77839dd4c3e74c96b5c7d91894cf882533485'
FRONTEND = R3 / 'runtime-build/frontend'
DEPLOY = Path('/Volumes/Audiodrive/stt/work/deploy15')
VALIDATION_SUBSAMPLE = 2000
VALIDATION_SEED = 20261105
CLASSES = 29
BLANK = 28


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Recognizer:
    """Frozen frontend binary + exported recognizer, with an on-disk int8 logit cache."""

    def __init__(self, cache: Path):
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)
        prior = R3.parent / 'compact16k-round2'
        old = R3.parent / 'overlap-ab'
        sys.path[:0] = [str(R3), str(prior), str(old), str(old / 'deps'), str(ROOT / 'tools/stt_p4'), str(ROOT / 'tools/stt_p4/speaker')]
        os.environ.update(STT_ROOT='/Volumes/Audiodrive/stt', OMP_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        import torch
        from release_benchmark import load_export
        torch.set_num_threads(1)
        self.torch = torch
        exp = DEPLOY / 'export-gen2-25397'
        manifest = json.loads((exp / 'manifest.json').read_text())
        self.forward, self.exponent, self.identity, _ = load_export(exp, DEPLOY / 'ckpt-gen2-25397', False, manifest['checkpoint']['weights_sha256'])
        assert self.identity == '47e58faa01470d32dad88f1faa46e3f61dff0fd605aa542103aefd11502dae72'
        assert FRONTEND.exists(), FRONTEND
        from resources import acquire
        self.lock = acquire('evaluation')

    CHUNK = 20 * labels.SAMPLE_RATE   # production segmenter maximum; the frontend binary refuses > 30 s

    def logits(self, pcm: np.ndarray) -> np.ndarray:
        """Int8 logits for one PCM array; audio longer than one production segment is processed in
        20 s pieces and concatenated, which is how the device would see it."""
        pcm = np.ascontiguousarray(pcm.astype('<i2'))
        if pcm.size > self.CHUNK:
            pieces = [self._logits(pcm[i:i + self.CHUNK]) for i in range(0, pcm.size, self.CHUNK) if pcm.size - i >= 320]
            return np.concatenate(pieces)
        return self._logits(pcm)

    def _logits(self, pcm: np.ndarray) -> np.ndarray:
        h = sha(pcm.tobytes())
        for folder in (R3_CACHE, self.cache):
            f = folder / f'{h}.logits.i8'
            if f.exists():
                return np.fromfile(f, 'i1').reshape(-1, CLASSES)
        pcm_file = self.cache / f'{h}.pcm'
        feat_file = self.cache / f'{h}.f32'
        pcm.tofile(pcm_file)
        subprocess.run([str(FRONTEND), str(pcm_file), str(feat_file), 'no_dither'], check=True, stdout=subprocess.DEVNULL)
        x = self.torch.from_numpy(np.fromfile(feat_file, '<f4').reshape(-1, 64).T.copy())[None, :, :, None]
        with self.torch.inference_mode():
            scores = self.forward(x)[0, :, :, 0].T.numpy()
        scaled = np.rint(scores / 2.0 ** self.exponent)
        assert np.isfinite(scores).all() and scaled.min() >= -128 and scaled.max() <= 127
        q = scaled.astype('i1')
        q.tofile(self.cache / f'{h}.logits.i8')
        pcm_file.unlink()
        feat_file.unlink()
        return q


def frame_scores(q: np.ndarray, exponent: int, n_frames: int):
    """Entropy and non-blank scores on the 10 ms label grid of length n_frames."""
    z = q.astype(np.float64) * 2.0 ** exponent
    z -= z.max(axis=1, keepdims=True)
    p = np.exp(z)
    p /= p.sum(axis=1, keepdims=True)
    entropy = -(p * np.log(np.maximum(p, 1e-12))).sum(axis=1) / np.log(CLASSES)
    nonblank = 1.0 - p[:, BLANK]
    out = []
    for s in (entropy, nonblank):
        up = np.repeat(s, 2)
        if up.size >= n_frames:
            up = up[:n_frames]
        else:
            up = np.concatenate([up, np.full(n_frames - up.size, up[-1] if up.size else 0.0)])
        out.append(up.astype(np.float16))
    return out


class PanelWriter:
    def __init__(self):
        self.rows = []
        self.counts, self.collar, self.entropy, self.nonblank = [], [], [], []

    def add(self, case_id, group, condition, counts, collar, entropy, nonblank, **extra):
        n = counts.size
        assert collar.size == n == entropy.size == nonblank.size
        self.rows.append(dict(id=case_id, group=group, condition=condition, frames=int(n), **extra))
        self.counts.append(counts.astype(np.int8))
        self.collar.append(collar.astype(bool))
        self.entropy.append(entropy)
        self.nonblank.append(nonblank)

    def save(self, path: Path, **meta):
        lengths = np.array([r['frames'] for r in self.rows])
        offsets = np.concatenate([[0], np.cumsum(lengths)])
        np.savez_compressed(path.with_suffix('.npz'), counts=np.concatenate(self.counts), collar=np.concatenate(self.collar),
                            entropy=np.concatenate(self.entropy), nonblank=np.concatenate(self.nonblank), offsets=offsets)
        path.with_suffix('.json').write_text(json.dumps(dict(meta, cases=len(self.rows), rows=self.rows), indent=1) + '\n')


def intervals_to_labels(intervals, seconds):
    merged = labels.merge_speaker_intervals(intervals)
    return labels.frame_counts(merged, 0.0, seconds), labels.collar_mask(merged, 0.0, seconds)


def read_pcm(path: str) -> np.ndarray:
    return np.fromfile(path, '<i2')


def panel_synthetic(rec: Recognizer, writer: PanelWriter):
    suite = json.loads((R3 / 'eval-suite.json').read_text())
    for c in suite['cases']:
        pcm = read_pcm(str(R3 / c['mixture']['pcm']) if not c['mixture']['pcm'].startswith('/') else c['mixture']['pcm'])
        assert sha(pcm.tobytes()) == c['mixture']['sha256']
        seconds = pcm.size / labels.SAMPLE_RATE
        if c['condition'] == 'real-overlap':
            a, b = c['annotation']['utterances']
            start = a['start']
            intervals = [(a['speaker'], a['start'] - start, a['end'] - start), (b['speaker'], b['start'] - start, b['end'] - start)]
        elif c['condition'] == 'two-speakers':
            s0, s1 = c['sources']
            intervals = [('s0', 0.0, s0['length'] / labels.SAMPLE_RATE),
                         ('s1', c['offset_samples'] / labels.SAMPLE_RATE, (c['offset_samples'] + s1['length']) / labels.SAMPLE_RATE)]
        elif c['condition'].startswith('no-speech'):
            intervals = []
        else:
            intervals = [('s0', 0.0, c['sources'][0]['length'] / labels.SAMPLE_RATE)]
        counts, collar = intervals_to_labels(intervals, seconds)
        q = rec.logits(pcm)
        ent, nb = frame_scores(q, rec.exponent, counts.size)
        writer.add(c['id'], c['group'], c['condition'], counts, collar, ent, nb, partition=c['partition'],
                   overlap_requested=c.get('overlap_requested'), second_db=c.get('second_db'))


def panel_microphone(rec: Recognizer, writer: PanelWriter):
    sys.path.insert(0, str(ROOT / 'private/stt-detector-followup'))
    cwd = os.getcwd()
    os.chdir(ROOT)
    from cases import cases  # noqa: E402  (loads the frozen 163-case panel audio)
    os.chdir(cwd)
    baseline = json.loads((ROOT / 'private/stt-loss-round3-review/baseline.json').read_text())
    clips = {c['id']: c for c in json.loads((ROOT / 'private/training-track/overlap-investigation/annotation-audit.json').read_text())}
    assert len(cases) == len(baseline['cases']) == 163
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
        q = rec.logits(pcm)
        ent, nb = frame_scores(q, rec.exponent, counts.size)
        writer.add(c['id'], c['group'], condition, counts, collar, ent, nb)


def panel_validation(rec: Recognizer, writer: PanelWriter, limit: int):
    frozen = json.loads((ROOT / 'private/training-track/overlap-gate/labels-validation.json').read_text())
    store = ROOT / 'private/training-baseline-20261103/corrected/stores/ami-sdm-validation'
    index = json.loads((store / 'index.json').read_text())
    audio = np.memmap(store / 'audio.bin', '<i2', 'r')
    eligible = [r for r in frozen['records'] if r.get('store_sdm') is not None]
    rng = random.Random(VALIDATION_SEED)
    rng.shuffle(eligible)
    chosen = eligible[:limit]
    t0 = time.time()
    for n, r in enumerate(chosen, 1):
        i = r['store_sdm']
        pcm = np.asarray(audio[index['offsets'][i]:index['offsets'][i] + index['lengths'][i]])
        counts = labels.expand(r['counts'])
        collar = labels.expand(r['collar']).astype(bool)
        q = rec.logits(pcm)
        ent, nb = frame_scores(q, rec.exponent, counts.size)
        writer.add(r['audio_id'], r['meeting'], 'ami-validation', counts, collar, ent, nb, store_index=i, speaker=r['speaker'])
        if n % 100 == 0:
            print(f'validation {n}/{len(chosen)} {time.time() - t0:.0f}s', flush=True)
    return dict(eligible=len(eligible), subsample=len(chosen), seed=VALIDATION_SEED)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('panel', choices=['synthetic', 'microphone', 'validation'])
    ap.add_argument('--out', type=Path, default=ROOT / 'private/training-track/overlap-gate/phase1/g0')
    ap.add_argument('--limit', type=int, default=VALIDATION_SUBSAMPLE)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rec = Recognizer(args.out / 'logit-cache')
    writer = PanelWriter()
    meta = dict(panel=args.panel, recognizer=rec.identity, logit_exponent=rec.exponent, hop_ms=labels.HOP_MS, collar_ms=labels.COLLAR_MS,
                scores=['entropy', 'nonblank'], frontend_sha256=sha(FRONTEND.read_bytes()), extractor_sha256=sha(Path(__file__).read_bytes()))
    if args.panel == 'synthetic':
        panel_synthetic(rec, writer)
    elif args.panel == 'microphone':
        panel_microphone(rec, writer)
    else:
        meta.update(panel_validation(rec, writer, args.limit))
    writer.save(args.out / args.panel, **meta)
    print(json.dumps(dict(panel=args.panel, cases=len(writer.rows), frames=int(sum(r['frames'] for r in writer.rows)))))


if __name__ == '__main__':
    main()
