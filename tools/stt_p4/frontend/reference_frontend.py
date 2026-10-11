"""Independent Torch frontend using the portable deployment dither sequence."""
import math
import numpy as np
import torch

DITHER_SEED = 0x12345678
MAX_SAMPLES = 480000

def portable_dither(count, seed=DITHER_SEED):
    """Unit Gaussian float32 values; reset only at an utterance boundary."""
    if not 0 < seed <= 0xffffffff:
        raise ValueError('Dither seed must be a nonzero uint32')
    pairs = (count + 1) // 2
    uniforms = np.empty((pairs, 2), dtype=np.float32)
    state = seed
    for i in range(pairs):
        for j in range(2):
            state ^= (state << 13) & 0xffffffff
            state ^= state >> 17
            state ^= (state << 5) & 0xffffffff
            uniforms[i, j] = ((state >> 8) + 1) / 16777217.0
    radius = np.sqrt(np.float32(-2.0) * np.log(uniforms[:, 0]))
    angle = np.float32(2.0 * math.pi) * uniforms[:, 1]
    noise = np.empty(pairs * 2, dtype=np.float32)
    noise[0::2] = radius * np.cos(angle)
    noise[1::2] = radius * np.sin(angle)
    return noise[:count]

def features_pcm16(pcm, state, seed=DITHER_SEED, dither=True):
    """Return contiguous float32 [T,64], no padding; T=ceil(N/160)."""
    pcm = np.asarray(pcm)
    if pcm.dtype != np.int16 or pcm.ndim != 1 or not 320 <= len(pcm) <= MAX_SAMPLES:
        raise ValueError('Expected 320..480000 mono int16 samples at 16kHz')
    return features_float(pcm.astype(np.float32) / np.float32(32768), state, seed, dither)

def features_float(samples, state, seed=DITHER_SEED, dither=True):
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim != 1 or not 320 <= len(samples) <= MAX_SAMPLES or not np.isfinite(samples).all():
        raise ValueError('Expected finite mono waveform, 320..480000 samples')
    x = torch.from_numpy(samples.copy()).unsqueeze(0)
    if dither:
        x = x + torch.from_numpy(portable_dither(len(samples), seed)).unsqueeze(0) * 1e-5
    x = torch.cat((x[:, :1], x[:, 1:] - 0.97 * x[:, :-1]), dim=1)
    valid = math.ceil(len(samples) / 160)
    spectrum = torch.stft(x, n_fft=512, hop_length=160, win_length=320,
                         window=state['preprocessor.featurizer.window'],
                         center=True, return_complex=True)
    mel = torch.matmul(state['preprocessor.featurizer.fb'], spectrum.abs().square())
    features = torch.log(mel + 2**-24)[:, :, :valid]
    # Stable reduction: float32 reductions can shift silent-bin means by one ULP.
    # Preserve unbiased sample variance, but accumulate in float64 on every host.
    precise = features.double()
    mean = precise.mean(dim=-1, keepdim=True)
    variance = (precise - mean).square().sum(dim=-1, keepdim=True) / (valid - 1)
    denominator = variance.float().sqrt() + 1e-5
    features = (features - mean.float()) / denominator
    return features[0].transpose(0, 1).contiguous().numpy()
