"""Recover a delayed onset without text/labels; reject inconsistent or stale evidence."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/bench'))
from align_experiments import fit_levels
from score_experiments import score_capture,live_reference_clips

rng=np.random.default_rng(284)
axis=np.arange(0,220,.01)
envelope=np.convolve(rng.uniform(0,100,len(axis)),np.ones(5)/5,mode='same')
times=np.arange(1,219,1.013)
onset=2.37
observed=np.log1p(.1*np.interp(times-onset,axis,envelope,left=0,right=0))
result=fit_levels(times,observed,axis,envelope,2.18)
assert result['usable'] and abs(result['estimated_sample_onset_s']-onset)<.011
# Different halves imply ambiguous telemetry; never publish a confident correction.
mixed=observed.copy()
mixed[1::2]=np.log1p(.1*np.interp(times[1::2]-onset-.35,axis,envelope,left=0,right=0))
assert not fit_levels(times,mixed,axis,envelope,2.18)['usable']
assert not fit_levels(times,rng.uniform(0,10,len(times)),axis,envelope,2.18)['usable']
assert not fit_levels(times,observed,axis,envelope,onset-.8)['usable']
for t,o in [(times[:10],observed[:10]),(times,np.ones(len(times)))]:
    try:fit_levels(t,o,axis,envelope,2.18)
    except ValueError:pass
    else:raise AssertionError('insufficient evidence accepted')

with tempfile.TemporaryDirectory() as temporary:
    d=Path(temporary)
    (d/'bench.json').write_text(json.dumps([{'captions':[],'estimated_playback_sample_offset_s':1.0}]))
    (d/'manifest-aligned.json').write_text('{"clips":[]}')
    (d/'serial-0.log').write_text('')
    alignment={'usable':False}
    try:score_capture({'path':str(d),'fixture':'synthetic'},alignment=alignment)
    except ValueError as error:assert 'quality gate' in str(error)
    else:raise AssertionError('unusable alignment accepted')
    alignment.update(usable=True,serial_sha256='stale',bench_sha256=hashlib.sha256((d/'bench.json').read_bytes()).hexdigest())
    try:score_capture({'path':str(d),'fixture':'synthetic'},alignment=alignment)
    except ValueError as error:assert 'do not match' in str(error)
    else:raise AssertionError('stale alignment evidence accepted')

with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary);(root/'conv').mkdir();(root/'capture').mkdir()
    raw={'clips':[{'start_s':1,'end_s':2,'speech_end_s':1.8,'text_norm':'unchanged words'}]}
    source=root/'conv/manifest.json';source.write_text(json.dumps(raw))
    # Actual legacy bug: only start/end were translated by playback offset.
    mixed={'clips':[{'start_s':4,'end_s':5,'speech_end_s':1.8}]}
    corrected,sha=live_reference_clips(root/'capture','conv',mixed,3,4.2)
    assert corrected[0]['start_s']==5.2 and corrected[0]['end_s']==6.2
    assert corrected[0]['speech_end_s']==6 and corrected[0]['text_norm']=='unchanged words'
    assert sha==hashlib.sha256(source.read_bytes()).hexdigest()
    try:live_reference_clips(root/'capture','conv',mixed,2,4.2)
    except ValueError:pass
    else:raise AssertionError('mismatched source manifest accepted')

print('experiment alignment checks passed')
