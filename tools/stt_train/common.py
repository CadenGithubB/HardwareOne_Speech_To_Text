"""Shared pieces for QuartzNet5x5 fine-tuning.

The trainable model keeps NeMo's parameter names and BatchNorm layers, so a
fine-tuned state dict drops straight back into model_weights.ckpt and the
existing experiments/stt_p4 export path (which folds BN) can consume it.

The feature code mirrors experiments/stt_p4/frontend/reference_frontend.py,
which is the device contract: pre-emphasis 0.97, 512-point STFT with the
checkpoint's 320-sample window and 160-sample hop, the checkpoint mel bank,
log with a 2^-24 guard, and whole-utterance CMVN with unbiased variance.
Only the dither differs: training uses random Gaussian dither at the same
1e-5 amplitude instead of the fixed deployment sequence.
"""
from pathlib import Path
import math
import re

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F
import yaml

VOCAB = " abcdefghijklmnopqrstuvwxyz'"
BLANK = len(VOCAB)  # 28
CHAR_TO_ID = {c: i for i, c in enumerate(VOCAB)}
SAMPLE_RATE = 16000
HOP = 160
MAX_SAMPLES = 480000  # device frontend limit (30 s); dictation uses <= 20 s


def normalize_text(text):
    """Map a transcript onto the 28-character model alphabet."""
    text = text.lower().replace('-', ' ')
    text = re.sub(r"[^a-z' ]", ' ', text)
    text = re.sub(r"\s+'|'\s+", ' ', f' {text} ')  # stray quote marks
    return re.sub(r'\s+', ' ', text).strip()


def encode(text):
    return [CHAR_TO_ID[c] for c in text]


def ctc_min_frames(ids):
    """Output frames CTC needs: one per label plus a blank between repeats."""
    return len(ids) + sum(1 for a, b in zip(ids, ids[1:]) if a == b)


# ---------------------------------------------------------------- checkpoint

def load_checkpoint(directory):
    directory = Path(directory)
    config = yaml.safe_load((directory / 'model_config.yaml').read_text())
    state = torch.load(directory / 'model_weights.ckpt', weights_only=True, map_location='cpu')
    return config, state


