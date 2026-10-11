"""Stores, on-the-fly augmentation and duration-bucketed batching."""
import json
import math
import random
from pathlib import Path

import numpy as np
import torch
from scipy.signal import fftconvolve, resample_poly, butter, sosfilt

from common import SAMPLE_RATE, HOP, Frontend, encode, ctc_min_frames
import os
STT_ROOT = Path(os.environ.get('STT_ROOT', 'stt-data'))  # data root: set STT_ROOT

STORES = (STT_ROOT / 'stores')


class Store:
    def __init__(self, name):
        directory = STORES / name
        index = json.loads((directory / 'index.json').read_text())
        self.name = name
        self.offsets = np.asarray(index['offsets'], dtype=np.int64)
        self.lengths = np.asarray(index['lengths'], dtype=np.int64)
        self.texts = index['texts']
        self.path = directory / 'audio.bin'
        self._audio = None

    @property
    def audio(self):  # opened lazily so DataLoader workers get their own map
        if self._audio is None:
            self._audio = np.memmap(self.path, dtype='<i2', mode='r')
        return self._audio

    def __len__(self):
        return len(self.lengths)

    def samples(self, i):
        o, n = self.offsets[i], self.lengths[i]
        return np.asarray(self.audio[o:o + n], dtype=np.float32) / 32768.0

    def random_chunk(self, rng, length):
        i = rng.randrange(len(self))
        audio = self.samples(i)
        if len(audio) >= length:
            start = rng.randrange(len(audio) - length + 1)
            return audio[start:start + length]
        reps = math.ceil(length / len(audio))
        return np.tile(audio, reps)[:length]


def _rms(x):
    return float(np.sqrt(np.mean(np.square(x)) + 1e-12))


class Augmenter:
    """Random device/room/noise conditions; mic-agnostic by design."""

    def __init__(self, noise, babble, rirs, strength=1.0):
        self.noise, self.babble, self.rirs = noise, babble, rirs
        self.strength = strength
        self.speech_pool = []  # fallback babble source: other training speech

    # Fallbacks used when the MUSAN / RIR corpora are unavailable.
    @staticmethod
    def _synthetic_rir(rng):
        rt60 = rng.uniform(0.15, 0.9)
        n = int(min(rt60, 1.0) * SAMPLE_RATE)
        gen = np.random.default_rng(rng.randrange(1 << 30))
        t = np.arange(n) / SAMPLE_RATE
        tail = gen.standard_normal(n) * np.exp(-6.9 * t / rt60)
        # Early reflections are sparse; smear the first few ms less.
        tail[:int(0.002 * SAMPLE_RATE)] = 0
        rir = tail * rng.uniform(0.05, 0.6) / (np.abs(tail).max() + 1e-9)
        rir[0] = 1.0
        return rir.astype(np.float32)

    @staticmethod
    def _coloured_noise(rng, n):
        gen = np.random.default_rng(rng.randrange(1 << 30))
        white = gen.standard_normal(n)
        exponent = rng.choice([0.0, 1.0, 2.0])  # white, pink, brown
        if exponent == 0.0:
            return white.astype(np.float32)
        spectrum = np.fft.rfft(white)
        freqs = np.fft.rfftfreq(n, 1 / SAMPLE_RATE)
        freqs[0] = freqs[1] if n > 1 else 1.0
        spectrum /= freqs ** (exponent / 2)
        return np.fft.irfft(spectrum, n).astype(np.float32)

    def _babble(self, rng, n):
        if self.babble is not None:
            return sum(self.babble.random_chunk(rng, n) for _ in range(rng.randint(3, 6)))
        if not self.speech_pool:
            return None
        return sum(rng.choice(self.speech_pool).random_chunk(rng, n) for _ in range(rng.randint(3, 6)))

    def __call__(self, x, rng, far_field=False):
        s = self.strength
        # Speed perturbation (pitch + tempo), standard for ASR robustness.
        r = rng.random()
        if r < 0.25 * s:
            x = resample_poly(x, 10, 9).astype(np.float32)   # 0.9x speed
        elif r < 0.5 * s:
            x = resample_poly(x, 10, 11).astype(np.float32)  # 1.1x speed
        # Room reverberation (less often for already-distant recordings).
        if rng.random() < (0.15 if far_field else 0.45) * s:
            rir = self.rirs.samples(rng.randrange(len(self.rirs))) if self.rirs is not None \
                else self._synthetic_rir(rng)
            direct = int(np.argmax(np.abs(rir)))
            rir = rir[max(0, direct - 16):]
            level = _rms(x)
            x = fftconvolve(x, rir)[:len(x)].astype(np.float32)
            x *= level / _rms(x)
        # Background noise / music at random SNR.
        if rng.random() < 0.55 * s:
            n = self.noise.random_chunk(rng, len(x)) if self.noise is not None \
                else self._coloured_noise(rng, len(x))
            snr = rng.uniform(0, 25)
            x = x + n * (_rms(x) / _rms(n)) / (10 ** (snr / 20))
        # Babble: several overlapping talkers, like meeting crosstalk.
        if rng.random() < 0.2 * s:
            b = self._babble(rng, len(x))
            if b is not None:
                snr = rng.uniform(5, 20)
                x = x + b * (_rms(x) / _rms(b)) / (10 ** (snr / 20))
        # Microphone / channel colouration: random band limits.
        if rng.random() < 0.4 * s:
            low = rng.uniform(40, 350)
            high = rng.uniform(3400, 7800)
            sos = butter(2, [low, high], btype='bandpass', fs=SAMPLE_RATE, output='sos')
            x = sosfilt(sos, x).astype(np.float32)
        # Level, occasional hard clipping, low-level hiss, int16 quantisation.
        target_db = rng.uniform(-40, -12)
        x = x * (10 ** (target_db / 20) / _rms(x))
        if rng.random() < 0.05 * s:
            x = x * rng.uniform(2, 6)
        if rng.random() < 0.2 * s:
            x = x + np.random.default_rng(rng.randrange(1 << 30)).standard_normal(len(x)).astype(np.float32) \
                * 10 ** (rng.uniform(-80, -60) / 20)
        x = np.clip(np.round(x * 32767), -32768, 32767) / 32768.0
        return x.astype(np.float32)


