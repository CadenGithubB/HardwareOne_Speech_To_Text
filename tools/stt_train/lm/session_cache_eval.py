#!/usr/bin/env python3
"""Would a session word cache help? Simulated on consecutive meeting segments.

  session_cache_eval.py --ckpt DIR --lm meeting.lm [--meetings 4 --segments 150]

Idea: words that already came up in this conversation (names, topic terms)
get a small bonus when they appear again. It reuses the decoder's hotword
mechanism (hw1lm.decode custom_words / hotword_bonus, same as the firmware's
custom_words.txt): after each phrase is decoded, its uncommon words join the
custom set used for the following phrases of the same meeting.

Runs on context_eval.py's cached logits (same meetings and segments), each
meeting decoded in order, and reports for every policy:
  WER        overall word error rate
  repeat     recall of "repeat" words: uncommon reference words that already
             occurred earlier in the same meeting's reference (the case the
             cache targets), bag-of-words matched per segment
  first      recall of uncommon words on their first occurrence (should not drop)
Policies: base (no cache), hyp-* (cache from decoded text: realistic, it can
learn its own mistakes), ref-* (cache from the reference: the ceiling).
"Uncommon" = length >= 4 and LM unigram log10 < --rare (or out of vocabulary).
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent))
import hw1lm  # noqa: E402
from context_eval import compute  # noqa: E402
from tune import wer  # noqa: E402

_W = {}


def _init(lm_path):
    _W['lm'] = hw1lm.read_lm(lm_path)


def uncommon(lm, word, rare):
    if len(word) < 4:
        return False
    wid = lm.word_id.get(word)
    return wid is None or lm.p1(wid) < rare


def _run(job):
    name, source, bonus, rare, capacity, texts, lps = job
    lm = _W['lm']
    cache = OrderedDict()  # word -> None, most recent last
    hyps = []
    for ref, lp in zip(texts, lps):
        custom = set(cache) if source != 'none' else None
        h = hw1lm.decode(lp, lm, custom, hotword_bonus=bonus if custom else None)
        hyps.append(h)
        new = (h if source == 'hyp' else ref).split() if source != 'none' else []
        for w in new:
            if uncommon(lm, w, rare):
                cache.pop(w, None)
                cache[w] = None
                while len(cache) > capacity:
                    cache.popitem(last=False)
    return name, hyps


def recalls(lm, rare, runs, hyps):
    rep = [0, 0]
    first = [0, 0]
    k = 0
    for run in runs:
        seen = set()
        for ref in run['texts']:
            hc = Counter(hyps[k].split())
            k += 1
            rc = Counter(w for w in ref.split() if uncommon(lm, w, rare))
            for w, n in rc.items():
                bucket = rep if w in seen else first
                bucket[0] += min(n, hc[w])
                bucket[1] += n
            seen.update(rc)
    return rep, first


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ckpt', required=True)
    ap.add_argument('--lm', required=True)
    ap.add_argument('--meetings', type=int, default=4)
    ap.add_argument('--segments', type=int, default=150)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--rare', type=float, default=-4.0, help='uncommon: unigram log10 below this')
    ap.add_argument('--capacity', type=int, default=128)
    ap.add_argument('--bonuses', default='1,2,3')
    ap.add_argument('--out')
    a = ap.parse_args()
    lm = hw1lm.read_lm(a.lm)
    policies = [('base', 'none', 0.0)]
    for b in [float(x) for x in a.bonuses.split(',')]:
        policies += [(f'hyp-b{b:g}', 'hyp', b), (f'ref-b{b:g}', 'ref', b)]
    report = {'ckpt': a.ckpt, 'lm': a.lm, 'rare': a.rare, 'capacity': a.capacity, 'params': lm.params}
    for mic in ('sdm', 'ihm'):
        runs, logits = compute(a.ckpt, mic, a.meetings, a.segments, a.seed)
        lps = [hw1lm.log_softmax(x) for x in logits]
        jobs, k = [], 0
        for run in runs:
            n = len(run['texts'])
            for name, source, bonus in policies:
                jobs.append((name, source, bonus, a.rare, a.capacity, run['texts'], lps[k:k + n]))
            k += n
        hyps = defaultdict(list)
        with mp.get_context('spawn').Pool(a.workers, _init, (a.lm,)) as pool:
            for name, h in pool.imap(_run, jobs):
                hyps[name].extend(h)
        refs = [t for run in runs for t in run['texts']]
        report[mic] = {}
        for name, _, _ in policies:
            w, e, n = wer(refs, hyps[name])
            rep, first = recalls(lm, a.rare, runs, hyps[name])
            report[mic][name] = {'wer': w, 'errors': e, 'words': n,
                                 'repeat_recall': rep, 'first_recall': first}
            print(f'{mic} {name:8s} WER {w * 100:6.2f}% ({e}/{n})  repeat {rep[0]}/{rep[1]} '
                  f'({rep[0] / max(rep[1], 1) * 100:5.1f}%)  first {first[0]}/{first[1]} '
                  f'({first[0] / max(first[1], 1) * 100:5.1f}%)', flush=True)
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
