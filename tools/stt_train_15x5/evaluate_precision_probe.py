#!/usr/bin/env python3
"""Decode an internal precision probe with the unchanged saved LM.

Requires unchanged final INT8 scale, checkpoint identity and decoder settings. Results remain
host counterfactual evidence, never candidate firmware qualification.
"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from diagnostics import atomic_json, error_counts, summarize, paired_changes, sha256
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'stt_train/lm'))
import hw1lm


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--probe',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--lm',type=Path,required=True)
    a=p.parse_args()
    destination=a.probe/'lm-results.json'
    if destination.exists():p.error('Refusing to overwrite results')
    report=json.loads((a.probe/'results.json').read_text())
    baseline=json.loads(a.baseline.read_text())
    provenance=baseline['provenance']
    plan=json.loads((a.probe/'plan.json').read_text())
    if plan['weights']['weights_sha256']!=provenance['weights_sha256']:
        raise ValueError('Acoustic checkpoint differs')
    lm=hw1lm.read_lm(a.lm)
    if baseline['provenance']['lm_sha256']!=lm.sha256:raise ValueError('LM identity differs')
    params={k:lm.params[k] for k in hw1lm.PARAM_NAMES}
    params['beam_width']=int(params['beam_width'])
    if params!=provenance['decoder_params']:raise ValueError('Decoder parameters differ')
    original={r['id']:r for r in baseline['records']}
    data=np.load(a.probe/'logits.npz');rows=report['records']
    if data['ids'].tolist()!=[r['id'] for r in rows]:raise ValueError('Logit ordering differs')
    offsets=data['offsets']; logits=data['post_output']
    if len(offsets)!=len(rows)+1 or offsets[0]!=0 or np.any(np.diff(offsets)<=0) or offsets[-1]!=len(logits):
        raise ValueError('Invalid utterance boundaries')
    q=np.rint(logits/.5)
    if np.any(q < -128) or np.any(q > 127) or not np.array_equal(q*.5,data['post_output']):
        raise ValueError('Expected unchanged final int8 scale 0.5')
    q=q.astype(np.int8);decoded=[];controls=[]
    for i,r in enumerate(rows):
        b=original[r['id']]
        if any(r[k]!=b[k] for k in ('ref','pcm_sha256')):raise ValueError('Input identity differs')
        h=hw1lm.decode_int8(q[data['offsets'][i]:data['offsets'][i+1]],1,lm,None,**params)
        decoded.append({**r,'hyp':h,**error_counts(r['ref'],h)})
        controls.append(b)
    if not report.get('activation_promotions') and report['mode']=='baseline':
        if any(r['hyp']!=b['hyp'] for r,b in zip(decoded,controls)):raise ValueError('LM baseline changed')
    atomic_json(destination,{'scope':'Host precision counterfactual, not exported/device evidence',
        'summary':summarize(decoded),'baseline_summary':summarize(controls),
        'paired':paired_changes(controls,decoded),'records':decoded,'decoder_params':params,
        'lm_sha256':lm.sha256,'probe_sha256':sha256(a.probe/'results.json'),
        'logits_sha256':sha256(a.probe/'logits.npz'),'script_sha256':sha256(__file__)})
    print(json.dumps(summarize(decoded)))

if __name__=='__main__':main()
