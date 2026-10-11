#!/usr/bin/env python3
"""Generate/check the canonical frontend identity consumed by model packaging."""
import argparse
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
PRODUCTION=HERE.parents[2]/'components/hardwareone/stt'

def contract_bytes():
    files=['quartznet_frontend.h','quartznet_frontend.cpp','quartznet_constants.h','reference_frontend.py','constants-manifest.json']
    value={
        'schema':1,'name':'hw1-quartznet5x5ls-en-frontend-v1',
        'input':{'sample_rate_hz':16000,'dtype':'int16','channels':1,'minimum_samples':320,'maximum_samples':480000,'scale':32768,'preprocessed':False},
        'dither':{'algorithm':'xorshift32-box-muller-float32','seed':'0x12345678','amplitude':1e-5,'reset':'utterance','uniform':'float32(((uint32 >> 8) + 1) / 16777217.0)'},
        'preemphasis':0.97,
        'stft':{'fft':512,'window':320,'hop':160,'center':True,'padding':'reflect','window_source':'checkpoint'},
        'mel':{'bins':64,'source':'checkpoint','sparse_nonzero':498,'power':2,'log_guard':2**-24},
        'cmvn':{'scope':'whole valid utterance','accumulator':'float64','variance_correction':1,'mean_cast':'float32','variance_cast_before_sqrt':'float32','std_epsilon':1e-5},
        'output':{'dtype':'float32','layout':'T,64','frames':'ceil(samples/160)','padding':False,'maximum_frames':3000},
        'ctc':{'vocabulary':" abcdefghijklmnopqrstuvwxyz'",'blank':28,'argmax_tie':'first','trim':'leading and trailing spaces','maximum_frames':3000},
        'source_sha256':{name:hashlib.sha256(((PRODUCTION if name.endswith(('.cpp','.h')) else HERE)/name).read_bytes()).hexdigest() for name in files},
    }
    return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    path=HERE/'frontend-contract.json';data=contract_bytes()
    if args.check:
        if not path.exists() or path.read_bytes()!=data: raise SystemExit('Frontend contract is stale')
    else: path.write_bytes(data)
    print(hashlib.sha256(data).hexdigest())
if __name__=='__main__':main()
