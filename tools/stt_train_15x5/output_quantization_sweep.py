#!/usr/bin/env python3
"""Predeclared final-logit quantizer counterfactuals on saved development logits.

No layer weights, hidden activation scales or decoder parameters are changed.
These reports are NOT export manifests and cannot be presented as device evidence.
"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from diagnostics import atomic_json,error_counts,summarize,paired_changes,sha256
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'stt_train/lm'))
import hw1lm


def quantize_logits(logits,step):
    if not step>0:raise ValueError('step must be positive')
    rounded=np.rint(logits/step)
    return np.clip(rounded,-128,127).astype(np.int8)


def decode_float_greedy(logits):
    ids=logits.argmax(axis=-1);previous=None;chars=[]
    for i in ids:
        if i!=previous and i<hw1lm.BLANK:chars.append(hw1lm.VOCAB[i])
        previous=i
    return ''.join(chars).strip()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--lm',type=Path,required=True)
    p.add_argument('--baseline-logits',type=Path,required=True)
    p.add_argument('--baseline-float',type=Path,required=True)
    p.add_argument('--baseline-lm',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('New output directory required')
    a.output.mkdir(parents=True)
    data=np.load(a.profile/'logits.npz');profile=json.loads((a.profile/'results.json').read_text())
    if profile['mode']!='baseline':raise ValueError('Baseline graph pre-output logits required')
    rows=profile['records'];ids=data['ids'].tolist()
    original_logits=np.load(a.baseline_logits)
    if original_logits['ids'].tolist()!=ids or not np.array_equal(original_logits['offsets'],data['offsets']):
        raise ValueError('Original baseline logit identity/lengths differ')
    original_step=2.0**int(original_logits['exponent'])
    if original_step!=.5 or not np.array_equal(original_logits['q'].astype(np.float32)*original_step,data['post_output']):
        raise ValueError('Profile logits do not reproduce original int8 baseline byte-exactly')
    float_reference={r['id']:r['hyp'] for r in json.loads(a.baseline_float.read_text())['records']}
    for i,row in enumerate(rows):
        hypothesis=decode_float_greedy(data['float_output'][data['offsets'][i]:data['offsets'][i+1]])
        if hypothesis!=float_reference[row['id']]:raise ValueError('Profile float transcript changed')
    if ids!=[r['id'] for r in rows]:raise ValueError('Cached logit ordering differs')
    lm=hw1lm.read_lm(a.lm);params={k:lm.params[k] for k in hw1lm.PARAM_NAMES};params['beam_width']=int(params['beam_width'])
    baseline_lm=json.loads(a.baseline_lm.read_text())
    if baseline_lm['provenance']['lm_sha256']!=lm.sha256:raise ValueError('LM identity differs')
    # Fixed before inspecting sweep outcomes: original 0.5, then two finer power-of-two steps.
    steps=(0.5,0.25,0.125)
    results={};pre=data['pre_output'];post=data['post_output']
    if not np.array_equal(quantize_logits(pre,.5).astype(np.float32)*.5,post):
        raise ValueError('Original output rounding does not reproduce saved baseline logits')
    no_round=[]
    for i,row in enumerate(rows):
        logits=pre[data['offsets'][i]:data['offsets'][i+1]]
        hyp=decode_float_greedy(logits)
        no_round.append({**row,'hyp':hyp,**error_counts(row['ref'],hyp)})
    results['no_output_rounding']={'scope':'float output only; diagnostic, not int8-deployable',
        'greedy':summarize(no_round),'greedy_records':no_round,
        'paired_greedy_vs_baseline':paired_changes(rows,no_round)}
    for step in steps:
        q=quantize_logits(pre,step);greedy_rows=[];lm_rows=[]
        exponent=int(round(-np.log2(step)))
        for i,row in enumerate(rows):
            logits=q[data['offsets'][i]:data['offsets'][i+1]]
            g=decode_float_greedy(logits)
            h=hw1lm.decode_int8(logits,exponent,lm,None,**params)
            greedy_rows.append({**row,'hyp':g,**error_counts(row['ref'],g)})
            lm_rows.append({**row,'hyp':h,**error_counts(row['ref'],h)})
        if step==.5:
            if any(x['hyp']!=y['hyp'] for x,y in zip(rows,greedy_rows)):raise ValueError('Original greedy differs')
            originals={r['id']:r['hyp'] for r in baseline_lm['records']}
            if any(r['hyp']!=originals[r['id']] for r in lm_rows):raise ValueError('Original LM differs')
        rounded=np.rint(pre/step)
        results[str(step)]={'scope':'host output-scale counterfactual; no candidate export',
            'step':step,'clipped_low':int((rounded < -128).sum()),'clipped_high':int((rounded > 127).sum()),
            'values':pre.size,'argmax_changed_frames':int((q.argmax(1)!=pre.argmax(1)).sum()),
            'frames':len(pre),
            'top_score_tie_frames':int(((q==q.max(axis=1,keepdims=True)).sum(axis=1)>1).sum()),
            'blank_to_character_frames':int(((pre.argmax(1)==hw1lm.BLANK)&(q.argmax(1)!=hw1lm.BLANK)).sum()),
            'character_to_blank_frames':int(((pre.argmax(1)!=hw1lm.BLANK)&(q.argmax(1)==hw1lm.BLANK)).sum()),
            'greedy':summarize(greedy_rows),'lm':summarize(lm_rows),
            'greedy_records':greedy_rows,'lm_records':lm_rows,
            'paired_greedy_vs_baseline':paired_changes(rows,greedy_rows),
            'paired_lm_vs_baseline':paired_changes(baseline_lm['records'],lm_rows)}
        atomic_json(a.output/'progress.json',{'last_step':step,'greedy':results[str(step)]['greedy'],'lm':results[str(step)]['lm']})
        print(step,results[str(step)]['greedy']['errors'],results[str(step)]['lm']['errors'],flush=True)
    report={'scope':'Development-only host output-quantizer experiments; reserve untouched; not device qualification',
        'baseline_logits_byte_exact':True,'all_float_transcripts_match':True,
        'predeclared_steps':steps,'profile_sha256':sha256(a.profile/'results.json'),
        'logits_sha256':sha256(a.profile/'logits.npz'),'lm_file_sha256':sha256(a.lm),
        'decoder_params':params,'script_sha256':sha256(__file__),
        'pre_output_min':float(pre.min()),'pre_output_max':float(pre.max()),'arms':results}
    atomic_json(a.output/'results.json',report)
    print(json.dumps({k:{f:v[f] for f in ('greedy','lm') if f in v} for k,v in results.items()}),flush=True)


if __name__=='__main__':main()
