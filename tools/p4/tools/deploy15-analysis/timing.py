"""Single-thread CPU time of the folded float graphs on one 8 s clip (first 8 s of fixture 1.wav)."""
import sys, os, time, json, statistics
sys.dont_write_bytecode=True
sys.path.insert(0,'experiments/stt_p4')
import torch, soundfile as sf
torch.set_num_threads(1)
from quartznet_graph import QuartzNet, load_checkpoint, DEFAULT_CHECKPOINT
from frontend.reference_frontend import features_pcm16
_,s5=load_checkpoint(DEFAULT_CHECKPOINT); fe={k:s5[k] for k in ('preprocessor.featurizer.window','preprocessor.featurizer.fb')}; del s5
pcm,_=sf.read(str(DEFAULT_CHECKPOINT/'fixtures/1.wav'),dtype='int16'); pcm=pcm[:128000]
x=torch.from_numpy(features_pcm16(pcm,fe).T.copy())[None,:,:,None]
res={'frames':x.shape[2]}
for name,ck,h in [('5x5_run2',os.path.join(os.environ.get('STT_ROOT', 'stt-data'), 'work/deploy/ckpt-run2'),'d6e7f963195194345e313d0a4ec6182967313a71acfff49a4622a42c968d9900'),
                  ('15x5_base',os.path.join(os.environ.get('STT_ROOT', 'stt-data'), 'work/deploy15/ckpt-base15'),'b2eb3ebc66e9e82829818131c4da02cf9e1109003c3d445b824d9489869143f9')]:
    os.environ['HW1_STT_ALLOW_WEIGHTS_SHA256']=h
    c,s=load_checkpoint(ck); m=QuartzNet(c,s).eval(); del s
    with torch.inference_mode():
        m(x); t=[]
        for _ in range(7):
            a=time.perf_counter(); m(x); t.append(time.perf_counter()-a)
    res[name]={'median_s':statistics.median(t),'min_s':min(t)}; del m
res['ratio_median']=res['15x5_base']['median_s']/res['5x5_run2']['median_s']
res['ratio_min']=res['15x5_base']['min_s']/res['5x5_run2']['min_s']
print(json.dumps(res,indent=1)); json.dump(res,open(sys.argv[1],'w'),indent=1)
