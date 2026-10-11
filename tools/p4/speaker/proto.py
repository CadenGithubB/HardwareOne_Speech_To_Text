#!/usr/bin/env python3
"""Speaker-label prototype on the Mac: clova Fast ResNet-34 (ResNetSE34L, 1.4 M weights) + online clustering.

  proto.py [--convs 20] [--turns 24] [--out results.json]

Builds synthetic conversations of 2-4 known speakers from the speech stores (each turn one utterance of
1-10 s; the -g2 stores are the simulated glasses channel), embeds every turn, then labels turns online the way
the P4 would: a turn joins the closest speaker so far if the cosine similarity is >= threshold, else starts a
new speaker (running-mean centroids). Reports, per store and threshold: label accuracy under the best
speaker mapping, mean |found - true| speaker count, and the pairwise equal error rate by turn length.
Numbers only.
"""
import argparse
import itertools
import json
import math
import os
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

HERE = Path(__file__).parent
STT = Path(os.environ.get('STT_ROOT', 'stt-data'))
# clovaai/voxceleb_trainer checkout with baseline_lite_ap.model beside it (kept out of git)
CLOVA = Path(os.environ.get('HW1_SPEAKER_CLOVA', STT / 'hw1-work/speaker/clova'))
sys.path.insert(0, str(CLOVA))
from models.ResNetBlocks import SEBasicBlock  # noqa: E402

STORES = STT / 'stores'
SR = 16000


