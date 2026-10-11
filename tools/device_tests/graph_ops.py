import os
import re, collections, json
P=os.path.join(os.environ.get('STT_ROOT', 'stt-data'), 'work/deploy15/export-gen2-25397/quartznet.info')
lines=open(P).read().split('\n')
inits={}
for l in lines[7:276]:
    m=re.match(r'\s*%(\S+)\[(\w+), ([0-9x]+)\]',l)
    if m: inits[m.group(1)]=(m.group(2),m.group(3))
ops=[]
for i,l in enumerate(lines[276:478],start=277):
    m=re.match(r'\s*%(\S+) = (\w+)\[(.*?)\]\((.*)\)\s*$',l)
    if not m: continue
    out,op,attrs,args=m.groups()
    a=dict(re.findall(r"(\w+) = ('[^']*'|\[[^\]]*\]|[-\w.]+)",attrs))
    argl=[x.strip().lstrip('%') for x in args.split(',')]
    w=inits.get(argl[1]) if len(argl)>1 else None
    ops.append(dict(line=i,out=out,op=op,attrs=a,args=argl,w=w))
cnt=collections.Counter()
for o in ops:
    if o['op']=='Conv':
        a=o['attrs']; g=int(a['group']); ks=a['kernel_shape']; d=a['dilations']; s=a['strides']; act=a['activation']
        wshape=o['w'][1]
        kind='dw' if g>1 else ('pw' if ks=='[1, 1]' else 'conv')
        key=(kind,ks,d,s,act,wshape,len(o['args'])==3)
        cnt[key]+=1
    else:
        cnt[(o['op'],o['attrs'].get('lut',''))]+=1
for k,v in sorted(cnt.items(),key=str): print(v,k)

# ---- per-stage mapping against the 09-29 sttperf stage profile (timings only)
us=json.load(open(os.path.join(os.environ.get('STT_ROOT', 'stt-data'), 'work/deploy15/stage_us.json')))['us']
assert len(us)==len(ops)==201
def kind(o):
    if o['op']!='Conv': return o['op']
    a=o['attrs']; g=int(a['group']); ws=o['w'][1]
    if g>1:
        K=int(ws.split('x')[0]); C=int(ws.split('x')[2]); return f"dw k{K} c{C} d{a['dilations']} s{a['strides']}"
    cin,cout=map(int,ws.split('x')[2:4]); return f"pw {cin}x{cout} {a['activation']}"
def macs(o):
    if o['op']!='Conv': return 0
    ws=list(map(int,o['w'][1].split('x')))
    a=o['attrs']; g=int(a['group'])
    if g>1: return ws[0]*ws[2]
    return ws[2]*ws[3]
agg=collections.OrderedDict()
for i,o in enumerate(ops):
    k=kind(o); e=agg.setdefault(k,[0,0,0]); e[0]+=1; e[1]+=us[i]; e[2]+=macs(o)
tot=sum(us)
print('\nstage 197 =',kind(ops[197]),' stage 199 =',kind(ops[199]), 'stage 0=',kind(ops[0]))
print(f"{'type':34s} n  ms/seg  share  MAC/outframe")
for k,(n,u,m) in agg.items():
    print(f"{k:34s} {n:3d} {u/1000:7.1f} {100*u/tot:5.1f}% {m:10d}")
print('total ms/seg',tot/1000, 'total MAC/frame', sum(macs(o) for o in ops))
