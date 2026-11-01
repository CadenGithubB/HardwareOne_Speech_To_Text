import importlib.util
from pathlib import Path

p=Path(__file__).resolve().parents[1]/'tools/device_tests/speaker/p4frontendbench.py'
spec=importlib.util.spec_from_file_location('bench',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
lines=[f'I (100) STT: TL spk_bench run={i} calls=3 reference_us=3000 candidate_us=2970' for i in range(10)]
done='I (100) STT: TL spk_bench_done cases=6 ok=1 workspace=100000 output=48000'
trial=m.parse(lines+[done]);s=m.summarize([trial]*5)
assert s['paired_delta_us_mean']==-10 and s['paired_delta_us_bootstrap95']==[-10,-10]
for bad in (lines, lines[:-1]+[done], lines+[lines[0],done], lines+[done,done],
            lines+[done.replace('ok=1','ok=0')],lines+[done,'TL spk_bench_error code=2']):
    try:m.parse(bad)
    except ValueError:pass
    else:raise AssertionError('accepted malformed benchmark')
try:m.summarize([trial]*4)
except ValueError:pass
else:raise AssertionError('accepted fewer than five boots')
print('p4frontendbench: synthetic sessions ok')