def mel_fbank(n_freqs=257, n_mels=40, sr=SR, f_min=0.0, f_max=8000.0):
    """torchaudio.functional.melscale_fbanks(norm=None, mel_scale='htk') as [n_freqs, n_mels]."""
    hz2mel = lambda f: 2595.0 * math.log10(1.0 + f / 700.0)
    mel2hz = lambda m: 700.0 * (10 ** (m / 2595.0) - 1.0)
    all_freqs = torch.linspace(0, sr // 2, n_freqs)
    m_pts = torch.linspace(hz2mel(f_min), hz2mel(f_max), n_mels + 2)
    f_pts = torch.tensor([mel2hz(float(m)) for m in m_pts])
    f_diff = f_pts[1:] - f_pts[:-1]
    slopes = f_pts.unsqueeze(0) - all_freqs.unsqueeze(1)
    down = (-1.0 * slopes[:, :-2]) / f_diff[:-1]
    up = slopes[:, 2:] / f_diff[1:]
    return torch.clamp(torch.min(down, up), min=0.0)


FB = mel_fbank()
WIN = torch.hamming_window(400, periodic=True)


def features(x):
    """x: float32 [N] at 16 kHz -> instance-normalised log mel [1, 1, 40, T] (the model's own front end)."""
    t = torch.from_numpy(np.asarray(x, dtype=np.float32))
    spec = torch.stft(t, n_fft=512, hop_length=160, win_length=400, window=WIN, center=True, pad_mode='reflect',
                      return_complex=True).abs() ** 2                      # [257, T]
    mel = (FB.T @ spec) + 1e-6                                              # [40, T]
    mel = mel.log()
    mel = (mel - mel.mean(dim=1, keepdim=True)) / torch.sqrt(mel.var(dim=1, unbiased=False, keepdim=True) + 1e-5)
    return mel.unsqueeze(0).unsqueeze(0)


class ResNetSE34L(nn.Module):
    """clova ResNetSE (num_filters 16-32-64-128, blocks 3-4-6-3, SAP pooling) without the torchaudio front end."""

    def __init__(self, n_out=512):
        super().__init__()
        nf, layers = [16, 32, 64, 128], [3, 4, 6, 3]
        self.inplanes = nf[0]
        self.conv1 = nn.Conv2d(1, nf[0], kernel_size=7, stride=(2, 1), padding=3, bias=False)
        self.bn1 = nn.BatchNorm2d(nf[0])
        self.relu = nn.ReLU(inplace=True)
        self.layer1 = self._make(nf[0], layers[0])
        self.layer2 = self._make(nf[1], layers[1], (2, 2))
        self.layer3 = self._make(nf[2], layers[2], (2, 2))
        self.layer4 = self._make(nf[3], layers[3], (1, 1))
        self.sap_linear = nn.Linear(nf[3], nf[3])
        self.attention = nn.Parameter(torch.zeros(nf[3], 1))
        self.fc = nn.Linear(nf[3], n_out)

    def _make(self, planes, blocks, stride=1):
        down = None
        if stride != 1 or self.inplanes != planes:
            down = nn.Sequential(nn.Conv2d(self.inplanes, planes, 1, stride=stride, bias=False), nn.BatchNorm2d(planes))
        out = [SEBasicBlock(self.inplanes, planes, stride, down)]
        self.inplanes = planes
        out += [SEBasicBlock(planes, planes) for _ in range(1, blocks)]
        return nn.Sequential(*out)

    def trunk(self, feats):
        x = self.relu(self.bn1(self.conv1(feats)))
        x = self.layer4(self.layer3(self.layer2(self.layer1(x))))
        return torch.mean(x, dim=2)                                         # [B, 128, T']

    def pool(self, frames):
        x = frames.permute(0, 2, 1)                                         # [B, T', 128]
        h = torch.tanh(self.sap_linear(x))
        w = F.softmax(torch.matmul(h, self.attention).squeeze(2), dim=1).unsqueeze(2)
        return self.fc(torch.sum(x * w, dim=1))

    def forward(self, feats):
        return self.pool(self.trunk(feats))


def load_model():
    m = ResNetSE34L()
    sd = torch.load(CLOVA / 'baseline_lite_ap.model', map_location='cpu')
    sd = {k[len('__S__.'):]: v for k, v in sd.items() if k.startswith('__S__.')}
    sd = {k: v for k, v in sd.items() if not k.startswith('torchfb') and not k.startswith('instancenorm')}
    missing, unexpected = m.load_state_dict(sd, strict=False)
    assert not missing and not unexpected, (missing, unexpected)
    return m.eval()


def load_store(name):
    d = json.loads((STORES / name / 'index.json').read_text())
    audio = np.memmap(STORES / name / 'audio.bin', dtype='<i2', mode='r')
    return d, audio


def conversations(name, n_convs, n_turns, seed, lo=1.0, hi=10.0):
    d, audio = load_store(name)
    by_spk = {}
    for i, (s, n) in enumerate(zip(d['speakers'], d['lengths'])):
        if lo <= n / SR <= hi:
            by_spk.setdefault(s, []).append(i)
    spks = [s for s, v in by_spk.items() if len(v) >= 6]
    rng = random.Random(seed)
    out = []
    for c in range(n_convs):
        k = [2, 3, 4][c % 3]
        chosen = rng.sample(spks, k)
        turns, last = [], None
        for _ in range(n_turns):
            s = rng.choice([x for x in chosen if x != last] if rng.random() < 0.8 and last else chosen)
            i = rng.choice(by_spk[s])
            turns.append((s, i))
            last = s
        out.append(turns)
    return d, audio, out


def online_labels(embs, threshold, max_speakers=8):
    cents, counts, labels = [], [], []
    for e in embs:
        if cents:
            sims = [float(np.dot(e, c / np.linalg.norm(c))) for c in cents]
            j = int(np.argmax(sims))
            if sims[j] >= threshold or len(cents) >= max_speakers:
                cents[j] = cents[j] + e
                counts[j] += 1
                labels.append(j)
                continue
        cents.append(e.copy())
        counts.append(1)
        labels.append(len(cents) - 1)
    return labels


def best_accuracy(true, pred):
    """Share of turns right under the best one-to-one mapping of clusters to speakers (either side may be larger)."""
    ts, ps = sorted(set(true)), sorted(set(pred))
    pairs = list(zip(true, pred))
    best = 0
    if len(ps) <= len(ts):
        for perm in itertools.permutations(ts, len(ps)):
            m = dict(zip(ps, perm))
            best = max(best, sum(1 for t, p in pairs if m[p] == t))
    else:
        for perm in itertools.permutations(ps, len(ts)):
            m = dict(zip(ts, perm))
            best = max(best, sum(1 for t, p in pairs if m[t] == p))
    return best / len(true)


def eer(scores, same):
    s, y = np.asarray(scores), np.asarray(same, dtype=bool)
    order = np.argsort(-s)
    s, y = s[order], y[order]
    tp = np.cumsum(y) / max(1, y.sum())
    fp = np.cumsum(~y) / max(1, (~y).sum())
    fnr = 1 - tp
    k = int(np.argmin(np.abs(fnr - fp)))
    return 100 * (fnr[k] + fp[k]) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--convs', type=int, default=21)
    ap.add_argument('--turns', type=int, default=24)
    ap.add_argument('--stores', default='librispeech-dev-clean,librispeech-dev-clean-g2,ami-ihm-validation,'
                                        'ami-ihm-validation-g2,voxpopuli-dev,voxpopuli-dev-g2')
    ap.add_argument('--out', default=str(STT / 'hw1-work/speaker/proto_results.json'))
    a = ap.parse_args()
    torch.set_num_threads(2)
    model = load_model()
    thresholds = [round(x, 2) for x in np.arange(0.30, 0.81, 0.05)]
    report = {}
    for store in a.stores.split(','):
        d, audio, convs = conversations(store, a.convs, a.turns, seed=20261011)
        cache = {}
        rows = []
        for conv in convs:
            embs, true, durs = [], [], []
            for s, i in conv:
                if i not in cache:
                    off, n = d['offsets'][i], d['lengths'][i]
                    x = np.asarray(audio[off:off + n], dtype=np.float32) / 32768.0
                    with torch.no_grad():
                        e = model(features(x))[0].numpy()
                    cache[i] = e / np.linalg.norm(e)
                embs.append(cache[i]); true.append(s); durs.append(d['lengths'][i] / SR)
            rows.append((embs, true, durs))
        # pairwise EER within conversations, by the shorter turn's length
        pairs = {'<2s': ([], []), '2-4s': ([], []), '>=4s': ([], [])}
        for embs, true, durs in rows:
            for i, j in itertools.combinations(range(len(embs)), 2):
                m = min(durs[i], durs[j])
                key = '<2s' if m < 2 else ('2-4s' if m < 4 else '>=4s')
                pairs[key][0].append(float(np.dot(embs[i], embs[j])))
                pairs[key][1].append(true[i] == true[j])
        eers = {k: round(eer(*v), 2) for k, v in pairs.items() if len(v[0]) > 50 and any(v[1]) and not all(v[1])}
        sweep = []
        for th in thresholds:
            acc, cnt = [], []
            for embs, true, durs in rows:
                pred = online_labels(embs, th)
                acc.append(best_accuracy(true, pred))
                cnt.append(abs(len(set(pred)) - len(set(true))))
            sweep.append({'threshold': th, 'accuracy': round(100 * float(np.mean(acc)), 1),
                          'count_error': round(float(np.mean(cnt)), 2)})
        best = max(sweep, key=lambda r: (r['accuracy'], -r['count_error']))
        report[store] = {'conversations': len(rows), 'turns': sum(len(r[0]) for r in rows), 'pair_eer_pct': eers,
                         'best': best, 'sweep': sweep}
        print(f'{store:28s} EER by length {eers}  best threshold {best["threshold"]}: '
              f'accuracy {best["accuracy"]}%, speaker-count error {best["count_error"]}', flush=True)
    Path(a.out).write_text(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
