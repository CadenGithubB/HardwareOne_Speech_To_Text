#!/usr/bin/env python3
"""Outcomes/worker costs for probes-off controls; no invented acoustic alignment."""
import argparse,hashlib,json,re,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/device_tests/bench'))
import benchscore
from standalone_capture import product_events

def distribution(values):
    ordered=sorted(values)
    return {'count':len(values),'median':statistics.median(values) if values else None,
            'p90':ordered[min(len(ordered)-1,int(.9*(len(ordered)-1)+.5))] if values else None,
            'maximum':max(values) if values else None}

def score(directory,manifest):
    directory=Path(directory);capture_path=directory/'capture.json';serial=directory/'serial.log'
    capture=json.loads(capture_path.read_text());assert capture['phase']=='complete'
    wav=Path(capture['wav']);assert hashlib.sha256(wav.read_bytes()).hexdigest()==capture['wav_sha256']
    text=serial.read_text(errors='replace');session=capture['session_id']
    if not capture.get('metrics',True):assert not re.search(r'\bSTT_PERF\s+\{',text),'Unexpected probes in disabled control'
    events=product_events(text.splitlines());finals=[e for e in events if e['type']=='final' and e['sessionId']==session]
    labels={e['sequence']:e['speaker'] for e in events if e['type']=='speaker' and e.get('ready') and e['sessionId']==session}
    clips=json.loads(Path(manifest).read_text())['clips']
    reference=[w for clip in clips for w in benchscore.norm(clip['text_norm'])]
    hypothesis=[w for event in finals for w in benchscore.norm(event['rawText'])]
    errors=benchscore.edits(reference,hypothesis)
    jobs=[]
    required={'seq','kind','ok','promoted','samples','load','fe','nn','lm','cached','worker_ms','psram','internal','largest'}
    for line in text.splitlines():
        match=re.search(r'TL stream (.*)',line)
        if match:
            row={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',match[1])}
            assert required<=row.keys(),'Incomplete worker timing row'
            jobs.append(row)
    groups={}
    for job in jobs:
        if not job['ok'] or job['promoted']:continue
        seconds=job['samples']/16000
        bucket='under2s' if seconds<2 else '2to4s' if seconds<4 else '4to8s' if seconds<8 else '8splus'
        groups.setdefault((job['kind'],bucket),[]).append(job)
    costs=[]
    for (kind,bucket),rows in sorted(groups.items()):
        costs.append({'kind':kind,'audio_length_bucket':bucket,'fields_ms':{
            key:distribution([r[key] for r in rows]) for key in ['load','fe','nn','lm','worker_ms']},
            'cached_rows':distribution([r['cached'] for r in rows]),
            'checkpoint_internal_free_min':min(r['internal'] for r in rows),
            'checkpoint_internal_largest_min':min(r['largest'] for r in rows),
            'checkpoint_psram_free_min':min(r['psram'] for r in rows)})
    return {'fixture':capture['fixture'],'path':str(directory.resolve()),'metrics':capture.get('metrics',True),
        'captions':len(finals),'word_edits':errors,'reference_words':len(reference),'wer':errors/len(reference) if reference else None,
        'raw_speaker_coverage':{'labelled':sum(labels.get(e['sequence'],-1)>=0 for e in finals),
            'unknown_or_missing':sum(labels.get(e['sequence'],-1)<0 for e in finals),
            'missing_updates':sum(e['sequence'] not in labels for e in finals)},
        'observed_dropped_phrases':max([e['droppedPhrases'] for e in finals],default=0),
        'watchdogs':capture['watchdogs'],'panic':capture['panic'],'worker_jobs':len(jobs),'worker_costs':costs,
        'settings':{k:capture.get(k) for k in ['lm_strength','custom_words','vocabulary_sha256','harness_sha256','speakers']},
        'evidence':{str(p.name):hashlib.sha256(p.read_bytes()).hexdigest() for p in [capture_path,serial,Path(manifest)]},
        'withheld':['No sample-RMS alignment: reference-speaker identity and true-end/display latency are not estimated here.',
            'Probes-off has no driver DMA-loss counters; no zero-loss claim follows from a complete capture.',
            'Worker timing buckets contain different acoustic inputs and are descriptive overhead controls, not paired exact-input kernel benchmarks.',
            'Heap fields are post-inference checkpoints, not transient peaks.']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture',type=Path);p.add_argument('--manifest',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    if 'private' not in a.out.resolve().parts:p.error('Results must remain private')
    result=score(a.capture,a.manifest);a.out.write_text(json.dumps(result,indent=2))
    print(json.dumps({k:result[k] for k in ['fixture','metrics','captions','word_edits','reference_words','worker_jobs']}))
if __name__=='__main__':main()
