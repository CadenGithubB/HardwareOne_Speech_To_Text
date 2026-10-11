#!/usr/bin/env python3
"""CPU-only real-weight ESP-DL export and paired float/quantized fixture check.

Outputs are private experiment artifacts. Calibration and evaluation initially
reuse two public clips: results are sanity checks, NOT held-out WER estimates.
--calib-stores adds seeded dev-store clips (never *-test stores) to the
calibration set only; the fixture cases, graph input shape and embedded test
values stay those of fixture 0. A non-pinned weights file is accepted only via
quartznet_graph.WEIGHTS_OVERRIDE_ENV. --frontend-checkpoint takes the portable
frontend's window/mel tensors from another (hash-pinned) checkpoint, e.g. the
deployed 5x5 one when exporting 15x5; by default they come from --checkpoint.
"""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
from pathlib import Path
import struct
import sys
import time
import numpy as np
import soundfile as sf
import torch
import random
from quartznet_graph import (QuartzNet, DEFAULT_CHECKPOINT, load_checkpoint, greedy,
                            word_errors, WEIGHTS_SHA256, CONFIG_SHA256, checkpoint_hashes,
                            WEIGHTS_OVERRIDE_ENV)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'speech_portable'))
from float_quartznet import Decoder, FIXTURES


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def record(path): return {'file': Path(path).name, 'bytes': Path(path).stat().st_size, 'sha256': sha(path)}


def metadata(path):
    from esp_ppq.parser.espdl import helper  # Registers generated FlatBuffers import path.
    from FlatBuffers.Dl.Model import Model, ModelT
    data = path.read_bytes()
    if data[:4] != b'EDL2' or struct.unpack_from('<II',data,4) != (0,len(data)-16):
        raise ValueError('Expected unencrypted EDL2 with bounded length')
    graph = ModelT.InitFromObj(Model.GetRootAs(data,16)).graph
    def tensor(v):
        t = v.valueInfoType.value
        return {'name': v.name.decode(), 'shape': [int(d.value.dimValue) for d in t.shape.dim],
                'dtype': int(t.elemType), 'exponents': [int(e) for e in v.exponents],
                'layout': v.docString.decode() if v.docString else ''}
    return {'inputs': [tensor(v) for v in graph.input], 'outputs': [tensor(v) for v in graph.output],
            'operators': dict(Counter(n.opType.decode() for n in graph.node)),
            'node_count': len(graph.node)}



def validate_embedded_values(path, case):
    """Prove fixture bytes use the same quantization/layout as ESPDL test data."""
    from esp_ppq.parser.espdl import helper
    from FlatBuffers.Dl.Model import Model, ModelT
    graph = ModelT.InitFromObj(Model.GetRootAs(path.read_bytes(),16)).graph
    result = {}
    for label, values in [('input',graph.testInputsValue),('output',graph.testOutputsValue)]:
        if len(values) != 1: raise ValueError('Expected one embedded '+label+' tensor')
        tensor = values[0]
        if list(tensor.dims) != case['runtime_'+label+'_shape']:
            raise ValueError('Embedded '+label+' shape mismatch')
        actual = (path.parent/case['files'][label]['file']).read_bytes()
        embedded = b''.join(bytes(chunk.bytes) for chunk in tensor.rawData)
        if embedded[:len(actual)] != actual or not 0 <= len(embedded)-len(actual) < 16:
            raise ValueError('Embedded '+label+' bytes disagree with host runtime fixture')
        result[label] = {'logical_bytes':len(actual),'aligned_bytes':len(embedded),'byte_exact':True}
    return result

def as_runtime(array, info):
    # PPQ executor and float model return NCHW; ESPDL convolution tensors use
    # NHWC. Refuse unknown layout/shape instead of silently assuming axes.
    expected = info['shape']
    if 'NHWC' in info['layout'] or (not info['layout'] and len(expected)==4 and expected[2]==1 and expected[3]==array.shape[1]):
        info['layout'] = 'NHWC; validated against exported dimensions and fixed channel/width contract'
        array = array.transpose(0,2,3,1)
    elif 'NCHW' in info['layout'] or (not info['layout'] and len(expected)==4 and expected[1]==array.shape[1] and expected[3]==1):
        info['layout'] = 'NCHW; validated against exported dimensions and fixed channel/width contract'
    else:
        raise ValueError('Unrecognized ESPDL tensor layout: '+str(info))
    dtype = info['dtype']
    if dtype == 1: return array.astype('<f4')
    if len(info['exponents']) != 1: raise ValueError('Expected per-tensor activation exponent')
    exponent = info['exponents'][0]
    limits = {3: (-128,127,np.int8), 5: (-32768,32767,np.dtype('<i2'))}
    if dtype not in limits: raise ValueError('Unhandled activation dtype: '+str(dtype))
    lo, hi, target = limits[dtype]
    # np.rint is nearest-even, matching the P4 quantizer. This also turns
    # PPQ's fake-quantized logits back into exact serialized integer values.
    return np.clip(np.rint(array / 2.0**exponent),lo,hi).astype(target)


