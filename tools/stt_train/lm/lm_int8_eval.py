#!/usr/bin/env python3
"""Greedy (device semantics) and LM WER on saved full-int8 model logits.

lm_int8_eval.py --npz-dir DIR --model NAME --lm LM [--lm-name label] ...
Uses the LM header params unchanged. Read-only use of experiments/stt_train/lm/hw1lm.py.
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
sys.dont_write_bytecode = True
sys.path.insert(0, 'experiments/stt_train/lm')
import hw1lm


def word_errors(ref, hyp):
    a, b = ref.split(), hyp.split()
    row = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        nxt = [i]
        for j, right in enumerate(b, 1):
            nxt.append(min(nxt[-1] + 1, row[j] + 1, row[j - 1] + (left != right)))
        row = nxt
    return row[-1]


ap = argparse.ArgumentParser()
ap.add_argument('--npz-dir', type=Path, required=True)
ap.add_argument('--model', required=True)
ap.add_argument('--lm', action='append', required=True)
ap.add_argument('--sets', nargs='*', default=['ami-sdm-validation', 'ami-ihm-validation', 'librispeech-dev-clean'])
a = ap.parse_args()
out = {}
for lm_path in a.lm:
    lm = hw1lm.read_lm(lm_path)
    params = {k: lm.params[k] for k in hw1lm.PARAM_NAMES}
    params['beam_width'] = int(params['beam_width'])
    res = {'params': params, 'lm_sha256': lm.sha256}
    for s in a.sets:
        d = np.load(a.npz_dir / f'{a.model}-{s}.npz')
        q, off, texts, e = d['q'], d['offsets'], d['texts'].tolist(), int(d['exponent'])
        ge = le = words = 0
        for i, ref in enumerate(texts):
            x = q[off[i]:off[i + 1]]
            g = ' '.join(hw1lm.greedy_device(x).split())
            h = hw1lm.decode_int8(x, -e, lm, None, **params)
            ge += word_errors(ref, g); le += word_errors(ref, h); words += len(ref.split())
        res[s] = {'utterances': len(texts), 'words': words, 'greedy_int8_wer': ge / words, 'lm_int8_wer': le / words}
        print(a.model, lm_path, s, json.dumps(res[s]), flush=True)
    out[lm_path] = res
print(json.dumps(out, indent=1))
