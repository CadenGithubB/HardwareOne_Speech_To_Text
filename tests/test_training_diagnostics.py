#!/usr/bin/env python3
"""Host checks for training integrity, comparison identity, and actual torch batching/state."""
import copy
import importlib.util
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/stt_train_15x5'))
from diagnostics import (atomic_json, audit_stores, effective_ids, inspect_store,
                         error_counts, paired_changes, summarize, sha256)
from compare_stages import stage_report, compare


def make_store(root, name, speakers=('a', 'b')):
    p = root / name
    p.mkdir(parents=True)
    (p / 'audio.bin').write_bytes(b'\0\0' * 1600 * len(speakers))
    atomic_json(p / 'index.json', {'offsets': [1600*i for i in range(len(speakers))],
                'lengths': [1600]*len(speakers), 'texts': ['a']*len(speakers), 'speakers': list(speakers)})
    return p


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_cross_shard_overlap_and_persistent_exclusion(self):
        a = make_store(self.root, 'voxpopuli-train', ('held', 'other'))
        make_store(self.root, 'voxpopuli-train-b', ('different',))
        make_store(self.root, 'voxpopuli-dev', ('held',))
        roles = {'train': ['voxpopuli-train', 'voxpopuli-train-b'], 'dev': ['voxpopuli-dev']}
        self.assertEqual(audit_stores(self.root, roles)['issues'][0]['speakers'], 1)
        atomic_json(a/'excluded.json', {'excluded': [0]})
        atomic_json(a/'keep.json', {'keep': [0, 1]})
        self.assertFalse(audit_stores(self.root, roles)['issues'])
        self.assertEqual(effective_ids(a, json.loads((a/'index.json').read_text())), [1])

    def test_missing_set_fails(self):
        with self.assertRaises(FileNotFoundError):
            audit_stores(self.root, {'dev': ['missing']})

    def test_audio_change_changes_identity(self):
        p = make_store(self.root, 'x')
        before = audit_stores(self.root, {'train': ['x']})['fingerprint']
        (p/'audio.bin').write_bytes(b'\x01\0'*3200)
        self.assertNotEqual(before, audit_stores(self.root, {'train': ['x']})['fingerprint'])

    def test_bad_ranges_and_duplicate_keep_rejected(self):
        p = make_store(self.root, 'x')
        atomic_json(p/'keep.json', {'keep': [0,0]})
        with self.assertRaises(ValueError): inspect_store(p)
        (p/'keep.json').unlink()
        (p/'audio.bin').write_bytes(b'')
        with self.assertRaises(ValueError): inspect_store(p)

    def test_writer_hash_checked(self):
        p = make_store(self.root, 'x')
        idx = json.loads((p/'index.json').read_text()); idx['audio_sha256'] = 'wrong'
        atomic_json(p/'index.json', idx)
        with self.assertRaises(ValueError): inspect_store(p)


class EvaluationTests(unittest.TestCase):
    def test_edit_breakdown_and_noise(self):
        self.assertEqual(error_counts('a b c', 'a x c d'),
                         dict(errors=2, substitutions=1, deletions=0, insertions=1, words=3))
        self.assertEqual(error_counts('a b', 'a')['deletions'], 1)
        row = {**error_counts('', 'phantom word'), 'seconds': 30}
        self.assertIsNone(summarize([row])['wer'])
        self.assertEqual(summarize([row])['phantom_words_per_minute'], 4)

    def record(self, hyp='a'):
        return {'id': 'dev:1', 'pcm_sha256': 'abc', 'ref': 'a', 'hyp': hyp, 'seconds': 1}

    def reports(self):
        provenance = {'weights_sha256': 'w', 'espdl_sha256': 'e', 'lm_sha256': 'l'}
        return [stage_report(s, provenance, [{**self.record('b' if s == 'int8' else 'a'),
                    'capture_sha256': 'c', 'alignment_passed': True}]) for s in ('float','int8','lm','streaming')]

    def test_stage_deltas(self):
        report = compare(self.reports())
        self.assertTrue(report['complete'])
        self.assertEqual(report['transitions']['float->int8']['errors_delta'], 1)
        self.assertEqual(report['transitions']['int8->lm']['errors_delta'], -1)

    def test_no_synthetic_completion_or_changed_identity(self):
        reports = self.reports()
        with self.assertRaises(ValueError): compare(reports[:2])
        self.assertFalse(compare(reports[:2], True)['complete'])
        reports[1]['records'][0]['pcm_sha256'] = 'different'
        with self.assertRaises(ValueError): compare(reports)

    def test_mismatched_model_or_coverage(self):
        reports = self.reports(); reports[1]['provenance'] = {'weights_sha256':'wrong', 'espdl_sha256':'e'}
        with self.assertRaises(ValueError): compare(reports)
        reports = self.reports(); reports[1]['records'][0]['id'] = 'different'
        with self.assertRaises(ValueError): compare(reports)

    def test_unaligned_streaming_rejected(self):
        with self.assertRaises(ValueError):
            stage_report('streaming', {'weights_sha256':'w','espdl_sha256':'e','lm_sha256':'l'}, [self.record()])


