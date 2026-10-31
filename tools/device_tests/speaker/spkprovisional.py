#!/usr/bin/env python3
"""Offline causal deferred-label experiment on private spkrules.py voiceprints.

spkprovisional.py SETS.json --shuffles 200 > private/report.json

Fixed experimental choices: confirmation by two or three complete-link long
phrases at cosine >=0.6, at most eight pending phrases/eight subsequent arrivals,
eight confirmed speakers. No reference IDs are used for clustering. Published
labels never change; only pending unknown labels can be resolved later.

Delay is subsequent phrase arrivals, NOT seconds. The output keeps final labels
to score them; the pending embedding state itself is bounded. Corpus even/odd
set indices form development/held-out summaries. Clean/session sets are reused
diagnostics, not held-out recordings. No model, firmware or device changes.
"""
import argparse
import collections
import json
import math
import os
from pathlib import Path
import random
import subprocess
import tempfile
import spkrules

HERE = Path(__file__).resolve().parent
RULES = ('production', 'deferred2', 'deferred3')


class Runner:
    def __init__(self, work):
        self.exe = Path(work) / 'provisional_replay'
        subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++17', '-O2',
                        str(HERE / 'provisional_replay.cpp'), '-o', str(self.exe)], check=True)

    def runs(self, phrases, jobs):
        lines = [f'clear {len(phrases[0]["e"])}']
        lines += ['load %d %s' % (p['samples'], ' '.join('%.7g' % v for v in p['e'])) for p in phrases]
        lines += ['run %d 8 %d %s' % (evidence, len(order), ' '.join(map(str, order)))
                  for evidence, order in jobs]
        out = subprocess.run([str(self.exe)], input='\n'.join(lines) + '\n', capture_output=True,
                             text=True, check=True).stdout.splitlines()
        if len(out) != len(jobs):
            raise ValueError('wrong number of replay results')
        results = []
        for line, (_, order) in zip(out, jobs):
            rows = [t.split(':') for t in line.split()]
            if len(rows) != len(order):
                raise ValueError('wrong number of phrase results')
            results.append([(int(s), why, int(delay)) for s, why, delay in rows])
        return results


def empty():
    return {'base': spkrules.empty(), 'delay': collections.Counter(),
            'labelled_delay': collections.Counter(), 'immediate_labelled': 0}


def add(total, phrases, order, assignments):
    spkrules.add(total['base'], spkrules.run_metrics(phrases, order, [(s, r) for s, r, _ in assignments]))
    for i, (speaker, _, delay) in zip(order, assignments):
        if phrases[i]['ref'] is None or phrases[i]['mixed']:
            continue
        total['delay'][delay] += 1
        if speaker >= 0:
            total['labelled_delay'][delay] += 1
            total['immediate_labelled'] += delay == 0


def delay_summary(hist):
    n = sum(hist.values())
    if not n:
        return {'n': 0, 'p50': None, 'p90': None, 'max': None}
    def quantile(frac):
        at = max(1, int(math.ceil(n * frac)))
        seen = 0
        for k, v in sorted(hist.items()):
            seen += v
            if seen >= at:
                return k
    return {'n': n, 'p50': quantile(.5), 'p90': quantile(.9), 'max': max(hist),
            'mean': round(sum(k * v for k, v in hist.items()) / n, 3)}


def derive(t):
    base = spkrules.derive(t['base'])
    base['immediate_coverage'] = spkrules.spkdiag.pct(t['immediate_labelled'], t['base']['scored'])
    base['finalization_delay_arrivals'] = delay_summary(t['delay'])
    base['labelled_delay_arrivals'] = delay_summary(t['labelled_delay'])
    return base


def confidence_intervals(rows, odd, repeats=10000):
    """Paired resampling of conversation indices, keeping clean/g2 together.

    Corpus dialogues can share speakers; these are conditional descriptive
    intervals, not speaker-independent generalization intervals.
    """
    keys = ('scored', 'labelled', 'right', 'split', 'merge')
    strata = collections.defaultdict(lambda: collections.defaultdict(list))
    for row in rows:
        if not row['group'].startswith('corpus:'):
            continue
        store, number = row['name'].rsplit('/', 1)
        if int(number) % 2 != odd:
            continue
        family = store[:-3] if store.endswith('-g2') else store
        strata[family][int(number)].append(row)
    def metric(c):
        n, labelled, right, split, merge = c
        return (100*labelled/n if n else None, 100*right/labelled if labelled else None,
                100*split/n if n else None, 100*merge/n if n else None)
    out = {}
    for rule in RULES[1:]:
        families = []
        for blocks in strata.values():
            family = []
            for block in blocks.values():
                family.append([[sum(row['rules'][r]['counts'][k] for row in block) for k in keys]
                               for r in ('production', rule)])
            families.append(family)
        rng = random.Random(913)
        distributions = [[] for _ in range(4)]
        for _ in range(repeats):
            sums = [[0]*5, [0]*5]
            for family in families:
                for _ in family:
                    pair = rng.choice(family)
                    for side in (0, 1):
                        for k in range(5):
                            sums[side][k] += pair[side][k]
            base, candidate = map(metric, sums)
            for dest, a, b in zip(distributions, candidate, base):
                if a is not None and b is not None:
                    dest.append(a-b)
        out[rule] = {key: ([round(sorted(values)[min(len(values)-1, int(len(values)*p))], 3)
                           for p in (.025, .975)] if values else None)
                     for key, values in zip(('coverage', 'accuracy_labelled', 'split_per_100', 'merge_per_100'), distributions)}
    return {'replicates': repeats, 'paired_blocks': sum(len(s) for s in strata.values()),
            'unit': 'conversation index within source family, paired clean/g2', 'ci95': out}