def features(pcm, reference, state, mode):
    if mode == 'torch':
        x, length = reference.features(pcm.astype(np.float32)/32768.0)
        return x[:,:,:length,None].contiguous()
    from frontend.reference_frontend import features_pcm16
    rows = features_pcm16(pcm, state)
    if isinstance(rows, tuple): rows = rows[0]
    if isinstance(rows, torch.Tensor): rows = rows.numpy()
    rows = np.asarray(rows,dtype=np.float32)
    if rows.ndim != 2 or rows.shape[1] != 64 or not 1 <= len(rows) <= 3000:
        raise ValueError('Portable frontend must return exact [T,64], T<=3000')
    return torch.from_numpy(rows.T.copy())[None,:,:,None]


def calibration_clips(specs, seed, min_seconds, max_seconds):
    """Seeded [(store, index, int16 pcm)] from read-only dev stores."""
    sys.dont_write_bytecode = True  # leave no caches beside the training modules
    sys.path.insert(0, str(HERE.parent/'stt_train'))
    from data import Store
    clips = []
    for spec in specs:
        name, count = spec.rsplit(':',1); count = int(count)
        if name.endswith('-test') or 'test' in name.split('-'): raise ValueError('Test stores never calibrate: '+name)
        store = Store(name); order = list(range(len(store)))
        random.Random(f'{seed}:{name}').shuffle(order)
        chosen = [i for i in order if min_seconds*16000 <= store.lengths[i] <= max_seconds*16000][:count]
        if len(chosen) != count: raise ValueError('Too few calibration clips in '+name)
        for i in chosen:
            o, n = int(store.offsets[i]), int(store.lengths[i])
            clips.append((name, i, np.array(store.audio[o:o+n], dtype=np.int16)))
    return clips


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',type=Path,default=DEFAULT_CHECKPOINT)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--frontend',choices=['portable','torch'],default='portable')
    p.add_argument('--stage',choices=['c1','full'],default='full')
    p.add_argument('--quant-type',choices=['w8a8','w8a16','w16a16'],default='w8a8')
    p.add_argument('--calib-steps',type=int,default=8)
    p.add_argument('--threads',type=int,default=4)
    p.add_argument('--calib-stores',nargs='*',default=[],metavar='STORE:COUNT',
                   help='extra calibration clips from dev stores, e.g. ami-sdm-validation:20')
    p.add_argument('--calib-seed',type=int,default=2026)
    p.add_argument('--calib-min-seconds',type=float,default=2.0)
    p.add_argument('--calib-max-seconds',type=float,default=15.0)
    p.add_argument('--frontend-checkpoint',type=Path,default=None,
                   help='take preprocessor window/fb from this checkpoint (portable frontend only)')
    args=p.parse_args()
    if args.output.exists() and any(args.output.iterdir()): p.error('Use a new empty output directory')
    if args.calib_steps < 8: p.error('At least eight calibration passes required')
    args.output.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(args.threads); torch.manual_seed(1234); np.random.seed(1234)
    config,state=load_checkpoint(args.checkpoint)
    frontend_state=state; frontend_source=None
    if args.frontend_checkpoint is not None:
        if args.frontend!='portable': p.error('--frontend-checkpoint requires the portable frontend')
        _,other=load_checkpoint(args.frontend_checkpoint)
        keys=('preprocessor.featurizer.window','preprocessor.featurizer.fb')
        frontend_state={k:other[k] for k in keys}
        frontend_source={**checkpoint_hashes(args.frontend_checkpoint),'directory':str(args.frontend_checkpoint),
                         'max_abs_diff_vs_checkpoint':{k:float((other[k].double()-state[k].double()).abs().max()) for k in keys}}
        del other
    hashes=checkpoint_hashes(args.checkpoint)
    pinned=hashes['weights_sha256']==WEIGHTS_SHA256
    # The independent float decoder pins the original weights; it is only a
    # cross-check (and the 'torch' frontend) for the pinned checkpoint.
    if not pinned and args.frontend=='torch': p.error('Torch frontend requires the pinned weights')
    full=QuartzNet(config,state).eval(); reference=Decoder(args.checkpoint) if pinned else None
    vocabulary=config['decoder']['params']['vocabulary']
    transcripts=dict(line.split(' ',1) for line in (args.checkpoint/'fixtures/trans.txt').read_text().splitlines() if line)
    cases=[]
    with torch.inference_mode():
        for fixture in FIXTURES[:2]:
            path=args.checkpoint/'fixtures'/fixture['name']
            if sha(path) != fixture['sha256']: raise ValueError('Fixture hash mismatch')
            pcm,rate=sf.read(path,dtype='int16')
            if rate != 16000 or pcm.ndim != 1: raise ValueError('Expected16k monoPCM')
            x=features(pcm,reference,frontend_state,args.frontend)
            baseline=full(x)
            item={'fixture':path.name,'wav_sha256':sha(path),'samples':len(pcm),'feature_frames':x.shape[2],
                  'reference':transcripts[path.name].lower(),'float_text':greedy(baseline,vocabulary),
                  'torch_original_text':reference.decode(pcm.astype(np.float32)/32768.0) if reference else None}
            item['float_word_errors']=word_errors(item['reference'],item['float_text'])
            if args.stage=='c1': x=full.input_to_stage(x,6)
            item['_x']=x; cases.append(item)
    extra=[]
    if args.calib_stores:
        if args.stage!='full': p.error('Store calibration is only defined for the full graph')
        with torch.inference_mode():
            for name,index,pcm in calibration_clips(args.calib_stores,args.calib_seed,
                                                     args.calib_min_seconds,args.calib_max_seconds):
                x=features(pcm,reference,frontend_state,args.frontend)
                extra.append(({'store':name,'index':index,'samples':len(pcm),'feature_frames':x.shape[2],
                               'pcm_sha256':hashlib.sha256(pcm.tobytes()).hexdigest()},x))
    calibration=[c['_x'] for c in cases]+[x for _,x in extra]
    calib_steps=max(args.calib_steps,len(calibration))
    model=full.blocks[6] if args.stage=='c1' else full
    from esp_ppq.api import espdl_quantize_torch
    from esp_ppq import TorchExecutor
    export=args.output/'quartznet.espdl'
    started=time.perf_counter()
    # Repeated passes only stabilize statistics; report the two unique clips.
    graph=espdl_quantize_torch(model=model,espdl_export_file=str(export),
        calib_dataloader=calibration,calib_steps=calib_steps,
        input_shape=list(cases[0]['_x'].shape),inputs=[cases[0]['_x']],
        target='esp32p4',quant_type=args.quant_type,device='cpu',error_report=False,
        export_test_values=True,verbose=0)
    info=metadata(export)
    if set(info['operators'])-{'Conv','Add','Relu','Transpose','QuantizeLinear','DequantizeLinear','RequantizeLinear'}:
        raise ValueError('Unexpected exported operators: '+str(info['operators']))
    executor=TorchExecutor(graph=graph,device='cpu')
    for index,item in enumerate(cases):
        x=item.pop('_x')
        with torch.inference_mode():
            quant=executor.forward(inputs=x)[0].detach()
            floating=model(x)
        item['quantized_max_abs_error']=float((quant-floating).abs().max())
        if args.stage=='full':
            item['quantized_text']=greedy(quant,vocabulary)
            item['quantized_word_errors']=word_errors(item['reference'],item['quantized_text'])
            item['float_quantized_text_equal']=item['float_text']==item['quantized_text']
        input_values=as_runtime(x.numpy(),info['inputs'][0])
        output_values=as_runtime(quant.numpy(),info['outputs'][0])
        item['runtime_input_shape']=list(input_values.shape);item['runtime_output_shape']=list(output_values.shape)
        files={}
        for kind,array in [('input',input_values),('output',output_values),
                           ('features',x.numpy().transpose(0,2,3,1).astype('<f4'))]:
            path=args.output/f'fixture-{index}-{kind}.bin';array.tofile(path);files[kind]=record(path)
        item['files']=files
    if export.stat().st_size > 24*1024*1024: raise ValueError('Export exceeds24MiB experiment model ceiling')
    embedded_values=validate_embedded_values(export,cases[0])
    frontend_contract=HERE/'frontend/frontend-contract.json'
    report={'scope':('Two-clip' if not extra else f'{len(calibration)}-clip')+' calibration; two-fixture evaluation sanity check; not held-out WER or device qualification',
            'checkpoint':{**hashes,'pinned_weights':pinned,
                          'weights_override_env':None if pinned else WEIGHTS_OVERRIDE_ENV},
            'stage':args.stage,'frontend':args.frontend,'quant_type':args.quant_type,'target':'esp32p4',
            'bn_epsilon':1e-3,'exact_valid_feature_length':True,'max_feature_frames':3000,
            'calibration_steps':calib_steps,'unique_calibration_clips':len(calibration),
            'calibration_stores':{'specs':args.calib_stores,'seed':args.calib_seed,
                                  'seconds':[args.calib_min_seconds,args.calib_max_seconds],
                                  'clips':[meta for meta,_ in extra]} if extra else None,
            'model':record(export),'runtime':info,'embedded_fixture0':embedded_values,
            'frontend_contract_sha256':sha(frontend_contract) if args.frontend=='portable' else None,'vocabulary':vocabulary,'ctc_blank':len(vocabulary),
            'host_export_seconds':time.perf_counter()-started,'cases':cases,
            'versions':{p:importlib.metadata.version(p) for p in ['torch','esp-ppq','onnx','onnxruntime','numpy']},
            'scripts':{n:sha(HERE/n) for n in ['quartznet_graph.py','export_quartznet.py'] + (['frontend/reference_frontend.py'] if args.frontend=='portable' else [])
                                                                        + (['../stt_train/data.py'] if extra else [])}}
    if frontend_source is not None: report['frontend_checkpoint']=frontend_source
    (args.output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
