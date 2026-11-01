#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/feature_cache'))
from p4hwwatch import summarize
from teardowndiag import PHASES
lines=[f'TL hwwatch_armed core={c} ok=1 address=1016 data1=553648330 data2=1017 control=136 end' for c in (0,1)]
lines+=['TL hwwatch_active ok=1 mask=3 heap=1000 address=1016 value=1020 expected=1020 end']
for stage in range(4):
 for c in (0,1):
  lines += [f'TL hwread stage={stage} core={c} ok=1 error=0 debugger=0 before=0 after=0 control_before=136 control_after=136 end',
   f'TL hwslots stage={stage} core={c} selected0=0 data10=553648330 data20=1017 selected1=1 data11=553648128 data21=0 selected2=2 data12=553648128 data22=0 end',
   f'TL hwcontext stage={stage} core={c} data30=0 data31=0 data32=0 end']
 lines += [f'TL hwheap stage={stage} heap=1000 field=1016 value=1020 expected=1020 ok=1 end',f'TL hwread_done stage={stage} ok=1 cores=2 slots=6 contexts=6 heap_ok=1 end']
for mode in (0,1):
 for kind in (0,1,2):
  rows=8 if kind==0 else 0;nonzero=int(mode==0 and kind!=0)
  lines += [f'TL feown_case mode={mode} kind={kind} ok=1 rows={rows} nonzero={nonzero} equal={rows} stack_free=2600 ms=55 end']
lines+=['TL feown_done ok=1 cases=6 samples=1280 stack_bytes=3072 end']
lines += [f'TL teardown phase={p} event=2 ms={i+100} end' for i,p in enumerate(PHASES)]
lines += [f'TL hwwatch_release core={c} ok=1 address=1016 data1=553648128 data2=0 control=0 end' for c in (0,1)]
lines += ['TL hwwatch_released ok=1 mask=0 end']
r=summarize(lines,1000);assert r['forced_ownership_checks']==6 and r['active_slot_checkpoints']==8
for bad in [lines[:-1],lines+[lines[-1]],[l.replace('core=1 ok=1 address=1016','core=1 ok=0 address=1016') for l in lines],
 [l.replace('data20=1017','data20=1019') for l in lines],[l.replace('data31=0','data31=1') for l in lines],
 [l.replace('stage=2 heap=1000','stage=2 heap=1004') for l in lines],lines+['MCAUSE : 0x00000003'],
 [l for l in lines if 'phase=321 ' not in l],[l.replace('mask=3','mask=1') for l in lines]]:
 try:summarize(bad,1000)
 except ValueError:pass
 else:raise AssertionError('damaged watch accepted')
assert 'PRIVATE' not in str(summarize(['PRIVATE text']+lines,1000))
print('P4 heap watch: both-core coverage, cleanup, interval and damaged evidence ok')

assert summarize(['=== PREVIOUS CRASH ===','Guru Meditation Error: Core 0','MCAUSE : 0x00000005','Task watchdog got triggered','======================']+lines,1000)['armed_cores']==2
try:summarize(lines+['=== PREVIOUS CRASH ==='],1000)
except ValueError:pass
else:raise AssertionError('unterminated history block accepted')

prefixed=[f'I ({1000+i}) STT: '+l for i,l in enumerate(lines)]
r=summarize(prefixed,1000);assert r['watch_after_phase321_ms']==3 and r['watch_interval_ms']==len(lines)-1
