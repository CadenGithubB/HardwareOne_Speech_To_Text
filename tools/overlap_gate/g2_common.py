"""G2 overlap classifier: shared definitions (protocol constants, frontend, data, model).

Every number here is part of the frozen phase-three protocol; g2_train.py writes them to
g2-protocol.json before the first optimizer step and refuses to run if they later differ.

Input: the production 64-bin log-mel at a 160-sample hop, *before* the recognizer's per-utterance
mean/variance normalization, so the classifier can score a stream frame by frame. The Python
frontend with dither disabled matches the portable C++ frontend to about 1e-6 mean absolute
difference (STT investigation 6). A fixed per-bin mean and standard deviation, measured on
training windows, replaces per-utterance normalization.

Output: per 20 ms frame, logits for {0: no active speaker, 1: one speaker, 2: two or more}.
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tools/stt_p4'))
from overlap_gate import labels  # noqa: E402

SAMPLE_RATE = 16000
HOP = 160
MELS = 64
WINDOW_FRAMES = 200                      # 2.0 s training windows
WINDOW_SAMPLES = WINDOW_FRAMES * HOP
CLASSES = 3
CHECKPOINT = Path('/Volumes/Audiodrive/stt/work/deploy15/ckpt-gen2-25397')
STORES = ROOT / 'private/training-baseline-20261103/corrected/stores'
LABELS = ROOT / 'private/training-track/overlap-gate'
PHASE3 = LABELS / 'phase3'
TRAIN_SPEAKER_EXCLUSIONS = ('FIE038', 'MIO036')
MIN_UTTERANCE_SECONDS = 0.6
VALIDATION_SEED, VALIDATION_SUBSAMPLE = 20261105, 2000        # identical windows to G0/G1

NEGATIVE_STORES = ('librispeech-train-clean-100', 'voxpopuli-train', 'commonvoice-en-train', 'peoples-clean-train')
DEV_NEGATIVE_STORES = ('librispeech-dev-clean', 'voxpopuli-dev', 'commonvoice-fresh-dev', 'peoples-dev')
DEV_NEGATIVES_PER_STORE, DEV_NEGATIVE_SEED = 100, 20261107

PROTOCOL = dict(
    phase='3 G2 classifier',
    input='64-bin log-mel, 160-sample hop, pre-CMVN, fixed per-bin normalization from 1,024 training windows',
    window_frames=WINDOW_FRAMES, classes={'0': 'no active speaker', '1': 'one', '2': 'two or more'},
    target_grid='20 ms: class = count at 10 ms frame 2j, collar = collar[2j] | collar[2j+1]',
    model=dict(stem='Conv1d 64->48 k5 s2 + BN + ReLU',
               blocks='3 x [depthwise k7 dilation 1/2/4 -> pointwise 48->48 + BN + ReLU] with residual',
               head='pointwise 48->3', parameters='about 24k', receptive_field_ms='about 900'),
    data=dict(speech='AMI train sdm (70%) and ihm (30%) store-matched windows, speaker not in exclusions, >= 0.6 s; '
                     'random 2 s crop aligned to the hop; shorter utterances zero-padded with class 0 and a collar at the pad edge',
              gain='uniform -10..+10 dB on speech crops',
              noise='10% of each batch: 2 s chunks of demand-noise-train or musan-noise at uniform -45..-20 dBFS RMS, class 0',
              silence='2% of each batch: digital silence with 1e-4 RMS noise, class 0',
              exclusions=list(TRAIN_SPEAKER_EXCLUSIONS), sampling='utterances weighted by duration'),
    training=dict(steps=12000, batch=64, optimizer='Adam', lr=2e-3, lr_end=1e-4, schedule='cosine', weight_decay=1e-4, seed=1,
                  loss='cross-entropy over 3 classes, collar frames excluded', checkpoint_every=1000),
    selection=dict(metric='frame ROC area of P(class 2) vs count >= 2 outside the collar on the fixed validation subsample (upsampled to 10 ms)',
                   rule='highest ROC area; ties to the earlier checkpoint', subsample=dict(seed=VALIDATION_SEED, size=VALIDATION_SUBSAMPLE)),
    then='frozen experiment.json protocol on P(class 2): frame threshold 0.5, segment fraction, threshold selected once on validation at the 2% ceiling; AMI test scored once',
)

# G2b: identical model, loss, optimizer, steps and seed. Only the data mix and the validation set change,
# to teach "one speaker" beyond AMI after G2 over-flagged clean read speech from other corpora.
PROTOCOL_G2B = dict(
    PROTOCOL,
    phase='3b G2b classifier',
    data=dict(
        PROTOCOL['data'],
        speech='88% of each batch is speech: 70% AMI train windows exactly as in G2, 30% non-AMI single-speaker windows (class 1 throughout, '
               'uniform over four stores then uniform over items, 15 h seeded subset per store, random 2 s crop, short items padded with silence)',
        non_ami_stores=list(NEGATIVE_STORES),
        non_ami_exclusions='voxpopuli-train speakers also present in voxpopuli-validation (phase3/g2b-voxpopuli-exclusions.json)',
        noise_mixing='50% of non-AMI windows: DEMAND/MUSAN noise added in the log-mel power domain (logaddexp) at SNR uniform 0..20 dB, '
                     'SNR measured on feature-domain mean power; AMI windows are not mixed, to stay comparable with G2',
    ),
    selection=dict(
        PROTOCOL['selection'],
        validation=f'the G2 AMI validation subsample (2,000 windows) plus {DEV_NEGATIVES_PER_STORE} seeded single-speaker windows from each of '
                   f'{len(DEV_NEGATIVE_STORES)} non-AMI dev stores (class 1); checkpoint by frame ROC area, threshold by segment false alarms <= 2% over all negatives',
        dev_negative_stores=list(DEV_NEGATIVE_STORES), dev_negative_seed=DEV_NEGATIVE_SEED,
    ),
    tests='AMI test and the saved-microphone panel scored once each; the saved panel is never used for selection',
)

# G2c: decorrelate corpus from voice count. Non-AMI windows appear both as single-speaker (class 1) and as
# log-domain two-speaker mixtures (class 2 where the spans overlap). The false-alarm ceiling is applied to
# AMI validation negatives only; other-corpus false alarms are reported separately, never pooled.
PROTOCOL_G2C = dict(
    PROTOCOL_G2B,
    phase='3c G2c classifier',
    data=dict(
        PROTOCOL_G2B['data'],
        speech='88% of each batch is speech: 70% AMI train windows as in G2, 15% non-AMI single-speaker windows as in G2b, '
               '15% non-AMI two-speaker mixtures: two different non-AMI items, each cropped/padded to 2 s, the second shifted by a '
               'uniform onset of 0..199 frames and scaled by uniform -12..+12 dB, combined with logaddexp; frame count = number of active spans; '
               'collar +-200 ms around every span edge inside the window; 50% of mixtures also get 0..20 dB SNR noise as in G2b',
    ),
    selection=dict(
        PROTOCOL['selection'],
        validation='checkpoint by frame ROC area on the G2 AMI validation subsample only; segment threshold by false alarms <= 2% on AMI validation '
                   'negatives only; the 364 non-AMI dev single-speaker windows are scored at that threshold and reported separately',
        dev_negative_stores=list(DEV_NEGATIVE_STORES), dev_negative_seed=DEV_NEGATIVE_SEED,
    ),
)

# Phase 5 recall variants (declared 6 Nov 2026 before any of them trained): G2c's data, sampler, seed and
# selection, with exactly one change each. Compared by device-rule recall on the AMI validation subsample at the
# 2% false-alarm ceiling (threshold re-selected under the device rule); AMI test is scored once, for the winner only.
ARCH = {'g2': {}, 'g2b': {}, 'g2c': {}, 'g2d': dict(width=64), 'g2e': dict(dilations=(1, 2, 4, 8)), 'g2f': {}, 'g2g': {}, 'g2h': {}, 'g2i': {}}
DATA_OF = {'g2': 'g2', 'g2b': 'g2b', 'g2c': 'g2c', 'g2d': 'g2c', 'g2e': 'g2c', 'g2f': 'g2c', 'g2g': 'g2c', 'g2h': 'g2h', 'g2i': 'g2i'}
CLASS_WEIGHTS = {'g2g': (1.0, 1.0, 2.0)}


def _variant(name, change, **training):
    return dict(PROTOCOL_G2C, phase=f'5 {name} recall variant of G2c', change=change,
                arch=dict(width=ARCH[name].get('width', 48), dilations=list(ARCH[name].get('dilations', (1, 2, 4)))),
                training=dict(PROTOCOL_G2C['training'], **training),
                selection=dict(PROTOCOL_G2C['selection'], variant_comparison='device rule (int8, 200-frame chunks, R10, no collar) on the AMI validation subsample; '
                               'threshold at <=2% segment false alarms on AMI negatives; highest recall wins; G2c reference 24.1%'))


PROTOCOLS = {'g2': PROTOCOL, 'g2b': PROTOCOL_G2B, 'g2c': PROTOCOL_G2C,
             'g2d': _variant('g2d', 'width 64 instead of 48'),
             'g2e': _variant('g2e', 'four blocks, dilations 1/2/4/8 (longer context)'),
             'g2f': _variant('g2f', 'twice the training steps', steps=24000),
             'g2g': _variant('g2g', 'two-or-more class weighted 2x in the loss', class_weights=[1.0, 1.0, 2.0])}

# G2h (declared 6 Nov 2026 after overnight run 1, before training): G2c with replayed audio in the batch.
# Night 1 showed the loudspeaker -> room -> P4 microphone chain removes the cue G2c uses (AUC 0.79 -> 0.59).
REPLAY = Path('/Volumes/Audiodrive/stt/overlap-gate/replay1')
REPLAY_SPLIT = LABELS / 'phase5' / 'replay-split.json'
REPLAY_SHARE = 0.25
PROTOCOLS['g2h'] = dict(
    PROTOCOL_G2C, phase='5 G2h: G2c plus replayed P4-microphone audio',
    change='25% of each batch\'s speech share is a replay window; everything else as G2c',
    arch=dict(width=48, dilations=[1, 2, 4]),
    data=dict(PROTOCOL_G2C['data'],
              replay=f'{REPLAY_SHARE:.0%} of the speech share (22% of each batch): 2 s crops of the P4-saved segments of overnight run 1 from '
                     'the 8 training blocks (replay-split.json, seed 20261106), AMI-validation clips only; frame labels from the playlist '
                     'after per-run alignment, playlist collar plus 200 ms at every clip edge; uniform -10..+10 dB gain; short segments '
                     'silence-padded with an edge collar as G2 speech',
              replay_exclusions='AMI test, LibriSpeech test, synthetic qualification suite, saved-microphone windows and test noise never train; '
                                'validation and test blocks never train'),
    selection=dict(metric='frame ROC area of P(class 2) outside the collar on two panels: the AMI validation subsample without the '
                          'AMI-validation clips replayed in training blocks, and the replay validation blocks (7, 8, 12, AMI-validation clips only)',
                   rule='highest mean of the two ROC areas; ties to the earlier checkpoint',
                   comparison='device rule (int8, 200-frame chunks, R10) against G2c on both panels; segment threshold at <=2% false alarms '
                              'on reduced-AMI-validation negatives, and separately on replay-validation negatives',
                   tests='replay test blocks (5, 9, 14, every category) and AMI test: once, only if adopted'),
)


class ReplayBank:
    """Replay segments (replay_store.py): float16 [frames, 64] with per-item labels and split."""

    def __init__(self, root: Path = None):
        root = root or REPLAY
        meta = json.loads((root / 'replay.json').read_text())
        self.items = meta['items']
        self.data = np.memmap(root / 'replay.f16', np.float16, 'r', shape=(meta['frames'], MELS))

    def slice(self, key: str, f0: int = 0, n: int | None = None) -> np.ndarray:
        e = self.items[key]
        n = e['frames'] - f0 if n is None else n
        return np.asarray(self.data[e['start'] + f0:e['start'] + f0 + n], dtype=np.float32).T

    def labels(self, key: str):
        e = self.items[key]
        counts = np.zeros(e['frames'], np.int8)
        collar = np.zeros(e['frames'], bool)
        for a, b, v in e['counts']:
            counts[a:b] = v
        for a, b, v in e['collar']:
            collar[a:b] = bool(v)
        return counts, collar

    def keys(self, split: str, ami_val_only: bool = False):
        return sorted(k for k, e in self.items.items() if e['split'] == split and (not ami_val_only or e['categories'] == ['ami-val']))


# G2i (declared 6 Nov 2026 before the night-2 session finished, before training): G2h plus night 2, a replay
# session of training-split material only (AMI train, non-AMI single speakers and two-speaker mixtures from the
# G2b/G2c training stores, training noise), so the replay channel sees both classes across corpora.
REPLAY2 = Path('/Volumes/Audiodrive/stt/overlap-gate/replay2')
PROTOCOLS['g2i'] = dict(
    PROTOCOLS['g2h'], phase='5 G2i: G2h plus night-2 replay of training-split material',
    change='replay share drawn uniformly over night-1 training-block AMI-validation segments and every night-2 segment',
    data=dict(PROTOCOLS['g2h']['data'],
              replay2='night 2 (phase4/night2 playlists, seed 20261107): ami-train, one-train (2-8 s crop of one non-AMI training utterance), '
                      'two-train (two non-AMI training crops, second at 0.3 s..first end, -6..+6 dB), noise-train; one gate-on run per block; '
                      'aligned and labelled exactly as night 1 (replay_store.py --night 2)'),
)


def reduced_validation_subsample():
    """The AMI validation subsample without clips that were replayed in training blocks."""
    used = set(json.loads(REPLAY_SPLIT.read_text())['ami_validation_ids_in_training'])
    return [r for r in validation_subsample() if r['audio_id'] not in used]


# ----------------------------------------------------------------------------- frontend


class RawFrontend:
    """Pre-CMVN log-mel exactly as the training/device frontend computes it, dither disabled."""

    def __init__(self):
        import os
        from quartznet_graph import load_checkpoint, WEIGHTS_OVERRIDE_ENV
        manifest = json.loads((CHECKPOINT.parent / 'export-gen2-25397/manifest.json').read_text())
        os.environ[WEIGHTS_OVERRIDE_ENV] = manifest['checkpoint']['weights_sha256']   # the deployed export's own checkpoint
        _cfg, state = load_checkpoint(CHECKPOINT)
        self.checkpoint_sha256 = manifest['checkpoint']['weights_sha256']
        self.window = state['preprocessor.featurizer.window'].float()
        self.fb = state['preprocessor.featurizer.fb'].float()[0]

    def __call__(self, samples: np.ndarray) -> torch.Tensor:
        """samples: float32 [-1, 1] -> [64, T] with T = ceil(len / 160)."""
        x = torch.from_numpy(np.ascontiguousarray(samples, dtype=np.float32))
        return self.batch(x[None])[0]

    def batch(self, x: torch.Tensor) -> torch.Tensor:
        """x: [B, N] float -> [B, 64, ceil(N/160)]."""
        x = torch.cat((x[:, :1], x[:, 1:] - 0.97 * x[:, :-1]), dim=1)
        valid = math.ceil(x.shape[1] / HOP)
        spec = torch.stft(x, n_fft=512, hop_length=HOP, win_length=len(self.window), window=self.window, center=True, return_complex=True)
        mel = torch.einsum('mf,bft->bmt', self.fb, spec.abs().square())
        return torch.log(mel + 2 ** -24)[:, :, :valid]


# ----------------------------------------------------------------------------- data


class Store:
    def __init__(self, name: str):
        d = STORES / name
        self.index = json.loads((d / 'index.json').read_text())
        self.audio = np.memmap(d / 'audio.bin', '<i2', 'r')

    def pcm(self, i: int) -> np.ndarray:
        o, n = self.index['offsets'][i], self.index['lengths'][i]
        return np.asarray(self.audio[o:o + n])

    def chunk(self, rng: random.Random, n: int) -> np.ndarray:
        for _ in range(100):
            i = rng.randrange(len(self.index['lengths']))
            if self.index['lengths'][i] >= n:
                s = rng.randrange(self.index['lengths'][i] - n + 1)
                return self.pcm(i)[s:s + n]
        raise RuntimeError('no chunk long enough')


def load_records(split: str, exclude=()):
    frozen = json.loads((LABELS / f'labels-{split}.json').read_text())
    recs = [r for r in frozen['records'] if r.get('store_sdm') is not None and r['speaker'] not in exclude
            and (r['end'] - r['begin']) >= MIN_UTTERANCE_SECONDS]
    return recs


def validation_subsample():
    """The same 2,000 validation windows G0 and G1 used (store-matched, seeded shuffle)."""
    frozen = json.loads((LABELS / 'labels-validation.json').read_text())
    eligible = [r for r in frozen['records'] if r.get('store_sdm') is not None]
    rng = random.Random(VALIDATION_SEED)
    rng.shuffle(eligible)
    return eligible[:VALIDATION_SUBSAMPLE]


def dev_negatives():
    """Seeded single-speaker windows from the non-AMI dev stores: (store, key, counts=1, collar=0)."""
    rng = random.Random(DEV_NEGATIVE_SEED)
    out = []
    for name in DEV_NEGATIVE_STORES:
        bank = Features(name)
        keys = sorted(bank.items, key=int)
        rng.shuffle(keys)
        for key in keys[:DEV_NEGATIVES_PER_STORE]:
            n = bank.frames(key)
            out.append(dict(store=name, key=key, audio_id=f'{name}:{key}', counts=np.ones(n, np.int8), collar=np.zeros(n, bool)))
    return out


def to_20ms(counts: np.ndarray, collar: np.ndarray):
    """Targets on the model's 20 ms grid for a 10 ms label sequence of even length."""
    n = counts.size // 2
    target = np.minimum(counts[0:2 * n:2], 2).astype(np.int64)
    mask = ~(collar[0:2 * n:2] | collar[1:2 * n:2])
    return target, mask


