"""Citrinet (NeMo ConvASREncoder with SE, 8x time reduction) for fine-tuning.

Mirrors common.QuartzNet: NeMo parameter names are kept so a fine-tuned state
dict drops straight back into model_weights.ckpt, BatchNorm layers stay
unfolded, and every convolution input is masked to the valid frames so a
padded batch gives the same result as one utterance at a time (the device
always runs one exact-length utterance).

Differences from QuartzNet, all read from model_config.yaml:
  * squeeze-and-excitation after the last sub-block of every block:
    x * sigmoid(W2 relu(W1 mean_t(x))), mean over the VALID frames;
  * stride_last blocks put their stride on the last sub-block's depthwise
    conv, and residual_mode stride_add strides the 1x1 residual conv too;
  * output is WordPiece tokens (vocab.txt, "##" = continuation), blank last.

Checked against NVIDIA's published LibriSpeech numbers by eval_citrinet.py.
"""
from pathlib import Path
import re

import torch
from torch import nn
import torch.nn.functional as F
import yaml

from common import _mask


def is_citrinet(config):
    return 'jasper' in config.get('encoder', {}) and config.get('tokenizer') is not None


class SqueezeExcite(nn.Module):
    def __init__(self, channels, reduction=8):
        super().__init__()
        self.fc1 = nn.Linear(channels, channels // reduction, bias=False)
        self.fc2 = nn.Linear(channels // reduction, channels, bias=False)

    def forward(self, x, lengths):
        mask = _mask(lengths, x.shape[-1], x.device)                  # [B,1,T]
        mean = (x * mask).sum(-1) / lengths.clamp(min=1)[:, None].to(x.dtype)
        scale = torch.sigmoid(self.fc2(F.relu(self.fc1(mean))))        # [B,C]
        return x * scale[:, :, None]


class CitrinetBlock(nn.Module):
    def __init__(self, cfg, in_channels):
        super().__init__()
        assert cfg.get('separable', False), 'Citrinet blocks are separable'
        self.repeat = cfg['repeat']
        self.kernel = cfg['kernel'][0]
        self.stride = cfg['stride'][0]
        self.dilation = cfg['dilation'][0]
        self.stride_last = cfg.get('stride_last', False)
        out = cfg['filters']
        self.pad = self.dilation * (self.kernel - 1) // 2
        self.dw, self.pw, self.norms, self.keys = nn.ModuleList(), nn.ModuleList(), nn.ModuleList(), []
        channels = in_channels
        for r in range(self.repeat):
            strided = (r == self.repeat - 1) if self.stride_last else (r == 0)
            self.dw.append(nn.Conv1d(channels, channels, self.kernel, stride=self.stride if strided else 1,
                                     padding=self.pad, dilation=self.dilation, groups=channels, bias=False))
            self.pw.append(nn.Conv1d(channels, out, 1, bias=False))
            self.norms.append(nn.BatchNorm1d(out, eps=1e-3, momentum=0.05))
            base = r * 5  # dw, pw, bn, relu, dropout
            self.keys.append((f'mconv.{base}.conv', f'mconv.{base + 1}.conv', f'mconv.{base + 2}'))
            channels = out
        self.strided_index = (self.repeat - 1) if self.stride_last else 0
        self.se_key = f'mconv.{(self.repeat - 1) * 5 + 3}'
        self.se = SqueezeExcite(out) if cfg.get('se', False) else None
        self.residual = cfg.get('residual', False)
        if self.residual:
            res_stride = self.stride if cfg.get('residual_mode', 'add') == 'stride_add' else 1
            self.res_conv = nn.Conv1d(in_channels, out, 1, stride=res_stride, bias=False)
            self.res_norm = nn.BatchNorm1d(out, eps=1e-3, momentum=0.05)

    def _strided_lengths(self, lengths):
        return (lengths + 2 * self.pad - self.dilation * (self.kernel - 1) - 1) // self.stride + 1

    def forward(self, x, lengths):
        residual_in, residual_len = x, lengths
        for r in range(self.repeat):
            x = self.dw[r](x * _mask(lengths, x.shape[-1], x.device))
            if r == self.strided_index and self.stride > 1:
                lengths = self._strided_lengths(lengths)
            x = self.norms[r](self.pw[r](x * _mask(lengths, x.shape[-1], x.device)))
            if r + 1 < self.repeat:
                x = F.relu(x)
        if self.se is not None:
            x = self.se(x, lengths)
        if self.residual:
            y = self.res_conv(residual_in * _mask(residual_len, residual_in.shape[-1], residual_in.device))
            x = x + self.res_norm(y)
        return F.relu(x), lengths


class Tokenizer:
    """BERT-style WordPiece over the model's vocab.txt (greedy longest match)."""

    def __init__(self, vocab):
        self.vocab = list(vocab)
        self.ids = {t: i for i, t in enumerate(self.vocab)}
        self.unk = self.ids.get('[UNK]', 1)
        self.special = {i for i, t in enumerate(self.vocab) if t.startswith('[') and t.endswith(']')}

    def encode(self, text):
        # BERT pre-tokenization (as the LibriSpeech tokenizer was trained):
        # punctuation is its own word, so "it's" -> it ' s.
        out = []
        for word in re.findall(r"[^\s']+|'", text):
            start, pieces = 0, []
            while start < len(word):
                end = len(word)
                while end > start:
                    piece = word[start:end] if start == 0 else '##' + word[start:end]
                    if piece in self.ids:
                        pieces.append(self.ids[piece])
                        break
                    end -= 1
                if end == start:
                    pieces = [self.unk]
                    break
                start = end
            out.extend(pieces)
        return out

    def decode(self, ids):
        text = ''
        for i in ids:
            if i in self.special:
                continue
            token = self.vocab[i]
            text += token[2:] if token.startswith('##') else ' ' + token
        text = re.sub(r"\s*'\s*", "'", text)  # it ' s -> it's
        return re.sub(r'\s+', ' ', text).strip()


class Citrinet(nn.Module):
    def __init__(self, config, vocab):
        super().__init__()
        enc = config['encoder']
        channels = enc.get('feat_in', 80)
        self.feat_in = channels
        self.blocks = nn.ModuleList()
        for cfg in enc['jasper']:
            self.blocks.append(CitrinetBlock(cfg, channels))
            channels = cfg['filters']
        self.tokenizer = Tokenizer(vocab)
        self.blank = config['decoder']['num_classes']
        assert self.blank == len(self.tokenizer.vocab), 'decoder size != vocab.txt'
        self.head = nn.Conv1d(channels, self.blank + 1, 1, bias=True)

    def forward(self, features, lengths):
        """features [B,80,T] -> logits [B,T/8,vocab+1], lengths [B]."""
        x = features
        for block in self.blocks:
            x, lengths = block(x, lengths)
        logits = self.head(x * _mask(lengths, x.shape[-1], x.device))
        return logits.transpose(1, 2), lengths

    def decode(self, log_probs, lengths):
        ids = log_probs.argmax(dim=-1).cpu().numpy()
        out = []
        for row, n in zip(ids, lengths.cpu().tolist()):
            prev, keep = None, []
            for t in row[:n]:
                if t != prev and t != self.blank:
                    keep.append(int(t))
                prev = t
            out.append(self.tokenizer.decode(keep))
        return out

    def encode_text(self, text):
        return self.tokenizer.encode(text)

    # --- NeMo name mapping -------------------------------------------------
    def _pairs(self):
        bn = ('weight', 'bias', 'running_mean', 'running_var', 'num_batches_tracked')
        for b, block in enumerate(self.blocks):
            p = f'encoder.encoder.{b}.'
            for dw, pw, norm, (k0, k1, kn) in zip(block.dw, block.pw, block.norms, block.keys):
                yield p + k0 + '.weight', dw.weight
                yield p + k1 + '.weight', pw.weight
                for name in bn:
                    yield f'{p}{kn}.{name}', getattr(norm, name)
            if block.se is not None:
                yield f'{p}{block.se_key}.fc.0.weight', block.se.fc1.weight
                yield f'{p}{block.se_key}.fc.2.weight', block.se.fc2.weight
            if block.residual:
                yield p + 'res.0.0.conv.weight', block.res_conv.weight
                for name in bn:
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


def load_vocab(directory):
    return (Path(directory) / 'vocab.txt').read_text().splitlines()


def build(directory):
    """(model, config, state) from an extracted .nemo directory."""
    directory = Path(directory)
    config = yaml.safe_load((directory / 'model_config.yaml').read_text())
    state = torch.load(directory / 'model_weights.ckpt', weights_only=True, map_location='cpu')
    model = Citrinet(config, load_vocab(directory)).load_nemo(state)
    return model, config, state
