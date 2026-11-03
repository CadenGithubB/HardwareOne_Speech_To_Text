#!/usr/bin/env python3
"""Score completed live experimental captures; output numbers only, never captions.

score_experiments.py STATUS.json [...] --out private/report.json
Incomplete captures are retained as evidence but not scored. Results do not constitute
promotion decisions. Acoustic reference alignment remains estimated.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'speaker'))
import spkrules
import benchscore
import benchsets

def fields(line):
    return {k:int(v) for k,v in re.findall(r'\b([a-z_0-9]+)=(-?\d+)',line)}

def activation(log,captions):
    calls=re.findall(r'TL lm_decode .*?strength=([\d.]+) status=(\S+)',log)
    beams=[int(x) for x in re.findall(r'Language model .*?beam (\d+),',log)]
    return {'decoder_strengths':sorted({float(x) for x,_ in calls}),
            'decoder_status_counts':dict(Counter(s for _,s in calls)),
            'decoder_ok':sum(s=='ok' for _,s in calls),'decoder_other':sum(s!='ok' for _,s in calls),
            'file_beams':sorted(set(beams)),
            'speculative_promotions':log.count('TL spec_promote '),
            'speculative_finished':log.count('TL spec_end '),
            'hard_boundaries':sum(bool(c.get('forcedBoundary')) for c in captions),
            'vocabulary_active':bool(re.search(r'TL vocab_test active=1\b',log))}

def speaker_cost(log):
    drafts=[];jobs=[]
    for line in log.splitlines():
        v=fields(line)
        if 'TL draft ' in line and 's' in v and 'e' in v:drafts.append((v['s'],v['e']))
        if 'TL spk seq=' in line and 'nn_us' in v:
            m=re.search(r'\[(\d+)\]',line)
            if m:jobs.append((int(m[1])-v['us']/1000,int(m[1]),v))
    if not jobs:return {'jobs':0}
    med=lambda key:round(statistics.median(v[key] for _,_,v in jobs)/1000,3)
    overlap=[]
    for a,b,v in jobs:
        busy=sum(max(0,min(b,e)-max(a,s)) for s,e in drafts)
        overlap.append(busy/max(.001,b-a))
    return {'jobs':len(jobs),'job_ms_median':med('us'),'trunk_ms_median':med('nn_us'),
            'frontend_ms_median':med('fe_us'),'head_ms_median':med('head_us'),
            'draft_overlap_median':round(statistics.median(overlap),4),
            'jobs_with_draft_overlap':sum(v>0 for v in overlap)}

def caption_speaker_metrics(clips,captions,log):
    # Include failures and captions with no embedding/label; never improve coverage
    # merely by excluding a skipped speaker job from the denominator.
    labels={};reasons={}
    for line in log.splitlines():
        v=fields(line)
        if 'TL spk seq=' in line and 'seq' in v and 'spk' in v:labels[v['seq']]=v['spk']
        if 'TL spk_submit seq=' in line and v.get('admitted')==0:labels[v['seq']]=-1
        if 'TL spk_match seq=' in line or ('TL spk_submit seq=' in line and v.get('admitted')==0):
            m=re.search(r'\breason=(\S+)',line)
            if m:reasons[v['seq']]=m[1]
    phrases=[];assigned=[]
    for cap in sorted(captions,key=lambda c:c['sequence']):
        a,b=cap['startSample']/16000,cap['endSample']/16000
        ref=benchsets.clip_at(clips,(a+b)/2)
        heard={c['speaker'] for c in clips if min(b,float(c['end_s']))-max(a,float(c['start_s']))>=.3}
        q=cap['sequence'];phrases.append({'id':q,'ref':ref['speaker'] if ref else None,'mixed':len(heard)>1})
        assigned.append((labels.get(q,-1),reasons.get(q,'unknown_or_missing')))
    metric=spkrules.run_metrics(phrases,list(range(len(phrases))),assigned)
    return metric,sum(c['sequence'] not in labels for c in captions)

def score_capture(entry):
    d=Path(entry['path']);manifest=d/'manifest-aligned.json'
    inputs=[d/'bench.json',d/'serial-0.log',manifest]
    digest=hashlib.sha256(b''.join(p.read_bytes() for p in inputs)).hexdigest()
    runs=json.loads(inputs[0].read_text())
    if len(runs)!=1:raise ValueError('expected one finalized run per capture')
    run=runs[0];log=inputs[1].read_text(errors='replace');caps=run['captions']
    clips=sorted(json.loads(manifest.read_text())['clips'],key=lambda c:float(c['start_s']))
    row={'fixture':entry['fixture'],'arm':entry.get('arm'),'path':str(d),'input_sha256':digest,
         'state':run['state'],'panic':bool(run.get('panic')),'watchdogs':run.get('watchdog'),
         'watchdogs_total_including_setup':log.count('Task watchdog got triggered'),
         'overruns':run.get('overruns'),'captions':len(caps),'activation':activation(log,caps),
         'speaker_cost':speaker_cost(log),'alignment':'estimated playback onset; acoustic comparison provisional'}
    row['memory_minima']={key:min(map(int,values)) if values else None for key in ['int_min','psram_min'] for values in [re.findall(r'\b'+key+r'=(\d+)',log)]}
    row['majority_metrics']=benchscore.score_run(clips,caps,log.splitlines())
    sets=benchsets.run_set(clips,d.name,caps,log.splitlines())
    phrases=sets['phrases']
    labels=[(p['dev_spk'] if p.get('dev_spk') is not None else -1,p.get('dev_reason','missing')) for p in phrases]
    row['diagnostic_one_to_one']=spkrules.run_metrics(phrases,list(range(len(phrases))),labels)
    row['actual_one_to_one'],row['captions_without_label']=caption_speaker_metrics(clips,caps,log)
    row['diagnostic_phrases']=len(phrases)
    row['captions_without_embedding']=len(caps)-len(phrases)
    row['alignment_sensitivity']=[]
    for delta in [-.5,-.25,0,.25,.5]:
        shifted=[{**c,'start_s':float(c['start_s'])+delta,'end_s':float(c['end_s'])+delta} for c in clips]
        metric,_=caption_speaker_metrics(shifted,caps,log)
        row['alignment_sensitivity'].append({'delta_s':delta,**{k:metric[k] for k in ['scored','labelled','right','split','merge']}})
    row['timing_tools']={}
    for tool,with_manifest in [('truelag.py',True),('latsplit.py',False),('draftlag.py',False)]:
        cmd=[sys.executable,str(HERE/tool)]+([str(manifest)] if with_manifest else [])+[str(d)]
        result=subprocess.run(cmd,capture_output=True,text=True)
        row['timing_tools'][tool]={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
    return row

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('statuses',nargs='+',type=Path);ap.add_argument('--out',required=True,type=Path);a=ap.parse_args()
    report={'captures':[],'incomplete':[],'controllers':[],'errors':[]}
    for path in a.statuses:
        status=json.loads(path.read_text());report['controllers'].append({'path':str(path),'phase':status['phase'],'restored_fixed_production':status.get('restored_fixed_production')})
        for entry in status.get('runs',[]):
            if entry.get('state')!='done' or 'path' not in entry:
                report['incomplete'].append(entry);continue
            try:report['captures'].append(score_capture(entry))
            except Exception as exc:report['errors'].append({'path':entry.get('path'),'error':str(exc)})
    a.out.parent.mkdir(parents=True,exist_ok=True);temp=a.out.with_suffix('.tmp');temp.write_text(json.dumps(report,indent=2));temp.replace(a.out)
    print(f"Scored {len(report['captures'])} captures; {len(report['errors'])} errors; {len(report['incomplete'])} incomplete")
    if report['errors']:raise SystemExit(1)
if __name__=='__main__':main()
