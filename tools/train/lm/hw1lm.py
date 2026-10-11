"""HW1LM1 word n-gram LM: writer, reader/validator, backoff scoring and the
reference CTC prefix beam decoder.

Implements experiments/stt_train/lm/FORMAT.md, which is the binding contract
shared with the firmware decoder. Pure Python + numpy (no torch import) so it
can be used from tests and fixture tools cheaply.

Readings of FORMAT.md that the text leaves implicit (kept deliberately, see
the parity fixtures):
  * char_prune applies to every non-blank char except the repeat of the
    prefix's last char. A space after a space is that repeat (never pruned,
    added to p_b like a blank); a leading space is an "other" char (pruned).
  * The returned text is the best prefix with any trailing space removed.
  * `<s>` has no probability; its unigram log10 is stored as -32.768 (the
    i16 minimum) because -99 does not fit the quantised field.
  * Custom-word lines are stripped, normalised like transcripts and kept when
    they form exactly one word of 1..31 bytes; the first 256 such words count.
"""
from __future__ import annotations

import hashlib
import math
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

MAGIC = b'HW1LM1\0\0'
VERSION = 1
HEADER = struct.Struct('<8sIIIIIfffIfIf8s')  # 64 bytes, FORMAT.md header table
assert HEADER.size == 64
UNI = np.dtype([('log10_q', '<i2'), ('backoff10_q', '<i2')])
BI = np.dtype([('w1', '<u2'), ('w2', '<u2'), ('log10_q', '<i2'), ('backoff10_q', '<i2')])
TRI = np.dtype([('w1', '<u2'), ('w2', '<u2'), ('w3', '<u2'), ('log10_q', '<i2')])
BOS, EOS, UNK = '<s>', '</s>', '<unk>'
SPECIALS = (BOS, EOS, UNK)
MAX_VOCAB = 65535
VOCAB = " abcdefghijklmnopqrstuvwxyz'"
BLANK = 28
SPACE = 0
CHAR_TO_ID = {c: i for i, c in enumerate(VOCAB)}
LN10 = math.log(10.0)
NEG_INF = float('-inf')
PARAM_NAMES = ('alpha', 'beta', 'unk_log10', 'beam_width', 'char_prune', 'hotword_bonus')
# Tuned for the baseline QuartzNet checkpoint (tune.py); used when a build has no --params.
DEFAULT_PARAMS = {'alpha': 0.45, 'beta': 2.0, 'unk_log10': -6.5, 'beam_width': 32,
                  'char_prune': -7.0, 'hotword_bonus': 3.0}
MAX_CUSTOM_WORDS, MAX_CUSTOM_BYTES = 256, 31
WORD_RE = re.compile(r"[a-z']+")


def normalize_text(text):
    """Identical to experiments/stt_train/common.py::normalize_text."""
    text = text.lower().replace('-', ' ')
    text = re.sub(r"[^a-z' ]", ' ', text)
    text = re.sub(r"\s+'|'\s+", ' ', f' {text} ')
    return re.sub(r'\s+', ' ', text).strip()


def quantise(log10_values):
    q = np.rint(np.asarray(log10_values, dtype=np.float64) * 1000.0)
    q = np.where(np.isnan(q), 0, q)
    return np.clip(q, -32768, 32767).astype(np.int16)


def _align4(n):
    return (n + 3) & ~3


def _f32(x):
    return struct.unpack('<f', struct.pack('<f', float(x)))[0]


# --------------------------------------------------------------------- write

