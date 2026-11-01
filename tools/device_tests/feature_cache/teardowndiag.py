#!/usr/bin/env python3
"""Numbers-only summary of diagnostic teardown markers; never emits input lines."""
import argparse
import json
from pathlib import Path
import re

PHASES=(100,110,120,200,201,202,140,141,142,143,144,145,160,300,301,310,311,320,321)
MARKER=re.compile(r'TL teardown phase=(\d+) event=([012]) ms=(\d+)(?: heap_ok=([01]) check_us=(\d+) int_free=(\d+) psram_free=(\d+))? end(?:\s|$)')

def summarize(lines, allow_gaps=False):
    cycles=[]; current=None
    for line in lines:
        if 'TL teardown ' not in line:continue
        m=MARKER.search(line)
        if not m:raise ValueError('incomplete teardown marker')
        phase,event,ms=map(int,m.group(1,2,3))
        if phase==100 and event in (0,2):
            if current is not None:
                if len(current['events'])!=len(PHASES)*(1 if current['mode']=='trace' else 2):raise ValueError('new teardown before previous cycle completed')
                cycles.append(current)
            current={'mode':'trace' if event==2 else 'heap','events':[]}
        if current is None:continue # Model reset during load is outside a session teardown.
        if phase not in PHASES:raise ValueError('unknown teardown phase')
        trace=current['mode']=='trace'
        if (event==2)!=trace:raise ValueError('mixed trace and heap markers')
        i=PHASES.index(phase) if trace else PHASES.index(phase)*2+event
        previous=current['events'][-1] if current['events'] else None
        last=(PHASES.index(previous['phase']) if trace else PHASES.index(previous['phase'])*2+previous['event']) if previous else -1
        if i<=last:raise ValueError('duplicate or out-of-order teardown marker')
        if i!=last+1 and not allow_gaps:raise ValueError('missing teardown marker')
        if bool(m.group(4) is not None)!=(event==1):raise ValueError('heap fields missing or misplaced')
        row={'phase':phase,'event':event,'ms':ms}
        if event==1:
            row.update(zip(('heap_ok','check_us','int_free','psram_free'),map(int,m.group(4,5,6,7))))
        current['events'].append(row)
    if current is not None:cycles.append(current)
    for cycle in cycles:
        events=cycle.pop('events'); checked=[e for e in events if e['event']==1]
        trace=cycle['mode']=='trace'
        expected=[(p,2) for p in PHASES] if trace else [(p,e) for p in PHASES for e in (0,1)]
        observed={(e['phase'],e['event']) for e in events}
        cycle.update(complete=len(events)==len(expected) and all(e['heap_ok'] for e in checked),
            last_entered_phase=events[-1]['phase'],last_observed_phase=events[-1]['phase'],
            last_completed_phase=(events[-1]['phase'] if trace else checked[-1]['phase'] if checked else None),
            missing_events=[[p,e] for p,e in expected if (p,e) not in observed],
            failed_heap_phases=[e['phase'] for e in checked if not e['heap_ok']],
            heap_checks=len(checked),heap_check_us=sum(e['check_us'] for e in checked),
            phase_markers=len(events),elapsed_ms=(events[-1]['ms']-events[0]['ms'])%(1<<32),
            phases=events if trace else checked)
    return {'cycles':cycles,'complete_cycles':sum(c['complete'] for c in cycles)}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('logs',nargs='+',type=Path);ap.add_argument('--partial',action='store_true',help='report missing markers as incomplete; never reconstruct them');a=ap.parse_args()
    print(json.dumps([{'log_index':i,**summarize(p.read_text(errors='replace').splitlines(),allow_gaps=a.partial)} for i,p in enumerate(a.logs)],indent=2))

if __name__=='__main__':main()
