#!/usr/bin/env python3
"""Derive the frozen QuartzNet graph's minimal ESP-DL 3.3.12 requirements.

Reads actual EDL2 tensors/attributes and the pinned runtime's Conv selector.
No quantization, firmware build or device access. Time-length overrides change
neither channels nor filter signatures, so this applies to every valid T.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import yaml

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DEFAULT_DL=HERE.parent/'speech_portable/private/app-p4/managed_components/espressif__esp-dl'
OUTPUT=ROOT/'components/hardwareone/stt/quartznet.compile_req.yml'
PROVENANCE=HERE/'compile-requirements-provenance.json'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def shape(value):return [int(d.value.dimValue) for d in value.valueInfoType.value.shape.dim]

def attribute(attr):
    if attr.attrType==2:return int(attr.i.i)
    if attr.attrType==3:return bytes(attr.s).decode()
    if attr.attrType==7:return [int(x) for x in attr.ints]
    raise ValueError('Unsupported required attribute: '+attr.name.decode())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,default=HERE/'private/full-portable-v2/quartznet.espdl')
    parser.add_argument('--esp-dl',type=Path,default=DEFAULT_DL)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    dl=args.esp_dl
    if str(yaml.safe_load((dl/'idf_component.yml').read_text())['version'])!='3.3.12':
        raise ValueError('Only inspected ESP-DL3.3.12 selector is supported')
    model_sha=sha(args.model)
    identity=(ROOT/'components/hardwareone/stt/stt_model_identity.h').read_text()
    identity_raw=re.search(r'kRawSha\[32\]\s*=\s*\{([^}]+)\}',identity).group(1)
    if bytes(int(x,16) for x in re.findall(r'0x([0-9a-fA-F]{2})',identity_raw)).hex()!=model_sha:
        raise ValueError('Actual model differs from production runtime identity')
    from esp_ppq.parser.espdl import helper
    from FlatBuffers.Dl.Model import Model,ModelT
    raw=args.model.read_bytes()
    if raw[:4]!=b'EDL2' or struct.unpack_from('<II',raw,4)!=(0,len(raw)-16):
        raise ValueError('Expected bounded unencrypted EDL2')
    graph=ModelT.InitFromObj(Model.GetRootAs(raw,16)).graph
    shapes={v.name:shape(v) for v in [*graph.input,*graph.output,*graph.valueInfo]}
    tensors={t.name:t for t in graph.initializer}
    rules=yaml.safe_load((dl/'spec/select/Conv.yml').read_text())
    catalog=yaml.safe_load((dl/'spec/kernels.yml').read_text())
    graph_ops=sorted(set(n.opType.decode() for n in graph.node))
    if graph_ops!=['Add','Conv','Relu']:raise ValueError('Review changed graph operator set: '+str(graph_ops))
    # Model's virtual run overloads link TensorBase::assign, whose typed
    # conversion branches call requantize_linear even for an int8-only graph.
    # ESP-SR incidentally supplied this before; standalone local STT must own it.
    runtime_support_ops=['RequantizeLinear']
    ops=sorted(set(graph_ops+runtime_support_ops))
    spec=importlib.util.spec_from_file_location('espdl_compile_finalize',dl/'cmake/compile_finalize.py')
    selector=importlib.util.module_from_spec(spec);spec.loader.exec_module(selector)
    kernels=set();nodes=[]
    for node in graph.node:
        if node.opType!=b'Conv':continue
        attr={a.name.decode():attribute(a) for a in node.attribute}
        inp=shapes[node.input[0]];out=shapes[node.output[0]];filt=tensors[node.input[1]]
        dimensions=[int(x) for x in filt.dims]
        if len(inp)!=4 or len(out)!=4 or len(dimensions)!=4 or attr['quant_type']!='S8':
            raise ValueError('Expected S8 NHWC Conv2D')
        kh,kw=dimensions[:2]
        if [kh,kw]!=attr['kernel_shape']:raise ValueError('Filter dimensions disagree with kernel_shape')
        group=attr['group'];cin=inp[-1];cout=out[-1]
        if group not in (1,cin):raise ValueError('Only regular/depthwise convolution supported')
        signature={'target':'pie_v2','dtype':'s8','group':'1' if group==1 else 'dw',
          'kshape':'11' if (kh,kw)==(1,1) else '33' if (kh,kw)==(3,3) else 'hw',
          'bias':len(node.input)==3,'act':attr['activation'].lower(),
          'per_ch':len(filt.exponents)>1,'c_align':cin%16==0 and cout%16==0}
        matches=[r for r in rules['rules'] if all(r.get(k)==v for k,v in signature.items())]
        if len(matches)!=1:raise ValueError('Ambiguous/missing Conv selector: '+str(signature))
        slots={slot:matches[0][slot] for slot in rules['slots']['pie_v2'] if matches[0].get(slot)}
        if not slots.get('body'):raise ValueError('No body kernel')
        kernels.update(slots.values())
        nodes.append({'node':node.name.decode(),'input_channels':cin,'output_channels':cout,
                      'filter_shape':dimensions,'signature':signature,
                      'packed_key':selector.pack_conv_rule(matches[0]),'slots':slots})
    if kernels-set(catalog['symbols']):raise ValueError('Selector names unknown kernel')
    req={'kernel_abi':int(catalog['kernel_abi']),'ops':ops,'kernels':sorted(kernels)}
    preface=('# Generated by experiments/stt_p4/generate_compile_requirements.py.\n'
      '# Frozen raw model SHA256: '+model_sha+'\n'
      '# ESP-DL3.3.12; actual Conv2D attributes, PIEv2 int8 channel alignment.\n'
      '# Runtime T may vary; channels/filter shapes and selected kernels do not.\n'
      '# RequantizeLinear supports Model/TensorBase::assign; it is not a graph node.\n')
    # ESP-DL's deliberately tiny YAML reader requires indented block lists.
    encoded=preface+'kernel_abi: '+str(req['kernel_abi'])+'\nops:\n'+''.join('  - '+x+'\n' for x in ops)
    encoded+='kernels:\n'+''.join('  - '+x+'\n' for x in req['kernels'])
    if args.check:
        if OUTPUT.read_text()!=encoded:raise ValueError('Committed compile requirements are stale')
    else:OUTPUT.write_text(encoded)
    # Verify standalone STT as well as the SR union, so another component
    # cannot accidentally supply a runtime dependency missing from our list.
    sr=dl.parent/'espressif__esp-sr/tool/esp-sr-req.yml'
    with tempfile.TemporaryDirectory(prefix='hw1-stt-compile-req-') as temp:
        tmp=Path(temp)
        for requirements in ([OUTPUT],[sr,OUTPUT]):
            command=[sys.executable,str(dl/'cmake/compile_finalize.py'),'--ops',str(dl/'spec/ops.yml'),
              '--kernels',str(dl/'spec/kernels.yml'),'--conv-yml',str(dl/'spec/select/Conv.yml'),
              '--target','esp32p4','--component-dir',str(dl),'--header',str(tmp/'config.h'),
              '--srcs',str(tmp/'srcs.cmake'),'--req',*[str(path) for path in requirements]]
            subprocess.run(command,check=True,text=True)
            header=(tmp/'config.h').read_text()
            if '#define DL_COMPILE_ALL 0' not in header:raise ValueError('Unexpected compile-all')
            merged_ops,merged_kernels,_=selector.union_reqs(requirements)
            for name in merged_ops:
                if '#define '+selector.macro_op(name)+' 1' not in header:raise ValueError('Missing merged op '+name)
            for name in merged_kernels:
                if '#define '+selector.macro_kernel(name)+' 1' not in header:raise ValueError('Missing merged kernel '+name)
    report={'schema':1,'esp_dl':'3.3.12','raw_model_sha256':model_sha,'model_nodes':len(graph.node),
      'operator_counts':dict(Counter(n.opType.decode() for n in graph.node)),
      'graph_ops':graph_ops,'runtime_support_ops':runtime_support_ops,
      'runtime_support_reason':'Model virtual run overloads link TensorBase::assign typed conversions requiring requantize_linear; independent of ESP-SR.',
      'kernel_abi':req['kernel_abi'],'kernels':req['kernels'],
      'source_sha256':{name:sha(dl/name) for name in ['spec/ops.yml','spec/kernels.yml','spec/select/Conv.yml',
        'cmake/compile_finalize.py','dl/base/dl_base_conv_select.hpp','dl/tensor/src/dl_tensor_base.cpp']},
      'requirements_sha256':hashlib.sha256(encoded.encode()).hexdigest(),
      'verification':'Official finalizer verifies standalone STT and SR+STT union with DL_COMPILE_ALL=0; all required op/kernel macros enabled.',
      'generator_sha256':sha(__file__),'convolutions':nodes}
    if args.check:
        if json.loads(PROVENANCE.read_text())!=report:raise ValueError('Compile requirement provenance is stale')
    else:PROVENANCE.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'ops':ops,'conv_nodes':len(nodes),'kernels':sorted(kernels),'check':args.check},indent=2))


if __name__=='__main__':main()
