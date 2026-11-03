"""No false precision when output was active, an edge is missing, or clocks fail."""
from pathlib import Path
import sys,math
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/bench'))
from playback_alignment import estimate_onset
x=estimate_onset(16000,16000,10,10.1,10.2,20)
assert x['usable'] and abs(x['estimated_sample_onset_s']-1.17)<1e-9
assert abs(x['round_trip_half_width_s']-.05)<1e-9
assert x['snapshot_age_unmeasured'] and not x['acoustic_onset_measured']
assert not estimate_onset(16000,16000,10,10.1,10.2,20,True)['usable']
assert not estimate_onset(16000,16000,10,10.1,None,20)['usable']
assert not estimate_onset(16000,16000,10,10.1,10.2,None)['usable']
assert not estimate_onset(16000,16000,10,10.1,math.nan,20)['usable']
for args in [(0,0,10,10.1),(0,16000,11,10),(-1,16000,10,10.1)]:
 try:estimate_onset(*args,10.2,20)
 except ValueError:pass
 else:raise AssertionError(args)
print('playback alignment checks passed')
