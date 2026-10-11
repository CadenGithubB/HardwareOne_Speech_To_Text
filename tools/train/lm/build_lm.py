#!/usr/bin/env python3
"""Build a HW1LM1 word trigram LM (FORMAT.md) from train-split transcripts.

Pipeline:
  1. transcripts (AMI train + LibriSpeech train-clean-100 only) -> normalised
     text cache under $STT_ROOT/work/lm/text/
  2. vocabulary (all words, or --max-vocab top words; --custom-words always in)
  3. one interpolated modified Kneser-Ney trigram per corpus (numpy)
  4. static linear mixture p = lam*AMI + (1-lam)*Libri (--mode mix, default
     lam 0.8; --ami-weight auto = EM on AMI dev text). --mode pool builds one
     KN model on pooled counts with AMI repeated --ami-repeat times (worse:
     repetition breaks the Kneser-Ney count-of-counts discounts).
  5. conversion to ARPA backoff form (backoff weights renormalised)
  6. Stolcke relative-entropy pruning to fit --target-bytes
  7. quantised binary with SHA-256 trailer, decoder params in the header.

Dev text (AMI sdm validation, LibriSpeech validation) is only used to pick
lam and to report perplexity; it never enters the counts.

Example:
  nice -n 15 python build_lm.py --out $STT_ROOT/work/lm/meeting.lm
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hw1lm  # noqa: E402
import os
STT_ROOT = Path(os.environ.get('STT_ROOT', 'stt-data'))  # data root: set STT_ROOT

USB = STT_ROOT
WORK = (STT_ROOT / 'work/lm')
TEXT_DIR = WORK / 'text'
LN10 = math.log(10.0)

CORPORA = {
    # name: (glob, expected file count or None)
    'ami-train': (USB / 'ami' / 'sdm', 'train-*.parquet'),
    'ami-dev': (USB / 'ami' / 'sdm', 'validation-*.parquet'),
    'libri-train': (USB / 'librispeech', 'clean_train.100_*.parquet'),
    'libri-dev': (USB / 'librispeech', 'clean_validation_*.parquet'),
    # 2026-10-01 (--mode mixn): People's Speech clean shards (public meetings,
    # interviews) and the LibriSpeech clean-360 text.
    'peoples-train': (USB / 'peoples_speech', 'clean_train_*.parquet'),
    'libri360-train': (USB / 'librispeech', 'clean_train.360_*.parquet'),
}


# ---------------------------------------------------------------- text cache

def complete_files(directory, pattern):
    files = sorted(Path(directory).glob(pattern))
    done = [f for f in files if Path(str(f) + '.done').exists()]
    m = re.search(r'-of-(\d+)\.parquet$', done[0].name) if done else None
    if m and len(done) != int(m.group(1)):
        raise SystemExit(f'{directory}/{pattern}: only {len(done)}/{int(m.group(1))} files complete')
    if not done:
        raise SystemExit(f'{directory}/{pattern}: no complete files')
    return done


def corpus_text(name, refresh=False):
    """Normalised non-empty transcript lines for a corpus (cached)."""
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    path = TEXT_DIR / f'{name}.txt'
    meta = TEXT_DIR / f'{name}.json'
    directory, pattern = CORPORA[name]
    files = complete_files(directory, pattern)
    if path.exists() and meta.exists() and not refresh:
        info = json.loads(meta.read_text())
        if info.get('files') == [f.name for f in files]:
            return path.read_text().splitlines()
    import pyarrow.parquet as pq
    lines = []
    for f in files:
        for text in pq.ParquetFile(f).read(columns=['text']).column('text').to_pylist():
            t = hw1lm.normalize_text(text or '')
            if t:
                lines.append(t)
    path.write_text('\n'.join(lines) + '\n')
    meta.write_text(json.dumps({'files': [f.name for f in files], 'lines': len(lines)}))
    return lines


# ------------------------------------------------------------------- vocab

def choose_vocab(corpora, custom, max_vocab=None, min_count=1):
    counts = [Counter(w for line in lines for w in line.split()) for lines in corpora]
    totals = [max(sum(c.values()), 1) for c in counts]
    words = set().union(*counts)
    # rank by the equal-weight mixture of relative frequencies
    score = {w: sum(c[w] / t for c, t in zip(counts, totals)) for w in words}
    pooled = {w: sum(c[w] for c in counts) for w in words}
    ranked = sorted((w for w in words if pooled[w] >= min_count and len(w.encode()) <= hw1lm.MAX_CUSTOM_BYTES),
                    key=lambda w: (-score[w], w))
    limit = hw1lm.MAX_VOCAB - len(hw1lm.SPECIALS) - len(custom)
    if max_vocab is not None:
        limit = min(limit, max_vocab)
    chosen = set(ranked[:limit]) | set(custom)
    vocab = sorted(chosen | set(hw1lm.SPECIALS), key=lambda w: w.encode())
    assert len(vocab) <= hw1lm.MAX_VOCAB
    return vocab


def to_ids(lines, word_id, extra_sentences=()):
    """Flat int64 token array: <s> w1 .. wn </s> per line, OOV -> <unk>."""
    bos, eos, unk = word_id['<s>'], word_id['</s>'], word_id['<unk>']
    out = []
    for line in list(lines) + list(extra_sentences):
        out.append(bos)
        out.extend(word_id.get(w, unk) for w in line.split())
        out.append(eos)
    return np.asarray(out, dtype=np.int64)


# --------------------------------------------------------- Kneser-Ney model

def _discounts(a):
    n = [int(np.sum(a == k)) for k in (1, 2, 3, 4)]
    if min(n) == 0:
        return np.array([0.0, 0.5, 1.0, 1.5])
    y = n[0] / (n[0] + 2 * n[1])
    d = [1 - 2 * y * n[1] / n[0], 2 - 3 * y * n[2] / n[1], 3 - 4 * y * n[3] / n[2]]
    d = [min(max(v, 0.05), k + 1 - 0.05) for k, v in enumerate(d)]
    return np.array([0.0] + d)


def _disc(a, d):
    return d[np.minimum(a, 3)]


def _gamma(ctx, a, d, size):
    total = np.bincount(ctx, weights=a, minlength=size)
    mass = np.bincount(ctx, weights=_disc(a, d), minlength=size)
    with np.errstate(divide='ignore', invalid='ignore'):
        gamma = np.where(total > 0, mass / np.maximum(total, 1e-300), 1.0)
    return total, gamma


class Model:
    """Trigram in backoff form; probabilities as float64 (not log)."""

    def __init__(self, V, bos, eos, uni_p, bi_keys, bi_p, tri_keys, tri_p,
                 uni_bow=None, bi_bow=None, p_bos=0.05):
        self.V, self.bos, self.eos = V, bos, eos
        self.uni_p, self.bi_keys, self.bi_p = uni_p, bi_keys, bi_p
        self.tri_keys, self.tri_p = tri_keys, tri_p
        self.uni_bow = np.ones(V) if uni_bow is None else uni_bow
        self.bi_bow = np.ones(len(bi_keys)) if bi_bow is None else bi_bow
        self.p_bos = p_bos

    # vectorised backoff lookups -------------------------------------------
    @staticmethod
    def _find(keys, q):
        idx = np.searchsorted(keys, q)
        idx = np.minimum(idx, max(len(keys) - 1, 0))
        found = (keys[idx] == q) if len(keys) else np.zeros(len(q), bool)
        return idx, found

    def p2(self, v, w):
        idx, found = self._find(self.bi_keys, (v << 16) | w)
        return np.where(found, self.bi_p[idx] if len(self.bi_p) else 0.0,
                        self.uni_bow[v] * self.uni_p[w])

    def p3(self, u, v, w):
        """u < 0 means context is only (v)."""
        u = np.asarray(u, dtype=np.int64)
        res = self.p2(v, w)
        has = u >= 0
        if has.any():
            uu, vv, ww = u[has], v[has], w[has]
            idx3, f3 = self._find(self.tri_keys, (uu << 32) | (vv << 16) | ww)
            idx2, f2 = self._find(self.bi_keys, (uu << 16) | vv)
            bow = np.where(f2, self.bi_bow[idx2], 1.0)
            res[has] = np.where(f3, self.tri_p[idx3] if len(self.tri_p) else 0.0, bow * res[has])
        return res

    def recompute_bows(self):
        """ARPA backoff weights so every context distribution sums to one."""
        V = self.V
        v = self.bi_keys >> 16
        w = self.bi_keys & 0xFFFF
        num = 1.0 - np.bincount(v, weights=self.bi_p, minlength=V)
        den = 1.0 - np.bincount(v, weights=self.uni_p[w], minlength=V)
        has = np.bincount(v, minlength=V) > 0
        self.uni_bow = np.where(has, np.maximum(num, 1e-12) / np.maximum(den, 1e-12), 1.0)
        ctx = self.tri_keys >> 16
        vv = (self.tri_keys >> 16) & 0xFFFF
        ww = self.tri_keys & 0xFFFF
        ci, found = self._find(self.bi_keys, ctx)
        assert found.all(), 'trigram context missing from bigrams'
        lower = self.p2(vv, ww)
        n2 = len(self.bi_keys)
        num = 1.0 - np.bincount(ci, weights=self.tri_p, minlength=n2)
        den = 1.0 - np.bincount(ci, weights=lower, minlength=n2)
        has = np.bincount(ci, minlength=n2) > 0
        self.bi_bow = np.where(has, np.maximum(num, 1e-12) / np.maximum(den, 1e-12), 1.0)
        return self

    def history_p(self, u):
        """Probability of a history word at a random position."""
        p = self.uni_p[u] * (1.0 - self.p_bos)
        return np.where(u == self.bos, self.p_bos, p)

    def logprob_sentences(self, sents, word_id):
        """Natural-log probs per scored token (in-vocab words and </s>)."""
        u, v, w = self._contexts(sents, word_id)
        return np.log(self.p3(u, v, w))

    def _contexts(self, sents, word_id):
        us, vs, ws = [], [], []
        bos, eos = self.bos, self.eos
        for line in sents:
            a, b = -1, bos
            for word in line.split() + ['</s>']:
                wid = word_id.get(word, -1) if word != '</s>' else eos
                if wid < 0 or word in ('<s>', '<unk>'):
                    a, b = b, word_id['<unk>']
                    continue
                us.append(a)
                vs.append(b)
                ws.append(wid)
                a, b = b, wid
        return (np.asarray(us, np.int64), np.asarray(vs, np.int64), np.asarray(ws, np.int64))

    def size_bytes(self, sbytes, n2=None, n3=None):
        n2 = len(self.bi_keys) if n2 is None else n2
        n3 = len(self.tri_keys) if n3 is None else n3
        return 64 + 8 * self.V + ((sbytes + 3) & ~3) + 8 * (n2 + n3) + 32


def kn_trigram(tok, V, bos, eos):
    """Interpolated modified Kneser-Ney trigram (Chen & Goodman), backoff form."""
    t0, t1, t2 = tok[:-2], tok[1:-1], tok[2:]
    ok3 = (t1 != bos) & (t1 != eos) & (t2 != bos)
    k3, c3 = np.unique((t0[ok3] << 32) | (t1[ok3] << 16) | t2[ok3], return_counts=True)
    b0, b1 = tok[:-1], tok[1:]
    ok2 = (b0 != eos) & (b1 != bos)
    k2, c2 = np.unique((b0[ok2] << 16) | b1[ok2], return_counts=True)
    # adjusted counts: continuation counts, except raw counts for <s>-initial n-grams
    s_keys, s_counts = np.unique(k3 & 0xFFFFFFFF, return_counts=True)
    a2 = c2.copy()
    not_bos = (k2 >> 16) != bos
    idx = np.minimum(np.searchsorted(s_keys, k2), len(s_keys) - 1)
    hit = s_keys[idx] == k2
    assert hit[not_bos].all()
    a2[not_bos] = s_counts[idx[not_bos]]
    a1 = np.bincount(k2 & 0xFFFF, minlength=V).astype(np.int64)
    a1[bos] = 0
    d1, d2, d3 = _discounts(a1[a1 > 0]), _discounts(a2), _discounts(c3)
    # unigrams, interpolated with uniform over V-1 words (all but <s>)
    A1 = a1.sum()
    nk = [np.sum(a1 == 1), np.sum(a1 == 2), np.sum(a1 >= 3)]
    g1 = (d1[1] * nk[0] + d1[2] * nk[1] + d1[3] * nk[2]) / A1
    uni = np.where(a1 > 0, (a1 - _disc(a1, d1)) / A1, 0.0) + g1 / (V - 1)
    uni[bos] = 0.0
    # bigrams
    v = k2 >> 16
    w = k2 & 0xFFFF
    A2, g2 = _gamma(v, a2, d2, V)
    bi = (a2 - _disc(a2, d2)) / A2[v] + g2[v] * uni[w]
    # trigrams
    ctx = k3 >> 16
    cu, ci = np.unique(ctx, return_inverse=True)
    A3, g3 = _gamma(ci, c3, d3, len(cu))
    low_idx = np.searchsorted(k2, k3 & 0xFFFFFFFF)
    assert (k2[low_idx] == (k3 & 0xFFFFFFFF)).all()
    tri = (c3 - _disc(c3, d3)) / A3[ci] + g3[ci] * bi[low_idx]
    uni_bow = np.where(A2 > 0, g2, 1.0)
    bi_bow = np.ones(len(k2))
    pos = np.searchsorted(k2, cu)
    assert (k2[pos] == cu).all()
    bi_bow[pos] = g3
    n_sent = int(np.sum(tok == bos))
    m = Model(V, bos, eos, uni, k2, bi, k3, tri, uni_bow, bi_bow, p_bos=n_sent / len(tok))
    m.discounts = {'1': d1[1:].tolist(), '2': d2[1:].tolist(), '3': d3[1:].tolist()}
    return m


def mix(models, weights):
    """Static interpolation of backoff models into one backoff model."""
    base = models[0]
    V, bos, eos = base.V, base.bos, base.eos
    bi_keys = np.unique(np.concatenate([m.bi_keys for m in models]))
    tri_keys = np.unique(np.concatenate([m.tri_keys for m in models]))
    v, w = bi_keys >> 16, bi_keys & 0xFFFF
    u3, v3, w3 = tri_keys >> 32, (tri_keys >> 16) & 0xFFFF, tri_keys & 0xFFFF
    uni = sum(l * m.uni_p for l, m in zip(weights, models))
    bi = sum(l * m.p2(v, w) for l, m in zip(weights, models))
    tri = sum(l * m.p3(u3, v3, w3) for l, m in zip(weights, models))
    p_bos = sum(l * m.p_bos for l, m in zip(weights, models))
    return Model(V, bos, eos, uni, bi_keys, bi, tri_keys, tri, p_bos=p_bos).recompute_bows()


def em_weights(models, sents, word_id, iters=60):
    probs = [np.exp(m.logprob_sentences(sents, word_id)) for m in models]
    lam = np.full(len(models), 1.0 / len(models))
    for _ in range(iters):
        post = np.stack([l * p for l, p in zip(lam, probs)])
        post /= post.sum(axis=0, keepdims=True)
        lam = post.mean(axis=1)
    return lam


# ----------------------------------------------------------------- pruning

def entropy_prune(model, budget_bytes, sbytes, protect_words=()):
    """Stolcke pruning of bigrams+trigrams to fit budget; returns new Model."""
    V = model.V
    full = model.size_bytes(sbytes)
    if full <= budget_bytes:
        return model, 0.0
    # trigram candidates
    k3 = model.tri_keys
    ctx3 = k3 >> 16
    ci3, found = Model._find(model.bi_keys, ctx3)
    assert found.all()
    u3, v3, w3 = k3 >> 32, (k3 >> 16) & 0xFFFF, k3 & 0xFFFF
    p = model.tri_p
    q = model.p2(v3, w3)
    n2 = len(model.bi_keys)
    num = 1.0 - np.bincount(ci3, weights=p, minlength=n2)
    den = 1.0 - np.bincount(ci3, weights=q, minlength=n2)
    num, den = np.maximum(num, 1e-12), np.maximum(den, 1e-12)
    bow_new = (num[ci3] + p) / (den[ci3] + q)
    ph = model.history_p(u3) * model.bi_p[ci3]
    d3 = -ph * (p * (np.log(q) + np.log(bow_new) - np.log(p))
                + num[ci3] * (np.log(bow_new) - np.log(num[ci3] / den[ci3])))
    # bigram candidates
    k2 = model.bi_keys
    v2, w2 = k2 >> 16, k2 & 0xFFFF
    p = model.bi_p
    q = model.uni_p[w2]
    num = np.maximum(1.0 - np.bincount(v2, weights=p, minlength=V), 1e-12)
    den = np.maximum(1.0 - np.bincount(v2, weights=q, minlength=V), 1e-12)
    bow_new = (num[v2] + p) / (den[v2] + q)
    ph = model.history_p(v2)
    d2 = -ph * (p * (np.log(q) + np.log(bow_new) - np.log(p))
                + num[v2] * (np.log(bow_new) - np.log(num[v2] / den[v2])))
    if protect_words:
        prot = np.zeros(V, bool)
        prot[list(protect_words)] = True
        d2 = np.where(prot[w2] & (v2 == model.bos), np.inf, d2)

    def keep(theta):
        keep3 = d3 >= theta
        keep2 = d2 >= theta
        keep2[ci3[keep3]] = True
        return keep2, keep3

    def size(theta):
        keep2, keep3 = keep(theta)
        return model.size_bytes(sbytes, int(keep2.sum()), int(keep3.sum()))

    finite = np.concatenate([d2[np.isfinite(d2)], d3[np.isfinite(d3)], [0.0]])
    hi = float(finite.max()) * 2 + 1e-12  # protected n-grams carry +inf and never set the bound
    if size(hi) > budget_bytes:
        raise SystemExit(f'budget {budget_bytes} B too small even without bi/trigrams '
                         f'({model.size_bytes(sbytes, 0, 0)} B)')
    lo = 1e-16
    for _ in range(80):  # geometric bisection on the threshold
        mid = math.sqrt(lo * hi)
        if size(mid) <= budget_bytes:
            hi = mid
        else:
            lo = mid
    keep2, keep3 = keep(hi)
    pruned = Model(V, model.bos, model.eos, model.uni_p, k2[keep2], model.bi_p[keep2],
                   k3[keep3], model.tri_p[keep3], p_bos=model.p_bos).recompute_bows()
    return pruned, hi


# ------------------------------------------------------------------- output

def model_to_file(model, vocab, path, params):
    uni_log = np.full(model.V, -32.768)
    ok = model.uni_p > 0
    uni_log[ok] = np.log10(model.uni_p[ok])
    uni_q = np.stack([hw1lm.quantise(uni_log), hw1lm.quantise(np.log10(model.uni_bow))], axis=1)
    bi = np.zeros(len(model.bi_keys), dtype=hw1lm.BI)
    bi['w1'] = model.bi_keys >> 16
    bi['w2'] = model.bi_keys & 0xFFFF
    bi['log10_q'] = hw1lm.quantise(np.log10(model.bi_p))
    bi['backoff10_q'] = hw1lm.quantise(np.log10(model.bi_bow))
    tri = np.zeros(len(model.tri_keys), dtype=hw1lm.TRI)
    tri['w1'] = model.tri_keys >> 32
    tri['w2'] = (model.tri_keys >> 16) & 0xFFFF
    tri['w3'] = model.tri_keys & 0xFFFF
    tri['log10_q'] = hw1lm.quantise(np.log10(model.tri_p))
    return hw1lm.write_lm(path, vocab, uni_q, bi, tri, params)


def perplexity(lm, lines):
    """Per-token perplexity of a written LM (OOV tokens excluded, SRILM style)."""
    total, n, oov, words = 0.0, 0, 0, 0
    for line in lines:
        ws = line.split()
        ctx = (-1, lm.bos)
        for w in ws + ['</s>']:
            wid = lm.eos if w == '</s>' else lm.word_id.get(w)
            if wid is None:
                oov += 1
                ctx = (ctx[1], lm.unk)
                continue
            total += lm.log10p(wid, ctx)
            n += 1
            ctx = (ctx[1], wid)
        words += len(ws)
    return {'ppl': 10 ** (-total / max(n, 1)), 'oov_rate': oov / max(words, 1), 'tokens': n}


def load_params(args):
    params = dict(hw1lm.DEFAULT_PARAMS)
    if args.params:
        src = Path(args.params)
        if src.suffix == '.lm':
            params.update(hw1lm.read_lm(src).params)
        else:
            params.update({k: v for k, v in json.loads(src.read_text()).items() if k in params})
    for k in hw1lm.PARAM_NAMES:
        v = getattr(args, k)
        if v is not None:
            params[k] = v
    return params


def build_mixn(args, log=print):
    """--mode mixn: one Kneser-Ney trigram per component, statically mixed.

    --components 'ami-train;peoples-train;libri-train+libri360-train' (';'
    separates components, '+' pools corpora inside one), --weights 'w1,w2,..'
    or 'auto' (EM on AMI dev text). Vocabulary ranks words by the components'
    equal-weight relative frequency, as in mix mode."""
    t0 = time.time()
    groups = [g.split('+') for g in args.components.split(';')]
    texts = [[line for name in g for line in corpus_text(name)] for g in groups]
    ami_dev, libri_dev = corpus_text('ami-dev'), corpus_text('libri-dev')
    for g, t in zip(groups, texts):
        log(f"text: {'+'.join(g)} {len(t)} lines/{sum(len(l.split()) for l in t)} words")
    custom = hw1lm.load_custom_words(args.custom_words) if args.custom_words else []
    vocab = choose_vocab(texts, custom, args.max_vocab, args.min_count)
    word_id = {w: i for i, w in enumerate(vocab)}
    V, bos, eos = len(vocab), word_id['<s>'], word_id['</s>']
    sbytes = sum(len(w) + 1 for w in vocab)
    log(f'vocab {V} ({len(custom)} custom words)')
    models = [kn_trigram(to_ids(t, word_id, custom if i == 0 else ()), V, bos, eos) for i, t in enumerate(texts)]
    if args.weights == 'auto':
        weights = [float(w) for w in em_weights(models, ami_dev, word_id)]
    else:
        weights = [float(w) for w in args.weights.split(',')]
        assert len(weights) == len(models) and abs(sum(weights) - 1) < 1e-6, '--weights must sum to 1, one per component'
    log('mixture weights ' + ', '.join(f"{'+'.join(g)}={w:.3f}" for g, w in zip(groups, weights)))
    model = mix(models, weights)
    info = {'vocab': V, 'mode': 'mixn', 'components': ['+'.join(g) for g in groups], 'weights': weights,
            'unpruned': {'bigrams': int(len(model.bi_keys)), 'trigrams': int(len(model.tri_keys)),
                         'bytes': int(model.size_bytes(sbytes))}}
    log(f"unpruned: {info['unpruned']}")
    model, theta = entropy_prune(model, args.target_bytes, sbytes, [word_id[w] for w in custom])
    info['prune_threshold'] = theta
    size = model_to_file(model, vocab, args.out, load_params(args))
    lm = hw1lm.read_lm(args.out)
    info.update(hw1lm.describe(lm))
    info['ppl'] = {'ami-dev': perplexity(lm, ami_dev), 'libri-dev': perplexity(lm, libri_dev)}
    info['seconds'] = round(time.time() - t0, 1)
    log(f"wrote {args.out}: {size} B, V={lm.V}, bigrams={len(lm.bigram)}, trigrams={len(lm.trigram)}")
    for k, v in info['ppl'].items():
        log(f"  {k}: ppl {v['ppl']:.1f}, OOV {v['oov_rate'] * 100:.2f}%")
    return info


def build(args, log=print):
    if args.mode == 'mixn':
        return build_mixn(args, log)
    t0 = time.time()
    ami, libri = corpus_text('ami-train'), corpus_text('libri-train')
    ami_dev, libri_dev = corpus_text('ami-dev'), corpus_text('libri-dev')
    log(f'text: ami-train {len(ami)} lines/{sum(len(l.split()) for l in ami)} words, '
        f'libri-train {len(libri)} lines/{sum(len(l.split()) for l in libri)} words')
    custom = hw1lm.load_custom_words(args.custom_words) if args.custom_words else []
    vocab = choose_vocab([ami, libri], custom, args.max_vocab, args.min_count)
    word_id = {w: i for i, w in enumerate(vocab)}
    V, bos, eos = len(vocab), word_id['<s>'], word_id['</s>']
    sbytes = sum(len(w) + 1 for w in vocab)
    log(f'vocab {V} ({len(custom)} custom words)')
    extra = [w for w in custom]  # custom words as one-word sentences in the AMI side
    info = {'vocab': V, 'mode': args.mode}
    if args.mode == 'pool':
        tok = to_ids(ami * args.ami_repeat + libri, word_id, extra)
        model = kn_trigram(tok, V, bos, eos)
        info['ami_repeat'] = args.ami_repeat
    else:
        m_ami = kn_trigram(to_ids(ami, word_id, extra), V, bos, eos)
        m_lib = kn_trigram(to_ids(libri, word_id), V, bos, eos)
        if args.mode == 'ami':
            model = m_ami
        elif args.mode == 'libri':
            model = m_lib
        else:
            if str(args.ami_weight) == 'auto':
                lam = float(em_weights([m_ami, m_lib], ami_dev, word_id)[0])
            else:
                lam = float(args.ami_weight)
            info['ami_weight'] = lam
            log(f'mixture weight AMI={lam:.3f}')
            model = mix([m_ami, m_lib], [lam, 1.0 - lam])
    info['unpruned'] = {'bigrams': int(len(model.bi_keys)), 'trigrams': int(len(model.tri_keys)),
                        'bytes': int(model.size_bytes(sbytes))}
    log(f"unpruned: {info['unpruned']}")
    protect = [word_id[w] for w in custom]
    model, theta = entropy_prune(model, args.target_bytes, sbytes, protect)
    info['prune_threshold'] = theta
    params = load_params(args)
    size = model_to_file(model, vocab, args.out, params)
    lm = hw1lm.read_lm(args.out)
    info.update(hw1lm.describe(lm))
    info['ppl'] = {'ami-dev': perplexity(lm, ami_dev), 'libri-dev': perplexity(lm, libri_dev)}
    info['seconds'] = round(time.time() - t0, 1)
    log(f"wrote {args.out}: {size} B, V={lm.V}, bigrams={len(lm.bigram)}, trigrams={len(lm.trigram)}")
    for k, v in info['ppl'].items():
        log(f"  {k}: ppl {v['ppl']:.1f}, OOV {v['oov_rate'] * 100:.2f}%")
    return info


def add_args(p):
    p.add_argument('--out', required=True)
    p.add_argument('--target-bytes', type=int, default=2_500_000,
                   help='file size budget in bytes (device LittleFS is tight; default 2.5 MB)')
    p.add_argument('--custom-words')
    p.add_argument('--mode', choices=['mix', 'pool', 'ami', 'libri', 'mixn'], default='mix')
    p.add_argument('--components', default='ami-train;peoples-train;libri-train+libri360-train',
                   help="--mode mixn: ';'-separated components, '+' pools corpora within one")
    p.add_argument('--weights', default='auto', help="--mode mixn: 'auto' (EM on AMI dev) or w1,w2,...")
    p.add_argument('--ami-weight', default='0.8',
                   help="AMI mixture weight, or 'auto' for EM on AMI dev text (default 0.8: EM gives "
                        "~0.94, same dev WER within noise but far worse general-English perplexity)")
    p.add_argument('--ami-repeat', type=int, default=4, help='--mode pool: AMI text repetitions')
    p.add_argument('--max-vocab', type=int)
    p.add_argument('--min-count', type=int, default=1)
    p.add_argument('--params', help='JSON file or .lm to copy decoder params from')
    for k in hw1lm.PARAM_NAMES:
        p.add_argument('--' + k.replace('_', '-'), dest=k,
                       type=int if k == 'beam_width' else float)
    p.add_argument('--report', help='write build info JSON here')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_args(p)
    args = p.parse_args()
    info = build(args)
    if args.report:
        Path(args.report).write_text(json.dumps(info, indent=2))


if __name__ == '__main__':
    main()
