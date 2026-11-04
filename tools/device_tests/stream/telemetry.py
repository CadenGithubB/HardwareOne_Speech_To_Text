"""Validate standalone bounded telemetry; histogram percentiles are bin ranges."""
import json,re
OPERATIONS=('push','take','complete','cancel','finish','feature_take','feature_complete','enable_features','status')
MEMORY=('queue_copy','snapshot_copy','cache_clear','slot_clear','snapshot_clear','cancel_clear','feature_window','feature_row','startup_clear','padding')

def histogram(h,bounds):
    assert type(h.get('count')) is int and h['count']>=0
    assert type(h.get('sum_us')) is int and h['sum_us']>=0
    assert type(h.get('max_us')) is int and 0<=h['max_us']<=h['sum_us']
    assert type(h.get('saturated')) is bool
    assert type(h.get('scale_us')) is int and h['scale_us']>0
    assert len(h['bins'])==len(bounds)+1
    assert all(type(v) is int and 0<=v<=0xffffffff for v in h['bins'])
    if not h['saturated']:assert sum(h['bins'])==h['count']
    if not h['count']:assert not h['max_us'] and not h['sum_us']
    return h

def percentile(h,bounds,p=.99):
    if not h['count'] or h['saturated']:return None
    needed=max(1,int((h['count']*p)+.999999));seen=0
    for i,n in enumerate(h['bins']):
        seen+=n
        if seen>=needed:
            return {'lower_exclusive_us':None if i==0 else bounds[i-1]*h['scale_us'],
                    'upper_inclusive_us':None if i==len(bounds) else bounds[i]*h['scale_us']}
    raise ValueError('Histogram mass missing')

def parse_lines(lines):
    events=[];reports=[];active=None
    for line in lines:
        match=re.search(r'STT_PERF (\{.*\})',line)
        if not match:continue
        event=json.loads(match[1]);assert isinstance(event,dict) and isinstance(event.get('type'),str)
        events.append(event)
        if event['type']=='begin':
            assert active is None,'incomplete telemetry report before next begin'
            assert event['schema']==1
            bounds=event['bin_upper_us'];assert bounds[-1] is None;bounds=bounds[:-1]
            assert bounds==sorted(set(bounds)) and all(type(x)is int and x>0 for x in bounds)
            assert event['telemetry_bytes']+event['largest_page_bytes']<=4096
            active={'begin':event,'locks':{},'memory':{},'bounds':bounds}
        elif active is not None:
            kind=event['type']
            if kind=='lock':
                op=event['op'];assert op in OPERATIONS and op not in active['locks']
                histogram(event['wait'],active['bounds']);histogram(event['hold'],active['bounds'])
                assert event['wait']['count']==event['hold']['count']
                active['locks'][op]=event
            elif kind=='memory':
                op=event['op'];assert op in MEMORY and op not in active['memory']
                histogram(event['time'],active['bounds'])
                assert len(event['by_caller'])==len(OPERATIONS) and all(type(v)is int and v>=0 for v in event['by_caller'])
                assert sum(event['by_caller'])==event['bytes']
                active['memory'][op]=event
            elif kind in ('capture','state','level_queue'):
                assert kind not in active;active[kind]=event
                if kind=='capture':
                    for key in ('read','interval','push','read_to_push'):histogram(event[key],active['bounds'])
                    for key in ('reads','bytes','warm_bytes','timeouts','errors','short_reads','odd_reads','rejected','dma_bytes_u32','overflow_count_u32','overflow_bytes_u32'):
                        assert type(event[key])is int and event[key]>=0
                    assert event['read']['count']==event['reads']
                    assert event['interval']['count']==max(0,event['reads']-1)
                    assert event['push']['count']==event['read_to_push']['count']<=event['reads']
                elif kind=='state':
                    for key in ('accepted_samples','cache_unavailable_checks','ready_high_water','ready','running','free_slots','free_caches','retired_caches','feature_capacity','drops','feature_overruns','drafts','canceled','promotions','psram_free','internal_free','internal_largest','owner_stack_min_bytes','psram_largest','psram_min_boot','internal_min_boot'):
                        assert type(event[key])is int and event[key]>=0
                    assert event['ready']+event['running']+event['free_slots']==3
                    assert event['ready_high_water']<=3 and event['free_caches']+event['retired_caches']<=2
                    assert len(event['frames'])==len(event['pins'])==2
                    assert all(type(v)is int and 0<=v<=event['feature_capacity'] for v in event['frames'])
                    assert all(type(v)is int and 0<=v<=1 for v in event['pins'])
                else:assert type(event['dropped'])is int and event['dropped']>=0
            elif kind=='end':
                assert set(active['locks'])==set(OPERATIONS) and set(active['memory'])==set(MEMORY)
                assert all(k in active for k in ('capture','state','level_queue'))
                assert event['uptime_us']>=active['begin']['uptime_us']
                active['end']=event;active['sample_window_us']=event['uptime_us']-active['begin']['uptime_us']
                active['p99_capture_wait']=percentile(active['locks']['push']['wait'],active['bounds'])
                active['p99_push_hold']=percentile(active['locks']['push']['hold'],active['bounds'])
                reports.append(active);active=None
    return {'events':events,'reports':reports,'incomplete_report':active is not None}
