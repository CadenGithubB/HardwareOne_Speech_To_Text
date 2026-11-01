import importlib.util
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'tools/device_tests/kernels/p4pointwise.py'
spec=importlib.util.spec_from_file_location('pw',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
lines=[]
for pair in range(3):
    for mode in (0,1):
        lines += [f'TL pw_time pair={pair} mode={mode} wall_us={2000-mode*10} inference_us={1000-mode*10} stages_us={900-mode*10} yield_us=100 end',
                  f'TL pw_calls pair={pair} mode={mode} tiled=106 width1=106 c512=100 end',
                  f'TL pw_mem pair={pair} mode={mode} low_int=100 low_psram=1000 free_int=200 free_psram=2000 largest_int=100 largest_psram=1000 end']
done='TL pw_done ok=1 hashes_equal=1 warm=4 pairs=3 samples=44560 end'
hashes=[f'TL pw_hash kind={k} sha='+str(i+1)*64+' end' for i,k in enumerate(('input','output','text'))]
lines+=hashes
t=m.parse(lines+[done]);s=m.summarize([t]*5)
assert s['hash_equal_calls']==50 and s['metrics']['inference_us']['paired_delta_bootstrap95']==[-10,-10]
different={**t,'hashes':{**t['hashes'],'output':'9'*64}}
try:m.summarize([t]*4+[different])
except ValueError:pass
else:raise AssertionError('accepted different outputs across boots')
for bad in (lines,lines[:-1]+[done],lines+[lines[0],done],lines+[done,done],
            lines+[done.replace('hashes_equal=1','hashes_equal=0')],
            [x.removesuffix(' end') for x in lines]+[done],lines+[done,'TL pw_error code=1'],
            [x.replace('c512=100','c512=0') for x in lines]+[done],
            [x.replace('yield_us=100','yield_us=100 yield_us=100') for x in lines]+[done],
            [x.replace('yield_us=100','yield_us=100 [9] debug') for x in lines]+[done]):
    try:m.parse(bad)
    except ValueError:pass
    else:raise AssertionError('accepted invalid/incomplete probe')
print('p4pointwise: synthetic sessions ok')
