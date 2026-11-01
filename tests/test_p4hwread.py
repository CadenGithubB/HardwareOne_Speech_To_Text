#!/usr/bin/env python3
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('probe',Path(__file__).resolve().parents[1]/'tools/device_tests/feature_cache/p4hwread.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
lines=[]
for stage in range(4):
 for core in (0,1):
  lines.extend([f'I (123) STT: TL hwread stage={stage} core={core} ok=1 error=0 debugger=0 before=2 after=2 control_before=136 control_after=136 end',
   f'TL hwslots stage={stage} core={core} selected0=0 data10=536870912 data20=0 selected1=1 data11=536870912 data21=0 selected2=2 data12=536870912 data22=0 end'])
 lines.extend([f'TL hwheap stage={stage} heap=1000 field=1016 value=1020 expected=1020 ok=1 end',f'TL hwread_done stage={stage} ok=1 cores=2 slots=6 heap_ok=1 end'])
r=p.summarize(lines);assert len(r['stages'])==4 and r['first_heap_mismatch_stage'] is None and not r['debugger_attached_any'] and r['trigger_low_bits_nonzero']==0
badheap=[l.replace('value=1020 expected=1020 ok=1','value=900 expected=1020 ok=0').replace('heap_ok=1','heap_ok=0') if 'stage=2 ' in l else l for l in lines]
assert p.summarize(badheap)['first_heap_mismatch_stage']==2
for bad in (lines[:-1],lines+[lines[0]], [l.replace('after=2','after=1') for l in lines], [l.replace('selected1=1','selected1=0') for l in lines], [l.replace('value=1020','value=10ASYNC20') for l in lines], [l.replace('expected=1020','expected=1024') for l in lines], [l.replace('data10=536870912','data10=4294967296') for l in lines]):
 try:p.summarize(bad)
 except ValueError:pass
 else:raise AssertionError('damaged/incomplete state accepted')
r=p.summarize([l.replace('data10=536870912','data10=536870914') for l in lines]);assert r['trigger_low_bits_nonzero']==8
assert 'private text' not in str(p.summarize(['private text']+lines))
# Real reset shape includes the read-only maskmax=8 field (bit 24), not
# active address/mode configuration. Legacy records did not read TDATA3.
real=[l.replace('536870912','553648128').replace('control_before=136 control_after=136','control_before=0 control_after=0') for l in lines]
r=p.summarize(real);assert r['trigger_low_bits_nonzero']==24 and r['trigger_configuration_nonzero']==0 and r['context_registers_read']==0 and not r['all_observed_reset_shape']
with_context=[]
for l in real:
    with_context.append(l.replace('slots=6 heap_ok','slots=6 contexts=6 heap_ok'))
    if 'TL hwslots ' in l:
        import re
        stage,core=re.search(r'stage=(\d+) core=(\d+)',l).groups()
        with_context.append(f'TL hwcontext stage={stage} core={core} data30=0 data31=0 data32=0 end')
r=p.summarize(with_context);assert r['context_registers_read']==24 and r['all_observed_reset_shape']
assert not p.summarize([l.replace('debugger=0','debugger=1') for l in with_context])['all_observed_reset_shape']
assert not p.summarize([l.replace('data30=0','data30=33554432') for l in with_context])['all_observed_reset_shape']
for bad in ([l for l in with_context if 'TL hwread stage=1 core=0' not in l], [l for l in with_context if 'TL hwcontext stage=2 core=1' not in l], [l.replace('contexts=6','contexts=0') for l in with_context]):
    try:p.summarize(bad)
    except (ValueError,KeyError):pass
    else:raise AssertionError('missing/mixed context accepted')
print('P4 heap readback: restoration, real maskmax defaults, context coverage and corruption cases ok')
