#!/usr/bin/env python3
"""Numeric summary of real-task P4 feature-cache ownership diagnostics."""
import argparse
import json
from pathlib import Path
import re


def parse(lines):
    cases={};done=None
    for line in lines:
        m=re.search(r'TL feown_case mode=(\d+) kind=(\d+) ok=(\d+) rows=(\d+) nonzero=(\d+) equal=(\d+) stack_free=(\d+) ms=(\d+) end(?:\s|$)',line)
        if m:
            mode,kind,ok,rows,nonzero,equal,stack,ms=map(int,m.groups());key=(mode,kind)
            if key in cases or mode not in (0,1) or kind not in (0,1,2) or ok!=1:
                raise ValueError('duplicate/failed case')
            cases[key]={'mode':mode,'kind':kind,'rows':rows,'nonzero':nonzero,'equal':equal,'stack_free':stack,'ms':ms}
        m=re.search(r'TL feown_done ok=(\d+) cases=(\d+) samples=(\d+) stack_bytes=(\d+) end(?:\s|$)',line)
        if m:
            if done is not None:raise ValueError('duplicate completion')
            ok,n,samples,stack=map(int,m.groups())
            if (ok,n,stack)!=(1,6,3072) or samples<1280:raise ValueError('failed/inconsistent completion')
            done={'samples':samples,'stack_bytes':stack}
    if done is None or set(cases)!={(m,k) for m in (0,1) for k in (0,1,2)}:
        raise ValueError('incomplete ownership probe')
    for (mode,kind),case in cases.items():
        if not 128<case['stack_free']<=done['stack_bytes']:raise ValueError('insufficient/invalid stack headroom')
        if kind==0:
            if case['rows']!=done['samples']//160 or case['equal']!=case['rows']:
                raise ValueError('normal rows differ')
        elif case['rows'] or case['equal'] or (case['nonzero']!=0 if mode else case['nonzero']<=0):
            raise ValueError('late-write control/repair did not reproduce')
    return {**done,'cases':[cases[m,k] for m in (0,1) for k in (0,1,2)]}


def summarize(trials,min_trials=5):
    if len(trials)<min_trials:raise ValueError('insufficient reboot trials')
    if len({(t['samples'],t['stack_bytes']) for t in trials})!=1:raise ValueError('input/stack configuration changed')
    groups=[]
    for mode in (0,1):
        for kind in (0,1,2):
            rows=[c for t in trials for c in t['cases'] if c['mode']==mode and c['kind']==kind]
            groups.append({'mode':mode,'kind':kind,'runs':len(rows),
                'rows_equal_total':sum(c['equal'] for c in rows),
                'committed_rows':sorted({c['rows'] for c in rows}),
                'nonzero':sorted({c['nonzero'] for c in rows}),
                'stack_free_min':min(c['stack_free'] for c in rows),'stack_free_max':max(c['stack_free'] for c in rows)})
    return {'boots':len(trials),'cases':sum(len(t['cases']) for t in trials),
            'samples':trials[0]['samples'],'stack_bytes':trials[0]['stack_bytes'],
            'minimum_reboot_count_met':len(trials)>=5,'groups':groups,
            'note':'forced schedules and fixed input; not fault-frequency or performance estimates'}


def load_trial(folder):
    if (folder/'failure.json').exists():raise ValueError('lifecycle attempt failed')
    status=json.loads((folder/'result.json').read_text())
    if any(status[k] for k in ('audio_overruns','watchdog_warnings','fatal_markers')):raise ValueError('lifecycle fault')
    trial=parse((folder/'raw.log').read_text(errors='replace').splitlines())
    if trial['samples']!=status['samples']:raise ValueError('fixture/probe input mismatch')
    return trial


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('trials',nargs='+',type=Path)
    p.add_argument('--smoke',action='store_true',help='accept a single explicit smoke trial, not a qualification matrix')
    a=p.parse_args()
    if len({f.resolve() for f in a.trials})!=len(a.trials):p.error('duplicate trial folders')
    trials=[]
    for folder in a.trials:
        trials.append(load_trial(folder))
    print(json.dumps(summarize(trials,1 if a.smoke else 5),indent=2))
