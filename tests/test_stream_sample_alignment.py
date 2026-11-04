"""Independent onset, ambiguous periodic audio and changing-clock rejection."""
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/device_tests/stream'),str(ROOT/'tools/device_tests/bench')]
from sample_alignment import fit_sample_levels
rng=np.random.default_rng(20261103);axis=np.arange(0,80,.01)
envelope=np.convolve(rng.uniform(0,500,len(axis)),np.ones(7)/7,mode='same')
times=np.arange(.25,86,.257);onset=2.87
observed=np.log1p(.05*np.interp(times-onset,axis,envelope,left=0,right=0))
result=fit_sample_levels(times,observed,axis,envelope,.65)
assert result['usable'] and abs(result['estimated_sample_onset_s']-onset)<.011
assert result['search_radius_s']==3 and result['unique_peak_margin']>=.05
mixed=observed.copy();mask=times>np.median(times)
mixed[mask]=np.log1p(.05*np.interp(times[mask]-onset-.30,axis,envelope,left=0,right=0))
assert not fit_sample_levels(times,mixed,axis,envelope,.65)['usable']
assert not fit_sample_levels(times,rng.uniform(0,10,len(times)),axis,envelope,.65)['usable']
periodic=300+200*np.sin(axis*2*np.pi)
pred=np.log1p(np.interp(times-onset,axis,periodic,left=300,right=300))
assert not fit_sample_levels(times,pred,axis,periodic,.65)['usable']
for t,y,a,e in [(times,np.zeros(len(times)),axis,envelope),
                (times[:20],observed[:20],axis,envelope),
                (times,observed[:-1],axis,envelope),
                (times[::-1],observed,axis,envelope),
                (times,observed,axis,envelope*np.nan)]:
 rejected=fit_sample_levels(t,y,a,e,.65)
 assert not rejected['usable'] and rejected.get('rejection')
print('Sample-clock alignment: >2 s launch uncertainty recovered; random, periodic and changing-offset evidence rejected')