class StreamingImportTests(unittest.TestCase):
    def test_raw_final_capture_and_bound_evidence(self):
        from import_streaming import import_capture
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'audio.pcm').write_bytes(b'\0\0'*16000)
            (root/'capture.jsonl').write_text(json.dumps({'type':'draft','sequence':1,'text':'wrong'})+'\n'+
                json.dumps({'type':'final','sequence':1,'rawText':'a','text':'Formatted content'})+'\n')
            atomic_json(root/'alignment.json',{'passed':True,'method':'fixture test only',
                'pcm_sha256':sha256(root/'audio.pcm'),'capture_sha256':sha256(root/'capture.jsonl')})
            manifest={'provenance':{'weights_sha256':'w','espdl_sha256':'e','lm_sha256':'l'},
                'cases':[{'id':'dev:1','pcm':'audio.pcm','capture':'capture.jsonl','alignment':'alignment.json',
                          'capture_complete':True,'ref':'a'}]}
            atomic_json(root/'manifest.json',manifest)
            report=import_capture(root/'manifest.json')
            self.assertEqual(report['records'][0]['hyp'],'a')
            self.assertEqual(report['summary']['errors'],0)
            (root/'audio.pcm').write_bytes(b'\1\0'*16000)
            with self.assertRaises(ValueError): import_capture(root/'manifest.json')


