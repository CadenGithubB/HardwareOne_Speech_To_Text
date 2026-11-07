#!/usr/bin/env python3
"""Greedy-CTC word error rate for a checkpoint on prepared stores.

evaluate.py --ckpt DIR --sets ami-sdm-test ami-ihm-test librispeech-test-clean
            [--limit N] [--out report.json]
"""
import argparse
import json
import random
import hashlib
from diagnostics import error_counts, summarize, paired_changes, atomic_json

import numpy as np
import torch

from common import QuartzNet, Frontend, load_checkpoint, greedy_decode, HOP


def _subset(store, limit):
    order = list(range(len(store)))
    random.Random(0).shuffle(order)
    return order if limit is None else order[:limit]


@torch.no_grad()
def evaluate_stores(model, template, sets, device, batch_seconds=200.0, examples=0, bucket=None):
    """bucket=(max_seconds, max_items): batch and pad like training's
    micro-batches (data.batch_shape) instead of by batch_seconds, so an MPS
    eval of the training model only meets shapes training has already compiled
    (train.py --eval-device mps). Filler rows are dropped before decoding.
    Items, their order and the dither stream are the same either way."""
    from data import Store, batch_shape
    frontend = Frontend(template)
    decode = getattr(model, 'decode', greedy_decode)  # Citrinet: WordPiece tokens
    rng = np.random.default_rng(0)
    results = {}
    for name, limit in sets:
        store = Store(name)  # Required evaluation sets must fail closed.
        items = sorted(_subset(store, limit), key=lambda i: store.lengths[i])
        shown = []
        utterances = []
        batch = []

        def flush():
            feats = [frontend(store.samples(i), dither=True, rng=rng) for i in batch]
            lengths = torch.tensor([f.shape[1] for f in feats])
            rows, frames = len(feats), int(lengths.max())
            if bucket:
                rows, frames = batch_shape(frames, *bucket)
                lengths = torch.cat([lengths, lengths[:1].repeat(rows - len(feats))])  # filler rows
            x = torch.zeros(rows, feats[0].shape[0], frames)
            for k, f in enumerate(feats):
                x[k, :, :f.shape[1]] = f
            log_probs, out_lengths = model(x.to(device), lengths.to(device))
            if not torch.isfinite(log_probs).all():
                raise FloatingPointError(f'{name}: nonfinite evaluation logits')
            log_probs, out_lengths = log_probs[:len(feats)], out_lengths[:len(feats)]
            for i, hyp in zip(batch, decode(log_probs, out_lengths)):
                ref = store.texts[i]
                pcm = np.asarray(store.audio[store.offsets[i]:store.offsets[i]+store.lengths[i]], dtype='<i2')
                counts = error_counts(ref, hyp)
                utterances.append({'id': f'{name}:{store.ids[i]}', 'source': name,
                    'speaker': store.speakers[i], 'ref': ref, 'hyp': hyp,
                    'pcm_sha256': hashlib.sha256(pcm.tobytes()).hexdigest(),
                    'seconds': float(store.lengths[i])/16000, **counts})
                if len(shown) < examples:
                    shown.append({'ref': ref, 'hyp': hyp})

        for i in items:
            if bucket:  # items are sorted, so item i sets the bucket's row count
                full = len(batch) >= batch_shape(-(-int(store.lengths[i]) // HOP), *bucket)[0]
            else:
                full = store.lengths[i] / 16000 * (len(batch) + 1) > batch_seconds
            if batch and full:
                flush()
                batch = []
            batch.append(i)
        if batch:
            flush()
        results[name] = {**summarize(utterances), 'examples': shown, 'records': utterances}
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--ckpt', required=True)
    p.add_argument('--sets', nargs='+', required=True)
    p.add_argument('--limit', type=int)
    p.add_argument('--examples', type=int, default=8)
    p.add_argument('--out')
    p.add_argument('--compare', help='Previous report with identical utterance coverage')
    p.add_argument('--device', default='cuda' if torch.cuda.is_available() else
                   'mps' if torch.backends.mps.is_available() else 'cpu')
    a = p.parse_args()
    device = torch.device(a.device)
    config, state = load_checkpoint(a.ckpt)
    from citrinet import is_citrinet, Citrinet, load_vocab
    if is_citrinet(config):
        model = Citrinet(config, load_vocab(a.ckpt)).load_nemo(state).to(device).eval()
    else:
        model = QuartzNet(config).load_nemo(state).to(device).eval()
    results = evaluate_stores(model, state, [(s, a.limit) for s in a.sets], device, examples=a.examples)
    if a.compare:
        previous = json.loads(open(a.compare).read())['results']
        if previous.keys() != results.keys():
            raise ValueError('Comparison dataset coverage differs')
        for name, r in results.items():
            r['paired'] = paired_changes(previous[name]['records'], r['records'])
    for name, r in results.items():
        metric = f"WER {r['wer']*100:.1f}%" if r['wer'] is not None else f"phantom words/min {r['phantom_words_per_minute']:.2f}"
        print(f"{name}: {metric} ({r['errors']}/{r['words']} words, {r['utterances']} utts)")
    if a.out:
        atomic_json(a.out, {'ckpt': a.ckpt, 'results': results})


if __name__ == '__main__':
    main()