class TrainSet(torch.utils.data.Dataset):
    """Items are (store_index, item_index) pairs chosen by the sampler."""

    def __init__(self, stores, far_field, frontend_state, augmenter, seed=0):
        self.stores, self.far_field = stores, far_field
        self.frontend = Frontend(frontend_state)
        self.augmenter = augmenter
        if augmenter is not None and augmenter.babble is None:
            augmenter.speech_pool = list(stores)
        self.seed = seed

    def __len__(self):
        return sum(len(s) for s in self.stores)

    def __getitem__(self, key):
        s, i, salt = key
        rng = random.Random((self.seed << 40) ^ (salt << 20) ^ (s << 32) ^ i)
        store = self.stores[s]
        x = store.samples(i)
        if self.augmenter is not None:
            x = self.augmenter(x, rng, self.far_field[s])
        feats = self.frontend(x, dither=True, rng=np.random.default_rng(rng.randrange(1 << 30)))
        label = encode(store.texts[i])
        # Speed-up can make a label too long for CTC; the collate drops those.
        return feats, torch.tensor(label, dtype=torch.long)


BUCKET_FRAMES = 64


def batch_shape(frames, max_seconds, max_items):
    """Fixed (items, frames) per length bucket: the MPS backend caches a
    compiled graph per input shape, so free-form shapes grow memory without
    bound (observed: 23 GB after ~450 steps)."""
    padded = -(-frames // BUCKET_FRAMES) * BUCKET_FRAMES
    items = max(1, min(max_items, int(max_seconds * 100 // padded)))
    return items, padded


def collate(batch, spec_augment=True, max_seconds=None, max_items=None):
    batch = [(f, l) for f, l in batch if ctc_min_frames(l.tolist()) <= f.shape[1] // 2 - 1]
    padded = None
    if max_seconds is not None and batch:
        items, padded = batch_shape(max(f.shape[1] for f, _ in batch), max_seconds, max_items)
        # Trim or repeat items to the bucket's size; SpecAugment still makes
        # repeated rows differ.
        batch = [batch[i % len(batch)] for i in range(items)]
    lengths = torch.tensor([f.shape[1] for f, _ in batch])
    feats = torch.zeros(len(batch), 64, padded or int(lengths.max()))
    for i, (f, _) in enumerate(batch):
        feats[i, :, :f.shape[1]] = f
        if spec_augment:
            _spec_augment(feats[i], f.shape[1])
    labels = torch.cat([l for _, l in batch])
    label_lengths = torch.tensor([len(l) for _, l in batch])
    return feats, lengths, labels, label_lengths


def _spec_augment(f, valid):
    # Milder than NeMo's pretraining recipe (5x rect 50x120): fine-tuning.
    for _ in range(2):
        w = random.randint(0, 12)
        s = random.randint(0, 64 - w)
        f[s:s + w, :valid] = 0
    for _ in range(2):
        w = random.randint(0, min(40, max(1, valid // 8)))
        s = random.randint(0, max(0, valid - w))
        f[:, s:s + w] = 0


class MixedBatchSampler(torch.utils.data.Sampler):
    """Weighted mix of stores, grouped by duration to limit padding."""

    def __init__(self, stores, weights, max_seconds, max_items, steps, seed=0):
        self.stores, self.max_seconds, self.max_items = stores, max_seconds, max_items
        total = sum(weights)
        self.weights = [w / total for w in weights]
        self.steps, self.seed = steps, seed

    def __len__(self):
        return self.steps

    def __iter__(self):
        rng = random.Random(self.seed)
        produced, salt = 0, 0
        while produced < self.steps:
            pool = []
            for _ in range(self.max_items * 50):
                s = rng.choices(range(len(self.stores)), self.weights)[0]
                i = rng.randrange(len(self.stores[s]))
                pool.append((self.stores[s].lengths[i], s, i))
            pool.sort()
            batches, current, seconds = [], [], 0.0
            for n, s, i in pool:
                dur = n / SAMPLE_RATE * 1.1  # headroom for 0.9x speed
                # Pool is sorted ascending, so this item is the batch's longest.
                if current and (len(current) >= self.max_items or dur * (len(current) + 1) > self.max_seconds):
                    batches.append(current)
                    current = []
                salt += 1
                current.append((s, i, salt))
            if current:
                batches.append(current)
            rng.shuffle(batches)
            for b in batches:
                if produced >= self.steps:
                    return
                produced += 1
                yield b
