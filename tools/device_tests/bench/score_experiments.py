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
import tempfile

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

def speaker_labels(log):
    labels={};reasons={}
    for line in log.splitlines():
        v=fields(line)
        if 'TL spk seq=' in line and 'seq' in v and 'spk' in v:labels[v['seq']]=v['spk']
        if 'TL spk_submit seq=' in line and v.get('admitted')==0:labels[v['seq']]=-1
        if 'TL spk_match seq=' in line or ('TL spk_submit seq=' in line and v.get('admitted')==0):
            m=re.search(r'\breason=(\S+)',line)
            if m:reasons[v['seq']]=m[1]
    return labels,reasons

def raw_speaker_coverage(captions,log):
    """All published captions, independent of reference timing or speaker identity."""
    labels,reasons=speaker_labels(log)
    unknown=[c['sequence'] for c in captions if labels.get(c['sequence'],-1)<0]
    return {'captions':len(captions),'labelled':len(captions)-len(unknown),
            'unknown_or_missing':len(unknown),
            'missing_diagnostic':sum(c['sequence'] not in labels for c in captions),
            'unknown_reasons':dict(Counter(reasons.get(q,'unknown_or_missing') for q in unknown))}

def caption_speaker_metrics(clips,captions,log):
    # Include failures and captions with no embedding/label; never improve coverage
    # merely by excluding a skipped speaker job from the denominator.
    labels,reasons=speaker_labels(log)
    phrases=[];assigned=[]
    for cap in sorted(captions,key=lambda c:c['sequence']):
        a,b=cap['startSample']/16000,cap['endSample']/16000
        ref=benchsets.clip_at(clips,(a+b)/2)
        heard={c['speaker'] for c in clips if min(b,float(c['end_s']))-max(a,float(c['start_s']))>=.3}
        q=cap['sequence'];phrases.append({'id':q,'ref':ref['speaker'] if ref else None,'mixed':len(heard)>1})
        assigned.append((labels.get(q,-1),reasons.get(q,'unknown_or_missing')))
    metric=spkrules.run_metrics(phrases,list(range(len(phrases))),assigned)
    metric['published_captions']=len(phrases)
    metric['excluded_no_reference']=sum(p['ref'] is None for p in phrases)
    metric['excluded_mixed']=sum(p['ref'] is not None and p['mixed'] for p in phrases)
    return metric,sum(c['sequence'] not in labels for c in captions)

def vocabulary_metrics(clips,captions,terms):
    terms=set(terms);by_clip=[[] for _ in clips];mixed=unattributed=0;all_words=[]
    for cap in captions:
        words=benchscore.norm(cap.get('sttText',''));all_words+=words
        a,b=cap['startSample']/16000,cap['endSample']/16000
        matches=[i for i,c in enumerate(clips) if min(b,float(c['end_s']))-max(a,float(c['start_s']))>=.3]
        count=sum(w in terms for w in words)
        if len(matches)>1:mixed+=count;continue
        if not matches:unattributed+=count;continue
        for i in matches:by_clip[i]+=words
    result={'expected_target_terms':0,'attributable_target_hits':0,'control_term_insertions':0,
            'mixed_caption_term_occurrences':mixed,'unattributed_term_occurrences':unattributed,
            'target_clips':0,'control_clips':0}
    refs=Counter(w for c in clips for w in benchscore.norm(c.get('text_norm','')) if w in terms)
    hyp=Counter(w for w in all_words if w in terms)
    result['global_excess_term_occurrences']=sum(max(0,hyp[w]-refs[w]) for w in terms)
    for c,words in zip(clips,by_clip):
        expected=Counter(w for w in benchscore.norm(c.get('text_norm','')) if w in terms)
        observed=Counter(w for w in words if w in terms)
        if c.get('kind')=='target':
            result['target_clips']+=1;result['expected_target_terms']+=sum(expected.values())
            result['attributable_target_hits']+=sum(min(observed[w],n) for w,n in expected.items())
        elif c.get('kind')=='control':
            result['control_clips']+=1;result['control_term_insertions']+=sum(max(0,observed[w]-expected[w]) for w in terms)
    return result

