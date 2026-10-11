#!/usr/bin/env python3
"""Host compiler/sanitizer checks and numerical parity with independent Torch frontend."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import numpy as np
import soundfile as sf
import torch
from export_constants import load_state
from reference_frontend import features_pcm16

HERE=Path(__file__).resolve().parent
PRODUCTION=HERE.parents[2]/'components/hardwareone/stt'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint',type=Path,default=HERE.parents[1]/'speech_portable/private/stt-quartznet')
    parser.add_argument('--sanitize',action='store_true')
    parser.add_argument('--output',type=Path,default=HERE.parent/'private/frontend')
    args=parser.parse_args()
    torch.set_num_threads(4)
    state=load_state(args.checkpoint)
    args.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hw1-quartz-frontend-') as directory:
        binary=Path(directory)/'frontend'
        cmd=['clang++','-std=c++17','-O2','-ffp-contract=off','-Wall','-Wextra','-Werror',str(PRODUCTION/'quartznet_frontend.cpp'),str(HERE/'test_driver.cpp'),'-I'+str(PRODUCTION),'-o',str(binary)]
        if args.sanitize: cmd[1:1]=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        subprocess.run(cmd,check=True)
        subprocess.run([str(binary)],check=True)
        rng=np.random.default_rng(921)
        cases=[('silence320',np.zeros(320,np.int16)),('silence1600',np.zeros(1600,np.int16)),
               ('near_silence1601',rng.integers(-1,2,1601,dtype=np.int16)),
               ('random321',rng.integers(-32768,32768,321,dtype=np.int16)),
               ('random1599',rng.integers(-30000,30001,1599,dtype=np.int16)),
               ('impulse1600',np.array([32767]+[0]*1599,dtype=np.int16)),
               ('sine480000',np.round(np.sin(np.arange(480000)*0.08)*16000).astype(np.int16))]
        for name in ['0.wav','1.wav']:
            pcm,rate=sf.read(args.checkpoint/'fixtures'/name,dtype='int16')
            if rate!=16000 or pcm.ndim!=1: raise ValueError('Unexpected fixture format')
            cases.append((name[:-4],pcm))
        results=[]
        for name,pcm in cases:
            raw=args.output/(name+'.pcm16le'); out=args.output/(name+'.features.f32le')
            raw.write_bytes(pcm.astype('<i2').tobytes())
            subprocess.run([str(binary),str(raw),str(out)],check=True,capture_output=True)
            actual=np.frombuffer(out.read_bytes(),dtype='<f4').reshape(-1,64)
            reference=features_pcm16(pcm,state)
            error=np.abs(actual-reference)
            item={'fixture':name,'samples':len(pcm),'frames':len(actual),'max_abs_error':float(error.max()),
                  'mean_abs_error':float(error.mean()),'p99_abs_error':float(np.quantile(error,0.99)),
                  'pcm_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'features_sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
            results.append(item); print(json.dumps(item),flush=True)
            if not np.isfinite(actual).all() or error.max()>0.0006 or error.mean()>0.00002:
                raise AssertionError('Frontend numeric parity exceeded tolerance: '+name)
            np.save(args.output/(name+'.reference.npy'),reference)
        record={'schema':1,'scope':'Host-only portable frontend parity, not P4 timing','sanitize':args.sanitize,'dither_seed':'0x12345678','results':results}
        (args.output/'results.json').write_text(json.dumps(record,indent=2)+'\n')
if __name__=='__main__': main()
