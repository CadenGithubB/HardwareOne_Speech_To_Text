#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/stt_train_15x5'))
from diagnostics import atomic_json,effective_ids,sha256
from prepare_split_baseline import prepare,role


def store(root,name,speakers):
    d=root/name;d.mkdir(parents=True)
    (d/'audio.bin').write_bytes(b'\0\0'*100*len(speakers))
    atomic_json(d/'index.json',{'offsets':[i*100 for i in range(len(speakers))],
        'lengths':[100]*len(speakers),'texts':['a']*len(speakers),'speakers':speakers})
    return d


class Splits(unittest.TestCase):
    def test_all_shards_unknowns_and_test_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'source'
            for name in ('voxpopuli-train','voxpopuli-train-b'):
                store(src,name,['train','dev','test',None])
            store(src,'voxpopuli-dev',['dev','test'])
            store(src,'voxpopuli-validation',['test'])
            before={str(p.relative_to(src)):sha256(p) for p in src.glob('*/*')}
            result=prepare(src,root/'corrected')
            for name in ('voxpopuli-train','voxpopuli-train-b'):
                d=root/'corrected/stores'/name
                self.assertEqual(effective_ids(d,json.loads((d/'index.json').read_text())),[0])
                self.assertTrue((d/'audio.bin').is_symlink())
            d=root/'corrected/stores/voxpopuli-dev'
            self.assertEqual(effective_ids(d,json.loads((d/'index.json').read_text())),[0])
            self.assertTrue(result['source_unchanged'])
            self.assertEqual(before,{str(p.relative_to(src)):sha256(p) for p in src.glob('*/*')})
            with self.assertRaises(ValueError):prepare(src,root/'corrected')

    def test_train2_and_unknown_role(self):
        self.assertEqual(role('peoples-clean-train2'),'train')
        self.assertEqual(role('commonvoice-fresh-test'),'test')
        with self.assertRaises(ValueError):role('unclassified')

    def test_existing_filters_and_exclusions_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'source'
            d=store(src,'peoples-clean-train2',['old','train','dev'])
            atomic_json(d/'keep.json',{'keep':[1,2]})
            atomic_json(d/'excluded.json',{'excluded':[0]})
            store(src,'peoples-dev',['dev'])
            prepare(src,root/'corrected')
            target=root/'corrected/stores/peoples-clean-train2'
            self.assertEqual(effective_ids(target,json.loads((target/'index.json').read_text())),[1])
            self.assertEqual(json.loads((target/'keep.json').read_text())['keep'],[1,2])


if __name__=='__main__':unittest.main()
