#!/usr/bin/env python3
"""Numeric-only known-input P4 ring-probe summary. Raw/private lines never emitted."""
import argparse
import json
from pathlib import Path
import re
import statistics

FIELDS={
 'case':{'pair','mode','ok','rows','equal','cpu_us','wall_us','stack_free'},
 'copy':{'pair','mode','calls','equal','sum_us','max_us'},
 'write':{'pair','mode','calls','sum_us','max_us'},
 'done':{'ok','cases','samples','stack_bytes','flip'},
}
PATTERN=re.compile(r'TL fering_(case|copy|write|done) ((?:[a-z_]+=\d+ )+)end(?:\s|$)')

def summarize(lines):
    records={};order=[];done=None
    for line in lines:
        if 'TL fering_' not in line:continue
        m=PATTERN.search(line)
        if not m:raise ValueError('damaged ring-probe marker')
        kind=m.group(1);pairs=re.findall(r'([a-z_]+)=(\d+)',m.group(2));row={k:int(v) for k,v in pairs}
        if len(pairs)!=len(row) or set(row)!=FIELDS[kind]:raise ValueError('ring-probe fields invalid')
        if kind=='done':
            if done is not None:raise ValueError('duplicate ring-probe completion')
            done=row;continue
        if done is not None:raise ValueError('ring-probe case after completion')
        key=(row['pair'],row['mode'])
        if key[0] not in range(5) or key[1] not in (0,1):raise ValueError('ring-probe ID invalid')
        if (key,kind) in records:raise ValueError('duplicate ring-probe record')
        records[key,kind]=row
        if kind=='case':order.append(key)
    if done is None or done['ok']!=1 or done['cases']!=10 or done['stack_bytes']!=3072 or done['flip'] not in (0,1):
        raise ValueError('ring-probe incomplete/failed')
    if not 1280<=done['samples']<=65536-1024:raise ValueError('ring-probe input extent invalid')
    expected=[(pair,1-order if (pair+done['flip'])&1 else order) for pair in range(5) for order in range(2)]
    if order!=expected or len(records)!=30:raise ValueError('ring-probe matched order/count invalid')
    cases=[]
    for key in order:
        row=records[key,'case'];copy=records[key,'copy'];write=records[key,'write'];mode=key[1]
        if row['ok']!=1 or row['rows']!=done['samples']//160 or row['equal']!=row['rows']:
            raise ValueError('ring-probe feature mismatch')
        if not 128<row['stack_free']<=3072 or not row['cpu_us'] or not row['wall_us']:
            raise ValueError('ring-probe task measurement invalid')
        if copy['calls']!=(500 if mode else 0) or copy['equal']!=copy['calls'] or copy['sum_us']<copy['max_us']:
            raise ValueError('ring-probe snapshot check invalid')
        if not mode and (copy['sum_us'] or copy['max_us']):raise ValueError('reference claimed snapshot timing')
        if write['calls']!=500 or write['sum_us']<write['max_us']:raise ValueError('ring-probe write measurement invalid')
        cases.append({**row,'snapshot':copy,'producer':write})
    pairs=[]
    for pair in range(5):
        a=records[(pair,0),'case'];b=records[(pair,1),'case']
        pairs.append({'pair':pair,'cpu_delta_us':b['cpu_us']-a['cpu_us'],'wall_delta_us':b['wall_us']-a['wall_us']})
    return {'samples':done['samples'],'stack_bytes':3072,'flip':done['flip'],'cases':cases,'pairs':pairs}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('trials',nargs='+',type=Path);a=ap.parse_args();boots=[]
    for i,path in enumerate(a.trials):
        if not path.is_dir():ap.error('pass trial directories, not private data contents')
        row={'boot_id':i,'lifecycle_complete':False}
        if (path/'result.json').exists() and not (path/'failure.json').exists():
            result=json.loads((path/'result.json').read_text())
            counts={k:result.get(k) for k in ('fatal_markers','watchdog_warnings','audio_overruns')}
            row['lifecycle_counts']=counts
            row['lifecycle_complete']=all(v==0 for v in counts.values()) and min(result.get('littlefs_before',0),result.get('littlefs_after',0))>=2097152
        row.update(summarize((path/'raw.log').read_text(errors='replace').splitlines()));boots.append(row)
    result={'boots':boots,'boot_count':len(boots),'lifecycle_complete':sum(b['lifecycle_complete'] for b in boots),
            'minimum_five_clean_boots_met':len(boots)>=5 and all(b['lifecycle_complete'] for b in boots),
            'all_attempts_in_cost_summary':True,
            'boot_mean_cpu_delta_us':[statistics.mean(p['cpu_delta_us'] for p in b['pairs']) for b in boots]}
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