def word_error_details(clips,captions):
    """One deterministic minimum-edit path; boundary words are diagnostic proxies."""
    reference=[];first=[];last=[]
    for clip in clips:
        words=clip.get('text_norm','').split()
        if words:
            first.append(len(reference));reference.extend(words);last.append(len(reference)-1)
    hypothesis=[w for c in sorted(captions,key=lambda c:c['sequence']) for w in benchscore.norm(c.get('sttText',''))]
    n,m=len(reference),len(hypothesis)
    costs=[list(range(m+1))]+[[i]+[0]*m for i in range(1,n+1)]
    for i in range(1,n+1):
        for j in range(1,m+1):
            costs[i][j]=min(costs[i-1][j-1]+(reference[i-1]!=hypothesis[j-1]),costs[i-1][j]+1,costs[i][j-1]+1)
    kinds={};counts=Counter();i,j=n,m
    while i or j:
        if i and j and reference[i-1]==hypothesis[j-1] and costs[i][j]==costs[i-1][j-1]:
            i-=1;j-=1;kinds[i]='matched'
        elif i and j and costs[i][j]==costs[i-1][j-1]+1:
            i-=1;j-=1;kinds[i]='substituted';counts['substitutions']+=1
        elif i and costs[i][j]==costs[i-1][j]+1:
            i-=1;kinds[i]='deleted';counts['deletions']+=1
        else:
            j-=1;counts['insertions']+=1
    boundary=lambda positions:{'words':len(positions),**{k:sum(kinds[p]==k for p in positions) for k in ['matched','substituted','deleted']}}
    return {'reference_words':n,'edits':costs[n][m],
            **{k:counts[k] for k in ['substitutions','deletions','insertions']},
            'first_words':boundary(first),'last_words':boundary(last),
            'limitation':'One minimum-edit path; repeated-word attribution can be ambiguous. '
                         'Boundary-word errors do not prove acoustic clipping or quiet-word recall.'}

def live_reference_clips(directory,fixture,original_manifest,original_onset,onset):
    """Rebuild all time fields from the immutable playlist reference.

    Early live harnesses shifted start/end but accidentally left speech_end_s
    on the playlist clock. Never propagate that mixture into true-lag scores.
    """
    source=directory.parent/fixture/'manifest.json'
    data=source.read_bytes();clips=json.loads(data)['clips']
    old=original_manifest['clips']
    if len(clips)!=len(old):raise ValueError('source/reference clip count mismatch')
    for raw,aligned in zip(clips,old):
        for key in ['start_s','end_s']:
            if abs(float(raw[key])+original_onset-float(aligned[key]))>1e-5:
                raise ValueError('source/reference boundaries do not match original onset')
    keys={'start_s','end_s','speech_start_s','speech_end_s'}
    shifted=[{k:float(v)+onset if k in keys else v for k,v in c.items()} for c in clips]
    return sorted(shifted,key=lambda c:float(c['start_s'])),hashlib.sha256(data).hexdigest()

