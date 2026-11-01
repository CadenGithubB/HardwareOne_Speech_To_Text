#!/usr/bin/env python3
"""Read numeric pointwise A/B diagnostics; raw logs and tensors remain private."""
import argparse
import json
from pathlib import Path
import random
import re
import statistics


def parse(lines):
    records={};done=None;hashes={}
    fields={
        'time':('wall_us','inference_us','stages_us','yield_us'),
        'calls':('tiled','width1','c512'),
        'mem':('low_int','low_psram','free_int','free_psram','largest_int','largest_psram'),
    }
    for line in lines:
        if 'TL pw_error' in line:raise ValueError('firmware probe failed')
        m=re.search(r'TL pw_(time|calls|mem) pair=(\d+) mode=(\d+) (.*?) end(?:\s|$)',line)
        if m:
            kind,pair,mode,values=m.groups();pair=int(pair);mode=int(mode)
            if not 0<=pair<3 or mode not in (0,1):raise ValueError('invalid pair/mode')
            tokens=values.split()
            if any(not re.fullmatch(r'\w+=\d+',token) for token in tokens):raise ValueError('interleaved metric line')
            row=dict(token.split('=') for token in tokens)
            if len(row)!=len(tokens):raise ValueError('duplicate metric value')
            if set(row)!=set(fields[kind]):raise ValueError('invalid metric fields')
            key=(pair,mode);record=records.setdefault(key,{})
            if kind in record:raise ValueError('duplicate metric block')
            record[kind]={k:int(v) for k,v in row.items()}
        m=re.search(r'TL pw_hash kind=(input|output|text) sha=([0-9a-f]{64}) end(?:\s|$)',line)
        if m:
            kind,sha=m.groups()
            if kind in hashes or int(sha,16)==0:raise ValueError('duplicate/empty tensor identity')
            hashes[kind]=sha
        m=re.search(r'TL pw_done ok=(\d+) hashes_equal=(\d+) warm=(\d+) pairs=(\d+) samples=(\d+) end(?:\s|$)',line)
        if m:
            if done is not None:raise ValueError('duplicate completion')
            ok,equal,warm,pairs,samples=map(int,m.groups())
            if (ok,equal,warm,pairs)!=(1,1,4,3) or samples<=0:raise ValueError('failed/incomplete comparison')
            done={'samples':samples,'warm_hash_checks':warm,'timed_hash_checks':pairs*2}
    if done is None or set(records)!={(p,m) for p in range(3) for m in (0,1)}:
        raise ValueError('missing comparison records')
    if set(hashes)!={'input','output','text'}:raise ValueError('missing tensor identities')
    for r in records.values():
        if set(r)!=set(fields):raise ValueError('missing metric block')
        c=r['calls'];t=r['time']
        if not (0<c['c512']<=c['tiled'] and 0<c['width1']<=c['tiled']):raise ValueError('target path not exercised')
        if not (t['wall_us']>=t['inference_us']>t['yield_us'] and t['stages_us']>0):
            raise ValueError('inconsistent timing')
        if not all(r['mem'].values()):raise ValueError('missing memory observations')
    for pair in range(3):
        if records[pair,0]['calls']!=records[pair,1]['calls']:
            raise ValueError('kernel shape/call counts changed')
    return {**done,'hashes':hashes,'pairs':[[records[p,m] for m in (0,1)] for p in range(3)]}


def summarize(trials):
    if len(trials)<5:raise ValueError('five independent boots required')
    if len({t['samples'] for t in trials})!=1:raise ValueError('input length changed')
    if len({tuple(sorted(t['hashes'].items())) for t in trials})!=1:
        raise ValueError('tensor/text identities changed between boots')
    rng=random.Random(17);samples=[[rng.randrange(len(trials)) for _ in trials] for _ in range(10000)]
    metrics={}
    for field in ('wall_us','inference_us','stages_us','yield_us'):
        boots=[]
        for t in trials:
            old=statistics.mean(p[0]['time'][field] for p in t['pairs'])
            new=statistics.mean(p[1]['time'][field] for p in t['pairs'])
            boots.append({'reference':old,'candidate':new,'delta':new-old})
        means=sorted(statistics.mean(boots[i]['delta'] for i in sample) for sample in samples)
        pct=sorted(100*sum(boots[i]['delta'] for i in sample)/sum(boots[i]['reference'] for i in sample)
                   for sample in samples) if all(b['reference'] for b in boots) else None
        values=[[p[mode]['time'][field] for t in trials for p in t['pairs']] for mode in (0,1)]
        metrics[field]={'reference_mean':statistics.mean(b['reference'] for b in boots),
            'candidate_mean':statistics.mean(b['candidate'] for b in boots),
            'paired_delta_mean':statistics.mean(b['delta'] for b in boots),
            'paired_delta_bootstrap95':[means[249],means[9749]],
            'paired_delta_percent':100*sum(b['delta'] for b in boots)/sum(b['reference'] for b in boots)
                if sum(b['reference'] for b in boots) else None,
            'paired_delta_percent_bootstrap95':[pct[249],pct[9749]] if pct else None,
            'distribution':{'reference':{'min':min(values[0]),'median':statistics.median(values[0]),'max':max(values[0])},
                            'candidate':{'min':min(values[1]),'median':statistics.median(values[1]),'max':max(values[1])}},
            'per_boot':boots}
    memory={}
    for field in ('low_int','low_psram','free_int','free_psram','largest_int','largest_psram'):
        values=[[p[mode]['mem'][field] for t in trials for p in t['pairs']] for mode in (0,1)]
        memory[field]={'reference_min':min(values[0]),'candidate_min':min(values[1]),
                       'reference_median':statistics.median(values[0]),'candidate_median':statistics.median(values[1])}
    return {'boots':len(trials),'timed_pairs':sum(len(t['pairs']) for t in trials),
            'hash_equal_calls':sum(t['warm_hash_checks']+t['timed_hash_checks'] for t in trials),
            'samples':trials[0]['samples'],'tensor_identities_equal_across_boots':True,'metrics':metrics,'memory':memory,
            'call_counts_per_inference':sorted({tuple(sorted(p[0]['calls'].items())) for t in trials for p in t['pairs']})}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('trials',nargs='+',type=Path);a=ap.parse_args()
    if len({p.resolve() for p in a.trials})!=len(a.trials):ap.error('duplicate trial folders')
    trials=[]
    for folder in a.trials:
        r=json.loads((folder/'result.json').read_text())
        if any(r[k] for k in ('audio_overruns','watchdog_warnings','fatal_markers')):raise ValueError('reliability fault')
        trial=parse((folder/'raw.log').read_text(errors='replace').splitlines())
        if trial['samples']!=r['samples']:raise ValueError('probe/fixture sample mismatch')
        trials.append(trial)
    print(json.dumps(summarize(trials),indent=2))
