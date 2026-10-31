#!/usr/bin/env python3
"""Numerical audit of actual C++ vs Python speaker features on identical PCM.

Needs proto.py's model environment. Only numbers and case/store IDs are emitted;
PCM, features and embeddings are never printed. Quantized inference is NOT
implemented here, so this cannot isolate float/quantization or microphone loss.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import numpy as np
import speaker_audio
import spkreplay


def synthetic():
    rng=np.random.default_rng(71)
    for n in (257,16000,32000,47840,80000):
        yield f'noise-{n}',rng.integers(-6000,6000,n,dtype=np.int16)
    for amp in (1,6000,40000):
        x=amp*np.sin(2*np.pi*177*np.arange(32000)/16000)
        yield f'tone-{amp}',np.clip(np.rint(x),-32768,32767).astype(np.int16)
    yield 'silence',np.zeros(32000,dtype=np.int16)
    yield 'dc',np.full(32000,4000,dtype=np.int16)


def audit(cases):
    sys.path.insert(0,str(spkreplay.SPEAKER_TOOLS))
    import export_speaker
    import torch
    torch.set_num_threads(2)
    model=export_speaker.proto.load_model()
    rows=[]
    with tempfile.TemporaryDirectory(prefix='speaker-audit-') as work:
        native=speaker_audio.Native(work)
        for name,pcm in cases:
            a=native.features(pcm)
            b=export_speaker.feats_for(pcm.astype(np.float32)/32768).numpy()
            diff=a-b
            with torch.inference_mode():
                ea=np.asarray(spkreplay.unit(model(torch.from_numpy(a))[0].numpy()))
                eb=np.asarray(spkreplay.unit(model(torch.from_numpy(b))[0].numpy()))
            rows.append({'case':name,'samples':len(pcm),'max_abs_feature_error':float(np.max(np.abs(diff))),
                         'rms_feature_error':float(np.sqrt(np.mean(diff**2))),
                         'relative_l2_error':float(np.linalg.norm(diff)/max(np.linalg.norm(b),1e-12)),
                         'embedding_cosine':float(ea@eb)})
    return {'case_count':len(rows),'cases':rows,
            'max_abs_feature_error':max(r['max_abs_feature_error'] for r in rows),
            'max_rms_feature_error':max(r['rms_feature_error'] for r in rows),
            'min_embedding_cosine':min(r['embedding_cosine'] for r in rows),
            'scope':'same PCM, C++ vs Python features, same float model; no quantized or microphone inference'}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan',help='private spkwindows.py plan; uses development utterances only')
    ap.add_argument('--per-store',type=int,default=5)
    a=ap.parse_args()
    if a.per_store<1:ap.error('--per-store must be positive')
    cases=list(synthetic())
    if a.plan:
        p=json.loads(Path(a.plan).read_text())
        for store in p['stores']:
            root=Path(p['root'])/'stores'/store
            d=json.loads((root/'index.json').read_text());audio=np.memmap(root/'audio.bin',dtype='<i2',mode='r')
            allowed=set(p['partitions'][store]['development'])
            eligible=[];seen=set()
            for i,(s,n) in enumerate(zip(d['speakers'],d['lengths'])):
                if str(s) in allowed and str(s) not in seen and 16000<=n<=160000:
                    eligible.append(i);seen.add(str(s))
                    if len(eligible)>=a.per_store:break
            for i in eligible:
                off,n=d['offsets'][i],d['lengths'][i]
                cases.append((f'{store}:{i}',np.asarray(audio[off:off+n],dtype=np.int16)))
    print(json.dumps(audit(cases)))


if __name__=='__main__':
    main()
