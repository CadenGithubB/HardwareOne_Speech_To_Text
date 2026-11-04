"""Comparison gates must retain incomplete cohorts and expose regressions."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/device_tests/stream'))
from compare_standalone import analyse

def row(arm,wer=.2,right=8,latency=1,clear=1000,unknown=0):
    return {'fixture':'synthetic','arm':arm,'wer':wer,'captions':10,
        'speaker_one_to_one':{'right':right,'scored':10},'raw_speaker_coverage':{'unknown_or_missing':unknown},
        'final_report':{'state':{'feature_overruns':0},'memory':{
            op:{'time':{'sum_us':clear},'bytes':clear*2} for op in ['cache_clear','queue_copy','snapshot_copy']}},
        'latency':{metric:{'median_s':latency,'p90_s':latency} for metric in ['reference_final_publication','reference_speaker_publication','draft_audio_freshness','first_draft_from_segment_start','label_after_caption']}}
a=row('baseline');b=row('prefix',clear=500);c=row('prefix',clear=500);d=row('baseline')
assert not analyse([a,b,c])[0]['comparison_complete']
assert not analyse([a,b,d,c])[0]['comparison_complete']
result=analyse([a,b,c,d])[0];assert result['comparison_complete'] and not result['flags']
assert result['cache_clear']['fraction_reduction']==.5
for kind,values in [('wer',{'wer':.4}),('speaker',{'right':3}),('unknown',{'unknown':5}),('latency',{'latency':1.2})]:
    flags=analyse([a,row('prefix',**values),row('prefix',**values),d])[0]['flags']
    assert flags,(kind,flags)
# Both latency criteria must be exceeded; percentages alone or 100 ms alone
# must not be mislabeled as the specified repeatable latency regression.
for base,candidate in [(1,1.06),(5,5.11)]:
    flags=analyse([row('baseline',latency=base),row('prefix',latency=candidate),row('prefix',latency=candidate),row('baseline',latency=base)])[0]['flags']
    assert not any('latency increase' in flag for flag in flags)
# A favorable run must not erase a repeated degradation in a different fixture.
good=[row(arm) for arm in ['baseline','prefix','prefix','baseline']]
bad=[row('baseline'),row('prefix',wer=.4),row('prefix',wer=.4),row('baseline')]
for record in bad:record['fixture']='bad'
assert any('WER worse' in flag for result in analyse(good+bad) if result['fixture']=='bad' for flag in result['flags'])
print('Comparison gates: incomplete/order rejection, per-fixture quality/coverage and conjunctive latency thresholds passed')