def compare(sets, shuffles=200, seed=1, bootstrap=10000):
    totals = collections.defaultdict(lambda: collections.defaultdict(lambda: [empty(), empty()]))
    per_set = []
    with tempfile.TemporaryDirectory(prefix='spk-provisional-') as tmp:
        production = spkrules.Runner(tmp)
        candidate = Runner(tmp)
        config = spkrules.parse_rule('production', .6)
        for k, s in enumerate(sets):
            ph = s['phrases']
            if not ph:
                continue
            rng = random.Random(seed * 1000003 + k)
            orders = [list(range(len(ph)))]
            if not s['group'].startswith('corpus'):
                for _ in range(shuffles):
                    order = list(range(len(ph)))
                    rng.shuffle(order)
                    orders.append(order)
            original = production.runs(ph, [(config, o) for o in orders], 32000)
            deferred = candidate.runs(ph, [(e, o) for e in (2, 3) for o in orders])
            by_rule = [ [[(spk, reason, 0) for spk, reason in rows] for rows in original],
                        deferred[:len(orders)], deferred[len(orders):] ]
            groups = [s['group'], 'all']
            if s['group'].startswith('corpus'):
                number = int(s['name'].rsplit('/', 1)[1])
                groups += ['corpus', 'corpus_development' if number % 2 == 0 else 'corpus_heldout']
            row = {'name': s['name'], 'group': s['group'], 'rules': {}}
            for rule, results in zip(RULES, by_rule):
                for j, (order, assignments) in enumerate(zip(orders, results)):
                    for group in groups:
                        add(totals[group][rule][0], ph, order, assignments)
                        if j == 0:
                            add(totals[group][rule][1], ph, order, assignments)
                    if j == 0:
                        t = empty()
                        add(t, ph, order, assignments)
                        row['rules'][rule] = derive(t)
                        row['rules'][rule]['counts'] = {k: t['base'][k] for k in
                                                       ('scored', 'labelled', 'right', 'split', 'merge')}
            per_set.append(row)
    groups = {g: {r: {'all_orders': derive(t[0]), 'in_order': derive(t[1])} for r, t in v.items()}
              for g, v in totals.items()}
    versus = {}
    for g, v in groups.items():
        base = v['production']['all_orders']
        versus[g] = {}
        for r in RULES[1:]:
            a = v[r]['all_orders']
            delta = {key: (round(a[key] - base[key], 2) if a[key] is not None and base[key] is not None else None) for key in
                     ('coverage', 'accuracy_labelled', 'split_per_100', 'merge_per_100')}
            delta['split_merge_criterion'] = a['split_per_100'] is not None and a['split_per_100'] < base['split_per_100'] and a['merge_per_100'] <= base['merge_per_100']
            delta['quality_nonregression'] = delta['split_merge_criterion'] and a['coverage'] >= base['coverage'] and a['accuracy_labelled'] >= base['accuracy_labelled']
            versus[g][r] = delta
    intervals = {}
    for odd, group in ((0, 'corpus_development'), (1, 'corpus_heldout')):
        if group in groups and bootstrap:
            intervals[group] = confidence_intervals(per_set, odd, bootstrap)
    return {'config': {'threshold': .6, 'min_new_samples': 32000, 'confirmations': [2, 3],
                       'pending_limit': 8, 'max_delay_arrivals': 8, 'max_speakers': 8},
            'shuffles': shuffles, 'seed': seed, 'sets': dict(collections.Counter(s['group'] for s in sets)),
            'groups': groups, 'versus_production': versus, 'paired_bootstrap': intervals,
            'per_set_in_order': per_set}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('sets')
    ap.add_argument('--shuffles', type=int, default=200)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--bootstrap', type=int, default=10000)
    a = ap.parse_args()
    if a.shuffles < 0 or a.bootstrap < 0:
        ap.error('--shuffles and --bootstrap must be nonnegative')
    print(json.dumps(compare(json.loads(Path(a.sets).read_text())['sets'], a.shuffles, a.seed, a.bootstrap)))


if __name__ == '__main__':
    main()
