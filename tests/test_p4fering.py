#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('probe',Path(__file__).resolve().parents[1]/'tools/device_tests/feature_cache/p4fering.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
lines=[]
for pair in range(5):
 for order in range(2):
  mode=1-order if pair&1 else order
  lines.extend([f'I (123) STT: TL fering_case pair={pair} mode={mode} ok=1 rows=278 equal=278 cpu_us={10000+mode*300} wall_us=14000 stack_free={2600-mode*1024} end',
   f'TL fering_copy pair={pair} mode={mode} calls={500*mode} equal={500*mode} sum_us={1000*mode} max_us={5*mode} end',
   f'TL fering_write pair={pair} mode={mode} calls=500 sum_us=1000 max_us=5 end'])
lines.append('TL fering_done ok=1 cases=10 samples=44560 stack_bytes=3072 flip=0 end')
r=p.summarize(lines);assert len(r['cases'])==10 and len(r['pairs'])==5 and all(x['cpu_delta_us']==300 for x in r['pairs'])
for bad in (lines[:-1],lines[:1]+lines,lines[:2]+lines[3:], [x.replace('equal=278','equal=277') for x in lines], [x.replace('stack_free=1576','stack_free=100') for x in lines], [x.replace('cases=10','cases=9') for x in lines], [x.replace('flip=0','flip=1') for x in lines], [x.replace('calls=500','calls=499') for x in lines], [x.replace('cpu_us=10300','cpu_us=0') for x in lines], [x.replace('cpu_us=10300','cpu_us=10ASYNC300') for x in lines]):
 try:p.summarize(bad)
 except ValueError:pass
 else:raise AssertionError('incomplete/invalid ring probe accepted')
assert 'private text' not in str(p.summarize(['private text']+lines))
with tempfile.TemporaryDirectory(prefix='p4-ring-loader-') as tmp:
    paths=[]
    for i in range(5):
        trial=Path(tmp)/str(i);trial.mkdir();paths.append(trial)
        (trial/'raw.log').write_text('private text\n'+'\n'.join(lines))
        (trial/'result.json').write_text(json.dumps({'fatal_markers':0,'watchdog_warnings':0,'audio_overruns':0,'littlefs_before':3000000,'littlefs_after':3000000}))
    def load():
        return json.loads(subprocess.check_output([sys.executable,p.__file__,*map(str,paths)],text=True))
    r=load();assert r['minimum_five_clean_boots_met'] and r['lifecycle_complete']==5
    (paths[3]/'failure.json').write_text('{}')
    r=load();assert not r['minimum_five_clean_boots_met'] and r['lifecycle_complete']==4 and r['boot_count']==5 and r['all_attempts_in_cost_summary']
    (paths[3]/'failure.json').unlink()
    (paths[3]/'result.json').write_text(json.dumps({'fatal_markers':0,'watchdog_warnings':1,'audio_overruns':0,'littlefs_before':3000000,'littlefs_after':3000000}))
    assert not load()['minimum_five_clean_boots_met']
print('p4 feature ring: matched order, parity, stack, timing, corruption and failed-lifecycle gates ok')
