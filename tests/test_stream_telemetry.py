"""Pure parser checks; actual device output is validated separately."""
import copy,importlib.util,json
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'tools/device_tests/stream/telemetry.py'
s=importlib.util.spec_from_file_location('stream_telemetry',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
bounds=[1,10,50,100,250,500,1000,2000,4000,8000,16000]
def h(n=0):return {'count':n,'sum_us':n*2,'max_us':2 if n else 0,'saturated':False,'scale_us':1,'bins':[0,n]+[0]*10}
rows=[{'type':'begin','schema':1,'uptime_us':10,'telemetry_bytes':3720,'largest_page_bytes':376,'bin_upper_us':bounds+[None]}]
for op in m.OPERATIONS:rows.append({'type':'lock','op':op,'wait':h(3),'hold':h(3)})
for op in m.MEMORY:rows.append({'type':'memory','op':op,'bytes':7,'by_caller':[7]+[0]*8,'time':h(1)})
capture={k:0 for k in ('reads','bytes','warm_bytes','timeouts','errors','short_reads','odd_reads','rejected','dma_bytes_u32','overflow_count_u32','overflow_bytes_u32')}
state={k:0 for k in ('accepted_samples','cache_unavailable_checks','ready_high_water','ready','running','free_slots','free_caches','retired_caches','feature_capacity','drops','feature_overruns','drafts','canceled','promotions','psram_free','internal_free','internal_largest','owner_stack_min_bytes','psram_largest','psram_min_boot','internal_min_boot')}
state.update(free_slots=3,free_caches=2,frames=[0,0],pins=[0,0])
rows += [{'type':'capture',**capture,**{k:h() for k in ('read','interval','push','read_to_push')}},{'type':'state',**state},{'type':'level_queue','dropped':0},{'type':'end','uptime_us':20}]
def parse(rows):return m.parse_lines(['123 STT_PERF '+json.dumps(r) for r in rows])
r=parse(rows);assert len(r['reports'])==1 and not r['incomplete_report'];assert r['reports'][0]['p99_capture_wait']=={'lower_exclusive_us':1,'upper_inclusive_us':10}
assert parse(rows[:-1])['incomplete_report']
for alter in ('mass','budget','duplicate','bytes','missing','state','scale'):
 bad=copy.deepcopy(rows)
 if alter=='mass':bad[1]['wait']['bins'][0]=1
 elif alter=='budget':bad[0]['telemetry_bytes']=4096
 elif alter=='duplicate':bad.insert(1,bad[1])
 elif alter=='bytes':bad[10]['bytes']=8
 elif alter=='missing':bad.pop(1)
 elif alter=='state':bad[-3]['free_slots']=4
 else:bad[1]['wait']['scale_us']=0
 try:parse(bad)
 except AssertionError:pass
 else:raise AssertionError('Invalid report accepted: '+alter)
a=h(1);a['saturated']=True;assert m.percentile(a,bounds) is None
print('Telemetry: bounded reports, histogram mass/ranges, saturation, attribution, duplicates and incomplete reports passed')
