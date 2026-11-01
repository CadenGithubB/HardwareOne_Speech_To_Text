#!/usr/bin/env python3
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('diag',Path(__file__).resolve().parents[1]/'tools/device_tests/feature_cache/teardowndiag.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
lines=[]
for i,p in enumerate(d.PHASES):
    lines.extend([f'I (123) STT: TL teardown phase={p} event=0 ms={i*2} end',f'TL teardown phase={p} event=1 ms={i*2+1} heap_ok=1 check_us=10 int_free=100 psram_free=200 end'])
s=d.summarize(lines);assert s['complete_cycles']==1 and s['cycles'][0]['heap_checks']==19 and s['cycles'][0]['heap_check_us']==190
s=d.summarize(lines[:7]);assert s['complete_cycles']==0 and s['cycles'][0]['last_entered_phase']==200 and s['cycles'][0]['last_completed_phase']==120
bad=lines[:8];bad[-1]=bad[-1].replace('heap_ok=1','heap_ok=0');s=d.summarize(bad);assert s['cycles'][0]['failed_heap_phases']==[200]
assert d.summarize(lines+lines)['complete_cycles']==2
# Real first diagnostic app omitted all three model phases: must not pass.
missing_model=[l for l in lines if not any(f'phase={p} ' in l for p in (200,201,202))]
for bad in (missing_model,lines[:1]+lines[:1],lines[:3]+lines[4:],['TL teardown phase=100 event=0 ms=1'],[lines[0],lines[1].split(' heap_ok')[0]+' end']):
    try:d.summarize(bad)
    except ValueError:pass
    else:raise AssertionError('invalid markers accepted')
assert d.summarize(['private text must never appear in output'])=={'cycles':[],'complete_cycles':0}
partial=d.summarize(missing_model,allow_gaps=True);assert partial['complete_cycles']==0 and len(partial['cycles'][0]['missing_events'])==6
# Real UART corruption lost the completed marker for phase 301; retain 18 checks.
lost=[l for l in lines if 'phase=301 event=1' not in l]
partial=d.summarize(lost,allow_gaps=True);assert partial['cycles'][0]['missing_events']==[[301,1]] and partial['cycles'][0]['heap_checks']==18 and partial['complete_cycles']==0
trace=[f'[1234] I (456) STT: TL teardown phase={p} event=2 ms={i} end' for i,p in enumerate(d.PHASES)]
t=d.summarize(trace);c=t['cycles'][0];assert t['complete_cycles']==1 and c['mode']=='trace' and c['heap_checks']==0 and c['heap_check_us']==0 and c['phase_markers']==19
assert all('heap_ok' not in r for r in c['phases'])
assert d.summarize(trace+trace)['complete_cycles']==2
assert d.summarize(trace[:-1])['complete_cycles']==0
partial=d.summarize(trace[:4]+trace[5:],allow_gaps=True);assert partial['cycles'][0]['missing_events']==[[201,2]]
for bad in ([trace[0],trace[1].replace('ms=1','ms=1SYNTHETIC_ASYNC')]+trace[2:],trace[:2]+[lines[2]],lines[:2]+[trace[1]],trace[:1]+trace[:1]):
    try:d.summarize(bad)
    except ValueError:pass
    else:raise AssertionError('mixed/duplicate markers accepted')
print('teardowndiag: synthetic heap/trace markers ok')
