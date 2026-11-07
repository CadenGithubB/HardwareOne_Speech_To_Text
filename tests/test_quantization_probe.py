#!/usr/bin/env python3
import sys
from pathlib import Path
import unittest
import torch
import numpy as np
from onnx import helper
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/stt_p4'))
sys.path.insert(0,str(ROOT/'tools/stt_train_15x5'))
from quantization_probe import Probe,operation
from output_quantization_sweep import quantize_logits


def tiny(mode):
    p=Probe.__new__(Probe);p.mode=mode;p.stats={};p.parameter_cache={}
    p.nodes=[helper.make_node('Conv',['input','weight'],['output'],name='/head/Conv')]
    p.params={'weight':torch.tensor([[[[.36]]]])};p.input='input';p.output='output'
    def cfg(key):return {'state':'ACTIVATED','dominator':key,'quant_min':-2,'quant_max':1,
                        'bit_width':2,'policy':{'PER_CHANNEL':False}}
    p.config={'configs':{'/head/Conv':{k:cfg(k) for k in ('input','weight','output')}},
              'values':{k:{'scale':.25,'zero_point':0} for k in ('input','weight','output')}}
    p.tensor_config={'output':cfg('output')};return p


class QuantizationTests(unittest.TestCase):
    def test_baseline_profile_and_pre_output(self):
        p=tiny('baseline');x=torch.tensor([[[[-1.0],[.5],[1.0]]]])
        out=p.run(x,True)
        qx=torch.clamp(torch.round(x/.25),-2,1)*.25
        pre=qx*.25
        torch.testing.assert_close(p.pre_output,pre)
        torch.testing.assert_close(out,torch.clamp(torch.round(pre/.25),-2,1)*.25)
        torch.testing.assert_close(p.float_output,x*.36)
        self.assertEqual(p.summary()['/head/Conv']['elements'],3)

    def test_parameter_and_activation_ablations_are_distinct(self):
        x=torch.ones(1,1,3,1)*.5
        p=tiny('parameters_float');p.run(x)
        torch.testing.assert_close(p.pre_output,torch.ones_like(x)*.25*.36)
        p=tiny('activations_float');out=p.run(x)
        torch.testing.assert_close(out,x*.25)
        for mode in ('float','head_float'):
            torch.testing.assert_close(tiny(mode).run(x),x*.36)

    def test_domain_promotion_changes_consumers_but_not_weights(self):
        p=tiny('baseline')
        cfg=dict(p.config['configs']['/head/Conv']['output'])
        p.config['configs']['consumer']={'output':cfg}
        changes=p.promote_activation_domains(['/head/Conv'])
        self.assertEqual(changes[0]['scale'],.25/128)
        self.assertEqual(cfg['bit_width'],16)
        self.assertEqual(p.config['configs']['/head/Conv']['weight']['bit_width'],2)
        self.assertEqual(p.config['values']['weight']['scale'],.25)
        out=p.run(torch.ones(1,1,1,1)*.5)
        torch.testing.assert_close(out,torch.ones_like(out)*.0625)
        with self.assertRaises(ValueError):p.promote_activation_domains(['missing'])

    def test_output_quantizer_rounding_and_saturation(self):
        x=np.array([-.375,-.125,.125,.375,-40,40],np.float32)
        np.testing.assert_array_equal(quantize_logits(x,.25),[-2,0,0,2,-128,127])
        with self.assertRaises(ValueError):quantize_logits(x,0)


if __name__=='__main__':unittest.main()