def save_checkpoint(model, template_state, config, directory):
    """Write model weights back under the original NeMo keys."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    out = {k: v.clone() for k, v in template_state.items()}
    for key, value in model.nemo_state_dict().items():
        if key not in out or out[key].shape != value.shape:
            raise KeyError(f'unexpected tensor {key}')
        out[key] = value.detach().to('cpu', out[key].dtype).clone()
    tmp = directory / 'model_weights.ckpt.tmp'
    torch.save(out, tmp)
    tmp.replace(directory / 'model_weights.ckpt')
    (directory / 'model_config.yaml').write_text(yaml.safe_dump(config, sort_keys=False))


# --------------------------------------------------------------------- model

class Block(nn.Module):
    """One Jasper/QuartzNet block with NeMo-compatible child names."""

    def __init__(self, cfg, in_channels):
        super().__init__()
        self.separable = cfg.get('separable', False)
        self.repeat = cfg['repeat']
        self.kernel = cfg['kernel'][0]
        self.stride = cfg['stride'][0]
        self.dilation = cfg['dilation'][0]
        out = cfg['filters']
        self.pad = self.dilation * (self.kernel - 1) // 2
        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()
        self.keys = []  # (kind, nemo_prefix) per parameterised layer
        channels = in_channels
        width = 5 if self.separable else 4
        for r in range(self.repeat):
            base = r * width
            stride = self.stride if r == 0 else 1
            if self.separable:
                dw = nn.Conv1d(channels, channels, self.kernel, stride=stride,
                               padding=self.pad, dilation=self.dilation, groups=channels, bias=False)
                pw = nn.Conv1d(channels, out, 1, bias=False)
                self.convs.append(nn.ModuleList([dw, pw]))
                self.keys.append((f'mconv.{base}.conv', f'mconv.{base + 1}.conv', f'mconv.{base + 2}'))
            else:
                conv = nn.Conv1d(channels, out, self.kernel, stride=stride,
                                 padding=self.pad, dilation=self.dilation, bias=False)
                self.convs.append(nn.ModuleList([conv]))
                self.keys.append((f'mconv.{base}.conv', None, f'mconv.{base + 1}'))
            self.norms.append(nn.BatchNorm1d(out, eps=1e-3, momentum=0.05))
            channels = out
        self.residual = cfg.get('residual', False)
        if self.residual:
            self.res_conv = nn.Conv1d(in_channels, out, 1, bias=False)
            self.res_norm = nn.BatchNorm1d(out, eps=1e-3, momentum=0.05)

    def out_lengths(self, lengths):
        # Same arithmetic as NeMo's MaskedConv1d for the strided first conv.
        return (lengths + 2 * self.pad - self.dilation * (self.kernel - 1) - 1) // self.stride + 1

    def forward(self, x, lengths):
        residual_in, residual_len = x, lengths
        for r, (convs, norm) in enumerate(zip(self.convs, self.norms)):
            x = x * _mask(lengths, x.shape[-1], x.device)
            x = convs[0](x)
            if r == 0 and self.stride > 1:
                lengths = self.out_lengths(lengths)
            if len(convs) > 1:
                x = x * _mask(lengths, x.shape[-1], x.device)
                x = convs[1](x)
            x = norm(x)
            if r + 1 < self.repeat:
                x = F.relu(x)
        if self.residual:
            y = self.res_conv(residual_in * _mask(residual_len, residual_in.shape[-1], residual_in.device))
            x = x + self.res_norm(y)
        return F.relu(x), lengths


def _mask(lengths, size, device):
    return (torch.arange(size, device=device)[None, :] < lengths[:, None]).unsqueeze(1).to(torch.float32)


class QuartzNet(nn.Module):
    def __init__(self, config):
        super().__init__()
        blocks = config['encoder']['params']['jasper']
        channels = config['encoder']['params'].get('feat_in', 64)
        self.blocks = nn.ModuleList()
        for cfg in blocks:
            self.blocks.append(Block(cfg, channels))
            channels = cfg['filters']
        self.head = nn.Conv1d(channels, len(VOCAB) + 1, 1, bias=True)

    def forward(self, features, lengths):
        """features [B,64,T] -> log-probs [B,T',29], lengths [B]."""
        x = features
        for block in self.blocks:
            x, lengths = block(x, lengths)
        logits = self.head(x * _mask(lengths, x.shape[-1], x.device))
        return logits.transpose(1, 2), lengths

    # --- NeMo name mapping -------------------------------------------------
    def _pairs(self):
        for b, block in enumerate(self.blocks):
            p = f'encoder.encoder.{b}.'
            for convs, norm, (k0, k1, kn) in zip(block.convs, block.norms, block.keys):
                yield p + k0 + '.weight', convs[0].weight
                if k1:
                    yield p + k1 + '.weight', convs[1].weight
                for name in ('weight', 'bias', 'running_mean', 'running_var', 'num_batches_tracked'):
                    yield f'{p}{kn}.{name}', getattr(norm, name)
            if block.residual:
                yield p + 'res.0.0.conv.weight', block.res_conv.weight
                for name in ('weight', 'bias', 'running_mean', 'running_var', 'num_batches_tracked'):
                    yield f'{p}res.0.1.{name}', getattr(block.res_norm, name)
        yield 'decoder.decoder_layers.0.weight', self.head.weight
        yield 'decoder.decoder_layers.0.bias', self.head.bias

    def load_nemo(self, state):
        with torch.no_grad():
            for key, tensor in self._pairs():
                src = state[key]
                if src.shape != tensor.shape:
                    raise ValueError(f'{key}: {tuple(src.shape)} != {tuple(tensor.shape)}')
                tensor.copy_(src)
        return self

    def nemo_state_dict(self):
        return {key: tensor for key, tensor in self._pairs()}


# ------------------------------------------------------------------ frontend

class Frontend:
    """Numpy/torch per-utterance features matching the device contract."""

    def __init__(self, state):
        self.window = state['preprocessor.featurizer.window'].float()
        self.fb = state['preprocessor.featurizer.fb'].float()[0]  # [64,257]

    def __call__(self, samples, dither=True, rng=None):
        x = torch.from_numpy(np.ascontiguousarray(samples, dtype=np.float32))
        if dither:
            gen = rng if rng is not None else np.random
            x = x + torch.from_numpy(gen.standard_normal(len(x)).astype(np.float32)) * 1e-5
        x = torch.cat((x[:1], x[1:] - 0.97 * x[:-1]))
        valid = math.ceil(len(samples) / HOP)
        spec = torch.stft(x, n_fft=512, hop_length=HOP, win_length=320, window=self.window,
                          center=True, return_complex=True)
        mel = self.fb @ spec.abs().square()
        feats = torch.log(mel + 2 ** -24)[:, :valid]
        precise = feats.double()
        mean = precise.mean(dim=-1, keepdim=True)
        var = (precise - mean).square().sum(dim=-1, keepdim=True) / max(valid - 1, 1)
        feats = (feats - mean.float()) / (var.float().sqrt() + 1e-5)
        return feats  # [64, T]


# ------------------------------------------------------------------- decode

def greedy_decode(log_probs, lengths):
    ids = log_probs.argmax(dim=-1).cpu().numpy()
    out = []
    for row, n in zip(ids, lengths.cpu().tolist()):
        prev, chars = None, []
        for t in row[:n]:
            if t != prev and t != BLANK:
                chars.append(VOCAB[t])
            prev = t
        out.append(re.sub(r'\s+', ' ', ''.join(chars)).strip())
    return out


def word_errors(reference, hypothesis):
    a, b = reference.split(), hypothesis.split()
    row = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        nxt = [i]
        for j, right in enumerate(b, 1):
            nxt.append(min(nxt[-1] + 1, row[j] + 1, row[j - 1] + (left != right)))
        row = nxt
    return row[-1]
