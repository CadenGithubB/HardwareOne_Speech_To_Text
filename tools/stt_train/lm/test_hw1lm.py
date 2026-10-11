#!/usr/bin/env python3
"""Tests for hw1lm.py (format, scoring, decoder) and build_lm.py (KN maths).

Run: python test_hw1lm.py   (or pytest test_hw1lm.py)
"""
import itertools
import math
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hw1lm  # noqa: E402
from hw1lm import BLANK, NEG_INF, VOCAB, _lse  # noqa: E402

NO_LM = dict(alpha=0.0, beta=0.0, hotword_bonus=0.0, unk_log10=0.0)


# --------------------------------------------------------------- tiny LM

def tiny_lm_bytes(**params):
    words = ['</s>', '<s>', '<unk>', 'a', 'b', 'c']
    ids = {w: i for i, w in enumerate(words)}
    uni = {'</s>': (-1.0, 0), '<s>': (-32.768, -0.5), '<unk>': (-2.0, 0),
           'a': (-0.5, -0.3), 'b': (-0.7, -0.2), 'c': (-1.2, 0)}
    uni_q = np.array([[round(uni[w][0] * 1000), round(uni[w][1] * 1000)] for w in words], np.int16)
    bigrams = [('<s>', 'a', -0.2, -0.1), ('<s>', 'b', -0.9, 0), ('a', 'b', -0.3, -0.4),
               ('b', '</s>', -0.6, 0)]
    trigrams = [('<s>', 'a', 'b', -0.05), ('a', 'b', '</s>', -0.25)]
    bi = np.array(sorted((ids[a], ids[b], round(p * 1000), round(q * 1000)) for a, b, p, q in bigrams),
                  dtype=hw1lm.BI)
    tri = np.array(sorted((ids[a], ids[b], ids[c], round(p * 1000)) for a, b, c, p in trigrams),
                   dtype=hw1lm.TRI)
    p = {**hw1lm.DEFAULT_PARAMS, 'unk_log10': -5.0, **params}
    return hw1lm.encode_lm(words, uni_q, bi, tri, p)


def test_backoff_scoring():
    lm = hw1lm.read_lm(tiny_lm_bytes())
    i = lm.word_id
    s, a, b, c, e, u = i['<s>'], i['a'], i['b'], i['c'], i['</s>'], i['<unk>']
    close = lambda x, y: abs(x - y) < 1e-9  # noqa: E731
    assert close(lm.p2(s, a), -0.2)
    assert close(lm.p2(s, c), -0.5 + -1.2)                   # unigram backoff
    assert close(lm.p3(s, a, b), -0.05)                      # explicit trigram
    assert close(lm.p3(s, a, c), -0.1 + (-0.3 + -1.2))       # bow2(<s>,a) + bow1(a) + p1(c)
    assert close(lm.p3(a, b, e), -0.25)
    assert close(lm.p3(b, a, b), -0.3)                       # bigram (b,a) absent: bow2 = 0
    assert close(lm.p3(s, b, e), -0.6)                       # bigram present, bow 0
    assert close(lm.p3(c, c, c), 0 + 0 + -1.2)               # all absent
    assert close(lm.score_words(['a', 'b'])[0], -0.2 - 0.05 - 0.25)
    # OOV scores unk_log10 flat and is pushed as <unk>
    total, oov = lm.score_words(['a', 'zzz', 'b'])
    assert oov == 1 and close(total, -0.2 + -5.0 + lm.p3(a, u, b) + lm.p3(u, b, e))
    assert close(lm.p3(a, u, b), -0.7) and close(lm.p3(u, b, e), -0.6)
    assert close(lm.score_words([])[0], -0.5 + -1.0)        # p2(<s>, </s>) via backoff


