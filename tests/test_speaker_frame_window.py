"""Window-shape change preserves deployed defaults and center/repeat semantics."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/stt_p4/speaker'))
import export_speaker as ex
import numpy as np
import torch
x=np.random.default_rng(17).normal(0,.02,80000).astype(np.float32)
assert torch.equal(ex.feats_for(x),ex.feats_for(x,300))
for frames in [300,400]:
 span=(frames-1)*160;start=(len(x)-span)//2
 expected=ex.proto.features(x[start:start+span])
 if expected.shape[-1]<frames:expected=expected[...,torch.arange(frames)%expected.shape[-1]]
 actual=ex.feats_for(x,frames)
 assert actual.shape==(1,1,40,frames)
 assert torch.equal(actual,expected[...,:frames])
 short=ex.feats_for(x[:1600],frames)
 assert short.shape==(1,1,40,frames) and torch.isfinite(short).all()
for invalid in [-4,0,3,399]:
 try:ex.feats_for(x,invalid)
 except ValueError:pass
 else:raise AssertionError(invalid)
print('speaker frame window checks passed')
