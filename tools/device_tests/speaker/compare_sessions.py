#!/usr/bin/env python3
"""Numeric paired session summaries. Inputs are equally sized ordered arm directories.

Only successful, analyzed runs are accepted. Bootstrap resamples matched session
pairs; it does not treat phrases or words within a run as independent samples.
"""
import argparse
import json
import random
import statistics
from pathlib import Path


def load(root):
    out = []
    for path in sorted(Path(root).glob('2026*/analysis.json')):
        data = json.loads(path.read_text())
        meta = json.loads((path.parent / 'session.json').read_text())
        if data.get('valid') and meta.get('status') == 'ok':
            out.append((data, meta))
    return out


def measurements(pair):
    data, meta = pair
    s = data['summary']
    memory = meta.get('memory_samples') or []
    workers = [x['worker_ms'] for x in data['phrases'] if x.get('worker_ms') is not None]
    return {'close_ms': s['L_close']['median'],
            'worker_ms': statistics.median(workers) if workers else None,
            'sampled_psram_free_bytes': min((x['psram_free'] for x in memory), default=None),
            'sampled_internal_largest_bytes': min((x['internal_largest'] for x in memory), default=None),
            'inference_ms': s['n']['median'], 'decode_ms': s['d']['median'],
            'preview_count': data['tl_counts'].get('draft', 0),
            'preview_preempted': data['drafts'].get('preempted'),
            'first_preview_ms': data['drafts'].get('first_text_median_ms'),
            'psram_min_bytes': data['health']['psram_min_min'],
            'audio_overruns': meta.get('audio_overruns')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('arm_a'); p.add_argument('arm_b')
    args = p.parse_args()
    aa, bb = load(args.arm_a), load(args.arm_b)
    if len(aa) < 5 or len(aa) != len(bb):
        p.error('need at least five successful matched sessions in each arm')
    a, b = list(map(measurements, aa)), list(map(measurements, bb))
    rnd = random.Random(0)
    out = {'sessions_per_arm': len(a), 'bootstrap': 'paired sessions', 'metrics': {}}
    for key in a[0]:
        av, bv = [v[key] for v in a], [v[key] for v in b]
        if any(x is None for x in av + bv):
            continue
        diffs = [y - x for x, y in zip(av, bv)]
        boot = sorted(statistics.mean(rnd.choices(diffs, k=len(diffs))) for _ in range(10000))
        out['metrics'][key] = {'a': av, 'b': bv, 'mean_delta_b_minus_a': statistics.mean(diffs),
                               'ci95': [boot[250], boot[9750]]}
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
