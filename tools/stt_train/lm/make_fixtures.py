#!/usr/bin/env python3
"""Generate firmware parity fixtures for the HW1LM1 decoder.

Writes components/hardwareone/test/host/fixtures/stt_lm/:
  tiny.lm             small LM from build_lm.py (top --vocab words), header
                      params copied from the tuned meeting LM
  custom_words.txt    custom word list used by the cases that name it
  caseN.i8            T x 29 int8 row-major raw logits (device output layout)
  manifest.json       per-case frames, exponent, expected texts, params

Real cases come from cached dev-set float logits (tune.py) quantised the way
the P4 model output is (ESP-DL exponent -2: logit = q * 2^-2), synthetic
cases cover all-blank/space-only input and the space/repeat/OOV/custom-word
mechanics. Every case has >= 2 final beams with a >= 0.25 nat margin between
the top two, and keeps its text and best beam when all log-probs are jittered
by 2e-4 nats (a stand-in for float32 vs float64 differences).

  make_fixtures.py [--ckpt-key stt-quartznet-51a92f946c8c] [--params meeting.lm]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_lm  # noqa: E402
import hw1lm  # noqa: E402
from hw1lm import BLANK, CHAR_TO_ID  # noqa: E402
import os
STT_ROOT = Path(os.environ.get('STT_ROOT', 'stt-data'))  # data root: set STT_ROOT

REPO = HERE.parents[2]
OUT = REPO / 'components' / 'hardwareone' / 'test' / 'host' / 'fixtures' / 'stt_lm'
WORK = (STT_ROOT / 'work/lm')
EXPONENT = 2          # logit = q * 2^-EXPONENT (ESP-DL tensor exponent -2)
BUILDER_CUSTOM = ['zorblax']   # forced into tiny.lm's vocabulary
MARGIN = 0.3                   # nats between the top two final beams (float32 safety; lead asked >= 0.25)


def quantise_logits(x):
    return np.clip(np.rint(np.asarray(x) * 2.0 ** EXPONENT), -128, 127).astype(np.int8)


def run_case(q, lm, custom=None):
    lp = hw1lm.log_softmax(hw1lm.dequantise(q, EXPONENT))
    text, info = hw1lm.decode(lp, lm, custom, return_beams=True)
    final = info['final']
    second = final[1] if len(final) > 1 else None
    runner = next((r for r in final[1:] if r[1].rstrip(' ') != text), None)
    return {'text': text, 'score': final[0][0], 'beams': len(final), 'best_prefix': final[0][1],
            'second_prefix': second[1] if second else None,
            'second_score': second[0] if second else None,
            'margin': final[0][0] - second[0] if second else math.inf,
            'runner_up': runner[1].rstrip(' ') if runner else None,
            'runner_up_score': runner[0] if runner else None,
            'margin_text': final[0][0] - runner[0] if runner else math.inf,
            'min_prune_gap': info['min_prune_gap'], 'prune_exact_ties': info['prune_exact_ties']}


def stable(q, lm, custom, ref, trials=6, sigma=2e-4):
    """Same text and best prefix when every log-prob is jittered by N(0, sigma) nats
    (well above accumulated float32 error); a stand-in for float-vs-double parity."""
    lp = hw1lm.log_softmax(hw1lm.dequantise(q, EXPONENT))
    rng = np.random.default_rng(1234)
    for _ in range(trials):
        text, info = hw1lm.decode(lp + rng.normal(0.0, sigma, lp.shape), lm, custom, return_beams=True)
        if text != ref['text'] or info['final'][0][1] != ref['best_prefix']:
            return False
    return True


def wer(ref, hyp):
    from tune import word_errors
    return word_errors(ref, hyp) / max(len(ref.split()), 1)


def synthetic(rows, strong=40, weak=-40):
    """rows: list of class ids or {class: q} dicts -> int8 [T, 29]."""
    q = np.full((len(rows), 29), weak, dtype=np.int8)
    for t, r in enumerate(rows):
        if isinstance(r, dict):
            for c, v in r.items():
                q[t, c] = v
        else:
            q[t, r] = strong
    return q


def spell(text):
    """Frames spelling text; a blank separates doubled letters."""
    rows, prev = [], None
    for ch in text:
        c = CHAR_TO_ID[ch]
        if c == prev:
            rows.append(BLANK)
        rows.append(c)
        prev = c
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ckpt-key', default='stt-quartznet-51a92f946c8c')
    ap.add_argument('--params', default=str(WORK / 'meeting.lm'), help='.lm or JSON with decoder params')
    ap.add_argument('--vocab', type=int, default=300)
    ap.add_argument('--target-bytes', type=int, default=24000)
    ap.add_argument('--ami-weight', type=float, default=0.8)
    ap.add_argument('--out', default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob('case*.i8'):
        old.unlink()

    # tiny LM from the same builder
    with tempfile.TemporaryDirectory() as tmp:
        cw = Path(tmp) / 'builder_custom.txt'
        cw.write_text('\n'.join(BUILDER_CUSTOM) + '\n')
        p = argparse.ArgumentParser()
        build_lm.add_args(p)
        args = p.parse_args(['--out', str(out / 'tiny.lm'), '--max-vocab', str(a.vocab),
                             '--target-bytes', str(a.target_bytes), '--custom-words', str(cw),
                             '--ami-weight', str(a.ami_weight), '--params', a.params])
        build_info = build_lm.build(args)
    lm = hw1lm.read_lm(out / 'tiny.lm')
    vocab = set(lm.words)

    # candidates from cached dev logits
    from tune import load_set, greedy_text
    cache = WORK / 'logits' / a.ckpt_key
    pool = []
    for name in ('ami-sdm-dev', 'ami-ihm-dev', 'libri-dev'):
        s = load_set(cache, name)
        for i, x in enumerate(s['logits']):
            dur = s['durations'][i]
            if not 1.5 <= dur <= 11.0:
                continue
            q = quantise_logits(x)
            r = run_case(q, lm)
            greedy = hw1lm.greedy_device(q)
            pool.append({'set': name, 'index': i, 'id': s['ids'][i], 'ref': s['texts'][i], 'q': q,
                         'dur': dur, 'greedy': greedy, 'clip': float(np.mean(np.abs(x * 4) > 127.5)), **r})

    def good(c):  # >= 2 final beams and top-two margin >= MARGIN nats
        return c['beams'] >= 2 and c['margin'] >= MARGIN

    def pick(pred, key):
        cands = [c for c in pool if pred(c) and good(c) and c not in chosen]
        cands.sort(key=key)
        for c in cands:
            if stable(c['q'], lm, None, c):
                chosen.append(c)
                return c
        raise SystemExit('no candidate for a fixture slot')

    chosen = []
    norm = lambda t: ' '.join(t.split())  # noqa: E731
    helped = lambda c: wer(c['ref'], c['text']) < wer(c['ref'], norm(c['greedy']))  # noqa: E731
    pick(lambda c: c['set'] == 'ami-sdm-dev' and helped(c) and 2 <= c['dur'] <= 6, lambda c: -len(c['ref']))
    pick(lambda c: c['set'] == 'ami-ihm-dev' and c['text'] != norm(c['greedy']) and 3 <= c['dur'] <= 8,
         lambda c: (not helped(c), -len(c['ref'])))
    pick(lambda c: c['set'] == 'libri-dev' and c['text'] != norm(c['greedy']) and c['dur'] >= 6,
         lambda c: (not helped(c), c['dur']))
    cases = [dict(c, custom=None, kind='real') for c in chosen]

    # real custom-word case: an OOV reference word that a hotword pulls in
    custom_case = None
    for c in sorted(pool, key=lambda c: c['dur']):
        if c in chosen or c['set'] == 'libri-dev':
            continue
        for w in c['ref'].split():
            if w in vocab or len(w) < 5 or w in c['text'].split():
                continue
            words = ['zorblax', w, 'kubernetes']
            r = run_case(c['q'], lm, words)
            if w in r['text'].split() and good(r) and stable(c['q'], lm, words, r):
                custom_case = dict(c, **r, custom=w, kind='real', custom_list=words)
                custom_case['text_without_custom'] = c['text']
                break
        if custom_case:
            break
    if custom_case is None:
        raise SystemExit('no custom-word case found')
    custom_words = custom_case['custom_list']
    (out / 'custom_words.txt').write_text('\n'.join(custom_words) + '\n')
    assert hw1lm.load_custom_words(out / 'custom_words.txt') == custom_words
    custom_case['custom'] = 'custom_words.txt'
    cases.append(custom_case)

    # synthetic 1: all blank with isolated spaces -> empty output
    q = synthetic([BLANK] * 12 + [0] + [BLANK] * 6 + [0, 0] + [BLANK] * 4)
    q[8, 1] = 24   # a weak 'a' (log-prob ~ -4) keeps a second beam alive
    cases.append({'kind': 'synthetic', 'id': 'all-blank-and-spaces', 'ref': '', 'q': q, 'custom': None,
                  'greedy': hw1lm.greedy_device(q), **run_case(q, lm)})
    # synthetic 2: leading/double spaces, repeated letters, apostrophe, OOV word,
    # in-vocab custom word, a doubled space before the end, trailing space
    rows = [0, 0, BLANK, 0] + [23, 23, 5, BLANK]                 # "  " + "we" (ww collapses)
    rows += [0, BLANK, 0, 0] + [14, 5, BLANK, 5, 4, 4]            # "  need" (e_e doubles, dd collapses)
    rows += [0] + spell('zorblax') + [0] + spell("don't") + [0]
    rows += [17, 24, 10] + [0, BLANK, BLANK]                      # OOV "qxj" + trailing space
    q = synthetic(rows)
    for t in (5, 17):   # weaker repeated-letter frames with a competing blank
        q[t, BLANK] = 20
    cases.append({'kind': 'synthetic', 'id': 'spaces-repeats-oov-custom', 'ref': "we need zorblax don't qxj",
                  'q': q, 'custom': 'custom_words.txt', 'greedy': hw1lm.greedy_device(q),
                  **run_case(q, lm, custom_words)})

    params = {k: (int(v) if k == 'beam_width' else float(v)) for k, v in lm.params.items()}
    manifest = {
        'format': 'hw1lm-parity-1',
        'lm': 'tiny.lm',
        'lm_bytes': lm.total_bytes,
        'lm_sha256': lm.sha256,
        'lm_vocab': lm.V, 'lm_bigrams': len(lm.bigram), 'lm_trigrams': len(lm.trigram),
        'lm_note': (f'built by build_lm.py --max-vocab {a.vocab} --target-bytes {a.target_bytes} '
                    f'--ami-weight {a.ami_weight} with builder custom words {BUILDER_CUSTOM} '
                    '(so "zorblax" is in-vocab); header params copied from the tuned meeting LM'),
        'classes': 29, 'alphabet': hw1lm.VOCAB, 'blank': BLANK,
        'dequantise': 'logit = q * 2^-exponent (exponent 2 == ESP-DL tensor exponent -2); '
                      'decoder input = per-frame natural-log log_softmax(logit)',
        'expected_greedy_semantics': 'device ctc_feed/ctc_finish: first-max argmax on int8, collapse '
                                     'repeats, drop blanks and leading spaces, trim trailing spaces; '
                                     'interior double spaces are kept',
        'expected_lm_semantics': 'FORMAT.md decoder with the case params; best prefix with trailing '
                                 'space trimmed',
        'score_fields': 'lm_score = total + lm (nats) of the best final beam after finish (float64 '
                        'reference); margin = lm_score - second_beam_score (top two final beams, any '
                        'text; >= 0.3 for every case); margin_text = lm_score - best score of a beam '
                        'whose trimmed text differs; min_prune_gap = smallest non-zero score gap '
                        'between the last kept and first dropped beam over all frames; '
                        'prune_exact_ties = frames where that gap is exactly 0 (settled by prefix bytes)',
        'params': params,
        'custom_words_file': 'custom_words.txt',
        'custom_words': custom_words,
        'cases': [],
    }
    total = sum(p.stat().st_size for p in (out / 'tiny.lm', out / 'custom_words.txt'))
    for n, c in enumerate(cases, 1):
        path = out / f'case{n}.i8'
        path.write_bytes(np.ascontiguousarray(c['q'], dtype=np.int8).tobytes())
        total += path.stat().st_size
        entry = {
            'name': f'case{n}', 'file': path.name, 'frames': int(c['q'].shape[0]), 'classes': 29,
            'exponent': EXPONENT, 'kind': c['kind'],
            'source': f"{c['set']}:{c['id']}" if c['kind'] == 'real' else c['id'],
            'reference': c['ref'],
            'expected_greedy': c['greedy'],
            'expected_lm': c['text'],
            'params': params,
            'custom_words': c['custom'],
            'lm_score': round(c['score'], 6),
            'final_beams': c['beams'],
            'second_beam_prefix': c['second_prefix'],
            'second_beam_score': None if c['second_score'] is None else round(c['second_score'], 6),
            'margin': round(c['margin'], 6),
            'runner_up_text': c['runner_up'],
            'runner_up_score': None if c['runner_up_score'] is None else round(c['runner_up_score'], 6),
            'margin_text': None if math.isinf(c['margin_text']) else round(c['margin_text'], 6),
            'min_prune_gap': None if math.isinf(c['min_prune_gap']) else float('%.3g' % c['min_prune_gap']),
            'prune_exact_ties': c['prune_exact_ties'],
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        if 'text_without_custom' in c:
            entry['expected_lm_without_custom_words'] = c['text_without_custom']
        manifest['cases'].append(entry)
        print(f"case{n} {entry['source']} T={entry['frames']} margin={entry['margin']}\n"
              f"   ref:    {c['ref']}\n   greedy: {c['greedy']!r}\n   lm:     {c['text']!r}")
    bad = [e['name'] for e, c in zip(manifest['cases'], cases)
           if e['final_beams'] < 2 or e['margin'] < MARGIN
           or not stable(c['q'], lm, custom_words if c['custom'] else None, c)]
    if bad:
        raise SystemExit(f'cases below the {MARGIN} nat margin: {bad}')
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    total += (out / 'manifest.json').stat().st_size
    print(f'fixtures in {out}: {total} bytes total; tiny.lm {lm.total_bytes} B '
          f'V={lm.V} bi={len(lm.bigram)} tri={len(lm.trigram)}; build {build_info["ppl"]}')
    assert total < 300_000


if __name__ == '__main__':
    main()
