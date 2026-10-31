#!/usr/bin/env python3
"""Fixed window-policy experiment and a speaker-ID-disjoint evaluation plan.

plan OLD_SETS OUT --root STT_ROOT: exclude all previously evaluated IDs, split
the eligible speakers in new stores before embedding. Artifacts stay private.
run PLAN OUT --partition development|final [--manifest M] [--session S]:
embed three fixed selection policies with the unchanged float model/frontend,
then replay the unchanged production clusterer at 0.6. Final evaluation must
only be opened after development supports a frozen candidate.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile
import numpy as np
import speaker_audio
import spkreplay
import spkrules

STORES=('librispeech-test-clean','librispeech-test-clean-g2','ami-ihm-test','ami-ihm-test-g2',
        'voxpopuli-validation','voxpopuli-validation-g2')
POLICIES=('center','activity','trim_activity')


def load_store(root,store):
    folder=Path(root)/'stores'/store
    return json.loads((folder/'index.json').read_text()),np.memmap(folder/'audio.bin',dtype='<i2',mode='r')


def plan(root,old,convs=30,turns=24):
    # Conservative exclusion across sources as well as within a source family.
    excluded={str(p['ref']) for s in old['sets'] for p in s['phrases'] if p['ref'] is not None}
    partitions={};counts={};by_family={}
    for base in STORES[::2]:
        pair=(base,base+'-g2');metas=[];eligible=[]
        for store in pair:
            d=json.loads((Path(root)/'stores'/store/'index.json').read_text());metas.append(d)
            c=collections.Counter(str(s) for s,n in zip(d['speakers'],d['lengths']) if 16000<=n<=160000)
            eligible.append({s for s,n in c.items() if n>=turns//2+2}-excluded)
        if metas[0]['speakers']!=metas[1]['speakers'] or metas[0]['lengths']!=metas[1]['lengths']:
            raise ValueError('paired store indices differ; explicit pairing required')
        by_family[base]=eligible[0]&eligible[1]
    all_speakers=sorted(set().union(*by_family.values()),key=lambda s:hashlib.sha256((s+':20261031').encode()).hexdigest())
    global_dev=set(all_speakers[::2]);global_final=set(all_speakers[1::2])
    for base,eligible in by_family.items():
        pair=(base,base+'-g2')
        dev,final=sorted(eligible&global_dev),sorted(eligible&global_final)
        if min(len(dev),len(final))<4:
            raise ValueError('not enough disjoint speakers for two-to-four-speaker conversations')
        assert not set(dev)&set(final) and not (set(dev)|set(final))&excluded
        for store in pair:
            partitions[store]={'development':dev,'final':final}
            counts[store]={'development_speakers':len(dev),'final_speakers':len(final)}
    return {'version':1,'root':str(root),'stores':list(STORES),'partitions':partitions,'counts':counts,
            'excluded_id_count':len(excluded),'conversations_per_store':convs,'turns':turns,
            'seed':20261031,'policies':list(POLICIES),
            'warning':'IDs disjoint from prior experiments and across partitions; not a claim of unseen pretraining identities'}


def bootstrap(rows,rule,repeats=10000):
    # Each pair shares speakers/utterances across clean and simulated channels.
    strata=collections.defaultdict(lambda:collections.defaultdict(list))
    for r in rows:
        if r['group'].startswith('corpus:'):
            store,index=r['name'].rsplit('/',1)
            strata[store.removesuffix('-g2')][index].append(r)
    keys=('scored','labelled','right','split','merge')
    def metrics(c):
        n,l,right,split,merge=c
        return [100*l/n,100*right/l if l else None,100*split/n,100*merge/n]
    families=[]
    for blocks in strata.values():
        families.append([[[sum(r['counts'][p][k] for r in block) for k in keys]
                          for p in ('center',rule)] for block in blocks.values()])
    if not families:return None
    rng=random.Random(31);values=[[] for _ in range(4)]
    for _ in range(repeats):
        totals=[[0]*5,[0]*5]
        for family in families:
            for _ in family:
                pair=rng.choice(family)
                for side in (0,1):
                    for k in range(5):totals[side][k]+=pair[side][k]
        a,b=map(metrics,totals)
        for dest,x,y in zip(values,a,b):
            if x is not None and y is not None:dest.append(y-x)
    return {k: [round(sorted(v)[min(len(v)-1,int(len(v)*p))],3) for p in (.025,.975)] if v else None
            for k,v in zip(('coverage','accuracy_labelled','split_per_100','merge_per_100'),values)}


def run(p,partition,manifests=(),sessions=(),shuffles=200):
    sys.path.insert(0,str(spkreplay.SPEAKER_TOOLS))
    import export_speaker,torch
    torch.set_num_threads(2);model=export_speaker.proto.load_model()
    cache={};sets=[];selection=collections.defaultdict(collections.Counter)
    with tempfile.TemporaryDirectory(prefix='speaker-windows-') as work:
        native=speaker_audio.Native(work)
        def embed(x,group):
            pcm=speaker_audio.int16(x);out={}
            for policy,name in enumerate(POLICIES):
                chosen=native.select(pcm,policy);start,n=chosen['start'],chosen['samples']
                selected=pcm[start:start+n]
                digest=hashlib.sha256(selected.tobytes()).hexdigest()
                if digest not in cache:
                    with torch.inference_mode():
                        f=export_speaker.feats_for(selected.astype(np.float32)/32768)
                        e=model(f)[0].numpy().tolist()
                    cache[digest]=[round(v,6) for v in spkreplay.unit(e)]
                out[name]=cache[digest]
                c=selection[group+':'+name];c['phrases']+=1
                c['changed']+=(start,n)!=((max(0,len(pcm)-47840)//2),min(47840,len(pcm)))
                c['input_samples']+=len(pcm);c['retained_samples']+=n
                c['active_frames']+=chosen['active_frames'];c['frames']+=chosen['frames']
            return out
        def make(name,group,inputs):
            variants={k:[] for k in POLICIES}
            for pid,ref,mixed,samples,x in inputs:
                embeddings=embed(x,group)
                for key,e in embeddings.items():
                    variants[key].append({'id':pid,'ref':ref,'mixed':mixed,'samples':samples,'e':e})
            sets.append({'name':name,'group':group,'variants':variants})
        for manifest in manifests:
            m=json.loads(Path(manifest).read_text());rate,pcm=spkreplay.read_wav(spkreplay.playlist_wav(manifest,m))
            segs,_=spkreplay.segments(m,None,32000,.3,.5)
            make(Path(manifest).parent.name,'clean',[(s['id'],s['ref'],s['mixed'],s['samples'],
                 spkreplay.cut(rate,pcm,s['span'])) for s in segs])
        for session in sessions:
            mpath=json.loads((Path(session)/'session.json').read_text())['manifest'];m=json.loads(Path(mpath).read_text())
            rate,pcm=spkreplay.read_wav(spkreplay.playlist_wav(mpath,m));segs,_=spkreplay.segments(m,session,32000,0,0)
            make(Path(session).parent.name+'/'+Path(session).name,'session',[(s['id'],s['ref'],s['mixed'],s['samples'],
                 spkreplay.cut(rate,pcm,s['span'])) for s in segs])
        for store in p['stores']:
            d,a=load_store(p['root'],store);allowed=set(p['partitions'][store][partition]);filtered=dict(d)
            filtered['lengths']=[n if str(s) in allowed else 0 for s,n in zip(d['speakers'],d['lengths'])]
            convs=spkrules.corpus_conversations(filtered,p['conversations_per_store'],p['turns'],p['seed'])
            for k,conv in enumerate(convs):
                inputs=[]
                for speaker,i in conv:
                    off,n=d['offsets'][i],d['lengths'][i]
                    inputs.append((i,speaker,False,n+12800,np.asarray(a[off:off+n],dtype=np.float32)/32768))
                make(store+'/'+str(k),'corpus:'+store,inputs)
        totals=collections.defaultdict(lambda:collections.defaultdict(lambda:[spkrules.empty(),spkrules.empty()]))
        per=[];runner=spkrules.Runner(work);rule=spkrules.parse_rule('production',.6)
        for k,s in enumerate(sets):
            n=len(s['variants']['center']);orders=[list(range(n))];rng=random.Random(1000003+k)
            if not s['group'].startswith('corpus'):
                for _ in range(shuffles):o=list(range(n));rng.shuffle(o);orders.append(o)
            row={'name':s['name'],'group':s['group'],'counts':{},'scores':{}}
            for policy,ph in s['variants'].items():
                labels=runner.runs(ph,[(rule,o) for o in orders],32000)
                groups=[s['group'],'all']+(['corpus'] if s['group'].startswith('corpus') else [])
                for j,(order,lab) in enumerate(zip(orders,labels)):
                    metrics=spkrules.run_metrics(ph,order,lab)
                    for group in groups:
                        spkrules.add(totals[group][policy][0],metrics)
                        if j==0:spkrules.add(totals[group][policy][1],metrics)
                    if j==0:
                        row['counts'][policy]={key:metrics[key] for key in ('scored','labelled','right','split','merge')}
                        one=spkrules.empty();spkrules.add(one,metrics);row['scores'][policy]=spkrules.derive(one)
            per.append(row)
    groups={g:{k:{'all_orders':spkrules.derive(v[0]),'in_order':spkrules.derive(v[1])} for k,v in group.items()}
            for g,group in totals.items()}
    ci={key:bootstrap(per,key) for key in POLICIES[1:]}
    return {'partition':partition,'policies':list(POLICIES),'threshold':.6,'shuffles':shuffles,
            'set_counts':dict(collections.Counter(s['group'] for s in sets)),
            'phrase_count':sum(len(s['variants']['center']) for s in sets),'unique_embeddings':len(cache),
            'selection':dict(selection),'groups':groups,'per_set_in_order':per,'corpus_ci95_vs_center':ci},sets


def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    a=sub.add_parser('plan');a.add_argument('old');a.add_argument('out');a.add_argument('--root',required=True)
    a.add_argument('--convs',type=int,default=30);a.add_argument('--turns',type=int,default=24)
    a=sub.add_parser('run');a.add_argument('plan');a.add_argument('out');a.add_argument('--partition',choices=('development','final'),required=True)
    a.add_argument('--embeddings',required=True);a.add_argument('--manifest',action='append',default=[])
    a.add_argument('--session',action='append',default=[]);a.add_argument('--shuffles',type=int,default=200)
    a=ap.parse_args()
    if a.command=='plan':
        if a.convs<1 or a.turns<4:ap.error('need positive conversations and at least four turns')
        data=plan(a.root,json.loads(Path(a.old).read_text()),a.convs,a.turns)
        if Path(a.out).exists():raise SystemExit('refusing to overwrite a frozen plan')
        Path(a.out).write_text(json.dumps(data));print(json.dumps({'stores':data['counts'],'excluded_ids':data['excluded_id_count']}))
    else:
        if a.shuffles<0:ap.error('--shuffles must be nonnegative')
        if Path(a.out).exists() or Path(a.embeddings).exists():raise SystemExit('refusing to overwrite results')
        result,sets=run(json.loads(Path(a.plan).read_text()),a.partition,a.manifest,a.session,a.shuffles)
        Path(a.embeddings).write_text(json.dumps({'version':1,'sets':sets}))
        Path(a.out).write_text(json.dumps(result));print(json.dumps({'partition':a.partition,'sets':result['set_counts'],'phrases':result['phrase_count']}))


if __name__=='__main__':main()
