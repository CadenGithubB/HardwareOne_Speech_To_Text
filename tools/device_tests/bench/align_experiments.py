#!/usr/bin/env python3
"""Estimate live playback alignment from independent clock and RMS telemetry.

Requires numpy. Does not use captions, reference text, or speaker labels to fit an
offset. Original captures/manifests remain untouched. Sparse level telemetry is
not a raw microphone recording; corrected timing still needs sensitivity checks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import wave

import numpy as np


def fit_levels(times, observed, axis, envelope, clock_offset, radius=.8):
    times, observed = np.asarray(times), np.asarray(observed)
    axis, envelope = np.asarray(axis), np.asarray(envelope)
    if len(times) < 50 or len(axis) < 2 or not np.all(np.isfinite(observed)):
        raise ValueError('insufficient/invalid level telemetry')
    if np.std(observed) < .1:
        raise ValueError('level telemetry has no usable variation')
    offsets = np.arange(clock_offset-radius, clock_offset+radius+.001, .01)
    fits = []
    for mask in [np.ones(len(times), dtype=bool), np.arange(len(times))%2 == 0,
                 np.arange(len(times))%2 == 1]:
        correlations = []
        for offset in offsets:
            relative = times-offset
            valid = mask & (relative >= axis[0]) & (relative <= axis[-1])
            if valid.sum() < 20:
                correlations.append(float('-inf'))
                continue
            predicted = np.log1p(np.interp(relative[valid], axis, envelope))
            actual = observed[valid]
            if np.std(predicted) < .1 or np.std(actual) < .1:
                correlations.append(float('-inf'))
            else:
                correlations.append(float(np.corrcoef(actual, predicted)[0, 1]))
        best = int(np.argmax(correlations))
        if not np.isfinite(correlations[best]):
            raise ValueError('no usable envelope correlation')
        fits.append({'offset_s':float(offsets[best]), 'correlation':correlations[best],
                     'at_search_edge':best < 10 or best >= len(offsets)-10})
    usable = (all(x['correlation'] >= .65 and not x['at_search_edge'] for x in fits)
              and abs(fits[1]['offset_s']-fits[2]['offset_s']) <= .1)
    return {'usable':bool(usable), 'estimated_sample_onset_s':fits[0]['offset_s'],
            'all_even_odd':fits, 'telemetry_points':len(times),
            'method':'clock-constrained RMS-envelope correlation; 10ms search grid',
            'limitation':'Sparse capture-task wall-clock levels, not recorded sample-clock audio; '
                         'split agreement is consistency, not absolute acoustic precision.'}


def align_capture(entry, fixture_root):
    directory = Path(entry['path'])
    serial, bench = directory/'serial-0.log', directory/'bench.json'
    wav = fixture_root/entry['fixture']/'playlist.wav'
    log = serial.read_text(errors='replace')
    run, = json.loads(bench.read_text())
    starts = re.findall(r'TL capture_start t=(\d+)', log)
    if len(starts) != 1:
        raise ValueError('expected exactly one capture-start clock')
    capture_start = int(starts[0])/1000
    clocks = sorted(float(h)-int(d)/1000 for h,d in
                    re.findall(r'(?m)^(\d+\.\d+) \[\s*(\d+)\].*', log))
    if len(clocks) < 50:
        raise ValueError('insufficient host/device clock pairs')
    # Low percentile avoids serial queue delay; reject gross clock instability.
    bridge = clocks[len(clocks)//100]
    spread = clocks[len(clocks)//2]-bridge
    if spread > .5:
        raise ValueError('host/device clock bridge too unstable')
    clock_offset = run['playback_host_time']-bridge-capture_start
    levels = [(int(t)/1000-capture_start, max(0,int(r)-int(n))) for t,r,n in
              re.findall(r'TL level t=(\d+) rms=(\d+) noise=(\d+)', log)]
    with wave.open(str(wav), 'rb') as audio:
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise ValueError('expected mono int16 fixture')
        rate = audio.getframerate()
        pcm = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(float)
    hop = round(rate*.01)
    frames = pcm[:len(pcm)//hop*hop].reshape(-1,hop)
    envelope = np.sqrt(np.maximum(0,np.mean(frames**2,axis=1)-np.mean(frames,axis=1)**2))
    axis = (np.arange(len(envelope))+.5)*hop/rate
    times, amplitude = zip(*levels)
    result = fit_levels(times,np.log1p(amplitude),axis,envelope,clock_offset)
    result.update(path=str(directory.resolve()), fixture=entry['fixture'], arm=entry.get('arm'),
                  original_onset_s=run['estimated_playback_sample_offset_s'],
                  clock_onset_s=clock_offset, clock_bridge_median_minus_p1_s=spread,
                  serial_sha256=hashlib.sha256(serial.read_bytes()).hexdigest(),
                  bench_sha256=hashlib.sha256(bench.read_bytes()).hexdigest(),
                  fixture_sha256=hashlib.sha256(wav.read_bytes()).hexdigest())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('statuses', nargs='+', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    report = {'captures':[], 'errors':[]}
    for status in args.statuses:
        for entry in json.loads(status.read_text()).get('runs',[]):
            if entry.get('state') != 'done':
                continue
            try:
                report['captures'].append(align_capture(entry,status.resolve().parent))
            except Exception as error:
                report['errors'].append({'path':entry.get('path'),'error':str(error)})
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2))
    print(f"Aligned {len(report['captures'])}; usable {sum(x['usable'] for x in report['captures'])}; errors {len(report['errors'])}")
    if report['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
