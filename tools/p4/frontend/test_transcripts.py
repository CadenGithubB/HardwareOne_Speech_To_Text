#!/usr/bin/env python3
"""Compare C++ features with the original Torch frontend on two public recordings."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import soundfile as sf
import torch
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'speech_portable'))
sys.path.insert(0,str(HERE.parent))
from float_quartznet import Decoder
from quartznet_graph import QuartzNet,load_checkpoint,greedy
from reference_frontend import features_pcm16

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint',type=Path,default=HERE.parents[1]/'speech_portable/private/stt-quartznet')
    parser.add_argument('--output',type=Path,default=HERE.parent/'private/frontend')
    args=parser.parse_args();torch.set_num_threads(4)
    config,state=load_checkpoint(args.checkpoint)
    graph=QuartzNet(config,state).eval();original=Decoder(args.checkpoint);results=[]
    with torch.inference_mode():
        for name in ['0','1']:
            wav=args.checkpoint/'fixtures'/(name+'.wav');pcm,rate=sf.read(wav,dtype='int16')
            if rate!=16000 or pcm.ndim!=1:raise ValueError('Unexpected fixture format')
            cpp=np.fromfile(args.output/(name+'.features.f32le'),dtype='<f4').reshape(-1,64)
            reference=features_pcm16(pcm,state)
            def infer(rows):return greedy(graph(torch.from_numpy(rows.T.copy())[None,:,:,None]),config['decoder']['params']['vocabulary'])
            texts={'original_torch':original.decode(pcm.astype(np.float32)/32768),'portable_reference':infer(reference),'portable_cpp':infer(cpp)}
            if len(set(texts.values()))!=1:raise AssertionError('Frontend transcript changed: '+str(texts))
            item={'fixture':name+'.wav','wav_sha256':hashlib.sha256(wav.read_bytes()).hexdigest(),'transcripts':texts,'all_equal':True}
            results.append(item);print(json.dumps(item),flush=True)
    report={'scope':'Two public clips, float graph, host only; not held-out accuracy or P4 timing','results':results}
    (args.output/'transcript-results.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
