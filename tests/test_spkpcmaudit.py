#!/usr/bin/env python3
"""Known delay, gain, polarity and silence cases for waveform timing."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/speaker'))
import numpy as np
from spkpcmaudit import SR,bandpass,align_waveform

rng=np.random.default_rng(13);reference=rng.normal(0,.1,SR*8)
start=SR*3+123;device=reference[start:start+32000]*-.23
r=align_waveform(bandpass(reference),device,3.2)
assert r['matched'] and r['polarity']==-1 and r['peak_correlation']>.99
assert abs(r['matched_model_start_s']*SR-start)<=1
assert not align_waveform(bandpass(reference),np.zeros(32000),3)['matched']
print('speaker PCM audit: waveform delay and polarity ok')
