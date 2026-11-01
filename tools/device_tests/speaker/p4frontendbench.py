#!/usr/bin/env python3
"""Summarize diagnostic frontend benchmark logs; output numeric evidence only.

Each positional folder is an independently rebooted trial containing raw.log
and result.json from p4speakerparity.py. Bootstrap samples whole boot trials,
not the ten correlated timing pairs within each boot. No transcripts/vectors
are copied into this summary.
"""
import argparse
import json
from pathlib import Path
import random
import re
import statistics


def parse(lines):
    rows = {}
    done = None
    for line in lines:
        if 'TL spk_bench_error' in line:
            raise ValueError('firmware benchmark failure')
        m = re.search(r'TL spk_bench run=(\d+) calls=(\d+) reference_us=(\d+) candidate_us=(\d+)(?:\s|$)', line)
        if m:
            run, calls, old, new = map(int, m.groups())
            if run in rows or not 0 <= run < 10 or calls != 3 or min(old, new) <= 0:
                raise ValueError('duplicate/invalid benchmark pair')
            rows[run] = {'run': run, 'reference_us': old/calls, 'candidate_us': new/calls}
        m = re.search(r'TL spk_bench_done cases=(\d+) ok=(\d+) workspace=(\d+) output=(\d+)(?:\s|$)', line)
        if m:
            if done is not None:
                raise ValueError('duplicate benchmark completion')
            cases, ok, workspace, output = map(int, m.groups())
            if cases != 6 or ok != 1 or min(workspace, output) <= 0:
                raise ValueError('invalid benchmark completion')
            done = {'bit_exact_cases': cases, 'workspace_bytes': workspace, 'output_bytes': output}
    if done is None or set(rows) != set(range(10)):
        raise ValueError('incomplete benchmark')
    return {**done, 'pairs': [rows[i] for i in range(10)]}


def summarize(trials):
    if len(trials) < 5:
        raise ValueError('at least five independent boot trials required')
    if len({(t['workspace_bytes'],t['output_bytes']) for t in trials}) != 1:
        raise ValueError('workspace/output changed between boots')
    rows = []
    for t in trials:
        pairs = t['pairs']
        old = statistics.mean(r['reference_us'] for r in pairs)
        new = statistics.mean(r['candidate_us'] for r in pairs)
        rows.append({'reference_us':old, 'candidate_us':new, 'delta_us':new-old,
                     'delta_percent':100*(new-old)/old})
    rng = random.Random(17)
    resamples = [[rng.choice(rows) for _ in rows] for _ in range(10000)]
    means = sorted(statistics.mean(r['delta_us'] for r in sample) for sample in resamples)
    percentages = sorted(100*sum(r['delta_us'] for r in sample)/sum(r['reference_us'] for r in sample)
                         for sample in resamples)
    def distribution(key):
        values=sorted(p[key] for t in trials for p in t['pairs'])
        def quantile(q):
            at=q*(len(values)-1);lo=int(at);hi=min(lo+1,len(values)-1)
            return values[lo]+(values[hi]-values[lo])*(at-lo)
        return {'min':values[0],'p05':quantile(.05),'median':statistics.median(values),
                'p95':quantile(.95),'max':values[-1]}
    return {'boots':len(trials), 'pairs':sum(len(t['pairs']) for t in trials),
            'bit_exact_cases':sum(t['bit_exact_cases'] for t in trials),
            'workspace_bytes_each':trials[0]['workspace_bytes'],
            'output_bytes_each':trials[0]['output_bytes'],
            'reference_us_mean':statistics.mean(r['reference_us'] for r in rows),
            'candidate_us_mean':statistics.mean(r['candidate_us'] for r in rows),
            'paired_delta_us_mean':statistics.mean(r['delta_us'] for r in rows),
            'paired_delta_us_bootstrap95':[means[249],means[9749]],
            'paired_delta_percent':100*sum(r['delta_us'] for r in rows)/sum(r['reference_us'] for r in rows),
            'paired_delta_percent_bootstrap95':[percentages[249],percentages[9749]],
            'reference_us_distribution':distribution('reference_us'),
            'candidate_us_distribution':distribution('candidate_us'),
            'per_boot':rows}


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('trials',nargs='+',type=Path);a=ap.parse_args()
    if len(set(p.resolve() for p in a.trials))!=len(a.trials):
        ap.error('duplicate trial folders')
    parsed=[]
    identities=set()
    for folder in a.trials:
        result=json.loads((folder/'result.json').read_text())
        if any(result[k] for k in ('audio_overruns','watchdog_warnings','fatal_markers')):
            raise ValueError('trial has a reliability fault')
        identities.add((result['samples'],result['dim']))
        parsed.append(parse((folder/'raw.log').read_text(errors='replace').splitlines()))
    if len(identities)!=1:
        raise ValueError('input sample count/dimension changed between trials')
    print(json.dumps(summarize(parsed),indent=2))
