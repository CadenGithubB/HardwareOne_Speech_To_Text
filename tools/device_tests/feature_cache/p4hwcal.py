#!/usr/bin/env python3
"""Numeric evidence for labelled synthetic P4 watchpoint traps, not STT qualification."""
import argparse,json,re
from pathlib import Path
FIELDS={
 'armed':{'core','address','data1','data2','control'},
 'probe':{'core','read_adjacent_ok','value'},
 'ready':{'cores','phase','verified'},
 'recovery':{'core','phase','address','word','adjacent','released','idle','data1','data2','control'},
}
def markers(text,dual=False):
    rows={}
    for line in text.splitlines():
        if 'TL hwcal_' not in line:continue
        m=re.search(r'TL hwcal_(armed|probe|ready|recovery) ((?:[a-z_0-9]+=\d+ )+)end(?:\s|$)',line)
        if not m:raise ValueError('failed/refused/damaged calibration marker')
        pairs=re.findall(r'([a-z_0-9]+)=(\d+)',m.group(2));r={k:int(v) for k,v in pairs};kind=m.group(1)
        if set(r)!=FIELDS[kind] or len(r)!=len(pairs) or any(v>0xffffffff for v in r.values()):raise ValueError('invalid calibration fields')
        key=(kind,r.get('core',-1)) if dual else kind
        if key in rows:raise ValueError('duplicate calibration marker')
        rows[key]=r
    return rows

def check_trap(trap,recovery,core,pc):
    if core not in (0,1) or not 0<pc<=0xffffffff:raise ValueError('invalid expected core/PC')
    pcs=[int(n,16) for n in re.findall(r'MEPC\s*:\s*0x([0-9a-fA-F]+)',trap)]
    causes=[int(n,16) for n in re.findall(r'MCAUSE\s*:\s*0x([0-9a-fA-F]+)',trap)]
    cores=[int(n) for n in re.findall(r'Guru Meditation Error: Core\s+(\d+)',trap)]
    if pcs!=[pc] or causes!=[3] or cores!=[core]:raise ValueError('trap PC/cause/core mismatch or extra trap')
    if re.search(r'MCAUSE\s*:|Guru Meditation Error:|Task watchdog|Interrupt wdt timeout',recovery) or re.search(r'Task watchdog|Interrupt wdt timeout',trap):raise ValueError('unexpected recovery fault/watchdog')

def check_pair(a,p,v,core):
    address=a['address']
    if not address or address%4 or a!={'core':core,'address':address,'data1':0x210000ca,'data2':address|1,'control':0x88}:raise ValueError('arm state invalid')
    if p!={'core':core,'read_adjacent_ok':1,'value':0x13579bdf}:raise ValueError('read/adjacent negative control failed')
    if any(v[k]!=n for k,n in {'core':core,'phase':2,'address':address,'word':0x13579bdf,'adjacent':0x2468ace0,'released':1,'idle':1}.items()):raise ValueError('recovery ownership/word state invalid')
    reset=v['data1']==0x21000000 and v['data2']==v['control']==0
    owned=(v['data1']&~(1<<20))==0x210000ca and v['data2']==(address|1) and not (v['control']&~0x88)
    if not reset and not owned:raise ValueError('post-reset trigger state unexpected')
    return {'core':core,'address':address,'read_adjacent_ok':1,'word_unchanged':1,'adjacent_written':1,'retained_phase':2,
        'post_reset_slot0_data1':v['data1'],'post_reset_slot0_data2':v['data2'],'post_reset_control':v['control'],
        'post_reset_slot0_reset_shape':reset,'released':1,'both_cores_idle_after_release':1}

def summarize(trap,recovery,core,pc):
    check_trap(trap,recovery,core,pc)
    t=markers(trap);r=markers(recovery)
    if set(t)!={'armed','probe'} or set(r)!={'recovery'}:raise ValueError('calibration evidence incomplete/mixed')
    return {**check_pair(t['armed'],t['probe'],r['recovery'],core),'expected_store_pc':pc,'trap_pc':pc,'mcause':3,'expected_traps':1}

def summarize_dual(trap,recovery,core,pc):
    check_trap(trap,recovery,core,pc)
    t=markers(trap,True);r=markers(recovery,True)
    if list(t)!=[('armed',0),('armed',1),('probe',0),('probe',1),('ready',-1)] or list(r)!=[('recovery',0),('recovery',1)]:raise ValueError('dual calibration incomplete/mixed/out of order')
    if t['ready',-1]!={'cores':2,'phase':2,'verified':1}:raise ValueError('dual lease verification failed')
    rows=[check_pair(t['armed',c],t['probe',c],r['recovery',c],c) for c in (0,1)]
    if rows[0]['address']!=rows[1]['address']:raise ValueError('dual calibration targets differ')
    return {'firing_core':core,'peer_core':1-core,'expected_store_pc':pc,'trap_pc':pc,'mcause':3,'expected_traps':1,
        'armed_cores':2,'verified_before_trap':1,'cores':rows,'both_post_reset_slot0_reset_shape':all(r['post_reset_slot0_reset_shape'] for r in rows)}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('trap',type=Path);ap.add_argument('recovery',type=Path)
    ap.add_argument('--core',required=True,type=int);ap.add_argument('--store-pc',required=True,type=lambda s:int(s,0));ap.add_argument('--dual',action='store_true');a=ap.parse_args()
    fn=summarize_dual if a.dual else summarize
    print(json.dumps(fn(a.trap.read_text(errors='replace'),a.recovery.read_text(errors='replace'),a.core,a.store_pc),indent=2))
if __name__=='__main__':main()
