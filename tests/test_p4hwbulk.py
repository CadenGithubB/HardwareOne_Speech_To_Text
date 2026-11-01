#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/feature_cache'))
from p4hwbulk import summarize
base=0x48001000;address=base+4;pc=0x4ff22cd4
pre=f'TL hwbulk_target core=0 offset=4 base={base} address={address} bytes=32 width=16 external=1 end\n'
pre+=''.join(f'TL hwbulk_warm core={c} ok=1 words=4 value=1369950974 end\n' for c in (0,1))
pre+=''.join(f'TL hwbulk_armed core={c} ok=1 address={address} data1=553648330 data2={address|1} control=136 end\n' for c in (0,1))
pre+=''.join(f'TL hwbulk_probe core={c} ok=1 value=324508639 end\n' for c in (0,1))
pre+='TL hwbulk_ready cores=2 phase=2 verified=1 end\n'
trap=pre+f'Guru Meditation Error: Core 0 panic\nMEPC : {pc:#x} MCAUSE : 0x00000003\n'
recovery=''.join(f'TL hwbulk_recovery core={c} phase=2 address={address} released=1 idle=1 data1=553648128 data2=0 control=0 end\n' for c in (0,1))
r=summarize(trap,recovery,0,4,pc);assert r['overlap_trap'] and r['both_post_reset_slot0_reset_shape']
returned=pre+f'TL hwbulk_result core=0 offset=4 address={address} returned=1 stored=1 value=1369950974 released=1 data1=553648330 data2={address|1} control=136 end\n'
returned+=''.join(f'TL hwbulk_release core={c} ok=1 data1=553648128 data2=0 control=0 end\n' for c in (0,1))
r=summarize(returned,'',0,4,pc);assert not r['overlap_trap'] and r['target_changed'] and not r['trigger_hit_after_return']
for a,b in [(trap.replace('width=16','width=8'),recovery),(trap,recovery.splitlines()[0]),(trap.replace('0x00000003','0x00000005'),recovery),
 (trap.replace(f'{pc:#x}',f'{pc+4:#x}'),recovery),(returned.replace('returned=1','returned=0'),''),(returned.replace('stored=1','stored=0'),''),
 (returned.replace('value=1369950974','value=0'),''),(returned.replace('released=1','released=0'),''),(returned,recovery),
 (returned.replace('control=136','control=0'),''),(trap+pre,recovery),(trap.replace('external=1','external=0'),recovery),
 (returned+'Guru Meditation Error: Core 0','')]:
 try:summarize(a,b,0,4,pc)
 except ValueError:pass
 else:raise AssertionError('damaged bulk evidence accepted')
assert summarize('=== PREVIOUS CRASH ===\nMCAUSE : 0x5\n======================\n'+returned,'',0,4,pc)['target_changed']
print('P4 bulk watch: trap and proven-return outcomes, overlap geometry, recovery and damaged cases ok')

for text,rec in [(trap,recovery),(returned,'')]:
 base_case=text.replace('offset=4','offset=0').replace(str(address|1),str(base|1)).replace(str(address),str(base))
 rec0=rec.replace(str(address),str(base))
 assert summarize(base_case,rec0,0,0,pc)['watch_offset']==0
core1=trap.replace('hwbulk_target core=0','hwbulk_target core=1').replace('Error: Core 0','Error: Core 1')
assert summarize(core1,recovery,1,4,pc)['firing_core']==1
for a,b in [(trap.replace('hwbulk_warm core=1 ok=1','hwbulk_warm core=1 ok=0'),recovery),
 (trap.replace('words=4','words=3'),recovery),
 ('\n'.join(l for l in trap.splitlines() if 'hwbulk_warm core=1 ' not in l),recovery)]:
 try:summarize(a,b,0,4,pc)
 except ValueError:pass
 else:raise AssertionError('missing/failed execution control accepted')