def encode_lm(words, uni_q, bi, tri, params):
    """Serialise to bytes.

    words: list of str, byte-sorted strictly increasing, includes SPECIALS.
    uni_q: int16 array [V, 2] (log10_q, backoff10_q).
    bi:    structured array of BI dtype, sorted by (w1, w2).
    tri:   structured array of TRI dtype, sorted by (w1, w2, w3).
    params: dict with PARAM_NAMES.
    """
    V = len(words)
    blob = b''.join(w.encode('ascii') + b'\0' for w in words)
    offsets = np.zeros(V, dtype='<u4')
    pos = 0
    for i, w in enumerate(words):
        offsets[i] = pos
        pos += len(w) + 1
    uni = np.zeros(V, dtype=UNI)
    uni['log10_q'] = np.asarray(uni_q)[:, 0]
    uni['backoff10_q'] = np.asarray(uni_q)[:, 1]
    bi = np.ascontiguousarray(bi, dtype=BI)
    tri = np.ascontiguousarray(tri, dtype=TRI)
    body = bytearray()
    body += uni.tobytes()
    body += offsets.tobytes()
    body += blob
    body += b'\0' * (_align4(64 + len(body)) - 64 - len(body))
    body += bi.tobytes()
    body += tri.tobytes()
    body += b'\0' * (_align4(64 + len(body)) - 64 - len(body))
    total = 64 + len(body) + 32
    p = {**DEFAULT_PARAMS, **(params or {})}
    header = HEADER.pack(MAGIC, VERSION, V, len(bi), len(tri), len(blob),
                         p['alpha'], p['beta'], p['unk_log10'], int(p['beam_width']),
                         p['char_prune'], total, p['hotword_bonus'], b'\0' * 8)
    data = header + bytes(body)
    return data + hashlib.sha256(data).digest()


def write_lm(path, words, uni_q, bi, tri, params):
    data = encode_lm(words, uni_q, bi, tri, params)
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_bytes(data)
    tmp.replace(path)
    return len(data)


def set_params(path, **params):
    """Rewrite header decoder params in place (recomputes the SHA-256)."""
    data = bytearray(Path(path).read_bytes())
    fields = list(HEADER.unpack_from(data, 0))
    index = {'alpha': 6, 'beta': 7, 'unk_log10': 8, 'beam_width': 9, 'char_prune': 10,
             'hotword_bonus': 12}
    for k, v in params.items():
        fields[index[k]] = int(v) if k == 'beam_width' else float(v)
    HEADER.pack_into(data, 0, *fields)
    body = bytes(data[:-32])
    data[-32:] = hashlib.sha256(body).digest()
    tmp = Path(str(path) + '.tmp')
    tmp.write_bytes(bytes(data))
    tmp.replace(path)
    return read_lm(path)


# ---------------------------------------------------------------------- read

class FormatError(ValueError):
    pass


@dataclass
class LM:
    words: list
    word_id: dict
    uni_logp: list          # log10 per word id (quantised / 1000)
    uni_bow: list
    bigram: dict            # (w1 << 16 | w2) -> (log10, backoff10)
    trigram: dict           # (w1 << 32 | w2 << 16 | w3) -> log10
    params: dict
    bos: int
    eos: int
    unk: int
    total_bytes: int = 0
    sha256: str = ''
    raw: dict = field(default_factory=dict)  # numpy views of the sections

    @property
    def V(self):
        return len(self.words)

    # FORMAT.md "LM scoring": log10 values.
    def p1(self, c):
        return self.uni_logp[c]

    def p2(self, b, c):
        e = self.bigram.get((b << 16) | c)
        if e is not None:
            return e[0]
        return self.uni_bow[b] + self.uni_logp[c]

    def p3(self, a, b, c):
        t = self.trigram.get((a << 32) | (b << 16) | c)
        if t is not None:
            return t
        e = self.bigram.get((a << 16) | b)
        return (e[1] if e is not None else 0.0) + self.p2(b, c)

    def log10p(self, wid, ctx):
        """ctx = (w_-2, w_-1); w_-2 == -1 means only (<s>) is known."""
        a, b = ctx
        return self.p2(b, wid) if a < 0 else self.p3(a, b, wid)

    def score_words(self, words, unk_log10=None, eos=True):
        """log10 P(sentence) with FORMAT.md OOV handling; returns (total, n_oov)."""
        unk_log10 = self.params['unk_log10'] if unk_log10 is None else unk_log10
        ctx = (-1, self.bos)
        total, oov = 0.0, 0
        for w in words:
            wid = self.word_id.get(w)
            if wid is None or wid in (self.bos, self.eos, self.unk):
                total += unk_log10
                oov += 1
                wid = self.unk
            else:
                total += self.log10p(wid, ctx)
            ctx = (ctx[1], wid)
        if eos:
            total += self.log10p(self.eos, ctx)
        return total, oov