def test_format_roundtrip_and_validation(tmp=Path('/tmp')):
    data = tiny_lm_bytes(alpha=0.25, beam_width=8)
    lm = hw1lm.read_lm(data)
    assert lm.total_bytes == len(data) and len(data) % 4 == 0
    assert lm.params['beam_width'] == 8 and abs(lm.params['alpha'] - 0.25) < 1e-7
    assert lm.words[:3] == ['</s>', '<s>', '<unk>']
    # header fields
    V, n2, n3, sb = np.frombuffer(data, '<u4', 4, 12)
    assert (V, n2, n3, sb) == (6, 4, 2, sum(len(w) + 1 for w in lm.words))
    bad = bytearray(data)
    bad[100] ^= 1
    for blob, msg in ((bytes(bad), 'SHA'), (data[:-4], 'total_bytes'), (b'X' + data[1:], 'magic')):
        try:
            hw1lm.read_lm(blob)
        except hw1lm.FormatError as e:
            assert msg in str(e), (msg, e)
        else:
            raise AssertionError(f'{msg} corruption not detected')
    # unsorted bigrams are rejected (valid sha)
    words = ['</s>', '<s>', '<unk>', 'a']
    uni = np.zeros((4, 2), np.int16)
    bi = np.array([(3, 0, -1, 0), (1, 3, -1, 0)], dtype=hw1lm.BI)
    try:
        hw1lm.read_lm(hw1lm.encode_lm(words, uni, bi, np.zeros(0, hw1lm.TRI), {}))
    except hw1lm.FormatError as e:
        assert 'sorted' in str(e)
    else:
        raise AssertionError('unsorted bigrams accepted')
    path = tmp / 'hw1lm_test.lm'
    path.write_bytes(data)
    lm2 = hw1lm.set_params(path, alpha=1.5, beam_width=32, hotword_bonus=4.0)
    assert lm2.params['beam_width'] == 32 and lm2.params['alpha'] == 1.5
    assert lm2.total_bytes == len(data)
    path.unlink()


def test_custom_words_parsing():
    text = "Kubernetes\n  zorblax \n\n# comment line\nwi-fi\nzorblax\n" + 'x' * 32 + '\n'
    assert hw1lm.parse_custom_words(text) == ['kubernetes', 'zorblax']
    many = '\n'.join(f'w{"a" * (i % 20)}{chr(97 + i % 26)}{chr(97 + i // 26 % 26)}' for i in range(400))
    assert len(hw1lm.parse_custom_words(many)) == 256


def test_normalize_matches_common():
    sys.path.insert(0, str(HERE.parent))
    try:
        from common import normalize_text
    except Exception:  # torch missing: skip
        return
    for s in ["UH-HUH I THINK A. G. N.", "'quoted' don't", "  Two  spaces--here ", "O'NEIL's 3D"]:
        assert hw1lm.normalize_text(s) == normalize_text(s)


# ----------------------------------------------------------- decoder oracle

def normalise_prefix(text):
    return re.sub(' +', ' ', text).lstrip(' ')


def brute_force(lp, classes):
    """Exact per-normalised-prefix log probability by enumerating alignments."""
    T = len(lp)
    out = defaultdict(lambda: NEG_INF)
    for path in itertools.product(classes, repeat=T):
        s = sum(lp[t][c] for t, c in enumerate(path))
        chars, prev = [], None
        for c in path:
            if c != prev and c != BLANK:
                chars.append(VOCAB[c])
            prev = c
        key = normalise_prefix(''.join(chars))
        out[key] = _lse(out[key], s)
    return dict(out)


def plain_prefix_search(lp, width):
    """Textbook CTC prefix beam search over all 28 labels (space is a label)."""
    beams = {(): (0.0, NEG_INF)}
    for row in lp:
        nxt = defaultdict(lambda: [NEG_INF, NEG_INF])
        for prefix, (pb, pnb) in beams.items():
            tot = _lse(pb, pnb)
            nxt[prefix][0] = _lse(nxt[prefix][0], tot + row[BLANK])
            for c in range(28):
                if row[c] == NEG_INF:  # impossible label: contributes nothing
                    continue
                if prefix and prefix[-1] == c:
                    nxt[prefix][1] = _lse(nxt[prefix][1], pnb + row[c])
                    nxt[prefix + (c,)][1] = _lse(nxt[prefix + (c,)][1], pb + row[c])
                else:
                    nxt[prefix + (c,)][1] = _lse(nxt[prefix + (c,)][1], tot + row[c])
        ranked = sorted(((k, v) for k, v in nxt.items() if _lse(*v) > NEG_INF),
                        key=lambda kv: -_lse(*kv[1]))[:width]
        beams = {k: tuple(v) for k, v in ranked}
    merged = defaultdict(lambda: NEG_INF)
    for prefix, (pb, pnb) in beams.items():
        key = normalise_prefix(''.join(VOCAB[c] for c in prefix))
        merged[key] = _lse(merged[key], _lse(pb, pnb))
    return dict(merged)


def restricted_lp(rng, T, classes, peak=3.0):
    lp = np.full((T, 29), -np.inf)
    for t in range(T):
        x = rng.normal(0, peak, len(classes))
        lp[t, classes] = x - np.log(np.exp(x).sum())
    return lp


