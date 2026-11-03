"""Guard activation evidence and timing clocks against misleading experiment scores."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/bench'))
from score_experiments import activation,speaker_cost,caption_speaker_metrics
log='''Language model fixture: beam 32, 0 custom words
TL lm_decode call=1 frames=10 strength=0.900 status=ok
TL lm_decode call=2 frames=10 strength=0.900 status=unavailable
TL spec_end seq=1 kept=1
TL spec_promote seg=1
TL vocab_test active=10 cap=1.5
'''
x=activation(log,[{'forcedBoundary':True},{}])
assert x['decoder_strengths']==[.9] and x['decoder_ok']==1 and x['decoder_other']==1
assert x['file_beams']==[32] and x['hard_boundaries']==1
assert x['speculative_promotions']==1 and not x['vocabulary_active']
assert activation('TL vocab_test active=1 cap=1.5',[])['vocabulary_active']
log='''1790000000.1 [1000] STT: TL spk seq=1 us=100000 nn_us=50000 fe_us=30000 head_us=20000
1790000000.2 [2000] STT: TL spk seq=2 us=500000 nn_us=100000 fe_us=300000 head_us=100000
TL draft seq=1 s=0 e=500
TL draft seq=2 s=1600 e=1800
'''
x=speaker_cost(log)
assert x['jobs']==2 and x['job_ms_median']==300
assert x['trunk_ms_median']==75 and x['draft_overlap_median']==.2
assert x['jobs_with_draft_overlap']==1
assert speaker_cost('')=={'jobs':0}
print('experiment scoring checks passed')

clips=[{'start_s':0,'end_s':2,'speaker':'a'},{'start_s':2,'end_s':4,'speaker':'b'}]
caps=[{'sequence':1,'startSample':8000,'endSample':24000},{'sequence':2,'startSample':40000,'endSample':56000}]
metric,missing=caption_speaker_metrics(clips,caps,'TL spk seq=1 spk=0')
assert metric['scored']==2 and metric['labelled']==1 and metric['right']==1 and missing==1
metric,missing=caption_speaker_metrics(clips,caps,'TL spk seq=1 spk=0\nTL spk_submit seq=2 admitted=0 spk=-1 reason=audio_pressure')
assert metric['scored']==2 and metric['labelled']==1 and missing==0