def read_lm(path_or_bytes, validate=True):
    data = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else Path(path_or_bytes).read_bytes()
    data = bytes(data)
    if len(data) < 64 + 32:
        raise FormatError('file too small')
    (magic, version, V, n2, n3, sbytes, alpha, beta, unk_log10, beam_width, char_prune,
     total, hotword, reserved) = HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise FormatError(f'bad magic {magic!r}')
    if version != VERSION:
        raise FormatError(f'unsupported version {version}')
    if total != len(data):
        raise FormatError(f'total_bytes {total} != file size {len(data)}')
    if hashlib.sha256(data[:-32]).digest() != data[-32:]:
        raise FormatError('SHA-256 mismatch')
    if not 3 <= V <= MAX_VOCAB:
        raise FormatError(f'vocab size {V} out of range')
    if reserved != b'\0' * 8:
        raise FormatError('reserved header bytes not zero')
    off_uni = 64
    off_off = _align4(off_uni + 4 * V)
    off_str = _align4(off_off + 4 * V)
    off_bi = _align4(off_str + sbytes)
    off_tri = _align4(off_bi + 8 * n2)
    end = off_tri + 8 * n3
    sha_off = _align4(end)
    if sha_off + 32 != len(data):
        raise FormatError(f'section sizes imply {sha_off + 32} bytes, file has {len(data)}')
    if any(data[off_str + sbytes:off_bi]) or any(data[end:sha_off]):
        raise FormatError('non-zero padding')
    uni = np.frombuffer(data, UNI, V, off_uni)
    offsets = np.frombuffer(data, '<u4', V, off_off)
    blob = data[off_str:off_str + sbytes]
    bi = np.frombuffer(data, BI, n2, off_bi)
    tri = np.frombuffer(data, TRI, n3, off_tri)
    words = []
    for i in range(V):
        o = int(offsets[i])
        if o >= sbytes:
            raise FormatError(f'string offset {o} out of range')
        z = blob.find(b'\0', o)
        if z < 0:
            raise FormatError('unterminated string')
        words.append(blob[o:z].decode('ascii'))
    if validate:
        _validate(words, offsets, sbytes, uni, bi, tri, beam_width)
    word_id = {w: i for i, w in enumerate(words)}
    for s in SPECIALS:
        if s not in word_id:
            raise FormatError(f'missing {s}')
    uni_logp = (uni['log10_q'].astype(np.float64) / 1000.0).tolist()
    uni_bow = (uni['backoff10_q'].astype(np.float64) / 1000.0).tolist()
    k2 = (bi['w1'].astype(np.int64) << 16) | bi['w2'].astype(np.int64)
    bigram = dict(zip(k2.tolist(), zip((bi['log10_q'] / 1000.0).tolist(),
                                        (bi['backoff10_q'] / 1000.0).tolist())))
    k3 = ((tri['w1'].astype(np.int64) << 32) | (tri['w2'].astype(np.int64) << 16)
          | tri['w3'].astype(np.int64))
    trigram = dict(zip(k3.tolist(), (tri['log10_q'] / 1000.0).tolist()))
    params = {'alpha': alpha, 'beta': beta, 'unk_log10': unk_log10, 'beam_width': beam_width,
              'char_prune': char_prune, 'hotword_bonus': hotword}
    return LM(words, word_id, uni_logp, uni_bow, bigram, trigram, params,
              word_id[BOS], word_id[EOS], word_id[UNK], total,
              hashlib.sha256(data).hexdigest(), {'uni': uni, 'bi': bi, 'tri': tri})


def _validate(words, offsets, sbytes, uni, bi, tri, beam_width):
    V = len(words)
    encoded = [w.encode('ascii') for w in words]
    for a, b in zip(encoded, encoded[1:]):
        if not a < b:
            raise FormatError(f'strings not strictly increasing: {a!r} >= {b!r}')
    pos = 0
    for i, w in enumerate(encoded):
        if offsets[i] != pos:
            raise FormatError('strings blob not contiguous')
        pos += len(w) + 1
        if w.decode() not in SPECIALS and not WORD_RE.fullmatch(w.decode()):
            raise FormatError(f'word {w!r} outside the model alphabet')
    if pos != sbytes:
        raise FormatError('strings_bytes does not match the blob')
    if not 1 <= beam_width <= 64:
        raise FormatError(f'beam_width {beam_width} out of range')
    for name, arr, cols in (('bigram', bi, ('w1', 'w2')), ('trigram', tri, ('w1', 'w2', 'w3'))):
        if len(arr) == 0:
            continue
        for c in cols:
            if int(arr[c].max()) >= V:
                raise FormatError(f'{name} word id out of range')
        key = np.zeros(len(arr), dtype=np.int64)
        for c in cols:
            key = (key << 16) | arr[c].astype(np.int64)
        if np.any(np.diff(key) <= 0):
            raise FormatError(f'{name} entries not strictly sorted')


