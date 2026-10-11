#!/usr/bin/env python3
"""Numerical folding/layout parity against the earlier independent float decoder."""
from pathlib import Path
import sys
import numpy as np
import soundfile as sf
import torch
from quartznet_graph import QuartzNet, load_checkpoint, DEFAULT_CHECKPOINT
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'speech_portable'))
from float_quartznet import Decoder
from frontend.reference_frontend import features_pcm16

@torch.inference_mode()
def unfolded(decoder,x):
    length=x.shape[2]
    for index,block in enumerate(decoder.cfg['encoder']['params']['jasper']):
        prefix=f'encoder.encoder.{index}'; residual,old=x,length
        separable=block.get('separable',False); width=5 if separable else 4
        for iteration in range(block['repeat']):
            offset=width*iteration
            x,length=decoder.conv(x,length,f'{prefix}.mconv.{offset}.conv',block['stride'][0],block['dilation'][0])
            if separable:x,length=decoder.conv(x,length,f'{prefix}.mconv.{offset+1}.conv')
            x=decoder.norm(x,f'{prefix}.mconv.{offset+(2 if separable else 1)}')
            if iteration+1<block['repeat']:x=torch.relu(x)
        if block.get('residual'):
            residual,_=decoder.conv(residual,old,prefix+'.res.0.0.conv')
            x=x+decoder.norm(residual,prefix+'.res.0.1')
        x=torch.relu(x)
    return decoder.conv(x,length,'decoder.decoder_layers.0')[0]

def main():
    torch.set_num_threads(4)
    config,state=load_checkpoint();model=QuartzNet(config,state).eval();reference=Decoder(DEFAULT_CHECKPOINT)
    with torch.inference_mode():
        for name in ['0.wav','1.wav']:
            pcm,rate=sf.read(DEFAULT_CHECKPOINT/'fixtures'/name,dtype='int16');assert rate==16000
            rows=features_pcm16(pcm,state);features=torch.from_numpy(rows.T.copy())[None]
            for length in sorted({3,31,features.shape[2]}):
                x=features[:,:,:length].contiguous();expected=unfolded(reference,x);actual=model(x[:,:,:,None])[:,:,:,0]
                torch.testing.assert_close(actual,expected,rtol=2e-4,atol=2e-4)
                assert actual.shape==expected.shape==(1,29,(length+1)//2)
                assert torch.equal(actual.argmax(1),expected.argmax(1))
                print(name,'T',length,'maximum_logit_difference',float((actual-expected).abs().max()))
    print('PASS: folded Conv2D graph preserves valid-length float logits and greedy tokens')

if __name__=='__main__':main()
