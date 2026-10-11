#!/usr/bin/env python3
"""Offline no-LM CTC prefix-beam diagnostic over existing frozen fixtures.

No model calibration, downloads, audio playback, or device access occurs.
Heldout synthetic sentences and calibration clips are reported separately.
"""
import argparse
import sys,json,hashlib,time,math,itertools,heapq
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
base=Path(__file__).resolve().parent;sys.path.insert(0,str(base))
from evaluate_heldout import FrozenQuantized,normalize
from quartznet_graph import load_checkpoint,QuartzNet,greedy,word_errors
from export_quartznet import features,as_runtime,Decoder
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
out=args.output
if out.exists() and any(out.iterdir()):parser.error('Use a new empty output directory')
out.mkdir(parents=True,exist_ok=True)
modeldir=base/'private/full-portable-v2';helddir=base/'private/heldout-tts-v1'
manifest=json.loads((modeldir/'manifest.json').read_text());baseline=json.loads((base/'heldout-provenance.json').read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(modeldir/'quartznet.espdl')==manifest['model']['sha256']==baseline['model_sha256']
assert sha(modeldir/'quartznet.onnx')==baseline['onnx_sha256']
assert sha(modeldir/'quartznet.json')==baseline['quantization_metadata_sha256']
torch.set_num_threads(4);config,state=load_checkpoint();full=QuartzNet(config,state).eval();quant=FrozenQuantized(modeldir,full)
original=Decoder(base.parent/'speech_portable/private/stt-quartznet')
vocab=config['decoder']['params']['vocabulary'];blank=len(vocab);neg=-math.inf

def add(a,b):
 if a==neg:return b
 if b==neg:return a
 if a<b:a,b=b,a
 return a+math.log1p(math.exp(b-a))

def collapse(ids,blank):
 result=[];prev=None
 for i in ids:
  if i!=prev and i!=blank:result.append(i)
  prev=i
 return tuple(result)

def beam(logp,width,blank):
 beams={(): (0.0,neg)}
 for row in logp:
  nxt={}
  def acc(prefix,index,value):
   if value==neg:return
   pair=nxt.setdefault(prefix,[neg,neg]);pair[index]=add(pair[index],value)
  for prefix,(pb,pnb) in beams.items():
   total=add(pb,pnb);acc(prefix,0,total+float(row[blank]))
   for token,p in enumerate(row):
    if token==blank:continue
    p=float(p)
    if prefix and token==prefix[-1]:
     acc(prefix,1,pnb+p);acc(prefix+(token,),1,pb+p)
    else:acc(prefix+(token,),1,total+p)
  beams=dict(heapq.nlargest(width,nxt.items(),key=lambda entry:(add(*entry[1]),entry[0])))
 return sorted(((prefix,add(*probs)) for prefix,probs in beams.items()),key=lambda entry:(entry[1],entry[0]),reverse=True)

for seed,frames in enumerate((1,2,4,5)):
 rng=np.random.default_rng(seed);p=rng.random((frames,3));p/=p.sum(1,keepdims=True);lp=np.log(p);exact={}
 for path in itertools.product(range(3),repeat=frames):
  prefix=collapse(path,2);score=sum(lp[t,c] for t,c in enumerate(path));exact[prefix]=add(exact.get(prefix,neg),score)
 measured=dict(beam(lp,512,2));assert exact.keys()==measured.keys();assert max(abs(exact[k]-measured[k]) for k in exact)<1e-12
print('Exhaustive decoder oracle passed',flush=True)
records=[];parity=[]
for index,case in enumerate(manifest['cases']):
 rows=np.fromfile(modeldir/case['files']['features']['file'],dtype='<f4').reshape(case['runtime_input_shape'])
 x=torch.from_numpy(rows.transpose(0,3,1,2).copy())
 with torch.inference_mode(): yq=quant(x);yf=full(x)
 actual=as_runtime(yq.numpy(),manifest['runtime']['outputs'][0]);expected=(modeldir/case['files']['output']['file']).read_bytes()
 assert actual.tobytes()==expected
 parity.append({'fixture':case['fixture'],'output_byte_exact':True,'sha256':hashlib.sha256(expected).hexdigest()})
 records.append((f'calibration-{index}',normalize(case['reference']),yf,yq,case['float_text'],case['quantized_text'],'calibration'))
for index,case in enumerate(baseline['cases']):
 wav=helddir/case['file'];pcmfile=wav.with_suffix('.pcm');assert sha(wav)==case['wav_sha256'] and sha(pcmfile)==case['pcm_sha256']
 pcm=np.fromfile(pcmfile,dtype='<i2');assert len(pcm)==case['samples']
 x=features(pcm,original,state,'portable')
 with torch.inference_mode(): yf=full(x);yq=quant(x)
 assert greedy(yf,vocab)==case['portable_float'];assert greedy(yq,vocab)==case['frozen_int8']
 records.append((f'heldout-{index}',case['reference'],yf,yq,case['portable_float'],case['frozen_int8'],'heldout'))
print('Frozen fixture parity and heldout greedy replay passed',flush=True)

def target_score(logp,text):
 labels=torch.tensor([vocab.index(c) for c in text],dtype=torch.long)
 return -float(F.ctc_loss(torch.from_numpy(logp)[:,None,:],labels,torch.tensor([len(logp)]),torch.tensor([len(labels)]),blank=blank,reduction='sum'))

results=[];arrays={}
for name,reference,yf,yq,gf,gq,split in records:
 case={'case':name,'split':split,'reference':reference,'word_count':len(reference.split()),'outputs':{}}
 for kind,y,g in [('float',yf,gf),('int8',yq,gq)]:
  logits=y[0,:,:,0].T.numpy().astype(np.float64);lp=logits-logits.max(1,keepdims=True);lp-=np.log(np.exp(lp).sum(1,keepdims=True));arrays[name+'_'+kind]=logits.astype(np.float32)
  item={'frames':len(lp),'greedy':g,'greedy_word_errors':word_errors(reference,g),'beams':{}}
  for width in (1,4,8,16,32,64):
   start=time.perf_counter();n=beam(lp,width,blank);best=''.join(vocab[i] for i in n[0][0]);seconds=time.perf_counter()-start
   result={'text':best.strip(),'word_errors':word_errors(reference,best.strip()),'ctc_log_probability':n[0][1],'host_seconds':seconds}
   if width==64:
    result['top5']=[{'text':''.join(vocab[i] for i in p).strip(),'log_probability':score} for p,score in n[:5]]
    result['greedy_target_log_probability']=target_score(lp,g)
    result['reference_target_log_probability']=target_score(lp,reference)
    result['best_exact_log_probability']=target_score(lp,best)
    assert result['best_exact_log_probability']+1e-7>=n[0][1]
   item['beams'][str(width)]=result
  case['outputs'][kind]=item
  print(name,kind,'greedy',repr(g),'beam64',repr(item['beams']['64']['text']),'errors',item['greedy_word_errors'],item['beams']['64']['word_errors'],flush=True)
 results.append(case)
np.savez(out/'logits.npz',**arrays)
report={'scope':'Offline decoder diagnostic on existing saved audio; four synthetic heldout sentences (50 words) plus two calibration clips reported separately. No tuning, new audio, model change, language model, dictionary, token pruning or device execution.',
 'model_sha256':baseline['model_sha256'],'frontend_sha256':baseline['frontend_sha256'],'onnx_sha256':baseline['onnx_sha256'],'quantization_metadata_sha256':baseline['quantization_metadata_sha256'],
 'input_provenance_sha256':sha(base/'heldout-provenance.json'),'logits_sha256':sha(out/'logits.npz'),'diagnostic_script_sha256':sha(__file__),'blank':blank,'vocabulary':vocab,
 'method':'Existing FrozenQuantized reconstruction, exact original PPQ fixture parity and heldout greedy replay. Log-domain CTC prefix beam, all29classes, no LM/lengthbonus; blank/nonblank prefix state. Four exhaustive3-class test cases agree to1e-12. Exact reference/hypothesis CTC marginals use torch.ctc_loss.',
 'frozen_fixture_parity':parity,'cases':results,'aggregate':{}}
for split in ('heldout','calibration'):
 cases=[r for r in results if r['split']==split];data={'words':sum(r['word_count'] for r in cases),'cases':len(cases)}
 for kind in ('float','int8'):
  data[kind]={'greedy_word_errors':sum(r['outputs'][kind]['greedy_word_errors'] for r in cases),'beam_word_errors':{str(w):sum(r['outputs'][kind]['beams'][str(w)]['word_errors'] for r in cases) for w in (1,4,8,16,32,64)}}
 report['aggregate'][split]=data
(out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report['aggregate'],indent=2),flush=True);print('REPORT',out/'results.json',flush=True)
