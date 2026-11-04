#!/usr/bin/env python3
"""Aggregate actual standalone ABBA captures, retaining incomplete/failed evidence."""
import argparse,hashlib,json,statistics
from pathlib import Path
from score_standalone import score
from standalone_capture import watchdog_counts

def median(rows,key):return statistics.median(key(row) for row in rows)
def analyse(records):
    outcomes=[]
    for fixture in sorted({row['fixture'] for row in records}):
        runs=[row for row in records if row['fixture']==fixture]
        arms={arm:[row for row in runs if row['arm']==arm] for arm in ['baseline','prefix']}
        result={'fixture':fixture,'runs':{arm:len(rows) for arm,rows in arms.items()},'comparison_complete':all(len(rows)==2 for rows in arms.values()) and [r['arm'] for r in runs]==['baseline','prefix','prefix','baseline'],'flags':[]}
        if not result['comparison_complete']:outcomes.append(result);continue
        a,b=arms['baseline'],arms['prefix'];flags=result['flags']
        if min(r['wer'] for r in b)>max(r['wer'] for r in a):flags.append('Candidate WER worse than both controls in both runs')
        if all('speaker_one_to_one' in r for r in runs):
            accuracy=lambda r:r['speaker_one_to_one']['right']/r['speaker_one_to_one']['scored'] if r['speaker_one_to_one']['scored'] else 0
            if max(map(accuracy,b))<min(map(accuracy,a)):flags.append('Candidate speaker correctness below both controls in both runs')
        else:flags.append('Reference speaker identity unavailable in at least one run')
        unknown=lambda r:r['raw_speaker_coverage']['unknown_or_missing']/r['captions'] if r['captions'] else 1
        if min(map(unknown,b))>max(map(unknown,a)):flags.append('Candidate unknown/missing coverage worse than both controls in both runs')
        fallback=lambda r:r['final_report']['state']['feature_overruns']
        if max(map(fallback,b))>max(map(fallback,a)):flags.append('Candidate feature overruns exceed the observed control range')
        for op in ['cache_clear','queue_copy','snapshot_copy']:
            base=median(a,lambda r:r['final_report']['memory'][op]['time']['sum_us'])
            candidate=median(b,lambda r:r['final_report']['memory'][op]['time']['sum_us'])
            result[op]={'baseline_median_total_us':base,'candidate_median_total_us':candidate,'fraction_reduction':1-candidate/base if base else None,
                'baseline_median_bytes':median(a,lambda r:r['final_report']['memory'][op]['bytes']),
                'candidate_median_bytes':median(b,lambda r:r['final_report']['memory'][op]['bytes'])}
        for metric in ['reference_final_publication','reference_speaker_publication','draft_audio_freshness','first_draft_from_segment_start','label_after_caption']:
            for percentile in ['median_s','p90_s']:
                def value(r):return r.get('latency',{}).get(metric,{}).get(percentile)
                if any(value(r) is None for r in runs):flags.append('Unavailable '+metric+' '+percentile);continue
                control=max(value(r) for r in a);candidate=min(value(r) for r in b)
                if candidate-control>.1 and candidate>control*1.05:flags.append('Repeatable latency increase: '+metric+' '+percentile)
        outcomes.append(result)
    return outcomes

def compare(status_path,fixture_root):
    status_path=Path(status_path);status=json.loads(status_path.read_text());records=[];failures=[]
    for run in status['runs']:
        if run.get('error'):failures.append(run);continue
        capture=Path(run['path']);manifest=Path(fixture_root)/run['fixture']/'manifest.json'
        record=score(capture,manifest);assert record['fixture']==run['fixture'];record['arm']=run['arm']
        data=json.loads((capture/'capture.json').read_text())
        record['watchdog_counts']=watchdog_counts((capture/'serial.log').read_text(errors='replace'))
        record['watchdogs']=max(record['watchdogs'],sum(record['watchdog_counts'].values()))
        record['application_errors']=sum(e['type']=='status' and e.get('state')=='error' for e in data['events'])
        record['forced_boundaries']=sum(e['type']=='final' and e.get('forcedBoundary',False) for e in data['events'])
        records.append(record)
    faults=[{'fixture':r['fixture'],'arm':r['arm'],'path':r['path']} for r in records if r['watchdogs'] or r['panic'] or r['application_errors'] or r['final_report']['capture']['overflow_count_u32'] or r['final_report']['state']['drops']]
    return {'controller_phase':status['phase'],'scope':status.get('scope','Primary conv2–4 ABBA'),'controller_error':status.get('error'),'controller_complete':bool(status.get('final_abba_complete') or status.get('comparison_complete')),
        'selected_app_restored':bool(status.get('restored_selected_app')),'lock_released':bool(status.get('lock_released')),
        'records':records,'failed_captures':failures,'faults':faults,'fixtures':analyse(records),
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'controller_status_sha256':hashlib.sha256(status_path.read_bytes()).hexdigest(),
        'limits':['Two runs per image do not establish statistical noninferiority.',
            'Repeatable flags use separation beyond both observed controls; absence of a flag is not proof of equivalence.',
            'Latency flags require both 100 ms and 5% beyond the worst observed control in both candidate runs.',
            'All per-run outcomes, failed captures, alignment rejections and missed reference ends remain evidence.',
            'This report does not complete instrumentation/secondary controls or the soak and does not promote defaults.']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('status',type=Path);p.add_argument('--fixtures',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    if 'private' not in a.out.resolve().parts:p.error('Results must remain private')
    report=compare(a.status,a.fixtures);a.out.write_text(json.dumps(report,indent=2))
    print(json.dumps({'phase':report['controller_phase'],'scored_runs':len(report['records']),'faults':report['faults'],'fixtures':report['fixtures']},indent=2))
if __name__=='__main__':main()