FEATURES = PHASE3 / 'features'


class Features:
    """Precomputed raw log-mel for one store (g2_features.py): float16 [frames, 64] plus an index."""

    def __init__(self, store_name: str):
        meta = json.loads((FEATURES / f'{store_name}.json').read_text())
        self.items = meta['items']
        self.data = np.memmap(FEATURES / f'{store_name}.f16', np.float16, 'r', shape=(meta['frames'], MELS))

    def slice(self, key: str, f0: int = 0, n: int | None = None) -> np.ndarray:
        e = self.items[key]
        n = e['frames'] - f0 if n is None else n
        return np.asarray(self.data[e['start'] + f0:e['start'] + f0 + n], dtype=np.float32).T      # [64, n]

    def frames(self, key: str) -> int:
        return self.items[key]['frames']


class Sampler:
    """Draws training windows from precomputed features: speech crops with real labels, noise, silence.

    Gain and level augmentation are exact log-domain offsets (2 ln g) on the raw log-mel.
    """

    def __init__(self, seed: int, variant: str = 'g2'):
        assert variant in DATA_OF
        variant = DATA_OF[variant]
        self.variant = variant
        self.rng = random.Random(seed)
        self.sdm, self.ihm = Features('ami-sdm-train'), Features('ami-ihm-train')
        self.records = [r for r in load_records('train', TRAIN_SPEAKER_EXCLUSIONS) if r['audio_id'] in self.sdm.items]
        self.weights = np.array([r['end'] - r['begin'] for r in self.records])
        self.weights /= self.weights.sum()
        self.cum = np.cumsum(self.weights)
        self.noise = [Features('demand-noise-train'), Features('musan-noise')]
        self.noise_keys = [[k for k, e in f.items.items() if e['frames'] >= WINDOW_FRAMES] for f in self.noise]
        self.silence = np.array(json.loads((FEATURES / 'silence-feature.json').read_text())['per_bin_mean'], np.float32)[:, None]
        self.low_noise = None   # feature of 1e-4 RMS white noise; filled lazily from the frontend
        if variant in ('g2h', 'g2i'):
            bank = ReplayBank()
            keys = sorted(k for k, e in bank.items.items() if e['trainable'])
            assert keys and all(bank.items[k]['split'] == 'train' and bank.items[k]['categories'] == ['ami-val'] for k in keys)
            self.replay_pool = [(bank, k) for k in keys]
            if variant == 'g2i':
                bank2 = ReplayBank(REPLAY2)
                keys2 = sorted(k for k, e in bank2.items.items() if e['trainable'])
                assert keys2 and all(bank2.items[k]['split'] == 'train' for k in keys2)
                self.replay_pool += [(bank2, k) for k in keys2]
        self.non_ami = []
        if variant in ('g2b', 'g2c', 'g2h', 'g2i'):
            excluded = set(json.loads((PHASE3 / 'g2b-voxpopuli-exclusions.json').read_text())['excluded_speakers'])
            for name in NEGATIVE_STORES:
                bank = Features(name)
                speakers = Store(name).index['speakers']
                keys = [k for k, e in bank.items.items() if e['frames'] >= 1 and not (name == 'voxpopuli-train' and speakers[e['store_index']] in excluded)]
                self.non_ami.append((bank, keys))

    def _crop(self, bank, key, n_frames):
        """Random 2 s crop (or silence-padded whole item) with frame count; returns feats, kept frames, pad collar."""
        if n_frames >= WINDOW_FRAMES:
            f0 = self.rng.randrange(n_frames - WINDOW_FRAMES + 1)
            return bank.slice(key, f0, WINDOW_FRAMES), f0, WINDOW_FRAMES, None
        pad = WINDOW_FRAMES - n_frames
        feats = np.concatenate([bank.slice(key, 0, n_frames), np.repeat(self.silence, pad, axis=1)], axis=1)
        return feats, 0, n_frames, pad

    def _non_ami_window(self):
        """One non-AMI single-speaker 2 s window: feats, active-frame mask, kept frames."""
        bank, keys = self.non_ami[self.rng.randrange(len(self.non_ami))]
        key = self.rng.choice(keys)
        feats, _f0, kept, _pad = self._crop(bank, key, bank.frames(key))
        active = np.zeros(WINDOW_FRAMES, bool)
        active[:kept] = True
        return feats, active, kept

    def _add_noise(self, feats, active):
        k = self.rng.randrange(2)
        nb, nkey = self.noise[k], self.rng.choice(self.noise_keys[k])
        noise = nb.slice(nkey, self.rng.randrange(nb.frames(nkey) - WINDOW_FRAMES + 1), WINDOW_FRAMES)
        speech_power = float(np.mean(np.exp(feats[:, active].astype(np.float64)))) if active.any() else 1.0
        noise_power = float(np.mean(np.exp(noise.astype(np.float64))))
        snr_db = self.rng.uniform(0, 20)
        offset = math.log(speech_power / noise_power) - snr_db * math.log(10) / 10
        return np.logaddexp(feats.astype(np.float64), noise.astype(np.float64) + offset).astype(np.float32)

    @staticmethod
    def _edge_collar(active):
        collar = np.zeros(active.size, bool)
        edges = np.flatnonzero(np.diff(active.astype(np.int8))) + 1
        for e in edges:
            collar[max(0, e - 20):e + 20] = True
        return collar

    def non_ami_speech(self):
        feats, active, kept = self._non_ami_window()
        counts = active.astype(np.int8)
        collar = self._edge_collar(active)
        feats = feats + np.float32(2 * math.log(10 ** (self.rng.uniform(-10, 10) / 20)))
        if self.rng.random() < 0.5:
            feats = self._add_noise(feats, active)
        return feats, counts, collar

    def non_ami_mixture(self):
        """Two non-AMI speakers in one window: second shifted by a random onset and scaled -12..+12 dB,
        combined in the log-mel power domain. Counts are the number of active spans per frame."""
        f1, a1, _ = self._non_ami_window()
        f2, a2, _ = self._non_ami_window()
        onset = self.rng.randrange(WINDOW_FRAMES)
        shifted = np.concatenate([np.repeat(self.silence, onset, axis=1), f2[:, :WINDOW_FRAMES - onset]], axis=1)
        a2s = np.concatenate([np.zeros(onset, bool), a2[:WINDOW_FRAMES - onset]])
        rel = np.float32(2 * math.log(10 ** (self.rng.uniform(-12, 12) / 20)))
        feats = np.logaddexp(f1.astype(np.float64), (shifted + rel).astype(np.float64)).astype(np.float32)
        counts = (a1.astype(np.int8) + a2s.astype(np.int8))
        collar = self._edge_collar(a1) | self._edge_collar(a2s)
        feats = feats + np.float32(2 * math.log(10 ** (self.rng.uniform(-10, 10) / 20)))
        if self.rng.random() < 0.5:
            feats = self._add_noise(feats, a1 | a2s)
        return feats, counts, collar

    def speech(self):
        r = self.records[int(np.searchsorted(self.cum, self.rng.random()))]
        bank = self.ihm if self.rng.random() >= 0.7 and r['audio_id'] in self.ihm.items else self.sdm
        counts = labels.expand(r['counts'])
        collar = labels.expand(r['collar']).astype(bool)
        n_frames = min(counts.size, bank.frames(r['audio_id']))
        counts, collar = counts[:n_frames], collar[:n_frames]
        if n_frames >= WINDOW_FRAMES:
            f0 = self.rng.randrange(n_frames - WINDOW_FRAMES + 1)
            feats = bank.slice(r['audio_id'], f0, WINDOW_FRAMES)
            counts, collar = counts[f0:f0 + WINDOW_FRAMES], collar[f0:f0 + WINDOW_FRAMES]
        else:
            pad = WINDOW_FRAMES - n_frames
            feats = np.concatenate([bank.slice(r['audio_id'], 0, n_frames), np.repeat(self.silence, pad, axis=1)], axis=1)
            counts = np.concatenate([counts, np.zeros(pad, np.int8)])
            collar = np.concatenate([collar, np.zeros(pad, bool)])
            collar[max(0, n_frames - 20):n_frames + 20] = True
        gain_db = self.rng.uniform(-10, 10)
        return feats + np.float32(2 * math.log(10 ** (gain_db / 20))), counts, collar

    def replay_window(self):
        bank, key = self.replay_pool[self.rng.randrange(len(self.replay_pool))]
        counts, collar = bank.labels(key)
        n_frames = counts.size
        if n_frames >= WINDOW_FRAMES:
            f0 = self.rng.randrange(n_frames - WINDOW_FRAMES + 1)
            feats = bank.slice(key, f0, WINDOW_FRAMES)
            counts, collar = counts[f0:f0 + WINDOW_FRAMES], collar[f0:f0 + WINDOW_FRAMES]
        else:
            pad = WINDOW_FRAMES - n_frames
            feats = np.concatenate([bank.slice(key), np.repeat(self.silence, pad, axis=1)], axis=1)
            counts = np.concatenate([counts, np.zeros(pad, np.int8)])
            collar = np.concatenate([collar, np.zeros(pad, bool)])
            collar[max(0, n_frames - 20):n_frames + 20] = True
        return feats + np.float32(2 * math.log(10 ** (self.rng.uniform(-10, 10) / 20))), counts, collar

    def noise_window(self):
        k = self.rng.randrange(2)
        bank, key = self.noise[k], self.rng.choice(self.noise_keys[k])
        f0 = self.rng.randrange(bank.frames(key) - WINDOW_FRAMES + 1)
        target = 10 ** (self.rng.uniform(-45, -20) / 20)
        offset = 2 * math.log(target / bank.items[key]['rms'])
        return bank.slice(key, f0, WINDOW_FRAMES) + np.float32(offset), np.zeros(WINDOW_FRAMES, np.int8), np.zeros(WINDOW_FRAMES, bool)

    def silence_window(self):
        if self.low_noise is None:
            fe = RawFrontend()
            pcm = np.random.default_rng(0).standard_normal(WINDOW_SAMPLES).astype(np.float32) * 1e-4
            self.low_noise = fe(pcm).numpy()
        return self.low_noise.copy(), np.zeros(WINDOW_FRAMES, np.int8), np.zeros(WINDOW_FRAMES, bool)

    def batch(self, size: int):
        feats, targets, masks = [], [], []
        for _ in range(size):
            u = self.rng.random()
            if u < 0.10:
                f, counts, collar = self.noise_window()
            elif u < 0.12:
                f, counts, collar = self.silence_window()
            elif self.variant == 'g2b' and self.rng.random() < 0.30:
                f, counts, collar = self.non_ami_speech()
            elif self.variant in ('g2h', 'g2i') and self.rng.random() < REPLAY_SHARE:
                f, counts, collar = self.replay_window()
            elif self.variant in ('g2c', 'g2h', 'g2i') and (v := self.rng.random()) < 0.30:
                f, counts, collar = self.non_ami_speech() if v < 0.15 else self.non_ami_mixture()
            else:
                f, counts, collar = self.speech()
            t, m = to_20ms(counts, collar)
            feats.append(f)
            targets.append(t)
            masks.append(m)
        return torch.from_numpy(np.stack(feats)), torch.from_numpy(np.stack(targets)), torch.from_numpy(np.stack(masks))


