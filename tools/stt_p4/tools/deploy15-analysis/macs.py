"""MACs per 10 ms output-frame pair and folded parameter counts, 5x5 vs 15x5 (from the folded graph)."""
import os
import sys, json
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,'experiments/stt_p4')
import torch
from torch import nn
from quartznet_graph import QuartzNet, load_checkpoint
out={}
for name,ck in [('5x5_run2',os.path.join(os.environ.get('STT_ROOT', 'stt-data'), 'work/deploy/ckpt-run2')),('15x5_base',os.path.join(os.environ.get('STT_ROOT', 'stt-data'), 'work/deploy15/ckpt-base15'))]:
    import os
    os.environ['HW1_STT_ALLOW_WEIGHTS_SHA256']={'5x5_run2':'d6e7f963195194345e313d0a4ec6182967313a71acfff49a4622a42c968d9900','15x5_base':'b2eb3ebc66e9e82829818131c4da02cf9e1109003c3d445b824d9489869143f9'}[name]
    config,state=load_checkpoint(ck); m=QuartzNet(config,state); del state
    macs=0; convs=0
    for mod in m.modules():
        if isinstance(mod,nn.Conv2d):
            convs+=1; w=mod.weight
            # per output frame of the stride-2 graph (input frames = 2 per output frame for C1)
            macs+=w.shape[0]*w.shape[1]*w.shape[2]
    out[name]={'blocks':len(config['encoder']['params']['jasper']),'convs':convs,
               'params':sum(p.numel() for p in m.parameters()),'macs_per_output_frame':macs,
               'vocabulary':config['decoder']['params']['vocabulary']}
    del m
r=out['15x5_base']['macs_per_output_frame']/out['5x5_run2']['macs_per_output_frame']
print(json.dumps({k:{kk:vv for kk,vv in v.items() if kk!='vocabulary'} for k,v in out.items()},indent=1))
print('mac ratio 15x5/5x5',r)
print('vocab identical',out['15x5_base']['vocabulary']==out['5x5_run2']['vocabulary'],len(out['5x5_run2']['vocabulary']),repr(''.join(out['5x5_run2']['vocabulary'])))
json.dump({'models':out,'mac_ratio':r},open(sys.argv[1],'w'),indent=1)
