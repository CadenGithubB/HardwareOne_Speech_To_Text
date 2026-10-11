#!/usr/bin/env python3
"""Score LM files (with their own header params) on named tune.py sets.

  lm_eval.py --ckpt DIR --lms a.lm b.lm ... [--sets peoples-test ami-sdm-test ...]

No search: each LM decodes with the parameters tune.py wrote into its header,
so candidates tuned on AMI dev can be compared on other data (e.g. the
held-out People's Speech set) without re-tuning on it.
"""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent))
import hw1lm  # noqa: E402
from tune import WORK, Decoder, ckpt_key, compute_logits, greedy_text, load_set, wer  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ckpt', required=True)
    ap.add_argument('--lms', nargs='+', required=True)
    ap.add_argument('--sets', nargs='+', default=['peoples-test', 'ami-sdm-test', 'ami-ihm-test', 'libri-test'])
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--out')
    a = ap.parse_args()
    cache_dir = WORK / 'logits' / ckpt_key(a.ckpt)
    compute_logits(a.ckpt, a.sets, cache_dir)
    report = {'ckpt': a.ckpt, 'sets': a.sets, 'greedy': {}, 'lms': {}}
    for n in a.sets:
        s = load_set(cache_dir, n)
        report['greedy'][n] = wer(s['texts'], [greedy_text(x) for x in s['logits']])[0]
    print('greedy  ' + '  '.join(f'{n} {report["greedy"][n] * 100:6.2f}' for n in a.sets), flush=True)
    for path in a.lms:
        params = hw1lm.read_lm(path).params
        dec = Decoder(path, cache_dir, a.sets, workers=a.workers)
        res = dec.run(params, a.sets)
        dec.close()
        report['lms'][path] = {'params': params, **{n: res[n]['wer'] for n in a.sets}}
        print(f'{Path(path).name:28s} ' + '  '.join(f'{n} {res[n]["wer"] * 100:6.2f}' for n in a.sets), flush=True)
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
