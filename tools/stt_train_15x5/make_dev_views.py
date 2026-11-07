#!/usr/bin/env python3
"""Hold out dev sets from training stores (whole speakers; small real copies).

make_dev_views.py SRC_STORE DEV_NAME --items 400 [--seed 5]

Picks whole speakers (People's Speech: source recording; VoxPopuli: speaker)
from SRC_STORE until ~--items utterances, writes stores/DEV_NAME/ as a small
real store (its own audio.bin with just those items: exFAT, where the data
now lives, has no symlinks) and removes
them from SRC_STORE's keep.json and writes independent excluded.json files in
all same-corpus training shards. Existing DEV_NAME audio is left untouched,
but re-running repairs cross-shard exclusions. Quality filtering cannot restore
these examples. Run only against prepared working copies when migrating old data.
"""
import argparse
import json
import os
import hashlib
import random
import re

from data import STORES
from diagnostics import atomic_json, effective_ids, family


def exclude_speakers(root, source, speakers):
    """Persist exclusions independently of quality filters, across every corpus train shard."""
    matched = []
    for directory in sorted(root.iterdir()):
        if family(directory.name) != family(source) or not any(re.fullmatch(r'train[0-9]*', token) for token in directory.name.split('-')):
            continue
        path = directory / 'index.json'
        if not path.exists():
            continue
        idx = json.loads(path.read_text())
        held = [i for i, speaker in enumerate(idx['speakers']) if speaker in speakers]
        target = directory / 'excluded.json'
        previous = json.loads(target.read_text()) if target.exists() else {}
        excluded = sorted(set(previous.get('excluded', [])) | set(held))
        atomic_json(target, {'excluded': excluded, 'reason': 'reserved development speakers'})
        matched.append({'store': directory.name, 'excluded': len(held)})
    return matched



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dev')
    ap.add_argument('--items', type=int, default=400)
    ap.add_argument('--seed', type=int, default=5)
    a = ap.parse_args()
    src, dev = STORES / a.src, STORES / a.dev
    if (dev / 'index.json').exists():
        existing = json.loads((dev / 'index.json').read_text())
        if existing.get('source', {}).get('store') != a.src:
            raise ValueError('Existing development store has a different source')
        print(exclude_speakers(STORES, a.src, set(existing['speakers'])))
        return
    index = json.loads((src / 'index.json').read_text())
    n = len(index['lengths'])
    keep_path = src / 'keep.json'
    keep = set(effective_ids(src, index))
    by_speaker = {}
    for i in sorted(keep):
        by_speaker.setdefault(index['speakers'][i], []).append(i)
    speakers = sorted(by_speaker)
    random.Random(a.seed).shuffle(speakers)
    chosen = []
    for s in speakers:
        if len(chosen) >= a.items:
            break
        chosen += by_speaker[s]
    chosen.sort()
    dev.mkdir(parents=True)
    import numpy as np
    audio = np.memmap(src / 'audio.bin', dtype='<i2', mode='r')
    offsets, pos = [], 0
    sha = hashlib.sha256()  # of exactly what was written; verify_stores.py re-reads it from disk
    with open(dev / 'audio.bin', 'wb') as f:
        for i in chosen:
            o, n = index['offsets'][i], index['lengths'][i]
            data = np.asarray(audio[o:o + n]).tobytes()
            f.write(data)
            sha.update(data)
            offsets.append(pos)
            pos += n
        f.flush()
        os.fsync(f.fileno())
    exclude_speakers(STORES, a.src, {index['speakers'][i] for i in chosen})
    (dev / 'index.json').write_text(json.dumps({
        'offsets': offsets, 'lengths': [index['lengths'][i] for i in chosen],
        'texts': [index['texts'][i] for i in chosen], 'speakers': [index['speakers'][i] for i in chosen],
        'source': {'store': a.src, 'held_out_from_training': True}, 'audio_sha256': sha.hexdigest()}))
    held = set(chosen)
    remaining = sorted(keep - held)
    info = json.loads(keep_path.read_text()) if keep_path.exists() else {}
    info.update({'keep': remaining, 'dev_held_out': {a.dev: len(chosen)}})
    keep_path.write_text(json.dumps(info))
    hours = sum(index['lengths'][i] for i in chosen) / 16000 / 3600
    print(f'{a.dev}: {len(chosen)} items, {hours:.2f} h, {len({index["speakers"][i] for i in chosen})} speakers; '
          f'{a.src} now trains on {len(remaining)}/{n}')


if __name__ == '__main__':
    main()
