#!/usr/bin/env python3
"""C/Python parity of phrase-context decoding (DecodeStart / context=, end_eos=).

  context_parity.py --harness BIN --lm meeting.lm [--logits DIR] [--count 40]

Real dev-set logits from tune.py's cache are quantised as the P4 emits them
(q = round(logit * 4), exponent -2), then decoded by hw1lm.decode_int8 and by
the C decoder (context_parity.cpp built against a firmware tree) under six
starts: sentence start with/without </s>, two-word context with/without </s>,
one-word context, and context ending in an out-of-vocabulary word. Any text
difference is printed and the exit status is non-zero.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import hw1lm  # noqa: E402
import os
STT_ROOT = Path(os.environ.get('STT_ROOT', 'stt-data'))  # data root: set STT_ROOT

STARTS = [('', True), ('', False), ('we need to', True), ('we need to', False),
          ('okay', False), ('the zzqxv', False)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--harness', required=True)
    ap.add_argument('--lm', required=True)
    ap.add_argument('--logits', default=str(STT_ROOT / 'work/lm/logits/best-a3487a5e8f68'))
    ap.add_argument('--count', type=int, default=40)
    a = ap.parse_args()
    lm = hw1lm.read_lm(a.lm)
    cases = []
    for name in ('ami-sdm-dev', 'ami-ihm-dev'):
        d = np.load(Path(a.logits) / f'{name}.npz')
        off, flat = d['offsets'], d['logits']
        for i in range(0, min(a.count, len(off) - 1)):
            q = np.clip(np.rint(flat[off[i]:off[i + 1]] * 4.0), -128, 127).astype(np.int8)
            cases.append(q)
    with tempfile.TemporaryDirectory() as tmp:
        lines, expected = [], []
        for k, q in enumerate(cases):
            path = Path(tmp) / f'c{k}.i8'
            q.tofile(path)
            for context, end in STARTS:
                lines.append(f'{path}\t{len(q)}\t{int(end)}\t{context}')
                expected.append(hw1lm.decode_int8(q, 2, lm, context=context or None, end_eos=end))
        out = subprocess.run([a.harness, a.lm], input='\n'.join(lines) + '\n', capture_output=True,
                             text=True, check=True).stdout.splitlines()
    bad = [(l, e, o) for l, e, o in zip(lines, expected, out) if e != o]
    differ = sum(1 for k in range(len(cases)) for s in range(1, len(STARTS))
                 if expected[k * len(STARTS) + s] != expected[k * len(STARTS)])
    print(f'{len(lines)} decodes, {len(bad)} C/Python mismatches; '
          f'{differ} of {len(cases) * (len(STARTS) - 1)} context variants change the text')
    for l, e, o in bad[:10]:
        print('MISMATCH', l.split('\t')[2:], '\n  py:', e, '\n  c: ', o)
    return 1 if bad or len(out) != len(lines) else 0


if __name__ == '__main__':
    sys.exit(main())