def test_oracle_exhaustive():
    lm = hw1lm.read_lm(tiny_lm_bytes())
    rng = np.random.default_rng(1)
    for trial in range(12):
        classes = [0, 1, 2, BLANK] if trial % 2 == 0 else [0, 1, 1 + trial % 26, BLANK]
        classes = sorted(set(classes))
        T = 7 if len(classes) == 4 else 8
        lp = restricted_lp(rng, T, classes, peak=1.0 + trial % 3)
        exact = brute_force(lp.tolist(), classes)
        text, info = hw1lm.decode(lp, lm, return_beams=True, beam_width=10 ** 9,
                                  char_prune=-math.inf, **NO_LM)
        got = {p: _lse(e[0], e[1]) for p, e in info['beams'].items()}
        assert set(got) == {k for k, v in exact.items() if v > NEG_INF}, trial
        for k, v in exact.items():
            assert abs(got[k] - v) < 1e-9, (trial, k, got[k], v)
        plain = plain_prefix_search(lp.tolist(), 10 ** 9)
        for k, v in exact.items():
            assert abs(plain[k] - v) < 1e-9
        best = max(exact.items(), key=lambda kv: (kv[1], [-ord(ch) for ch in kv[0]]))
        assert text == best[0].rstrip(' '), (trial, text, best)


def peaky_lp(rng, T):
    x = rng.normal(0, 1.0, (T, 29))
    hot = rng.integers(0, 29, T)
    hot[rng.random(T) < 0.6] = BLANK
    x[np.arange(T), hot] += rng.uniform(3.0, 9.0, T)  # CTC-like: mostly confident frames
    return hw1lm.log_softmax(x)


def test_matches_plain_prefix_search_wide_beam():
    lm = hw1lm.read_lm(tiny_lm_bytes())
    rng = np.random.default_rng(7)
    for trial in range(25):
        lp = peaky_lp(rng, 40)
        plain = plain_prefix_search(lp.tolist(), 256)
        best_plain = max(plain.items(), key=lambda kv: kv[1])[0].rstrip(' ')
        text, info = hw1lm.decode(lp, lm, return_beams=True, beam_width=256,
                                  char_prune=-math.inf, **NO_LM)
        assert text == best_plain, (trial, text, best_plain)
        top = info['final'][0]
        # The textbook beam spends slots on space variants (" a", "a  b") that the
        # FORMAT.md decoder merges, so it can only lose pruned mass, never gain.
        assert -1e-9 <= top[0] - plain[top[1]] < 0.1, (trial, top[0], plain[top[1]])


def test_greedy_agreement_beam1_peaky():
    """Clearly peaked frames: any beam returns the greedy path."""
    lm = hw1lm.read_lm(tiny_lm_bytes())
    seq = [0, 0, 1, BLANK, 2, 2, BLANK, 0, BLANK, 0, 3, BLANK]  # "  a b  c" style path
    q = np.full((len(seq), 29), -40, np.int8)
    q[np.arange(len(seq)), seq] = 60
    assert hw1lm.greedy_device(q) == 'ab  c'  # device keeps interior double spaces
    for w in (1, 4, 16):
        assert hw1lm.decode_int8(q, 2, lm, beam_width=w, **NO_LM) == 'ab c'


def one_hot_frames(path, rng=None, strong=8.0):
    x = np.zeros((len(path), 29))
    for t, choices in enumerate(path):
        if isinstance(choices, int):
            x[t, choices] = strong
        else:
            for c, v in choices.items():
                x[t, c] = v
    return hw1lm.log_softmax(x)


def test_lm_changes_choice_and_hotword():
    lm = hw1lm.read_lm(tiny_lm_bytes())
    a, b, c, sp = 1, 2, 3, 0
    # "a" then space, then b/c nearly tied (c slightly ahead acoustically)
    lp = one_hot_frames([a, BLANK, sp, {b: 8.0, c: 8.3}, BLANK])
    assert hw1lm.decode(lp, lm, **NO_LM) == 'a c'
    assert hw1lm.decode(lp, lm, alpha=1.0, beta=0.0) == 'a b'
    assert hw1lm.decode(lp, lm, ['c'], alpha=1.0, beta=0.0, hotword_bonus=5.0) == 'a c'
    # OOV word flat penalty: "a" vs OOV "q" at unk_log10
    q_ = 17
    lp = one_hot_frames([{a: 8.0, q_: 8.2}, BLANK])
    assert hw1lm.decode(lp, lm, **NO_LM) == 'q'
    assert hw1lm.decode(lp, lm, alpha=1.0, beta=0.0) == 'a'
    assert hw1lm.decode(lp, lm, ['q'], alpha=1.0, beta=0.0, hotword_bonus=20.0) == 'q'


