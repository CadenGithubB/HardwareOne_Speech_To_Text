#!/usr/bin/env python3
"""Frozen-model host sanity evaluation on new, file-only macOS speech.

No calibration or model export occurs. Reconstructs CPU fake quantization from
saved ONNX weights and PPQ scale metadata, first requiring byte-exact agreement
with both original PPQ output fixtures. This is not an acoustic/held-out-corpus
accuracy benchmark. macOS say writes WAV files and does not play audio.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import numpy as np
import onnx
from onnx import numpy_helper, helper
import soundfile as sf
import torch
import torch.nn.functional as F
from quartznet_graph import load_checkpoint, QuartzNet, greedy, word_errors
from export_quartznet import features, as_runtime, Decoder

HERE = Path(__file__).resolve().parent
SENTENCES = [
 ('Samantha', 'Please write a note that the next meeting starts at ten tomorrow morning.'),
 ('Daniel', 'The blue camera is on the desk beside the small black battery.'),
 ('Karen', 'I would like to test speech recognition without an internet connection.'),
 ('Samantha', 'Add milk and bread to my shopping list and remind me to call Alex.'),
]


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def normalize(s): return re.sub(r"[^a-z' ]",'',s.lower()).strip()


class FrozenQuantized:
    def __init__(self, directory, model):
        graph = onnx.load(directory/'quartznet.onnx').graph
        self.nodes = list(graph.node)
        self.params = {x.name:torch.from_numpy(numpy_helper.to_array(x).copy()) for x in graph.initializer}
        state = model.state_dict()
        if any(name not in state or not torch.equal(value,state[name]) for name,value in self.params.items()):
            raise ValueError('ONNX parameters differ from pinned folded checkpoint')
        self.config = json.loads((directory/'quartznet.json').read_text())
        self.output = graph.output[0].name
        self.input = graph.input[0].name
        self.tensor_config = {}
        for configs in self.config['configs'].values():
            for name, config in configs.items():
                # A produced activation's active configuration is authoritative;
                # consuming operations can additionally requantize to their own scales.
                if config['state'] in ('ACTIVATED','PASSIVE'):
                    self.tensor_config[name] = config

    def quant(self, x, config):
        if config is None: return x
        if config['state'] not in ('ACTIVATED','PASSIVE','OVERLAPPED'):
            raise ValueError('Unhandled quantization state')
        values = self.config['values'][str(config['dominator'])]
        scale = torch.tensor(values['scale'],dtype=x.dtype)
        zero = torch.tensor(values['zero_point'],dtype=x.dtype)
        if config['policy']['PER_CHANNEL']:
            shape = [len(scale)]+[1]*(x.ndim-1)
            scale=scale.reshape(shape);zero=zero.reshape(shape)
        return torch.clamp(torch.round(x/scale)+zero,config['quant_min'],config['quant_max']).sub(zero).mul(scale)

    @torch.inference_mode()
    def __call__(self, x):
        values = dict(self.params); values[self.input]=x
        for node in self.nodes:
            config = self.config['configs'].get(node.name,{})
            args = [self.quant(values[name],config.get(name)) for name in node.input]
            attrs = {a.name:helper.get_attribute_value(a) for a in node.attribute}
            if node.op_type=='Conv':
                pads=attrs.get('pads',[0,0,0,0])
                if pads[:2]!=pads[2:]: raise ValueError('Only symmetric convolution padding supported')
                out=F.conv2d(args[0],args[1],args[2] if len(args)>2 else None,
                             stride=attrs.get('strides',[1,1]),padding=pads[:2],
                             dilation=attrs.get('dilations',[1,1]),groups=attrs.get('group',1))
            elif node.op_type=='Add': out=args[0]+args[1]
            elif node.op_type=='Relu': out=F.relu(args[0])
            else: raise ValueError('Unhandled frozen graph operator '+node.op_type)
            name=node.output[0]
            # Fused Conv+Relu quantizes only at the Relu result. Its pre-ReLU
            # tensor has no entry in the exported config and stays floating here.
            values[name]=self.quant(out,config.get(name,self.tensor_config.get(name)))
        return values[self.output]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir',type=Path,default=HERE/'private/full-portable-v2')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()): parser.error('Use a new empty output directory')
    args.output.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(4)
    manifest=json.loads((args.model_dir/'manifest.json').read_text())
    if sha(args.model_dir/'quartznet.espdl')!=manifest['model']['sha256']: raise ValueError('Frozen model hash differs')
    config,state=load_checkpoint(); full=QuartzNet(config,state).eval()
    quantized=FrozenQuantized(args.model_dir,full); original=Decoder(HERE.parent/'speech_portable/private/stt-quartznet')
    vocab=config['decoder']['params']['vocabulary']
    parity=[]
    for case in manifest['cases']:
        rows=np.fromfile(args.model_dir/case['files']['features']['file'],dtype='<f4').reshape(case['runtime_input_shape'])
        x=torch.from_numpy(rows.transpose(0,3,1,2).copy())
        values=as_runtime(quantized(x).numpy(),manifest['runtime']['outputs'][0])
        expected=(args.model_dir/case['files']['output']['file']).read_bytes()
        if values.tobytes()!=expected:
            other=np.frombuffer(expected,dtype=np.int8).reshape(values.shape)
            raise ValueError(f"Frozen-scale reconstruction mismatch: {np.count_nonzero(values!=other)} values; max {np.abs(values.astype(int)-other).max()}")
        parity.append({'fixture':case['fixture'],'output_byte_exact':True,'sha256':hashlib.sha256(expected).hexdigest()})
    results=[]
    for index,(voice,text) in enumerate(SENTENCES):
        path=args.output/f'heldout-{index}-{voice.lower()}.wav'
        command=['/usr/bin/say','-v',voice,'-r','150','--file-format=WAVE','--data-format=LEI16@16000','-o',str(path),text]
        subprocess.run(command,check=True)
        pcm,rate=sf.read(path,dtype='int16')
        if rate!=16000 or pcm.ndim!=1 or not 320<=len(pcm)<=480000: raise ValueError('Invalid generated PCM')
        x=features(pcm,original,state,'portable')
        with torch.inference_mode():
            floating=greedy(full(x),vocab); quant=greedy(quantized(x),vocab)
        baseline=original.decode(pcm.astype(np.float32)/32768.0)
        reference=normalize(text)
        pcm.tofile(path.with_suffix('.pcm'))
        results.append({'file':path.name,'voice':voice,'words_per_minute':150,'reference':reference,
            'wav_sha256':sha(path),'pcm_sha256':sha(path.with_suffix('.pcm')),'samples':len(pcm),'seconds':len(pcm)/16000,
            'feature_frames':x.shape[2],'original_float':baseline,'portable_float':floating,'frozen_int8':quant,
            'word_count':len(reference.split()),'original_float_word_errors':word_errors(reference,baseline),
            'portable_float_word_errors':word_errors(reference,floating),'frozen_int8_word_errors':word_errors(reference,quant)})
    report={'scope':'Four synthetic sentences excluded from calibration; file-only macOS voices, no microphone/acoustic/device evidence.',
        'model_sha256':manifest['model']['sha256'],'frontend_sha256':manifest['frontend_contract_sha256'],
        'onnx_sha256':sha(args.model_dir/'quartznet.onnx'),'quantization_metadata_sha256':sha(args.model_dir/'quartznet.json'),
        'method':'Frozen ONNX float weights plus exported PPQ scales, nearest-even CPU fake quantization; no calibration performed.',
        'macos':platform.mac_ver()[0],'script_sha256':sha(__file__),'frozen_fixture_parity':parity,'cases':results}
    (args.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
