#!/usr/bin/env python3
"""Validate completed numeric heap-field watch lifecycles; raw evidence stays private."""
import argparse,json,re
from pathlib import Path
import p4hwread,p4feownership,teardowndiag
FIELDS={
 'armed':{'core','ok','address','data1','data2','control'},
 'active':{'ok','mask','heap','address','value','expected'},
 'release':{'core','ok','address','data1','data2','control'},
 'released':{'ok','mask'},
}
def summarize(lines,heap):
    # Match the live reader: a retained previous-crash summary is history,
    # not another fault in this lifecycle. Never repair a live fault line.
    live=[];previous=False
    for line in lines:
        if '=== PREVIOUS CRASH ===' in line:previous=True;continue
        if previous:
            if line.strip()=='======================':previous=False
            continue
        live.append(line)
    if previous:raise ValueError('previous-crash block incomplete')
    lines=live;rows={};indices={};ticks={}
    for index,line in enumerate(lines):
        if 'TL hwwatch_' not in line:continue
        m=re.search(r'TL hwwatch_(armed|active|release|released) ((?:[a-z_0-9]+=\d+ )+)end(?:\s|$)',line)
        if not m:raise ValueError('failed/refused/damaged heap watch marker')
        kind=m.group(1);pairs=re.findall(r'([a-z_0-9]+)=(\d+)',m.group(2));r={k:int(v) for k,v in pairs};key=(kind,r.get('core',-1))
        if set(r)!=FIELDS[kind] or len(r)!=len(pairs) or any(v>0xffffffff for v in r.values()) or key in rows:raise ValueError('invalid/duplicate heap watch fields')
        rows[key]=r;indices[key]=index
        tick=re.search(r'[IDW] \((\d+)\)',line);ticks[key]=int(tick.group(1)) if tick else None
    order=[('armed',0),('armed',1),('active',-1),('release',0),('release',1),('released',-1)]
    if list(rows)!=order:raise ValueError('heap watch markers incomplete/out of order')
    address=heap+16
    for core in (0,1):
        if rows['armed',core]!={'core':core,'ok':1,'address':address,'data1':0x210000ca,'data2':address|1,'control':0x88}:raise ValueError('heap watch arm state invalid')
        if rows['release',core]!={'core':core,'ok':1,'address':address,'data1':0x21000000,'data2':0,'control':0}:raise ValueError('heap watch release state invalid')
    if rows['active',-1]!={'ok':1,'mask':3,'heap':heap,'address':address,'value':heap+20,'expected':heap+20} or rows['released',-1]!={'ok':1,'mask':0}:raise ValueError('heap watch active/release state invalid')
    readback=p4hwread.summarize(lines)
    if readback['debugger_attached_any'] or readback['first_heap_mismatch_stage'] is not None:raise ValueError('heap/header state changed')
    for stage in readback['stages']:
        if stage['heap']['heap']!=heap:raise ValueError('watched heap differs from runtime heap')
        for c in stage['cores']:
            t=c['triggers']
            if c['control_before']!=0x88 or t[0]['data1']!=0x210000ca or t[0]['data2']!=(address|1) or t[0]['data3']!=0 or not all(s['observed_reset_shape'] for s in t[1:]):raise ValueError('heap watch not present at checkpoint/unexpected peer slot')
    read_indices=[i for i,l in enumerate(lines) if 'TL hwread_done ' in l]
    end_indices=[i for i,l in enumerate(lines) if re.search(r'TL teardown phase=321 event=2 ',l)]
    if len(end_indices)!=1 or not indices['active',-1]<min(read_indices) or not max(read_indices)<end_indices[0]<indices['release',0]:raise ValueError('heap watch interval did not cover teardown')
    ownership=p4feownership.parse(lines);teardown=teardowndiag.summarize(lines)
    if teardown['complete_cycles']!=1 or len(teardown['cycles'])!=1:raise ValueError('teardown incomplete')
    if any(re.search(r'MCAUSE\s*:|Guru Meditation Error:|Task watchdog|Interrupt wdt timeout',l) for l in lines):raise ValueError('fault/watchdog in completed watch lifecycle')
    start,end=ticks['armed',0],ticks['released',-1]
    # esp_log_timestamp (RTOS/base) and the probe's esp_timer clock have a
    # boot-dependent offset. Compare log prefixes to each other, not to ms=.
    phase_tick=re.search(r'[IDW] \((\d+)\)',lines[end_indices[0]])
    phase_tick=int(phase_tick.group(1)) if phase_tick else None
    return {'heap':heap,'watched_field':address,'expected_control':heap+20,'armed_cores':2,'active_slot_checkpoints':8,'heap_checkpoints':4,
        'forced_ownership_checks':len(ownership['cases']),'teardown_markers':19,'released_cores':2,
        'watch_interval_ms':end-start if start is not None and end is not None and end>=start else None,
        'watch_after_phase321_ms':end-phase_tick if phase_tick is not None and end is not None and end>=phase_tick else None}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('logs',nargs='+',type=Path);ap.add_argument('--heap',required=True,type=lambda s:int(s,0));a=ap.parse_args()
    print(json.dumps([{'log_id':i,**summarize(p.read_text(errors='replace').splitlines(),a.heap)} for i,p in enumerate(a.logs)],indent=2))
if __name__=='__main__':main()