def test_empty_and_all_blank():
    lm = hw1lm.read_lm(tiny_lm_bytes())
    lp = one_hot_frames([BLANK] * 5)
    assert hw1lm.decode(lp, lm) == ''
    assert hw1lm.decode(np.zeros((0, 29)), lm) == ''
    lp = one_hot_frames([0, BLANK, 0, 0])  # only spaces
    text, info = hw1lm.decode(lp, lm, return_beams=True)
    assert text == '' and info['final'][0][1] == ''


# ------------------------------------------------------------ builder maths

def test_kn_normalisation_and_pruning():
    import build_lm
    rng = random.Random(3)
    words = [f'w{i}' for i in range(40)]
    sents = [' '.join(rng.choice(words[:int(rng.random() * 39) + 1]) for _ in range(rng.randint(1, 8)))
             for _ in range(400)]
    other = [' '.join(rng.choice(words[10:]) for _ in range(rng.randint(1, 6))) for _ in range(300)]
    vocab = sorted(set(w for s in sents + other for w in s.split()) | set(hw1lm.SPECIALS),
                   key=lambda w: w.encode())
    wid = {w: i for i, w in enumerate(vocab)}
    V, bos, eos = len(vocab), wid['<s>'], wid['</s>']
    m1 = build_lm.kn_trigram(build_lm.to_ids(sents, wid), V, bos, eos)
    m2 = build_lm.kn_trigram(build_lm.to_ids(other, wid), V, bos, eos)
    mixed = build_lm.mix([m1, m2], [0.7, 0.3])
    sbytes = sum(len(w) + 1 for w in vocab)
    pruned, _ = build_lm.entropy_prune(mixed, mixed.size_bytes(sbytes) // 2, sbytes)
    assert pruned.size_bytes(sbytes) <= mixed.size_bytes(sbytes) // 2
    # protected (custom) words keep their <s> bigram without collapsing the budget search
    first = wid[sents[0].split()[0]]
    kept, _ = build_lm.entropy_prune(mixed, mixed.size_bytes(sbytes) // 2, sbytes, [first])
    assert int((bos << 16) | first) in set(kept.bi_keys.tolist())
    assert kept.size_bytes(sbytes) > 0.95 * pruned.size_bytes(sbytes)
    allw = np.array([i for i in range(V) if i != bos], np.int64)
    for m in (m1, m2, mixed, pruned):
        assert abs(m.uni_p[allw].sum() - 1) < 1e-9
        for u, v in [(-1, bos), (bos, wid['w1']), (wid['w3'], wid['w5']), (wid['w12'], wid['w30'])]:
            s = m.p3(np.full(len(allw), u), np.full(len(allw), v), allw).sum()
            assert abs(s - 1) < 1e-6, (u, v, s)
    # interpolated KN == backoff form for the unpruned model (bow = gamma)
    re_bowed = build_lm.Model(V, bos, eos, m1.uni_p, m1.bi_keys, m1.bi_p, m1.tri_keys, m1.tri_p)
    re_bowed.recompute_bows()
    assert np.allclose(re_bowed.uni_bow, m1.uni_bow) and np.allclose(re_bowed.bi_bow, m1.bi_bow)


FIXTURES = HERE.parents[2] / 'components' / 'hardwareone' / 'test' / 'host' / 'fixtures' / 'stt_lm'


def test_parity_fixtures():
    """Replay the firmware parity fixtures exactly as a consumer would."""
    import hashlib
    import json
    man = json.loads((FIXTURES / 'manifest.json').read_text())
    assert man['format'] == 'hw1lm-parity-1'
    lm = hw1lm.read_lm(FIXTURES / man['lm'])
    assert lm.sha256 == man['lm_sha256'] and lm.total_bytes == man['lm_bytes']
    custom = hw1lm.load_custom_words(FIXTURES / man['custom_words_file'])
    assert custom == man['custom_words']
    assert len(man['cases']) >= 6
    for case in man['cases']:
        raw = (FIXTURES / case['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == case['sha256']
        q = np.frombuffer(raw, np.int8).reshape(case['frames'], 29)
        assert hw1lm.greedy_device(q) == case['expected_greedy'], case['name']
        lp = hw1lm.log_softmax(q.astype(np.float64) * 2.0 ** -case['exponent'])
        words = custom if case['custom_words'] else None
        text, info = hw1lm.decode(lp, lm, words, return_beams=True, **case['params'])
        assert text == case['expected_lm'], (case['name'], text, case['expected_lm'])
        assert abs(info['final'][0][0] - case['lm_score']) < 1e-5
        assert case['margin'] >= 0.25 and case['final_beams'] >= 2


def main():
    tests = [(n, f) for n, f in globals().items() if n.startswith('test_') and callable(f)]
    for name, fn in tests:
        fn()
        print('ok', name, flush=True)
    print(f'{len(tests)} tests passed')


if __name__ == '__main__':
    main()