HAS_TORCH = importlib.util.find_spec('torch') is not None
@unittest.skipUnless(HAS_TORCH, 'requires training Python with torch/scipy/yaml')
class TorchTests(unittest.TestCase):
    def setUp(self):
        import torch
        torch.set_num_threads(1)
        self.torch = torch

    def test_uneven_microbatch_gradients_equal_full_batch(self):
        t = self.torch
        from training_state import seed_all
        seed_all(42)
        a = t.nn.Linear(3, 2); b = copy.deepcopy(a)
        x, y = t.randn(7,3), t.randn(7,2)
        ((a(x)-y).square().mean(dim=1)).mean().backward()
        for ids in (slice(0,2), slice(2,7)):
            ((b(x[ids])-y[ids]).square().mean(dim=1)).sum().backward()
        for p,q in zip(a.parameters(), b.parameters()):
            q.grad.div_(7)
            t.testing.assert_close(p.grad, q.grad)

    def test_rng_model_and_optimizer_resume(self):
        from training_state import seed_all, save_state, restore_matching
        t = self.torch
        seed_all(19)
        model = t.nn.Linear(3,2); opt = t.optim.AdamW(model.parameters(), lr=.01)
        def step():
            opt.zero_grad(); model(t.randn(2,3)).square().mean().backward(); opt.step()
        step()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'state.pt'; save_state(path, model, opt)
            step(); expected = copy.deepcopy(model.state_dict()); expected_opt = copy.deepcopy(opt.state_dict())
            restore_matching(path, model, opt, restore_random=True); step()
            for k,v in model.state_dict().items(): t.testing.assert_close(v, expected[k], rtol=0, atol=0)
            for k, v in opt.state_dict()['state'].items():
                for key, value in v.items(): t.testing.assert_close(value, expected_opt['state'][k][key], rtol=0, atol=0)

    def test_batch_counters_and_determinism(self):
        from data import collate
        t = self.torch
        def item(i, frames=100, labels=None):
            return t.ones(64,frames), t.tensor(labels or [1,2]), {'source':'s', 'id':i, 'salt':i, 'spec_seed':i}
        batch = [item(0), item(1)]
        out = collate(batch, max_seconds=5.12, max_items=4)
        self.assertEqual(out[-1]['repeated'],2)
        self.assertEqual(out[0].shape, (4,64,128))
        t.testing.assert_close(out[0], collate(batch,max_seconds=5.12,max_items=4)[0], rtol=0,atol=0)
        out = collate(batch,max_seconds=1.28,max_items=4)
        self.assertEqual(out[-1]['bucket_dropped'],1)
        out = collate([item(0,2,[1,1,1]),item(1)])
        self.assertEqual(out[-1]['ctc_dropped'],1)
        with self.assertRaises(ValueError): collate([item(0,2,[1,1,1])])

    def test_sampler_resume_ignores_prefetch(self):
        from data import MixedBatchSampler
        class Store:
            lengths = [16000,32000,48000]
            def __len__(self): return 3
        kwargs = dict(stores=[Store()],weights=[1],max_seconds=5,max_items=3,steps=30,seed=123)
        all_batches = list(MixedBatchSampler(**kwargs))
        resumed = list(MixedBatchSampler(**kwargs,start_batch=7))
        self.assertEqual(all_batches[7:],resumed)

    def test_evaluation_missing_data_is_fatal(self):
        from evaluate import evaluate_stores
        from common import Frontend
        t=self.torch
        state={'preprocessor.featurizer.window':t.ones(320),'preprocessor.featurizer.fb':t.ones(1,64,257)}
        with self.assertRaises(FileNotFoundError):
            evaluate_stores(None,state,[('absent-training-audit-fixture',1)],t.device('cpu'))

    def test_actual_rollback_restores_optimizer(self):
        from unittest.mock import patch
        from train import run_eval
        from common import QuartzNet
        t=self.torch
        config={'encoder':{'params':{'feat_in':2,'jasper':[{'filters':2,'repeat':1,
                    'kernel':[3],'stride':[2],'dilation':[1],'residual':False,'separable':True}]}}}
        model=QuartzNet(config)
        template=copy.deepcopy(model.nemo_state_dict())
        opt=t.optim.AdamW(model.parameters(),lr=.01)
        def step():
            opt.zero_grad(); model(t.randn(2,2,20),t.tensor([20,20]))[0].square().mean().backward(); opt.step()
        step()
        expected=copy.deepcopy(model.state_dict()); expected_opt=copy.deepcopy(opt.state_dict())
        record={'id':'dev:0','ref':'a','hyp':'a','pcm_sha256':'x','seconds':1,**error_counts('a','a')}
        results={'dev':{**summarize([record]),'records':[record]}}
        guard={'audio_seconds':0,'bad':0,'lr_scale':1}
        with tempfile.TemporaryDirectory() as tmp, patch('train.evaluate_stores',return_value=results):
            out=Path(tmp)
            best=run_eval(model,template,config,out,0,None,lambda **kw:None,t.device('cpu'),guard,2,
                          dev_sets=[('dev',1)],optimizer=opt)
            step()
            record.update(hyp='b',**error_counts('a','b'))
            results['dev'].update(summarize([record]))
            run_eval(model,template,config,out,1,best,lambda **kw:None,t.device('cpu'),guard,2,
                     dev_sets=[('dev',1)],optimizer=opt)
            for k,v in model.state_dict().items(): t.testing.assert_close(v,expected[k],rtol=0,atol=0)
            for k,state in opt.state_dict()['state'].items():
                for key,value in state.items():t.testing.assert_close(value,expected_opt['state'][k][key],rtol=0,atol=0)
            self.assertEqual(guard['lr_scale'],.5)

    def test_filter_preserves_legacy_exclusions_and_rejects_stale_cache(self):
        from unittest.mock import patch
        import filter_store
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); store=make_store(root,'peoples-clean-train',('held','train'))
            atomic_json(store/'keep.json',{'keep':[1],'dev_held_out':{'peoples-dev':1}})
            ckpt=root/'ckpt'; ckpt.mkdir()
            (ckpt/'model_weights.ckpt').write_bytes(b'fixture')
            (ckpt/'model_config.yaml').write_text('{}')
            argv=['filter_store.py','--store','peoples-clean-train','--ckpt',str(ckpt)]
            with patch.object(filter_store,'STORES',root),patch.object(sys,'argv',argv), \
                 patch.object(filter_store,'score',return_value=([0.0,0.0],[1600,1600])):
                filter_store.main()
                self.assertEqual(json.loads((store/'keep.json').read_text())['keep'],[1])
                filter_store.main()
                self.assertEqual(json.loads((store/'keep.json').read_text())['keep'],[1])
                (store/'audio.bin').write_bytes(b'\1\0'*3200)
                with self.assertRaises(ValueError): filter_store.main()

    def test_glasses_copy_keeps_filtered_labels_aligned(self):
        from unittest.mock import patch
        import make_g2_stores
        import data
        class Channel:
            def __call__(self,x,**kw): return x
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); store=make_store(root,'peoples-dev',('removed','retained'))
            atomic_json(store/'excluded.json',{'excluded':[0]})
            with patch.object(data,'STORES',root),patch.object(make_g2_stores,'STORES',root), \
                 patch.object(make_g2_stores,'G2Channel',Channel), \
                 patch.object(make_g2_stores,'agc',lambda x,*args,**kw:x):
                make_g2_stores.convert('peoples-dev')
            result=json.loads((root/'peoples-dev-g2/index.json').read_text())
            self.assertEqual(result['speakers'],['retained'])
            self.assertEqual(result['source']['source_indices'],[1])
            self.assertEqual(len(result['texts']),len(result['offsets']))
            inspect_store(root/'peoples-dev-g2')

    def test_benchmark_identity_changes_with_dataset(self):
        from unittest.mock import patch
        import benchmark
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); store=make_store(root/'stores','x')
            with patch.object(benchmark,'STT_ROOT',root),patch.object(benchmark,'_IDENTITIES',{}):
                before=benchmark.evaluation_identity('x')
                (store/'audio.bin').write_bytes(b'\1\0'*3200)
                benchmark._IDENTITIES.clear()
                self.assertNotEqual(before,benchmark.evaluation_identity('x'))
                with self.assertRaises(ValueError): benchmark.import_existing()

    def test_real_lm_cli_emits_linked_records(self):
        import subprocess
        import os
        import numpy as np
        lm_dir=ROOT/'tools/stt_train/lm'
        sys.path.insert(0,str(lm_dir))
        from test_hw1lm import tiny_lm_bytes
        import hw1lm
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            lm=root/'tiny.lm'; lm.write_bytes(tiny_lm_bytes(alpha=0,beam_width=4))
            q=np.full((3,29),-100,dtype=np.int8)
            q[0,hw1lm.BLANK]=0; q[1,hw1lm.VOCAB.index('a')]=0; q[2,hw1lm.BLANK]=0
            np.savez(root/'tiny-dev.npz',q=q,offsets=np.array([0,3]),texts=np.array(['a']),exponent=-3,
                ids=np.array(['dev:0']),pcm_sha256=np.array(['pcm-fixture']),seconds=np.array([1.0]),
                provenance=np.array(json.dumps({'weights_sha256':'w','espdl_sha256':'e'})))
            subprocess.run([sys.executable,'-B',str(lm_dir/'lm_int8_eval.py'),'--npz-dir',str(root),
                '--model','tiny','--lm',str(lm),'--sets','dev','--output-dir',str(root/'out')],
                check=True,capture_output=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},timeout=30)
            report=json.loads(next((root/'out').glob('*-lm.json')).read_text())
            self.assertEqual(report['stage'],'lm')
            self.assertEqual(report['records'][0]['pcm_sha256'],'pcm-fixture')
            self.assertEqual(report['summary']['errors'],0)

    def test_split_repair_covers_all_shards(self):
        from make_dev_views import exclude_speakers
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('voxpopuli-train','voxpopuli-train-b'):
                make_store(root,name,('held','other'))
            exclude_speakers(root,'voxpopuli-train-b',{'held'})
            for name in ('voxpopuli-train','voxpopuli-train-b'):
                self.assertEqual(json.loads((root/name/'excluded.json').read_text())['excluded'],[0])


if __name__ == '__main__':
    unittest.main()
