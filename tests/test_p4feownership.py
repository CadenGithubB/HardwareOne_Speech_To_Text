import importlib.util
import tempfile
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'tools/device_tests/feature_cache/p4feownership.py'
spec=importlib.util.spec_from_file_location('feown',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
lines=[]
for mode in (0,1):
    for kind in (0,1,2):
        n=10 if kind==0 else 0;nonzero=640 if kind==0 else (512 if mode==0 else 0)
        lines.append(f'TL feown_case mode={mode} kind={kind} ok=1 rows={n} nonzero={nonzero} equal={n} stack_free=1500 ms=30 end')
done='TL feown_done ok=1 cases=6 samples=1600 stack_bytes=3072 end'
t=m.parse(lines+[done]);s=m.summarize([t]*5);assert s['cases']==30 and s['groups'][0]['rows_equal_total']==50
assert not m.summarize([t],1)['minimum_reboot_count_met']
with tempfile.TemporaryDirectory() as tmp:
    folder=Path(tmp);(folder/'failure.json').write_text('{"status":"failed"}')
    try:m.load_trial(folder)
    except ValueError as e:assert str(e)=='lifecycle attempt failed'
    else:raise AssertionError('accepted a failed lifecycle')
for bad in (lines,lines[:-1]+[done],lines+[lines[0],done],lines+[done,done],
            [x.removesuffix(' end') for x in lines]+[done],
            [x.replace('stack_free=1500','stack_free=120') for x in lines]+[done],
            [x.replace('ok=1','ok=0') for x in lines]+[done],
            [x.replace('nonzero=512','nonzero=0') for x in lines]+[done],
            [x.replace('equal=10','equal=9') for x in lines]+[done]):
    try:m.parse(bad)
    except ValueError:pass
    else:raise AssertionError('accepted invalid ownership probe')
try:m.summarize([t]*4)
except ValueError:pass
else:raise AssertionError('accepted fewer than five boots')
print('p4feownership: synthetic sessions ok')
