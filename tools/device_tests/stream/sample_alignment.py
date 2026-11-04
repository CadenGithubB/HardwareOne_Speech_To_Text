"""Sample-clock envelope qualification, independent of text and speaker labels."""
import numpy as np
from align_experiments import fit_levels

def fit_sample_levels(times,observed,axis,envelope,estimated_onset,radius=3.0):
    """Return an explicit rejection instead of losing the whole score on bad RMS."""
    try:
        arrays=[np.asarray(x,dtype=float) for x in (times,observed,axis,envelope)]
        if any(x.ndim!=1 or not np.all(np.isfinite(x)) for x in arrays):
            raise ValueError('Nonfinite or non-vector alignment data')
        times,observed,axis,envelope=arrays
        if len(times)!=len(observed) or len(axis)!=len(envelope):
            raise ValueError('Alignment array lengths differ')
        if len(times)<100 or len(axis)<2:
            raise ValueError('Too few levels for independent temporal halves')
        if not np.all(np.diff(times)>0) or not np.all(np.diff(axis)>0):
            raise ValueError('Alignment clocks must increase strictly')
        if not np.isfinite(estimated_onset) or not np.isfinite(radius) or radius<=0:
            raise ValueError('Invalid onset search bounds')
        return _fit_sample_levels(times,observed,axis,envelope,estimated_onset,radius)
    except ValueError as error:
        return {'usable':False,'version':'sample-rms-v1','rejection':str(error),
                'search_center_s':float(estimated_onset),'search_radius_s':float(radius)}

def _fit_sample_levels(times,observed,axis,envelope,estimated_onset,radius):
    times=np.asarray(times);observed=np.asarray(observed);axis=np.asarray(axis);envelope=np.asarray(envelope)
    result=fit_levels(times,observed,axis,envelope,estimated_onset,radius=radius)
    result.update(version='sample-rms-v1',search_center_s=float(estimated_onset),search_radius_s=float(radius))
    halves=[]
    if len(times)<100:
        result.update(usable=False,half_fits=[],rejection='Too few levels for independent temporal halves');return result
    for mask in [times<np.median(times),times>=np.median(times)]:
        halves.append(fit_levels(times[mask],observed[mask],axis,envelope,estimated_onset,radius=radius))
    best=result['estimated_sample_onset_s'];alternative=[]
    for offset in np.arange(estimated_onset-radius,estimated_onset+radius+.001,.01):
        if abs(offset-best)<=.20:continue
        relative=times-offset;valid=(relative>=axis[0])&(relative<=axis[-1])
        if valid.sum()<20:continue
        predicted=np.log1p(np.interp(relative[valid],axis,envelope));actual=observed[valid]
        if np.std(predicted)>=.1 and np.std(actual)>=.1:alternative.append(float(np.corrcoef(actual,predicted)[0,1]))
    other=max(alternative) if alternative else float('-inf');margin=result['all_even_odd'][0]['correlation']-other
    result.update(half_fits=halves,alternative_peak_correlation=other if np.isfinite(other) else None,unique_peak_margin=margin if np.isfinite(margin) else None,
        gates={'minimum_split_correlation':.65,'maximum_even_odd_offset_difference_s':.10,
               'maximum_half_offset_difference_s':.05,'alternative_peak_exclusion_s':.20,'minimum_unique_peak_margin':.05})
    result['usable']=bool(result['usable'] and all(h['usable'] for h in halves)
        and abs(halves[0]['estimated_sample_onset_s']-halves[1]['estimated_sample_onset_s'])<=.05 and margin>=.05)
    return result