# ----------------------------------------------------------------------------- model


class Block(nn.Module):
    def __init__(self, c: int, dilation: int):
        super().__init__()
        self.dw = nn.Conv1d(c, c, 7, padding=3 * dilation, dilation=dilation, groups=c, bias=False)
        self.pw = nn.Conv1d(c, c, 1, bias=False)
        self.bn = nn.BatchNorm1d(c)

    def forward(self, x):
        return torch.relu(self.bn(self.pw(self.dw(x))) + x)


class G2Net(nn.Module):
    def __init__(self, mean: torch.Tensor, std: torch.Tensor, width: int = 48, dilations=(1, 2, 4)):
        super().__init__()
        self.register_buffer('mean', mean.view(1, MELS, 1))
        self.register_buffer('std', std.view(1, MELS, 1))
        self.stem = nn.Conv1d(MELS, width, 5, stride=2, padding=2, bias=False)
        self.stem_bn = nn.BatchNorm1d(width)
        self.blocks = nn.Sequential(*(Block(width, int(d)) for d in dilations))
        self.head = nn.Conv1d(width, CLASSES, 1)

    def forward(self, feats):
        """feats: [B, 64, T] raw log-mel -> logits [B, 3, ceil(T/2)]."""
        x = (feats - self.mean) / self.std
        x = torch.relu(self.stem_bn(self.stem(x)))
        return self.head(self.blocks(x))


def parameter_count(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


def overlap_posterior_10ms(logits: torch.Tensor, n_frames: int) -> np.ndarray:
    """P(class 2) per 20 ms frame, repeated to the 10 ms grid and trimmed/padded to n_frames."""
    p = torch.softmax(logits, dim=0)[2].detach().cpu().numpy().astype(np.float64)
    up = np.repeat(p, 2)
    if up.size >= n_frames:
        return up[:n_frames]
    return np.concatenate([up, np.full(n_frames - up.size, up[-1] if up.size else 0.0)])
