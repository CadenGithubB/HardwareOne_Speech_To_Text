#!/usr/bin/env python3
"""Score standalone events using sample-indexed RMS; keep raw data private.

No reference text or speaker identity is used to fit audio onset. Failed fits
withhold identity/true-end timing; waveform-independent coverage/WER remain.
"""
import argparse,hashlib,json,re,statistics,sys,wave
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/device_tests/bench'))
sys.path.insert(0,str(ROOT/'tools/device_tests/speaker'))
import benchscore,benchsets,spkrules
from sample_alignment import fit_sample_levels
from telemetry import parse_lines

def summary(values):
    if not values:return {'count':0,'median_s':None,'p90_s':None}
    return {'count':len(values),'median_s':float(statistics.median(values)),
            'p90_s':float(sorted(values)[min(len(values)-1,int(.9*(len(values)-1)+.5))])}

def score(directory,manifest):
    directory=Path(directory);capture=json.loads((directory/'capture.json').read_text());assert capture['phase']=='complete'
    log=(directory/'serial.log').read_text(errors='replace');perf=parse_lines(log.splitlines());assert not perf['incomplete_report']
    levels=[e for e in perf['events'] if e['type']=='level'];assert levels
    wav=Path(capture['wav']);assert hashlib.sha256(wav.read_bytes()).hexdigest()==capture['wav_sha256']
    with wave.open(str(wav),'rb') as source:
        assert source.getnchannels()==1 and source.getsampwidth()==2
        rate=source.getframerate();pcm=np.frombuffer(source.readframes(source.getnframes()),dtype='<i2').astype(float)
    hop=round(rate*.01);frames=pcm[:len(pcm)//hop*hop].reshape(-1,hop)
    envelope=np.sqrt(np.maximum(0,np.mean(frames**2,axis=1)-np.mean(frames,axis=1)**2));axis=(np.arange(len(envelope))+.5)*hop/rate
    # RMS comes from the last completed 160-sample analysis frame, at its centre.
    times=np.array([(int(e['sample_u32'])//160*160-80)/16000 for e in levels])
    observed=np.log1p([max(0,int(e['rms'])-int(e['noise'])) for e in levels])
    alignment=fit_sample_levels(times,observed,axis,envelope,capture['estimated_playback_sample_offset_s'])
    clock=np.array([e['uptime_ms']/1000-e['sample_u32']/16000 for e in levels])
    clock_base=float(np.quantile(clock,.01));spread=float(np.median(clock)-clock_base)
    alignment.update(method='Sample-indexed capture RMS, clock-constrained 10 ms envelope fit',
        limitation='Sparse scalar RMS observations, not raw microphone audio; split agreement is consistency, not absolute acoustic precision.',
        capture_zero_uptime_s=clock_base,clock_sample_median_minus_p1_s=spread)
    alignment['usable']=bool(alignment['usable'] and spread<=.05)
    rows=[];pending=[];labels={};caps=[];shown=[];host_clock=[];host_times=[]
    session=capture['session_id']
    for line in log.splitlines():
        stamp=re.match(r'^(\d+\.\d+) ',line)
        if not stamp:continue
        host=float(stamp[1]);host_times.append(host)
        m=re.search(r'STT_EVENT (\{.*\})',line)
        if m:
            event=json.loads(m[1]);event['_host']=host
            if event.get('sessionId')==session:
                if event['type']=='final':caps.append(event);pending.append(event)
                elif event['type']=='draft':pending.append(event)
                elif event['type']=='speaker' and event.get('ready'):labels[event['sequence']]=event
        m=re.search(r'STT_PERF (\{.*\})',line)
        if m:
            event=json.loads(m[1])
            if event['type']=='level':host_clock.append(host-event['uptime_ms']/1000)
            if event['type']=='inference':
                rows.append(event)
                for e in pending:
                    if e['type']=='final' and event['kind']==0 and int(e['startSample'])==event['start_sample'] and int(e['endSample'])==event['start_sample']+event['captured']:
                        e['_inference']=event
                    elif e['type']=='draft' and e.get('text') and event['kind']==1 and event['valid']:
                        shown.append({'event':e,'inference':event})
                pending=[]
    base=json.loads(Path(manifest).read_text())['clips']
    reference=[word for c in base for word in benchscore.norm(c['text_norm'])]
    hypothesis=[word for c in caps for word in benchscore.norm(c['rawText'])]
    edits=benchscore.edits(reference,hypothesis)
    final=perf['reports'][-1];out={'fixture':capture['fixture'],'path':str(directory.resolve()),'captions':len(caps),
        'wer':edits/len(reference),'word_edits':edits,'reference_words':len(reference),
        'raw_speaker_coverage':{'labelled':sum(labels.get(c['sequence'],{}).get('speaker',-1)>=0 for c in caps),
            'unknown_or_missing':sum(labels.get(c['sequence'],{}).get('speaker',-1)<0 for c in caps),
            'missing_updates':sum(c['sequence'] not in labels for c in caps)},
        'alignment':alignment,'watchdogs':capture['watchdogs'],'panic':capture['panic'],
        'final_report':final,'source_manifest_sha256':hashlib.sha256(Path(manifest).read_bytes()).hexdigest(),
        'capture_sha256':hashlib.sha256((directory/'capture.json').read_bytes()).hexdigest(),
        'serial_sha256':hashlib.sha256((directory/'serial.log').read_bytes()).hexdigest(),
        'limits':['One capture is descriptive, not a quality promotion or statistical noninferiority result.']}
    if not alignment['usable']:
        out['withheld']='Reference identity and true-end timing: RMS/clock fit failed';return out
    onset=alignment['estimated_sample_onset_s'];keys={'start_s','end_s','speech_start_s','speech_end_s'}
    clips=[{k:float(v)+onset if k in keys else v for k,v in c.items()} for c in base]
    phrases=[];assigned=[]
    for c in caps:
        a,b=int(c['startSample'])/16000,int(c['endSample'])/16000;ref=benchsets.clip_at(clips,(a+b)/2)
        heard={x['speaker'] for x in clips if min(b,float(x['end_s']))-max(a,float(x['start_s']))>=.3}
        phrases.append({'id':c['sequence'],'ref':ref['speaker'] if ref else None,'mixed':len(heard)>1})
        label=labels.get(c['sequence']);assigned.append((label['speaker'] if label else -1,'published' if label else 'missing'))
    metrics=spkrules.run_metrics(phrases,list(range(len(phrases))),assigned)
    metrics.update(excluded_no_reference=sum(p['ref'] is None for p in phrases),excluded_mixed=sum(p['ref'] is not None and p['mixed'] for p in phrases));out['speaker_one_to_one']=metrics
    out['outside_reference_captions']=sum(int(c['endSample'])/16000<onset or int(c['startSample'])/16000>onset+capture['duration_s'] for c in caps)
    clock_valid=all(a<=b for a,b in zip(host_times,host_times[1:])) and len(host_clock)>=50
    out['host_clock_valid']=clock_valid
    if not clock_valid:out['withheld']='Publication timing: host timestamp evidence insufficient';return out
    host_base=float(np.quantile(host_clock,.01));out['host_device_bridge_s']=host_base
    final_lag=[];worker_lag=[];label_lag=[];close=[];missed=0
    for clip in clips:
        if 'speech_end_s' not in clip:missed+=1;continue
        end=float(clip['speech_end_s']);hit=next((c for c in caps if int(c['startSample'])/16000<=end<=int(c['endSample'])/16000),None)
        if hit is None:missed+=1;continue
        end_uptime=clock_base+end;end_host=host_base+end_uptime
        final_lag.append(hit['_host']-end_host)
        if '_inference' in hit:
            job=hit['_inference'];worker_lag.append(job['done_ms']/1000-end_uptime);close.append(job['closed_ms']/1000-end_uptime)
        if hit['sequence'] in labels:label_lag.append(labels[hit['sequence']]['_host']-end_host)
    visible=[];first={}
    for entry in shown:
        e,job=entry['event'],entry['inference'];end=clock_base+(job['start_sample']+job['samples'])/16000
        visible.append(e['_host']-(host_base+end))
        first.setdefault(job['sequence'],e['_host']-(host_base+clock_base+job['start_sample']/16000))
    ready_delay=[labels[c['sequence']]['_host']-c['_host'] for c in caps if c['sequence'] in labels]
    out['latency']={'reference_final_publication':summary(final_lag),'reference_worker_done':summary(worker_lag),
        'reference_speaker_publication':summary(label_lag),'reference_close':summary(close),'missed_reference_ends':missed,
        'draft_audio_freshness':summary(visible),'first_draft_from_segment_start':summary(list(first.values())),
        'label_after_caption':summary(ready_delay),
        'definitions':'Publication is host receipt; reference timing uses qualified sample-RMS onset and minimum-delay host/device bridge. Draft freshness is lag behind the latest represented audio, not word alignment.'}
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture',type=Path);p.add_argument('--manifest',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    if 'private' not in a.out.resolve().parts:p.error('Results must remain private')
    result=score(a.capture,a.manifest);a.out.write_text(json.dumps(result,indent=2));print(json.dumps({k:result[k] for k in ('fixture','captions','wer','raw_speaker_coverage','alignment')},indent=2))
if __name__=='__main__':main()
