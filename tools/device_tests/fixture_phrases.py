# Rough phrase-count model of the proposed replay fixture (lengths only, no text).
# Simplified segmenter: phrase opens 0.3 s before speech, closes at
# max(speech_end+0.6, open+4.0) if the next speech starts later; 20 s cap.
# Clip-internal pauses are ignored, so counts are a lower bound for long clips.
import os
import json, random, statistics as st
S=os.path.join(os.environ.get('STT_ROOT', 'stt-data'), 'stores/')
def lens(name):
    d=json.load(open(S+name+'/index.json')); L=[l/16000 for l in d['lengths']]
    o=list(range(len(L))); random.Random(0).shuffle(o); return [L[i] for i in o]
def partA(budget=130):
    pools=[iter([x for x in lens(n) if x>=4.0]) for n in ('librispeech-dev-clean-g2','peoples-dev-g2','voxpopuli-dev-g2')]
    out=[];t=0;k=0
    while t<budget:
        x=next(pools[k%3]);k+=1;out.append(x);t+=x
    return out
def partB(budget=80, consecutive=False):
    L=json.load(open(S+'ami-ihm-validation-g2/index.json'))['lengths']; L=[l/16000 for l in L]
    if not consecutive:
        o=list(range(len(L))); random.Random(0).shuffle(o); L=[L[i] for i in o]
    out=[];t=0;i=0
    while t<budget: out.append(L[i]); t+=L[i]; i+=1
    return out
def phrases(clips, gaps, rng):
    # build speech intervals
    t=8.0; iv=[]
    for c,(lo,hi) in zip(clips,gaps):
        iv.append((t,t+c)); t+=c+rng.uniform(lo,hi)
    ph=[]; i=0
    while i<len(iv):
        op=iv[i][0]-0.3; end=iv[i][1]; j=i
        while True:
            if end-op>=20: # hard cut (approx at cap)
                ph.append(20.0); op=op+20; 
                if end-op<=0: break
                continue
            close=max(end+0.6, op+4.0)
            if j+1<len(iv) and iv[j+1][0]<close:
                j+=1; end=iv[j][1]; continue
            ph.append(round(close-op,2)); break
        i=j+1
    return ph
rng=random.Random(1)
A=partA(); 
for cons in (False,True):
    B=partB(consecutive=cons)
    pa=phrases(A,[(0.8,1.5)]*len(A),rng); pb=phrases(B,[(0.3,1.5)]*len(B),rng)
    allp=pa+pb
    bins={'4.0':sum(1 for x in allp if x<=4.01),'4-6':sum(1 for x in allp if 4.01<x<=6),'6-10':sum(1 for x in allp if 6<x<=10),'>10':sum(1 for x in allp if x>10)}
    print(f'AMI consecutive={cons}: partA clips={len(A)} phrases={len(pa)}; partB clips={len(B)} phrases={len(pb)}; total={len(allp)}; bins={bins}')
    print('   partB phrase lengths median', st.median(pb))
