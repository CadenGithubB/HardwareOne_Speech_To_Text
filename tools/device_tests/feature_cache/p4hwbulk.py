#!/usr/bin/env python3
"""Numeric validation of a bounded 128-bit store/watch overlap experiment."""
import argparse,json,re
from pathlib import Path
from p4hwcal import check_trap,check_recovery
FIELDS={
 'target':{'core','offset','base','address','bytes','width','external'},
 'warm':{'core','ok','words','value'},
 'armed':{'core','ok','address','data1','data2','control'},
 'probe':{'core','ok','value'},'ready':{'cores','phase','verified'},
 'result':{'core','offset','address','returned','stored','value','released','data1','data2','control'},
 'release':{'core','ok','data1','data2','control'},
 'recovery':{'core','phase','address','released','idle','data1','data2','control'},
}
def live(text):
    lines=[];previous=False
    for line in text.splitlines():
        if '=== PREVIOUS CRASH ===' in line:previous=True;continue
        if previous:
            if line.strip()=='======================':previous=False
            continue
        lines.append(line)
    if previous:raise ValueError('previous-crash summary incomplete')
    return '\n'.join(lines)

def markers(text):
    rows={}
    for line in text.splitlines():
        if 'TL hwbulk_' not in line:continue
        m=re.search(r'TL hwbulk_(target|warm|armed|probe|ready|result|release|recovery) ((?:[a-z_0-9]+=\d+ )+)end(?:\s|$)',line)
        if not m:raise ValueError('refused/damaged bulk marker')
        kind=m.group(1);pairs=re.findall(r'([a-z_0-9]+)=(\d+)',m.group(2));r={k:int(v) for k,v in pairs}
        key=(kind,r.get('core',-1))
        if key in rows or set(r)!=FIELDS[kind] or len(r)!=len(pairs) or any(v>0xffffffff for v in r.values()):raise ValueError('invalid/duplicate bulk fields')
        rows[key]=r
    return rows

def summarize(attempt,recovery,core,offset,pc):
    if core not in (0,1) or offset not in (0,4) or not 0<pc<=0xffffffff:raise ValueError('invalid expected condition')
    attempt=live(attempt);recovery=live(recovery);a=markers(attempt);r=markers(recovery)
    order=[('target',core),('warm',0),('warm',1),('armed',0),('armed',1),('probe',0),('probe',1),('ready',-1)]
    if list(a)[:8]!=order:raise ValueError('bulk preconditions incomplete/out of order')
    target=a['target',core];base=target['base'];address=base+offset
    if target!={'core':core,'offset':offset,'base':base,'address':address,'bytes':32,'width':16,'external':1} or base%16 or not 0x48000000<=base<=0x4c000000-32:raise ValueError('bulk target/alignment/span invalid')
    for c in (0,1):
        if a['warm',c]!={'core':c,'ok':1,'words':4,'value':0x51a7cafe}:raise ValueError('unwatched vector execution control failed')
        if a['armed',c]!={'core':c,'ok':1,'address':address,'data1':0x210000ca,'data2':address|1,'control':0x88}:raise ValueError('bulk arm state invalid')
        if a['probe',c]!={'core':c,'ok':1,'value':0x13579bdf}:raise ValueError('bulk negative control failed')
    if a['ready',-1]!={'cores':2,'phase':2,'verified':1}:raise ValueError('bulk lease verification failed')
    common={'firing_core':core,'watch_offset':offset,'store_base':base,'watched_address':address,'store_bytes':16,'watch_bytes':4,'allocated_payload_bytes':32,'armed_cores':2,'expected_store_pc':pc}
    if re.search(r'MCAUSE\s*:',attempt):
        if list(a)!=order or list(r)!=[('recovery',0),('recovery',1)]:raise ValueError('bulk trap/recovery evidence incomplete/mixed')
        check_trap(attempt,recovery,core,pc)
        states=[check_recovery(r['recovery',c],address,c) for c in (0,1)]
        return {**common,'overlap_trap':True,'expected_traps':1,'trap_pc':pc,'mcause':3,'post_reset_target_read':False,
            'recovery':states,'both_post_reset_slot0_reset_shape':all(s['post_reset_slot0_reset_shape'] for s in states)}
    if list(a)!=order+[('result',core),('release',0),('release',1)] or r:raise ValueError('returned-store evidence incomplete/mixed')
    if re.search(r'Guru Meditation Error:|Task watchdog|Interrupt wdt timeout',attempt+recovery):raise ValueError('unexpected fault/watchdog')
    result=a['result',core]
    if any(result[k]!=v for k,v in {'core':core,'offset':offset,'address':address,'returned':1,'stored':1,'value':0x51a7cafe,'released':1,'data2':address|1,'control':0x88}.items()) or (result['data1']&~(1<<20))!=0x210000ca:raise ValueError('returned store not proven with watch still present')
    for c in (0,1):
        if a['release',c]!={'core':c,'ok':1,'data1':0x21000000,'data2':0,'control':0}:raise ValueError('bulk owned release failed')
    return {**common,'overlap_trap':False,'expected_traps':0,'store_returned':True,'target_changed':True,'target_after':result['value'],
        'trigger_hit_after_return':bool(result['data1']&(1<<20)),'released_cores':2}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('attempt',type=Path);ap.add_argument('--recovery',type=Path)
    ap.add_argument('--core',required=True,type=int);ap.add_argument('--offset',required=True,type=int);ap.add_argument('--store-pc',required=True,type=lambda v:int(v,0));a=ap.parse_args()
    print(json.dumps(summarize(a.attempt.read_text(errors='replace'),a.recovery.read_text(errors='replace') if a.recovery else '',a.core,a.offset,a.store_pc),indent=2))
if __name__=='__main__':main()
