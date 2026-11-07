#!/usr/bin/env python3
"""Exercise the REAL trainer with tiny synthetic data; proves plumbing, not ASR accuracy.

All generated audio, labels, weights and reports must be written under private/.
Runs uninterrupted vs resumed (including DataLoader worker-count change), then a
final evaluation. Does not use source datasets, models, GPU, or hardware.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
import torch
import yaml
from common import QuartzNet
from diagnostics import atomic_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = a.output.resolve()
    if 'private' not in root.parts or root.exists():
        p.error('Use a new directory under private/')
    root.mkdir(parents=True)
    torch.manual_seed(11)
    config = {'encoder': {'params': {'feat_in':64,'jasper':[{'filters':8,'repeat':1,
              'kernel':[3], 'stride':[2], 'dilation':[1], 'residual':False, 'separable':True}]}},
              'decoder':{'params':{'vocabulary':list(" abcdefghijklmnopqrstuvwxyz'")}}}
    model = QuartzNet(config)
    state = model.nemo_state_dict()
    state.update({'preprocessor.featurizer.window':torch.hann_window(320),
                  'preprocessor.featurizer.fb':torch.rand(1,64,257)})
    init = root/'init'; init.mkdir()
    torch.save(state, init/'model_weights.ckpt')
    (init/'model_config.yaml').write_text(yaml.safe_dump(config))
    names = ['ami-sdm-train','ami-ihm-train','librispeech-train-clean-100',
             'ami-sdm-validation','ami-ihm-validation','librispeech-dev-clean',
             'musan-noise','musan-speech','rirs']
    rng = np.random.default_rng(11)
    for name in names:
        store = root/'stores'/name; store.mkdir(parents=True)
        offsets=[]; lengths=[]; pos=0
        with (store/'audio.bin').open('wb') as f:
            for i,n in enumerate([8000,12000,16000]):
                offsets.append(pos); lengths.append(n); pos+=n
                f.write(rng.integers(-1000,1000,n,dtype=np.int16).astype('<i2').tobytes())
        atomic_json(store/'index.json', {'offsets':offsets,'lengths':lengths,
            'texts':['a','ab','ba'], 'speakers':[f'{name}-{i}' for i in range(3)]})
    env = {**os.environ, 'STT_ROOT':str(root), 'PYTHONDONTWRITEBYTECODE':'1',
           'OMP_NUM_THREADS':'1', 'MKL_NUM_THREADS':'1', 'OPENBLAS_NUM_THREADS':'1'}
    trainer = Path(__file__).with_name('train.py')
    common = [sys.executable,'-B',str(trainer),'--init',str(init),'--deadline','+1h',
              '--device','cpu','--fused-adamw','off','--fast-dwconv','off','--accum','2',
              '--max-seconds','3','--max-items','4','--warmup','1','--target-hours','.003',
              '--first-eval-hours','100','--eval-hours','100','--rollback','off',
              '--gradient-diagnostics-every','1','--noise-only-share','.2']
    def run(name, workers, stop):
        log=root/f'{name}-{workers}-{stop}.log'
        with log.open('w') as f:
            subprocess.run(common+['--out',str(root/name),'--workers',str(workers),
                                   '--stop-after-steps',str(stop)],env=env,stdout=f,stderr=subprocess.STDOUT,
                           check=True,timeout=120)
    run('continuous',0,4)
    run('resumed',0,2)
    run('resumed',2,4)
    left=torch.load(root/'continuous/resume.pt',weights_only=False)
    right=torch.load(root/'resumed/resume.pt',weights_only=False)
    for key,value in left['model'].items():
        torch.testing.assert_close(value,right['model'][key],rtol=0,atol=0)
    for key,state in left['optimizer']['state'].items():
        for field,value in state.items():
            torch.testing.assert_close(value,right['optimizer']['state'][key][field],rtol=0,atol=0)
    assert left['exposure']==right['exposure']
    assert left['guard']['consumed_batches']==right['guard']['consumed_batches']==8
    run('resumed',0,0)
    reports=list((root/'resumed/evals').glob('*/utterances.json'))
    assert len(reports)>=2
    final=json.loads(sorted(reports)[-1].read_text())
    assert all('paired' in report for report in final.values())
    atomic_json(root/'smoke-result.json',{'passed':True,'scope':'synthetic CPU trainer plumbing',
        'resume_weights_and_optimizer':'byte-exact tensor equality after 4 steps',
        'worker_change':'0 to 2', 'exposure_equal':True,'final_evaluation':True})
    print((root/'smoke-result.json').read_text())


if __name__ == '__main__':
    main()