def describe(lm):
    return {'V': lm.V, 'bigrams': len(lm.bigram), 'trigrams': len(lm.trigram),
            'bytes': lm.total_bytes, 'sha256': lm.sha256, **lm.params}


# -------------------------------------------------------------- custom words

def parse_custom_words(text):
    out, seen = [], set()
    for line in text.splitlines():
        word = normalize_text(line.strip())
        if not word or ' ' in word or len(word.encode()) > MAX_CUSTOM_BYTES or word in seen:
            continue
        seen.add(word)
        out.append(word)
        if len(out) == MAX_CUSTOM_WORDS:
            break
    return out


def load_custom_words(path):
    return parse_custom_words(Path(path).read_text(encoding='utf-8', errors='replace'))


# ------------------------------------------------------------------ decoding

def log_softmax(logits):
    x = np.asarray(logits, dtype=np.float64)
    m = x.max(axis=-1, keepdims=True)
    return x - m - np.log(np.exp(x - m).sum(axis=-1, keepdims=True))


def dequantise(q, exponent):
    """Device int8 logits -> float: q * 2^-exponent (exponent=2 for the P4 model)."""
    return np.asarray(q, dtype=np.float64) * (2.0 ** -exponent)


def greedy_device(q):
    """Device ctc_feed/ctc_finish semantics on raw scores (int8 or float):
    first-max argmax, collapse repeats, drop blanks and leading spaces, trim
    trailing spaces. Interior double spaces are kept, as on the device."""
    ids = np.argmax(np.asarray(q), axis=1)  # numpy returns the first maximum
    out, prev = [], -1
    for t in ids.tolist():
        if t != BLANK and t != prev and not (not out and t == SPACE):
            out.append(VOCAB[t])
        prev = t
    return ''.join(out).rstrip(' ')


def _lse(a, b):
    if a == NEG_INF:
        return b
    if b == NEG_INF:
        return a
    if a > b:
        return a + math.log1p(math.exp(b - a))
    return b + math.log1p(math.exp(a - b))


def start_context(lm, context):
    """LM history (w2, w1) for a phrase that follows `context` (earlier text).

    Empty/None context is a sentence start, (-1, <s>). Otherwise the last two
    words of the context; a word outside the vocabulary becomes <unk>, and with
    a single word w2 is -1 (bigram history), as after <s>."""
    words = (context or '').split()[-2:]
    if not words:
        return (-1, lm.bos)
    ids = [lm.word_id.get(w, lm.unk) for w in words]
    specials = (lm.bos, lm.eos)
    ids = [lm.unk if i in specials else i for i in ids]
    return (ids[0], ids[1]) if len(ids) == 2 else (-1, ids[0])


