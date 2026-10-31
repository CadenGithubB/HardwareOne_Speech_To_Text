"""Export numeric-only native-glasses profiling evidence; retain raw logs privately."""
import argparse
import json
from pathlib import Path
import re
import statistics as stats

ROOT=Path(__file__).resolve().parents[2]


def numbers(text):
    out={}
    for key,value in re.findall(r'\b([a-zA-Z_][\w]*)=(-?\d+(?:\.\d+)?)',text):
        out[key]=float(value) if '.' in value else int(value)
    return out


def analyze(folder):
    folder=folder.resolve()
    session=json.loads((folder/'session.json').read_text())
    assert session['outcome']=='captured'
    records=[json.loads(line) for line in (folder/'serial.jsonl').read_text().splitlines()]
    segments={};inputs={};features={};speaker={};sends={};promoted=set();yields={}
    previews={'successful_drafts':0,'canceled_or_failed_drafts':0}
    for record in records:
        text=record['text'];n=numbers(text)
        if 'TL seg=' in text and all(k in n for k in ['seg','q','s','m','f','n','d','e','ok','psram_min','int_min']):
            segments[n['seg']]=n
        elif 'TL input seg=' in text:inputs[n['seg']]=n
        elif 'TL fe seg=' in text:features[n['seg']]=n
        elif 'TL spec_promote ' in text:promoted.add(n['seg'])
        elif 'TL yield ' in text:yields[n['seg']]=n
        elif 'TL spk seq=' in text:speaker[n['seq']]=n
        elif 'TL send seq=' in text and n.get('ack_ms',-1)>=0:sends[n['seq']]=n
        elif 'TL draft ' in text:
            previews['successful_drafts' if n.get('ok')==1 else 'canceled_or_failed_drafts']+=1
    rows=[]
    for seq,row in sorted(segments.items()):
        input_row=inputs.get(seq,{})
        elapsed=row['e']-row['s'];phase_sum=sum(row[k] for k in ['m','f','n','d'])
        if elapsed<phase_sum-5:raise ValueError('Invalid/incomplete segment timing')
        rows.append({'seq':seq,'capture_audio_s':input_row.get('captured',0)/16000,
                     'inferred_audio_s':input_row.get('inference',0)/16000,
                     'load_ms':row['m'],'frontend_ms':row['f'],'inference_ms':row['n'],
                     'decode_ms':row['d'],'other_ms':max(0,elapsed-phase_sum),
                     'worker_elapsed_ms':elapsed,'close_to_done_ms':row['e']-row['q'],
                     'worker_start_relative_close_ms':row['s']-row['q'],
                     'save_hook_ms':row.get('sv1',0)-row.get('sv0',0),
                     'ok':row['ok']==1,'lm':row.get('lm')==1,'promoted':seq in promoted,
                     'boot_min_psram_bytes':row['psram_min'],'boot_min_internal_bytes':row['int_min'],
                     'features':features.get(seq),'yield':yields.get(seq),
                     'speaker':speaker.get(seq),'send_ack_ms':sends.get(seq,{}).get('ack_ms')})
    if not rows:raise ValueError('No complete final timing records')
    snapshots=[]
    start=session['window_start_mono']
    for sample in session['samples']:
        m=sample['memory']
        snapshots.append({'t_s':round(sample['mono']-start,3),
            'psram_free':m['psram']['free'],'psram_total':m['psram']['total'],
            'internal_free':m['dram']['free'],'internal_total':m['dram']['total'],
            'internal_largest':m['heapCaps']['internalLargest'],
            'internal_boot_min':m['dram']['minFree']})
    phase_keys=['load_ms','frontend_ms','inference_ms','decode_ms','other_ms']
    mean={key:stats.mean(r[key] for r in rows) for key in phase_keys}
    mean['worker_elapsed_ms']=stats.mean(r['worker_elapsed_ms'] for r in rows)
    mean['close_to_done_ms']=stats.mean(r['close_to_done_ms'] for r in rows)
    mean['inference_share_percent']=100*mean['inference_ms']/sum(mean[k] for k in phase_keys)
    # Firmware returns floor(total_us / completed_runs); undo that normalization.
    profiles=[]
    for key in ['stages_before','stages_after']:
        match=re.search(r'stages (\d+) segments (\d+) us:([\d,]+)',session[key])
        if not match:raise ValueError('Missing stage-counter snapshot')
        values=list(map(int,match[3].split(',')))
        if len(values)!=int(match[1]):raise ValueError('Truncated stage-counter snapshot')
        profiles.append((int(match[2]),values))
    before,old=profiles[0];after,new=profiles[1];runs=after-before
    assert runs>0 and len(old)==len(new)==201
    delta=[(b*after-a*before)/1000 for a,b in zip(old,new)]
    assert all(value>=0 for value in delta)
    nodes=json.loads((Path(__file__).with_name('graph_nodes.json')).read_text())
    groups={'512→512 pointwise':0,'Other pointwise':0,'Depthwise':0,'Add / ReLU':0}
    for node,value in zip(nodes,delta):
        if node['op']!='Conv':key='Add / ReLU'
        elif node['kind']=='dw':key='Depthwise'
        elif node.get('Cin')==node.get('Cout')==512:key='512→512 pointwise'
        else:key='Other pointwise'
        groups[key]+=value
    def native(key):return numbers(session[key])
    n0,n1=native('native_before'),native('native_after')
    mic0,mic1=native('g2_before'),native('g2_after')
    result={
        'schema':1,'date':'2026-10-31','firmware':'0.99.99','source':'G2 native Conversate',
        'conditions':'live uncontrolled speech; requested debug flags and per-frame logs ON; loglink ON; Showcase paused; no file logging',
        'session_dir':str(folder.relative_to(ROOT)),'cold_start_captured':False,
        'window_seconds':session['window_end_mono']-start,'phrases':len(rows),'segments':rows,'mean':mean,
        'previews':previews,
        'memory_samples':snapshots,'memory_sample_interval_seconds_approx':2,
        'sampled_min_psram_free':min(x['psram_free'] for x in snapshots),
        'sampled_min_internal_free':min(x['internal_free'] for x in snapshots),
        'boot_min_psram_free':min(r['boot_min_psram_bytes'] for r in rows),
        'boot_min_internal_free':min(r['boot_min_internal_bytes'] for r in rows),
        'layers':{'completed_model_runs':runs,'final_phrases':len(rows),
            'stage_time_delta_ms':sum(delta),'groups_ms':groups,
            'group_percent':{key:100*value/sum(delta) for key,value in groups.items()},
            'stage_total_quantization_error_bound_ms':201*(before+after)/1000,
            'scope':'finals, drafts, speculative runs, and partial canceled stage work; stage wall time, not exclusive CPU time',
            'counter_limit':'rounded, unsynchronized counter snapshots; shares are approximate'},
        'bluetooth':{'packets_delta':n1['packets']-n0['packets'],
            'audio_span_delta_ms':n1['audio_span_ms']-n0['audio_span_ms'],
            'packet_rate_per_second':1000*(n1['packets']-n0['packets'])/(n1['audio_span_ms']-n0['audio_span_ms']),
            'lost_delta':n1['lost']-n0['lost'],'duplicates_delta':n1['duplicates']-n0['duplicates'],
            'max_gap_ms_session':n1['max_gap_ms'],
            'decode_fail_delta':mic1['decode_fail']-mic0['decode_fail'],
            'plc_delta':mic1['plc']-mic0['plc'],'overrun_delta':mic1['overrun']-mic0['overrun'],
            'degraded_end':mic1['degraded']},
        'storage':session.get('storage_after'),
        'limits':['no ground-truth audio or WER score','close-to-done excludes endpointing and display draw',
                  'heap samples miss transient peaks; boot minima are not session-attributed',
                  'no physical flash/cache-read counters or SD I/O timing instrumentation',
                  'speaker timings include preemption; do not add them to caption time'],
    }
    config=ROOT/'docs/performance-device-config.json'
    if config.exists():result['allocation_reference']=json.loads(config.read_text())
    result['speaker_observed_wall_ms']=[r['speaker']['us']/1000 for r in rows if r['speaker']]
    result['speaker_observed_lag_ms']=[r['speaker']['lag_ms'] for r in rows
                                     if r['speaker'] and 'lag_ms' in r['speaker']]
    result['feature_cached_fraction']=sum(r['features']['cached'] for r in rows if r['features']) / sum(r['features']['frames'] for r in rows if r['features'])
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/performance-glasses-live.json')
    args=parser.parse_args();value=analyze(args.session)
    args.output.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({'phrases':value['phrases'],'mean':value['mean'],
        'min_psram_free':value['sampled_min_psram_free'],'min_internal_free':value['sampled_min_internal_free'],
        'bluetooth':value['bluetooth'],'layers':value['layers']},indent=2))
