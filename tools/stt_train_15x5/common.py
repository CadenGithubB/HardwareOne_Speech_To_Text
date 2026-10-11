"""Shared pieces for QuartzNet fine-tuning (5x5 and 15x5).

Copied from experiments/stt_train/common.py: the block builder reads every
block (filters, repeat, kernel, stride, dilation, residual) from the NeMo
config, so the 15x5 config (18 blocks, 15 of them residual with R=5) loads as is.
Added 2026-10-09: QuartzNet(config, fast=True), the training speed path (off by
default, so evaluate.py / benchmark.py / filter_store.py run the plain model).
It computes the same function: depthwise convs get a faster backward on MPS
(DepthwiseConv1d) and the length masks are built once per forward.

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

class _DepthwiseConv1dFn(torch.autograd.Function):
    """Stride-1 depthwise conv1d with 2*pad == dilation*(K-1) (output keeps T).

    Forward is the stock grouped conv. Backward is built from forward convs,
    because MPS's own depthwise backward is slow (one K=75 layer at 1x512x768:
    12.4 ms forward+backward, 3.1 ms this way; the 15x5's optimizer step went
    from 3.93 to 1.41 s, 2026-10-09):
      grad_x = the same conv with the flipped kernel (same padding);
      grad_w = x padded, correlated with grad_out as the kernel, every
               dilation-th tap. With B > 1 the batch is folded into time with
               2*pad zero gaps, so it is one conv instead of B.
    Same maths, only the fp32 summation order of grad_w differs (worst tensor
    ~1e-6 relative)."""

    @staticmethod
    def forward(ctx, x, weight, pad, dilation):
        ctx.save_for_backward(x, weight)
        ctx.pad, ctx.dilation = pad, dilation
        return F.conv1d(x, weight, padding=pad, dilation=dilation, groups=weight.shape[0])

    @staticmethod
    def backward(ctx, grad):
        x, weight = ctx.saved_tensors
        pad, dilation = ctx.pad, ctx.dilation
        channels, batch, frames = weight.shape[0], x.shape[0], x.shape[-1]
        grad = grad.contiguous()
        grad_x = grad_w = None
        if ctx.needs_input_grad[0]:
            grad_x = F.conv1d(grad, weight.flip(-1), padding=pad, dilation=dilation, groups=channels)
        if ctx.needs_input_grad[1]:
            if batch > 1:
                span = frames + 2 * pad
                xp = F.pad(x, (pad, pad)).transpose(0, 1).reshape(1, channels, batch * span)
                kernel = F.pad(grad, (0, 2 * pad)).transpose(0, 1).reshape(channels, 1, batch * span)
                grad_w = F.conv1d(xp, kernel[:, :, :-2 * pad].contiguous(), groups=channels)
            else:
                xp = F.pad(x, (pad, pad)).transpose(0, 1).reshape(1, channels, frames + 2 * pad)
                grad_w = F.conv1d(xp, grad.transpose(0, 1).contiguous(), groups=channels)
            grad_w = grad_w.reshape(channels, 1, -1)[:, :, ::dilation].contiguous()
        return grad_x, grad_w, None, None


class DepthwiseConv1d(nn.Conv1d):
    """nn.Conv1d (same parameters and state-dict names) that uses
    _DepthwiseConv1dFn while `fast` is set, gradients are being recorded and
    the call is one it is exact for: MPS (where it was measured; CPU and CUDA
    keep their own backward), fp32, no autocast, and a layer that is stride-1
    depthwise with symmetric 'same' zero padding and no bias. Anything else
    runs the stock conv."""

    fast = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        (k,), (s,), (d,), p = self.kernel_size, self.stride, self.dilation, self.padding
        self.custom_ok = (s == 1 and self.bias is None and self.padding_mode == 'zeros'
                          and self.groups == self.in_channels == self.out_channels
                          and isinstance(p, tuple) and p[0] > 0 and 2 * p[0] == d * (k - 1))

    def forward(self, x):
        if (self.fast and self.custom_ok and torch.is_grad_enabled() and x.device.type == 'mps'
                and x.dtype == self.weight.dtype == torch.float32 and not torch.is_autocast_enabled('mps')):
            return _DepthwiseConv1dFn.apply(x, self.weight, self.padding[0], self.dilation[0])
        return super().forward(x)


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
                dw = DepthwiseConv1d(channels, channels, self.kernel, stride=stride,
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

    def forward_fast(self, x, lengths, mask):
        """forward() with the [B,1,T] bool mask passed in and handed on, and
        without the mask between the depthwise and the 1x1 conv: the 1x1 conv,
        frozen BN and ReLU act per frame, so what they leave in padded frames
        is masked off before the next conv, the residual and the head."""
        residual_in, residual_mask = x, mask
        for r, (convs, norm) in enumerate(zip(self.convs, self.norms)):
            x = convs[0](x * mask)
            if r == 0 and self.stride > 1:
                lengths = self.out_lengths(lengths)
                mask = _mask(lengths, x.shape[-1], x.device, torch.bool)
            elif mask.shape[-1] != x.shape[-1]:  # a conv that does not keep T (even kernel)
                mask = _mask(lengths, x.shape[-1], x.device, torch.bool)
            if len(convs) > 1:
                if norm.training:  # BN batch statistics would count the padded frames
                    x = x * mask
                x = convs[1](x)
            x = norm(x)
            if r + 1 < self.repeat:
                x = F.relu(x)
        if self.residual:
            x = x + self.res_norm(self.res_conv(residual_in * residual_mask))
        return F.relu(x), lengths, mask


def _mask(lengths, size, device, dtype=torch.float32):
    # x * bool mask gives the same bits as x * float mask and keeps x's dtype.
    return (torch.arange(size, device=device)[None, :] < lengths[:, None]).unsqueeze(1).to(dtype)


class QuartzNet(nn.Module):
    def __init__(self, config, fast=False):
        super().__init__()
        blocks = config['encoder']['params']['jasper']
        channels = config['encoder']['params'].get('feat_in', 64)
        self.blocks = nn.ModuleList()
        for cfg in blocks:
            self.blocks.append(Block(cfg, channels))
            channels = cfg['filters']
        self.head = nn.Conv1d(channels, len(VOCAB) + 1, 1, bias=True)
        self.set_fast(fast)

    def set_fast(self, fast):
        """Training speed path (train.py --fast-dwconv): the depthwise convs'
        own backward and masks built once per forward. Same function and
        parameters either way; returns how many depthwise convs take the
        custom backward (76 for the 15x5, whose strided C1 cannot; 0 if off)."""
        self.fast = bool(fast)
        dws = [m for m in self.modules() if isinstance(m, DepthwiseConv1d)]
        for m in dws:
            m.fast = self.fast
        return sum(m.custom_ok for m in dws) if self.fast else 0

    def forward(self, features, lengths):
        """features [B,64,T] -> log-probs [B,T',29], lengths [B]."""
        x = features
        if self.fast and not torch.is_autocast_enabled(x.device.type):
            mask = _mask(lengths, x.shape[-1], x.device, torch.bool)
            for block in self.blocks:
                x, lengths, mask = block.forward_fast(x, lengths, mask)
            return self.head(x * mask).transpose(1, 2), lengths
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
        self.fb = state['preprocessor.featurizer.fb'].float()[0]  # [mels,257]: 64 QuartzNet, 80 Citrinet

    def __call__(self, samples, dither=True, rng=None):
        x = torch.from_numpy(np.ascontiguousarray(samples, dtype=np.float32))
        if dither:
            gen = rng if rng is not None else np.random
            x = x + torch.from_numpy(gen.standard_normal(len(x)).astype(np.float32)) * 1e-5
        x = torch.cat((x[:1], x[1:] - 0.97 * x[:-1]))
        valid = math.ceil(len(samples) / HOP)
        spec = torch.stft(x, n_fft=512, hop_length=HOP, win_length=len(self.window), window=self.window,
                          center=True, return_complex=True)
        mel = self.fb @ spec.abs().square()
        feats = torch.log(mel + 2 ** -24)[:, :valid]
        precise = feats.double()
        mean = precise.mean(dim=-1, keepdim=True)
        var = (precise - mean).square().sum(dim=-1, keepdim=True) / max(valid - 1, 1)
        feats = (feats - mean.float()) / (var.float().sqrt() + 1e-5)
        return feats  # [mels, T]


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
