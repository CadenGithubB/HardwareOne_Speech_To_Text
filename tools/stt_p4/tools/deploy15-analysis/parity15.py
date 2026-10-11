"""15x5 folded Conv2D graph vs unfolded float reference (float_quartznet.Decoder ops)."""
import sys, os
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path('experiments/stt_p4'); sys.path.insert(0,str(HERE))
import numpy as np, soundfile as sf, torch, yaml
from quartznet_graph import QuartzNet, load_checkpoint, DEFAULT_CHECKPOINT
from test_graph import unfolded
from float_quartznet import Decoder
from frontend.reference_frontend import features_pcm16
torch.set_num_threads(4)
ck=Path(sys.argv[1]); config,state=load_checkpoint(ck); model=QuartzNet(config,state).eval()
ref=Decoder.__new__(Decoder); ref.cfg=config; ref.state=state; ref.used=set()
_,s5=load_checkpoint(DEFAULT_CHECKPOINT); fe={k:s5[k] for k in ('preprocessor.featurizer.window','preprocessor.featurizer.fb')}; del s5
print('blocks',len(config['encoder']['params']['jasper']),'params',sum(p.numel() for p in model.parameters()))
with torch.inference_mode():
    for name in ['0.wav','1.wav']:
        pcm,_=sf.read(ck/'fixtures'/name,dtype='int16'); rows=features_pcm16(pcm,fe); f=torch.from_numpy(rows.T.copy())[None]
        for L in sorted({3,31,f.shape[2]}):
            x=f[:,:,:L].contiguous(); e=unfolded(ref,x); a=model(x[:,:,:,None])[:,:,:,0]
            torch.testing.assert_close(a,e,rtol=5e-4,atol=5e-4); assert torch.equal(a.argmax(1),e.argmax(1))
            print(name,L,float((a-e).abs().max()))
unused={k for k in state if not k.startswith('preprocessor') and 'num_batches' not in k}-ref.used
print('unused state tensors:',sorted(unused)); assert not unused
print('PASS')