def decode(log_probs, lm, custom_words=None, return_beams=False, context=None, end_eos=True, **overrides):
    """FORMAT.md CTC prefix beam search with word LM.

    log_probs: [T, 29] natural-log probabilities (log_softmax of logits).
    lm: LM from read_lm (header params are defaults; keyword overrides win).
    custom_words: iterable of normalised words that earn hotword_bonus.
    context: text decoded before this phrase (continuous transcription); its
      last two words seed the LM history instead of a sentence start.
    end_eos: score </s> after the phrase (a phrase cut at a pause is often
      mid-sentence; False leaves the end open).
    Returns the best text (trailing space trimmed), or (text, info) with
    return_beams=True where info has the final scored beams.
    """
    p = dict(lm.params)
    for k, v in overrides.items():
        if k not in PARAM_NAMES:
            raise TypeError(f'unknown decoder parameter {k}')
        if v is not None:
            p[k] = v
    alpha_ln = float(p['alpha']) * LN10
    beta = float(p['beta'])
    unk_log10 = float(p['unk_log10'])
    width = int(p['beam_width'])
    char_prune = float(p['char_prune'])
    bonus = float(p['hotword_bonus'])
    custom = frozenset(custom_words or ())
    word_id, unk = lm.word_id, lm.unk
    specials = (lm.bos, lm.eos, lm.unk)
    cache = {}

    def complete(word, ctx):
        key = (word, ctx)
        hit = cache.get(key)
        if hit is not None:
            return hit
        wid = word_id.get(word)
        if wid is None or wid in specials:
            l10, wid = unk_log10, unk
        else:
            l10 = lm.log10p(wid, ctx)
        delta = alpha_ln * l10 + beta + (bonus if word in custom else 0.0)
        hit = (delta, (ctx[1], wid))
        cache[key] = hit
        return hit

    lp = np.asarray(log_probs, dtype=np.float64)
    if lp.ndim != 2 or lp.shape[1] != 29:
        raise ValueError('log_probs must be [T, 29]')
    rows = lp.tolist()
    allowed = [np.nonzero(r)[0].tolist() for r in (lp[:, :28] >= char_prune)]
    # beam: prefix -> [p_b, p_nb, lm, ctx]
    beams = {'': [0.0, NEG_INF, 0.0, start_context(lm, context)]}
    min_gap, exact_ties = math.inf, 0
    for row, cands in zip(rows, allowed):
        nxt = {}
        lp_blank = row[BLANK]
        for prefix, (pb, pnb, lms, ctx) in beams.items():
            tot = _lse(pb, pnb)
            e = nxt.get(prefix)
            if e is None:
                e = nxt[prefix] = [NEG_INF, NEG_INF, lms, ctx]
            e[0] = _lse(e[0], tot + lp_blank)
            last = CHAR_TO_ID[prefix[-1]] if prefix else -1
            if last == SPACE:
                # space after space: like blank, never a new prefix
                e[0] = _lse(e[0], tot + row[SPACE])
            elif last > 0:
                lc = row[last]
                e[1] = _lse(e[1], pnb + lc)
                if pb != NEG_INF:
                    np_ = prefix + prefix[-1]
                    f = nxt.get(np_)
                    if f is None:
                        f = nxt[np_] = [NEG_INF, NEG_INF, lms, ctx]
                    f[1] = _lse(f[1], pb + lc)
            if tot == NEG_INF:
                continue
            for c in cands:
                if c == last:
                    continue
                lc = row[c]
                if c == SPACE:
                    if not prefix:
                        e[0] = _lse(e[0], tot + lc)
                        continue
                    word = prefix[prefix.rfind(' ') + 1:]
                    delta, nctx = complete(word, ctx)
                    np_ = prefix + ' '
                    f = nxt.get(np_)
                    if f is None:
                        f = nxt[np_] = [NEG_INF, NEG_INF, lms + delta, nctx]
                else:
                    np_ = prefix + VOCAB[c]
                    f = nxt.get(np_)
                    if f is None:
                        f = nxt[np_] = [NEG_INF, NEG_INF, lms, ctx]
                f[1] = _lse(f[1], tot + lc)
        scored = []
        for prefix, e in nxt.items():
            s = _lse(e[0], e[1])
            if s != NEG_INF:
                scored.append((-(s + e[2]), prefix))
        if len(scored) > width:
            scored.sort()
            if return_beams:  # kept-vs-dropped score gap at the cut (float32 robustness);
                gap = scored[width][0] - scored[width - 1][0]  # exact ties are settled by bytes
                if gap > 0:
                    min_gap = min(min_gap, gap)
                else:
                    exact_ties += 1
            scored = scored[:width]
        beams = {prefix: nxt[prefix] for _, prefix in scored}
    eos_cache = {}
    final = []
    for prefix, (pb, pnb, lms, ctx) in beams.items():
        tot = _lse(pb, pnb)
        if prefix and prefix[-1] != ' ':
            delta, ctx = complete(prefix[prefix.rfind(' ') + 1:], ctx)
            lms += delta
        if end_eos:
            eos = eos_cache.get(ctx)
            if eos is None:
                eos = eos_cache[ctx] = alpha_ln * lm.log10p(lm.eos, ctx)
            lms += eos
        final.append((tot + lms, prefix, tot, lms))
    final.sort(key=lambda r: (-r[0], r[1]))
    text = final[0][1].rstrip(' ') if final else ''
    if return_beams:
        return text, {'final': final, 'beams': beams, 'params': p, 'min_prune_gap': min_gap,
                      'prune_exact_ties': exact_ties}
    return text


def decode_int8(q, exponent, lm, custom_words=None, **overrides):
    return decode(log_softmax(dequantise(q, exponent)), lm, custom_words, **overrides)
