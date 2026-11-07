#!/usr/bin/env python3
"""Read-only frozen-int8 diagnostics and explicitly non-deployable counterfactuals.

Profile local activation clipping/rounding plus propagated float-vs-int8 error.
Save pre-output-quantizer logits for fixed output-scale experiments without
re-running convolutions. Never uses a test store, recalibrates or exports firmware.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import numpy as np
import torch
import torch.nn.functional as F
from onnx import helper
from evaluate_heldout import FrozenQuantized
from quartznet_graph import QuartzNet, load_checkpoint, checkpoint_hashes, greedy
from export_quartznet import features, as_runtime

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'stt_train_15x5'))
from diagnostics import atomic_json,sha256,error_counts,summarize,digest


def operation(node,args):
    attrs={a.name:helper.get_attribute_value(a) for a in node.attribute}
    if node.op_type=='Conv':
        pads=attrs.get('pads',[0,0,0,0])
        if pads[:2]!=pads[2:]:raise ValueError('Asymmetric convolution')
        return F.conv2d(args[0],args[1],args[2] if len(args)>2 else None,
            stride=attrs.get('strides',[1,1]),padding=pads[:2],
            dilation=attrs.get('dilations',[1,1]),groups=attrs.get('group',1))
    if node.op_type=='Add':return args[0]+args[1]
    if node.op_type=='Relu':return F.relu(args[0])
    raise ValueError('Unsupported operator '+node.op_type)


class Probe(FrozenQuantized):
    def __init__(self,directory,model,mode='baseline'):
        super().__init__(directory,model)
        if mode not in ('baseline','float','parameters_float','activations_float','head_float'):
            raise ValueError('Unsupported mode')
        self.mode=mode
        self.stats={}
        self.pre_output=None
        self.float_output=None
        self.parameter_cache={}

    def promote_activation_domains(self, nodes):
        """Host sensitivity only: 16-bit range, 128x finer step, ~2x range.

        Promote every occurrence of the shared output quantizer domain so a
        consumer cannot immediately discard the extra precision. Weights remain
        unchanged; this is not a physical W8A16 kernel simulation or export.
        """
        selected = []
        for name in nodes:
            node = next((n for n in self.nodes if n.name == name), None)
            if node is None:
                raise ValueError('Unknown node: ' + name)
            tensor = node.output[0]
            cfg = self.config['configs'].get(name, {}).get(tensor, self.tensor_config.get(tensor))
            if cfg is None:
                raise ValueError('Node has no output quantizer: ' + name)
            selected.append(str(cfg['dominator']))
        domains = set(selected)
        occurrences = []
        for name, configs in self.config['configs'].items():
            for tensor, cfg in configs.items():
                if str(cfg['dominator']) in domains:
                    if tensor in self.params:
                        raise ValueError('Activation domain includes a parameter')
                    occurrences.append((name, tensor, cfg))
        changes = []
        for domain in sorted(domains):
            value = self.config['values'][domain]
            if np.asarray(value['scale']).size != 1 or np.any(np.asarray(value['zero_point']) != 0):
                raise ValueError('Expected symmetric scalar activation scale')
            old = float(np.asarray(value['scale']).item())
            value['scale'] = old / 128
            changes.append({'dominator': domain, 'original_scale': old, 'scale': old / 128,
                'occurrences': [{'node': n, 'tensor': t} for n,t,c in occurrences if str(c['dominator']) == domain]})
        for _, _, cfg in occurrences:
            cfg.update(bit_width=16, quant_min=-32768, quant_max=32767)
        return changes

    def selected_quant(self,x,config,node,tensor,parameter=False):
        bypass=(self.mode=='float' or (self.mode=='parameters_float' and parameter)
                or (self.mode=='activations_float' and not parameter)
                or (self.mode=='head_float' and node.startswith('/head/')))
        if bypass:return x
        if parameter:
            key=(node,tensor)
            if key not in self.parameter_cache:self.parameter_cache[key]=super().quant(x,config)
            return self.parameter_cache[key]
        return super().quant(x,config)

    @torch.inference_mode()
    def run(self,x,profile=False):
        values=dict(self.params);values[self.input]=x
        floats=dict(self.params);floats[self.input]=x
        for node in self.nodes:
            configs=self.config['configs'].get(node.name,{})
            args=[self.selected_quant(values[n],configs.get(n),node.name,n,n in self.params) for n in node.input]
            out=operation(node,args)
            name=node.output[0]
            cfg=configs.get(name,self.tensor_config.get(name))
            if name==self.output:self.pre_output=out.detach().clone()
            result=self.selected_quant(out,cfg,node.name,name)
            values[name]=result
            if profile:
                reference=operation(node,[floats[n] for n in node.input]);floats[name]=reference
                row=self.stats.setdefault(node.name,{'elements':0,'quantized_elements':0,'clipped_low':0,
                    'clipped_high':0,'local_error_sq':0.0,'propagated_error_sq':0.0,'reference_sq':0.0,
                    'local_max_abs':0.0,'propagated_max_abs':0.0,'op':node.op_type})
                delta=result-reference;local=result-out
                row['elements']+=result.numel()
                row['local_error_sq']+=float(local.double().square().sum())
                row['propagated_error_sq']+=float(delta.double().square().sum())
                row['reference_sq']+=float(reference.double().square().sum())
                row['local_max_abs']=max(row['local_max_abs'],float(local.abs().max()))
                row['propagated_max_abs']=max(row['propagated_max_abs'],float(delta.abs().max()))
                if cfg is not None:
                    info=self.config['values'][str(cfg['dominator'])]
                    scale=torch.as_tensor(info['scale'],dtype=out.dtype)
                    zero=torch.as_tensor(info['zero_point'],dtype=out.dtype)
                    if scale.numel()!=1:raise ValueError('Activation profiling requires scalar scale')
                    row['scale']=float(scale);row['bits']=cfg['bit_width']
                    rounded=torch.round(out/scale)+zero
                    row['clipped_low']+=int((rounded<cfg['quant_min']).sum())
                    row['clipped_high']+=int((rounded>cfg['quant_max']).sum())
                    row['quantized_elements']+=out.numel()
        self.float_output=floats[self.output] if profile else None
        return values[self.output]

    def summary(self):
        return {name:{**v,'local_rmse':(v['local_error_sq']/v['elements'])**.5,
            'propagated_relative_rmse':(v['propagated_error_sq']/max(v['reference_sq'],1e-30))**.5,
            'clipped_fraction':(v['clipped_low']+v['clipped_high'])/max(v['quantized_elements'],1)}
                for name,v in self.stats.items()}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--export',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True,help='Previously frozen int8 stage report')
    p.add_argument('--stores',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',choices=['baseline','float','parameters_float','activations_float','head_float'],default='baseline')
    p.add_argument('--speaker-count',type=int,default=0,help='0=all; otherwise fixed hash-ranked speaker subset')
    p.add_argument('--profile',action='store_true')
    p.add_argument('--activation-node',action='append',default=[],help='Promote shared output quantizer domain; host sensitivity only')
    p.add_argument('--threads',type=int,default=2)
    a=p.parse_args()
    if a.output.exists():p.error('Use a new output directory')
    a.output.mkdir(parents=True)
    torch.set_num_threads(a.threads)
    baseline=json.loads(a.baseline.read_text())
    if baseline['stage']!='int8':raise ValueError('Expected frozen-int8 baseline report')
    manifest=json.loads((a.export/'manifest.json').read_text())
    weights=checkpoint_hashes(a.checkpoint)
    if weights['weights_sha256']!=baseline['provenance']['weights_sha256'] or sha256(a.export/'quartznet.espdl')!=baseline['provenance']['espdl_sha256']:
        raise ValueError('Baseline provenance differs')
    config,state=load_checkpoint(a.checkpoint);model=QuartzNet(config,state).eval()
    control=FrozenQuantized(a.export,model);probe=Probe(a.export,model,a.mode)
    if a.activation_node and a.mode != 'baseline':p.error('Domain interventions require baseline mode')
    promotions=probe.promote_activation_domains(a.activation_node)
    parity=[]
    for case in manifest['cases']:
        data=np.fromfile(a.export/case['files']['features']['file'],dtype='<f4').reshape(case['runtime_input_shape'])
        x=torch.from_numpy(data.transpose(0,3,1,2).copy())
        original=control(x)
        if as_runtime(original.numpy(),dict(manifest['runtime']['outputs'][0])).tobytes()!=(a.export/case['files']['output']['file']).read_bytes():
            raise ValueError('Original frozen evaluator failed exported fixture')
        check=Probe(a.export,model)
        found=check.run(x,profile=True)
        torch.testing.assert_close(found,original,rtol=0,atol=0)
        with torch.inference_mode():floating=model(x)
        torch.testing.assert_close(check.float_output,floating,rtol=0,atol=0)
        parity.append(case['fixture'])
    rows=baseline['records']
    speakers=sorted({r['speaker'] for r in rows},key=lambda s:hashlib.sha256(('quant-probe-v1:'+s).encode()).hexdigest())
    selected=set(speakers[:a.speaker_count] if a.speaker_count else speakers)
    rows=[r for r in rows if r['speaker'] in selected]
    atomic_json(a.output/'plan.json',{'mode':a.mode,'selected_ids':[r['id'] for r in rows],
        'speaker_count':len(selected),'selection':'fixed hash rank, independent of recognition error',
        'scope':'Host-only diagnostic; not an exported or deployable model',
        'activation_promotions':promotions,'baseline_sha256':sha256(a.baseline),'scripts':{Path(__file__).name:sha256(__file__),
        'evaluate_heldout.py':sha256(HERE/'evaluate_heldout.py')},'weights':weights,'fixture_parity':parity})
    stores={};results=[];pre=[];post=[];float_logits=[];offsets=[0];started=time.time()
    vocabulary=config['decoder']['params']['vocabulary']
    for k,row in enumerate(rows):
        name,raw_index=row['id'].rsplit(':',1);i=int(raw_index)
        if 'test' in name.split('-'):raise ValueError('Reserved test store is forbidden')
        if name not in stores:
            idx=json.loads((a.stores/name/'index.json').read_text())
            stores[name]=(idx,np.memmap(a.stores/name/'audio.bin',dtype='<i2',mode='r'))
        idx,audio=stores[name];o,n=idx['offsets'][i],idx['lengths'][i]
        pcm=np.array(audio[o:o+n],dtype='<i2')
        if hashlib.sha256(pcm.tobytes()).hexdigest()!=row['pcm_sha256'] or idx['texts'][i]!=row['ref']:
            raise ValueError('Input identity changed')
        x=features(pcm,None,state,'portable')
        output=probe.run(x,profile=a.profile)
        hypothesis=greedy(output,vocabulary)
        if a.mode=='baseline' and not promotions and hypothesis!=row['hyp']:raise ValueError('Baseline transcript changed')
        results.append({**row,'hyp':hypothesis,**error_counts(row['ref'],hypothesis)})
        pre.append(probe.pre_output[0,:,:,0].T.numpy().copy())
        post.append(output[0,:,:,0].T.numpy().copy());offsets.append(offsets[-1]+len(pre[-1]))
        if a.profile:float_logits.append(probe.float_output[0,:,:,0].T.numpy().copy())
        if (k+1)%4==0 or k+1==len(rows):
            atomic_json(a.output/'progress.json',{'completed':k+1,'total':len(rows),'elapsed_s':time.time()-started})
            print(a.mode,k+1,len(rows),round(time.time()-started,1),flush=True)
    np.savez(a.output/'logits.npz',pre_output=np.concatenate(pre),post_output=np.concatenate(post),
        float_output=np.concatenate(float_logits) if float_logits else np.empty((0,29),np.float32),
        offsets=np.array(offsets),ids=np.array([r['id'] for r in rows]))
    report={'mode':a.mode,'activation_promotions':promotions,'scope':'Host-only diagnostic; no export/device qualification',
        'summary':summarize(results),'records':results,'layers':probe.summary(),
        'elapsed_s':time.time()-started,'fixture_parity':parity}
    atomic_json(a.output/'results.json',report)
    print(json.dumps(report['summary']),flush=True)


if __name__=='__main__':main()
