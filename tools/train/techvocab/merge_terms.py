#!/usr/bin/env python3
"""Merge the cat_*.tsv term lists into one checked list and measure what is new to an LM.

  merge_terms.py [--lm LM]        writes terms.tsv (display, spoken, category, subcategory) + terms_report.json

Each spoken form is checked against the recognizer's alphabet (lowercase a-z, apostrophe, single spaces;
the same normalize_text as training) and dropped if normalizing changes it. Duplicates (same spoken form)
keep the first display. Against the LM: words not in its vocabulary, and multi-word terms whose adjacent
word pairs are not stored bigrams.
"""
import os
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lm'))
import hw1lm  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lm', default=os.path.join(os.environ.get('STT_ROOT', 'stt-data'), 'work/lm/meeting-gen2-25397.lm'))
    a = ap.parse_args()
    rows, bad, seen = [], Counter(), set()
    for f in sorted(HERE.glob('cat_*.tsv')):
        cat = f.stem[4:]
        for line in open(f, encoding='utf-8'):
            parts = line.rstrip('\n').split('\t')
            if len(parts) < 2 or not parts[1].strip():
                bad['format'] += 1
                continue
            display, spoken = parts[0].strip(), parts[1].strip()
            sub = parts[2].strip() if len(parts) > 2 else ''
            if hw1lm.normalize_text(spoken) != spoken:
                bad['alphabet'] += 1
                continue
            if spoken in seen:
                bad['duplicate'] += 1
                continue
            seen.add(spoken)
            rows.append((display, spoken, cat, sub))
    lm = hw1lm.read_lm(open(a.lm, 'rb').read())
    vocab = lm.word_id
    words = Counter(w for _, s, _, _ in rows for w in s.split())
    oov = {w for w in words if w not in vocab}
    multi = [s for _, s, _, _ in rows if ' ' in s]
    unseen_pair = 0
    for s in multi:
        ws = s.split()
        if all(w in vocab for w in ws) and any(((vocab[x] << 16) | vocab[y]) not in lm.bigram for x, y in zip(ws, ws[1:])):
            unseen_pair += 1
    with open(HERE / 'terms.tsv', 'w') as f:
        for r in rows:
            f.write('\t'.join(r) + '\n')
    by_cat = Counter(c for _, _, c, _ in rows)
    terms_with_oov = sum(1 for _, s, _, _ in rows if any(w in oov for w in s.split()))
    rep = {'terms': len(rows), 'dropped': dict(bad), 'by_category': dict(by_cat), 'distinct_words': len(words),
           'words_new_to_lm': len(oov), 'terms_with_a_new_word': terms_with_oov, 'multiword_terms': len(multi),
           'multiword_known_words_unseen_pair': unseen_pair, 'lm': a.lm, 'lm_vocab': lm.V}
    (HERE / 'terms_report.json').write_text(json.dumps(rep, indent=1))
    (HERE / 'new_words.txt').write_text('\n'.join(sorted(oov)) + '\n')
    print(json.dumps(rep, indent=1))


if __name__ == '__main__':
    main()
