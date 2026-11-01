#!/usr/bin/env python3
"""Align private exact speaker PCM to clean reference; compare unchanged float/P4 embeddings.

Outputs numbers/IDs only. Raw PCM and all saved vectors remain under private/.
A source waveform match estimates audio timing independently of console clocks.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy import signal

import p4speakerpcm
import spkdiag
import spkreplay
from spkcuts import overlap

SR=16000


def bandpass(x):
    sos=signal.butter(4,[100,3500],btype='bandpass',fs=SR,output='sos')
    return signal.sosfiltfilt(sos,np.asarray(x,dtype=np.float64))


def align_waveform(reference_filtered,device,expected_start_s,search_s=1):
    """Gain/polarity-independent normalized correlation, discarding 40 ms edges.

    Match confidence is a fixed diagnostic threshold (0.25), not a learned
    detector. A confident peak must also lie away from the search edge.
    """
    n=len(device)
    if n<1600:return {'matched':False,'peak_correlation':0.0}
    trim=640;y=bandpass(device)[trim:-trim]
    lo=max(0,round((expected_start_s-search_s)*SR)+trim)
    hi=min(len(reference_filtered),round((expected_start_s+search_s)*SR)+n-trim)
    ref=reference_filtered[lo:hi];energy=float(np.dot(y,y))
    if len(ref)<len(y) or energy<=1e-15:return {'matched':False,'peak_correlation':0.0}
    corr=signal.correlate(ref,y,mode='valid',method='fft')
    sums=np.concatenate(([0.],np.cumsum(ref*ref)))
    powers=np.maximum(sums[len(y):]-sums[:-len(y)],0)
    norm=np.sqrt(energy*powers);scores=np.divide(corr,norm,out=np.zeros_like(corr),where=norm>1e-15)
    scores=np.clip(scores,-1,1);i=int(np.argmax(np.abs(scores)));peak=abs(float(scores[i]))
    others=np.abs(scores).copy();others[max(0,i-800):min(len(others),i+801)]=0
    runner=float(np.max(others));at_edge=i<160 or i>len(scores)-161
    start=(lo+i-trim)/SR
    return {'matched':bool(peak>=.25 and not at_edge),'peak_correlation':peak,
            'runner_up_outside_50ms':runner,'peak_margin':peak-runner,'at_search_edge':bool(at_edge),
            'polarity':1 if scores[i]>=0 else -1,'matched_model_start_s':start,
            'offset_from_predicted_ms':1000*(start-expected_start_s)}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('captures');ap.add_argument('session');ap.add_argument('output')
    a=ap.parse_args();root=Path(a.captures);out=Path(a.output)
    if 'private' not in root.parts or 'private' not in out.parts:ap.error('private paths required')
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    own=json.loads((root/'pcm-ownership.json').read_text());meta,analysis,manifest,pipe,rows=spkdiag.phrase_rows(a.session,32000)
    by_seq={r['seq']:r for r in rows};rate,pcm=spkreplay.read_wav(spkreplay.playlist_wav(meta['manifest'],manifest))
    reference=np.asarray(pcm,dtype=np.float64)
    if rate!=SR:
        g=math.gcd(rate,SR);reference=signal.resample_poly(reference,SR//g,rate//g)
    reference=np.clip(np.rint(reference),-32768,32767)/32768.;filtered=bandpass(reference)
    embed=spkreplay.model_embedder();records=[];vectors={}
    for entry in own['files']:
        raw=(root/f'capture-seq{entry["seq"]}.bin').read_bytes()
        if raw==p4speakerpcm.arm_bytes(entry['seq'],bytes.fromhex(entry['nonce'])):continue
        packet=p4speakerpcm.parse_capture(raw,entry['seq'],bytes.fromhex(entry['nonce']))
        seq=packet['seq'];r=by_seq.get(seq)
        if r is None:raise ValueError('capture has no analysed speaker row')
        if r['samples']!=packet['retained_samples']:raise ValueError('capture length disagrees with speaker log')
        crop=(packet['retained_samples']-packet['model_samples'])//2
        expected=r['span_play_s'][0]+crop/SR
        x=np.frombuffer(packet['pcm_bytes'],dtype='<i2').astype(np.float32)/32768.
        match=align_waveform(filtered,x,expected)
        p4=spkreplay.unit(packet['embedding']);mac=spkreplay.unit(embed(x));v={'p4':p4,'mac_mic':mac}
        result={'seq':seq,'ref':r['ref'],'clips':r['clips'],'retained_samples':packet['retained_samples'],
                'model_samples':packet['model_samples'],'predicted_model_start_s':expected,'alignment':match,
                'mic_rms_pcm':float(np.sqrt(np.mean((x*32768.)**2))),
                'mic_peak_pcm':float(np.max(np.abs(x*32768.))),
                'clipped_samples':int(np.count_nonzero(np.abs(x*32768.)>=32767)),
                'p4_vs_float_identical_mic_pcm_cosine':spkreplay.dot(p4,mac)}
        if match['matched']:
            start=round(match['matched_model_start_s']*SR);clean=reference[start:start+len(x)]
            if len(clean)!=len(x):raise ValueError('matched reference outside source')
            v['mac_clean']=spkreplay.unit(embed(clean))
            span=(start/SR,(start+len(x))/SR)
            candidates=[c for c in manifest['clips'] if c['speaker']==r['ref']]
            primary=max(candidates,key=lambda c:overlap(span,(c['speech_start_s'],c['speech_end_s'])),default=None)
            if primary:
                speech=(primary['speech_start_s'],primary['speech_end_s'])
                capture_start=span[0]-crop/SR
                result.update(primary_clip=primary['i'],matched_model_span_s=list(span),
                              estimated_speech_span_s=list(speech),matched_capture_start_s=capture_start,
                              capture_onset_lost_ms=max(0,capture_start-speech[0])*1000,
                              model_onset_lost_ms=max(0,span[0]-speech[0])*1000,
                              model_end_lost_ms=max(0,speech[1]-span[1])*1000,
                              model_other_speaker_ids=sorted({str(c['speaker']) for c in manifest['clips']
                                 if c['speaker']!=r['ref'] and overlap(span,(c['speech_start_s'],c['speech_end_s']))>0}))
            result['float_mic_vs_aligned_clean_cosine']=spkreplay.dot(mac,v['mac_clean'])
        records.append(result);vectors[str(seq)]=v
        print(json.dumps(result),flush=True)
    pairs=[]
    for i,r in enumerate(records):
        for s in records[i+1:]:
            u,v=vectors[str(r['seq'])],vectors[str(s['seq'])]
            p={'seq_a':r['seq'],'seq_b':s['seq'],'ref_a':r['ref'],'ref_b':s['ref'],
               'same_reference':r['ref']==s['ref'],'p4_mic':spkreplay.dot(u['p4'],v['p4']),
               'float_mic':spkreplay.dot(u['mac_mic'],v['mac_mic'])}
            if 'mac_clean' in u and 'mac_clean' in v:p['float_aligned_clean']=spkreplay.dot(u['mac_clean'],v['mac_clean'])
            pairs.append(p)
    result={'session':Path(a.session).name,'records':records,'pairs':pairs,
            'speech_bounds':'energy_envelopes_not_phonetic_labels','search_s':1.0,'match_min_correlation':.25}
    (out/'results.json').write_text(json.dumps(result,indent=2));(out/'embeddings.json').write_text(json.dumps(vectors))
    print(json.dumps({'pairs':pairs}),flush=True)


if __name__=='__main__':main()
