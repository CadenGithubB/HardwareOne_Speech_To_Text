#!/usr/bin/env python3
"""Greedy-CTC word error rate for a checkpoint on prepared stores.

evaluate.py --ckpt DIR --sets ami-sdm-test ami-ihm-test librispeech-test-clean
            [--limit N] [--out report.json]
"""
import argparse
import json
import random

import numpy as np
import torch

from common import QuartzNet, Frontend, load_checkpoint, greedy_decode, word_errors


def _subset(store, limit):
    order = list(range(len(store)))
    random.Random(0).shuffle(order)
    return order if limit is None else order[:limit]


@torch.no_grad()
def evaluate_stores(model, template, sets, device, batch_seconds=200.0, examples=0):
    from data import Store
    frontend = Frontend(template)
    rng = np.random.default_rng(0)
    results = {}
    for name, limit in sets:
        try:
            store = Store(name)
        except FileNotFoundError:
            continue
        items = sorted(_subset(store, limit), key=lambda i: store.lengths[i])
        errors = words = 0
        shown = []
        batch = []

        def flush():
            nonlocal errors, words
            feats = [frontend(store.samples(i), dither=True, rng=rng) for i in batch]
            lengths = torch.tensor([f.shape[1] for f in feats])
            x = torch.zeros(len(feats), 64, int(lengths.max()))
            for k, f in enumerate(feats):
                x[k, :, :f.shape[1]] = f
            log_probs, out_lengths = model(x.to(device), lengths.to(device))
            for i, hyp in zip(batch, greedy_decode(log_probs, out_lengths)):
                ref = store.texts[i]
                errors += word_errors(ref, hyp)
                words += len(ref.split())
                if len(shown) < examples:
                    shown.append({'ref': ref, 'hyp': hyp})

        for i in items:
            if batch and store.lengths[i] / 16000 * (len(batch) + 1) > batch_seconds:
                flush()
                batch = []
            batch.append(i)
        if batch:
            flush()
        results[name] = {'wer': errors / max(words, 1), 'errors': errors, 'words': words,
                         'utterances': len(items), 'examples': shown}
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--ckpt', required=True)
    p.add_argument('--sets', nargs='+', required=True)
    p.add_argument('--limit', type=int)
    p.add_argument('--examples', type=int, default=8)
    p.add_argument('--out')
    a = p.parse_args()
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    config, state = load_checkpoint(a.ckpt)
    model = QuartzNet(config).load_nemo(state).to(device).eval()
    results = evaluate_stores(model, state, [(s, a.limit) for s in a.sets], device, examples=a.examples)
    for name, r in results.items():
        print(f"{name}: WER {r['wer'] * 100:.1f}% ({r['errors']}/{r['words']} words, {r['utterances']} utts)")
    if a.out:
        with open(a.out, 'w') as f:
            json.dump({'ckpt': a.ckpt, 'results': results}, f, indent=2)


if __name__ == '__main__':
    main()