def score_capture(entry,terms=None,alignment=None):
    d=Path(entry['path']);manifest=d/'manifest-aligned.json'
    inputs=[d/'bench.json',d/'serial-0.log',manifest]
    digest=hashlib.sha256(b''.join(p.read_bytes() for p in inputs)).hexdigest()
    runs=json.loads(inputs[0].read_text())
    if len(runs)!=1:raise ValueError('expected one finalized run per capture')
    run=runs[0];log=inputs[1].read_text(errors='replace');caps=run['captions']
    manifest_data=json.loads(manifest.read_text())
    clips=sorted(manifest_data['clips'],key=lambda c:float(c['start_s']))
    if alignment is not None:
        if not alignment.get('usable'):raise ValueError('alignment quality gate rejected capture')
        if alignment['serial_sha256']!=hashlib.sha256(inputs[1].read_bytes()).hexdigest() or alignment['bench_sha256']!=hashlib.sha256(inputs[0].read_bytes()).hexdigest():
            raise ValueError('alignment inputs do not match capture')
        if alignment['original_onset_s']!=run['estimated_playback_sample_offset_s']:
            raise ValueError('alignment original onset does not match capture')
        delta=alignment['estimated_sample_onset_s']-alignment['original_onset_s']
        clips=[{**c,'start_s':float(c['start_s'])+delta,'end_s':float(c['end_s'])+delta} for c in clips]
    source_sha=None
    if run.get('mode')=='live-microphone':
        if alignment is not None and hashlib.sha256((d.parent/entry['fixture']/'playlist.wav').read_bytes()).hexdigest()!=alignment['fixture_sha256']:
            raise ValueError('alignment fixture audio does not match capture reference')
        onset=run['estimated_playback_sample_offset_s'] if alignment is None else alignment['estimated_sample_onset_s']
        clips,source_sha=live_reference_clips(d,entry['fixture'],manifest_data,run['estimated_playback_sample_offset_s'],onset)
    row={'fixture':entry['fixture'],'arm':entry.get('arm'),'path':str(d),'input_sha256':digest,
         'state':run['state'],'panic':bool(run.get('panic')),'watchdogs':run.get('watchdog'),
         'watchdogs_total_including_setup':log.count('Task watchdog got triggered'),
         'overruns':run.get('overruns'),'captions':len(caps),'activation':activation(log,caps),
         'speaker_cost':speaker_cost(log),'alignment':'estimated playback onset; acoustic comparison provisional'}
    row['raw_speaker_coverage']=raw_speaker_coverage(caps,log)
    if source_sha:
        row['source_manifest_sha256']=source_sha
        row['reference_timing']='all time fields rebuilt from original playlist manifest; legacy mixed-clock manifest not used for true lag'
    if alignment is not None:
        row['alignment']='secondary RMS/clock estimate; sparse wall-clock telemetry, sample-clock acoustic onset unproven'
        row['alignment_details']=alignment
    row['memory_minima']={key:min(map(int,values)) if values else None for key in ['int_min','psram_min'] for values in [re.findall(r'\b'+key+r'=(\d+)',log)]}
    if terms:row['vocabulary']=vocabulary_metrics(clips,caps,terms)
    row['majority_metrics']=benchscore.score_run(clips,caps,log.splitlines())
    row['word_errors']=word_error_details(clips,caps)
    if round(row['word_errors']['edits']/row['word_errors']['reference_words'],4)!=row['majority_metrics']['wer']:
        raise ValueError('word-error breakdown does not agree with WER')
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
        row['alignment_sensitivity'].append({'delta_s':delta,**{k:metric[k] for k in ['scored','labelled','right','split','merge','excluded_no_reference','excluded_mixed']}})
    row['timing_tools']={}
    with tempfile.TemporaryDirectory(prefix='stt-score-') as temporary:
        timing_manifest=manifest
        if alignment is not None or source_sha is not None:
            timing_manifest=Path(temporary)/'manifest.json'
            data=json.loads(manifest.read_text());data['clips']=clips
            timing_manifest.write_text(json.dumps(data))
        for tool,with_manifest in [('truelag.py',True),('latsplit.py',False),('draftlag.py',False)]:
            cmd=[sys.executable,str(HERE/tool)]+([str(timing_manifest)] if with_manifest else [])+[str(d)]
            result=subprocess.run(cmd,capture_output=True,text=True)
            row['timing_tools'][tool]={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
    return row

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('statuses',nargs='+',type=Path);ap.add_argument('--out',required=True,type=Path);ap.add_argument('--vocab-config',type=Path);ap.add_argument('--alignment-report',type=Path);a=ap.parse_args()
    report={'captures':[],'incomplete':[],'controllers':[],'errors':[]}
    terms=None
    alignments=None
    if a.alignment_report:
        data=a.alignment_report.read_bytes()
        report['alignment_report_sha256']=hashlib.sha256(data).hexdigest()
        alignments={x['path']:x for x in json.loads(data)['captures']}
    if a.vocab_config:
        data=a.vocab_config.read_bytes();terms=json.loads(data)['words']
        if not terms or any(not re.fullmatch(r"[a-z']{1,31}",w) for w in terms):raise ValueError('invalid vocabulary experiment configuration')
        report['vocabulary_config_sha256']=hashlib.sha256(data).hexdigest()
    for path in a.statuses:
        status=json.loads(path.read_text());report['controllers'].append({'path':str(path),'phase':status['phase'],'restored_fixed_production':status.get('restored_fixed_production')})
        for entry in status.get('runs',[]):
            if entry.get('state')!='done' or 'path' not in entry:
                report['incomplete'].append(entry);continue
            try:
                alignment=None if alignments is None else alignments[str(Path(entry['path']).resolve())]
                report['captures'].append(score_capture(entry,terms,alignment))
            except Exception as exc:report['errors'].append({'path':entry.get('path'),'error':str(exc)})
    a.out.parent.mkdir(parents=True,exist_ok=True);temp=a.out.with_suffix('.tmp');temp.write_text(json.dumps(report,indent=2));temp.replace(a.out)
    print(f"Scored {len(report['captures'])} captures; {len(report['errors'])} errors; {len(report['incomplete'])} incomplete")
    if report['errors']:raise SystemExit(1)
if __name__=='__main__':main()
