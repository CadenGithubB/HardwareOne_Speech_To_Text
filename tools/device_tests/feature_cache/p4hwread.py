#!/usr/bin/env python3
"""Numeric-only parser for the P4 readback-only heap/trigger diagnostic."""
import argparse
import json
from pathlib import Path
import re

FIELDS={
 'hwread':{'stage','core','ok','error','debugger','before','after','control_before','control_after'},
 'hwslots':{'stage','core','selected0','data10','data20','selected1','data11','data21','selected2','data12','data22'},
 'hwcontext':{'stage','core','data30','data31','data32'},
 'hwheap':{'stage','heap','field','value','expected','ok'},
 'hwread_done':{'stage','ok','cores','slots','heap_ok'},
}
MARKER=re.compile(r'TL (hwread_done|hwread|hwslots|hwcontext|hwheap) ((?:[a-z_0-9]+=\d+ )+)end(?:\s|$)')

def summarize(lines):
    records={};stage_order=[]
    for line in lines:
        if not re.search(r'TL hw(?:read|slots|context|heap)',line):continue
        m=MARKER.search(line)
        if not m:raise ValueError('damaged heap/trigger readback marker')
        kind=m.group(1);pairs=re.findall(r'([a-z_0-9]+)=(\d+)',m.group(2));r={k:int(v) for k,v in pairs}
        allowed=[FIELDS[kind]]+([FIELDS[kind]|{'contexts'}] if kind=='hwread_done' else [])
        if set(r) not in allowed or len(r)!=len(pairs) or any(v>0xffffffff for v in r.values()):raise ValueError('heap/trigger fields invalid')
        if r['stage'] not in range(4) or r.get('core',0) not in (0,1):raise ValueError('heap/trigger ID invalid')
        key=(r['stage'],kind,r.get('core',-1))
        if key in records:raise ValueError('duplicate heap/trigger marker')
        records[key]=r
        if kind=='hwread_done':stage_order.append(r['stage'])
    if stage_order!=[0,1,2,3]:raise ValueError('heap/trigger readback incomplete')
    stages=[];expected_records=0
    for stage in range(4):
        done=records[stage,'hwread_done',-1];heap=records[stage,'hwheap',-1];cores=[]
        contexts=done.get('contexts',0)
        if contexts not in (0,6):raise ValueError('trigger context count invalid')
        expected_records+=8 if contexts else 6
        required=[(stage,'hwheap',-1)]+[(stage,k,c) for c in (0,1) for k in ('hwread','hwslots')]+([(stage,'hwcontext',c) for c in (0,1)] if contexts else [])
        if not all(k in records for k in required):raise ValueError('missing heap/trigger record')
        if done['ok']!=1 or done['cores']!=2 or done['slots']!=6:raise ValueError('heap/trigger readback failed')
        if heap['field']!=heap['heap']+16 or heap['expected']!=heap['heap']+20 or heap['ok']!=int(heap['value']==heap['expected']) or done['heap_ok']!=heap['ok']:
            raise ValueError('heap pointer marker inconsistent')
        for core in (0,1):
            meta=records[stage,'hwread',core];slots=records[stage,'hwslots',core]
            context=records.get((stage,'hwcontext',core))
            if bool(context)!=bool(contexts):raise ValueError('trigger context records missing/mixed')
            if meta['ok']!=1 or meta['error']!=0 or meta['before']!=meta['after'] or meta['control_before']!=meta['control_after']:
                raise ValueError('trigger state not restored')
            parsed=[]
            for slot in range(3):
                if slots[f'selected{slot}']!=slot:raise ValueError('trigger selection unsupported')
                data1=slots[f'data1{slot}'];data2=slots[f'data2{slot}'];data3=context[f'data3{slot}'] if context else None
                parsed.append({'slot':slot,'data1':data1,'data2':data2,'data3':data3,'type':data1>>28,'maskmax':(data1>>21)&63,'low_bits':data1&0x0fffffff,
                    'configuration_bits':data1&0x081fffff,'observed_reset_shape':data1==0x21000000 and data2==0 and data3==0})
            cores.append({**meta,'triggers':parsed})
        stages.append({'stage':stage,'heap':heap,'cores':cores})
    if len(records)!=expected_records:raise ValueError('unexpected/missing heap-trigger records')
    return {'stages':stages,'first_heap_mismatch_stage':next((r['stage'] for r in stages if r['heap']['ok']!=1),None),
            'debugger_attached_any':any(c['debugger'] for r in stages for c in r['cores']),
            'trigger_low_bits_nonzero':sum(t['low_bits']!=0 for r in stages for c in r['cores'] for t in c['triggers']),
            'trigger_configuration_nonzero':sum(t['configuration_bits']!=0 for r in stages for c in r['cores'] for t in c['triggers']),
            'context_registers_read':sum(t['data3'] is not None for r in stages for c in r['cores'] for t in c['triggers']),
            'trigger_context_nonzero':sum(t['data3'] not in (None,0) for r in stages for c in r['cores'] for t in c['triggers']),
            'all_observed_reset_shape':all(t['observed_reset_shape'] for r in stages for c in r['cores'] for t in c['triggers']) and all(c['debugger']==0 and c['control_before']==c['control_after']==0 for r in stages for c in r['cores'])}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('logs',nargs='+',type=Path);a=ap.parse_args()
    print(json.dumps([{'log_id':i,**summarize(p.read_text(errors='replace').splitlines())} for i,p in enumerate(a.logs)],indent=2))
if __name__=='__main__':main()
