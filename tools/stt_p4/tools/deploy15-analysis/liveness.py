"""Peak live int8 activation bytes per output frame from an exported quartznet.onnx
(execution order = ONNX node order; a tensor is live from producer to last consumer).
Input (64 ch at 2 frames per output frame) counted as 128 bytes/output frame."""
import sys, json, onnx
from onnx import numpy_helper
res={}
for path in sys.argv[1:]:
    g=onnx.load(path).graph
    init={i.name for i in g.initializer}
    shapes={}
    for i in g.initializer: pass
    ch={}  # channels per activation
    ch[g.input[0].name]=('in',64)
    w={i.name:numpy_helper.to_array(i).shape for i in g.initializer}
    for n in g.node:
        if n.op_type=='Conv': ch[n.output[0]]=('out',w[n.input[1]][0])
        else: ch[n.output[0]]=('out',ch[[x for x in n.input if x not in init][0]][1])
    def size(t): k,c=ch[t]; return c*(2 if k=='in' else 1)
    last={}
    for idx,n in enumerate(g.node):
        for x in n.input:
            if x in ch: last[x]=idx
    for o in g.output: last[o.name]=len(g.node)
    live={g.input[0].name}; peak=0; where=None
    for idx,n in enumerate(g.node):
        live|=set(n.output)
        cur=sum(size(t) for t in live)
        if cur>peak: peak,where=cur,(idx,n.op_type,n.name)
        live={t for t in live if last.get(t,-1)>idx}
    res[path]={'nodes':len(g.node),'peak_bytes_per_output_frame':peak,'at':where}
print(json.dumps(res,indent=1))
