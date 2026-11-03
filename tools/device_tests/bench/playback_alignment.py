"""Provisional sample alignment from a status round trip and observed output IO.

This does not measure acoustic onset or the age of the board's sample snapshot.
Keep those limitations visible rather than calling the estimate an exact timestamp.
"""
import math


def estimate_onset(samples,rate,sent,received,io_started,pipeline_ms,initially_running=False):
    values=[samples,rate,sent,received]
    if not all(math.isfinite(v) for v in values) or rate<=0 or samples<0 or received<sent:
        raise ValueError('invalid status timing')
    result={'usable':False,'status_round_trip_s':received-sent,
            'snapshot_age_unmeasured':True,'acoustic_onset_measured':False}
    if initially_running:
        return dict(result,reason='output was already running; onset not attributable')
    if io_started is None:
        return dict(result,reason='no output-start transition observed')
    if pipeline_ms is None or not math.isfinite(pipeline_ms) or pipeline_ms<0:
        return dict(result,reason='output pipeline estimate unavailable')
    if not math.isfinite(io_started) or io_started<sent:
        return dict(result,reason='invalid output-start transition')
    midpoint=(sent+received)/2
    onset=samples/rate+(io_started+pipeline_ms/1000-midpoint)
    if onset<0:return dict(result,reason='estimated onset precedes capture')
    return dict(result,usable=True,estimated_sample_onset_s=onset,
                round_trip_half_width_s=(received-sent)/2,pipeline_ms=pipeline_ms,
                reason='observed output IO plus pipeline estimate; not acoustic correlation')
