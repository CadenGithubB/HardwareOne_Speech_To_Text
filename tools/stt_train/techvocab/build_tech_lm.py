#!/usr/bin/env python3
"""build_lm.py with two extra text components (same command line as build_lm.py):

  techterms   the spoken form of every entry in terms.tsv, one per line
  techwiki    wiki_spoken.txt (Wikipedia introductions in spoken form)

e.g.  build_tech_lm.py --out T.lm --target-bytes 4000000 --mode mixn \
        --components 'ami-train;peoples-train;libri-train+libri360-train;techterms;techwiki' \
        --weights 0.51,0.21,0.13,0.05,0.10 --max-vocab 46000 --params meeting-gen2-25397.lm
Without those component names it is plain build_lm.py.
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lm'))
import build_lm  # noqa: E402

_orig = build_lm.corpus_text


def corpus_text(name, refresh=False):
    if name == 'techterms':
        return [l.rstrip('\n').split('\t')[1] for l in open(HERE / 'terms.tsv', encoding='utf-8') if '\t' in l]
    if name == 'techwiki':
        return [l.strip() for l in open(HERE / 'wiki_spoken.txt', encoding='utf-8') if l.strip()]
    return _orig(name, refresh)


build_lm.corpus_text = corpus_text

if __name__ == '__main__':
    build_lm.main()
