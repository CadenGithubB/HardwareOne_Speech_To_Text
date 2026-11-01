#!/usr/bin/env python3
"""Audit captured, retained and model-selected spans against playlist speech envelopes.

Numbers and IDs only. Speech envelopes are energy estimates from the manifest,
not human phonetic boundaries or a detector of background voices inside a clip.
No audio, transcripts, firmware changes or playback are needed.
"""
import argparse
import json
from pathlib import Path
import statistics

import spkdiag
from spkreplay import SR, session_span


def overlap(a,b):
    return max(0.0,min(a[1],b[1])-max(a[0],b[0]))


def union_length(intervals):
    total=0.0;end=None
    for a,b in sorted(intervals):
        if b<=a:continue
        if end is None or a>end:total+=b-a
        elif b>end:total+=b-end
        end=max(end if end is not None else b,b)
    return total


def geometry(row,clips,window_samples=47840):
    capture=tuple(row['span_play_s']);retained=session_span(row);n=row['samples']
    offset=max(0,(n-window_samples)//2)
    window=(retained[0]+offset/SR,retained[0]+(offset+min(n,window_samples))/SR)
    ref=row.get('ref');same=[c for c in clips if c['speaker']==ref]
    primary=max(same,key=lambda c:overlap(capture,(c['start_s'],c['end_s'])),default=None)
    amounts={};inside=[];clip_ids=[]
    for c in clips:
        speech=(c['speech_start_s'],c['speech_end_s']);v=overlap(window,speech)
        if v>1e-9:
            key=str(c['speaker']);amounts[key]=amounts.get(key,0)+v*1000;clip_ids.append(c['i'])
            inside.append((max(window[0],speech[0]),min(window[1],speech[1])))
    out={'captured_span_s':list(capture),'retained_span_s':list(retained),'model_span_s':list(window),
         'speaker_samples':n,'model_samples':min(n,window_samples),'center_crop_offset_samples':offset,
         'discarded_capture_tail_ms':round(max(0,capture[1]-retained[1])*1000,3),
         'speech_envelope_ms_by_speaker':{k:round(v,3) for k,v in amounts.items()},
         'speech_envelope_clip_ids':clip_ids,'window_mixed_by_manifest':len(amounts)>1,
         'other_speaker_ids':[k for k in amounts if k!=str(ref)],
         'outside_speech_envelopes_ms':round(((window[1]-window[0])-union_length(inside))*1000,3)}
    if primary is not None:
        a,b=primary['speech_start_s'],primary['speech_end_s'];duration=b-a
        lost=lambda start:1000*min(duration,max(0,start-a))
        out.update(primary_clip=primary['i'],primary_speech_span_s=[a,b],
                   capture_onset_lost_ms=round(lost(capture[0]),3),
                   retained_end_lost_ms=round(1000*min(duration,max(0,b-retained[1])),3),
                   model_onset_lost_ms=round(lost(window[0]),3),
                   model_end_lost_ms=round(1000*min(duration,max(0,b-window[1])),3),
                   capture_onset_lost_ms_shift_100=[round(lost(capture[0]+d),3) for d in (-.1,.1)])
    return out


def envelope_coverage(speech,spans):
    a,b=speech
    pieces=[(max(a,x),min(b,y)) for x,y in spans if min(b,y)>max(a,x)]
    covered=union_length(pieces)
    return {'gap_ms':round(1000*((b-a)-covered),3),
            'leading_gap_ms':round(1000*((min(x for x,y in pieces)-a) if pieces else b-a),3),
            'trailing_gap_ms':round(1000*((b-max(y for x,y in pieces)) if pieces else b-a),3)}


def audit(session,window_samples=47840,with_phrases=False):
    meta,analysis,manifest,pipeline,rows=spkdiag.phrase_rows(session,32000)
    out=[]
    for r in rows:
        if r['pipeline']!='labelled' or not r.get('span_play_s'):continue
        out.append({'seq':r['seq'],'ref':r['ref'],'spk':r['spk'],'reason':r.get('reason'),
                    'end_kind':r.get('end_kind'),'continuation':r.get('continuation'),
                    **geometry(r,manifest['clips'],window_samples)})
    capture_spans=[p['span_play_s'] for p in analysis['phrases'] if p.get('span_play_s')]
    coverage=[]
    for c in manifest['clips']:
        speech=(c['speech_start_s'],c['speech_end_s'])
        coverage.append({'clip':c['i'],'speaker':c['speaker'],
            'captured':envelope_coverage(speech,capture_spans),
            'retained_speaker':envelope_coverage(speech,[r['retained_span_s'] for r in out]),
            'model':envelope_coverage(speech,[r['model_span_s'] for r in out])})
    result={'session':Path(session).name,'phrases':len(out),'model_window_samples':window_samples,
            'speech_bounds':'manifest_energy_envelopes','alignment_delta_ms':analysis['alignment']['delta_ms'],
            'trimmed_capture_tails':sum(r['discarded_capture_tail_ms']>1 for r in out),
            'captured_clips_leading_gap_over_100ms':[r['clip'] for r in coverage if r['captured']['leading_gap_ms']>100],
            'model_windows_mixed':sum(r['window_mixed_by_manifest'] for r in out),
            'mixed_sequences':[r['seq'] for r in out if r['window_mixed_by_manifest']],
            'pause_noncontinuation_onset_lost_over_100ms':[r['seq'] for r in out
                if r.get('end_kind')==0 and not r.get('continuation') and r.get('capture_onset_lost_ms',0)>100],
            'model_outside_speech_envelopes_ms_median':round(statistics.median(
                r['outside_speech_envelopes_ms'] for r in out),3) if out else None}
    if with_phrases:
        result['phrase_geometry']=out
        result['clip_coverage']=coverage
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sessions',nargs='+')
    p.add_argument('--window-samples',type=int,default=47840);p.add_argument('--phrases',action='store_true');a=p.parse_args()
    if a.window_samples<=0:p.error('window size must be positive')
    print(json.dumps([audit(s,a.window_samples,a.phrases) for s in a.sessions],indent=2))


if __name__=='__main__':main()
