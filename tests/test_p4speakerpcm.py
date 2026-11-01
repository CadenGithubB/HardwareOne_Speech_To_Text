#!/usr/bin/env python3
"""Synthetic nonce/length/checksum/cleanup identity guards; no real PCM."""
import hashlib
from pathlib import Path
import struct
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/speaker'))
import p4speakerpcm as p


def reject(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('invalid capture accepted')


def main():
    nonce=b'1234567890abcdef';arm=p.arm_bytes(3,nonce)
    assert len(arm)==32
    body=p.HEADER.pack(b'SPKPCM1\0',nonce,3,1000,500,4)+b'\0'*1000+struct.pack('<4f',.5,.5,.5,.5)
    data=body+hashlib.sha256(body).digest();r=p.parse_capture(data,3,nonce)
    # Firmware stores raw FC vectors; cosine consumers normalize them.
    unnormalized=body[:-16]+struct.pack('<4f',2,2,2,2)
    assert p.parse_capture(unnormalized+hashlib.sha256(unnormalized).digest(),3,nonce)['embedding']==(2,2,2,2)
    zero=body[:-16]+b'\0'*16
    reject(lambda:p.parse_capture(zero+hashlib.sha256(zero).digest(),3,nonce))
    assert r['model_samples']==500 and r['retained_samples']==1000
    reject(lambda:p.parse_capture(data[:-1],3,nonce))
    reject(lambda:p.parse_capture(data,2,nonce))
    reject(lambda:p.parse_capture(data,3,b'x'*16))
    reject(lambda:p.parse_capture(data[:-32]+b'x'*32,3,nonce))
    entry={'seq':3,'nonce':nonce.hex()}
    assert p.owned_content(b'',entry) and p.owned_content(arm,entry)
    assert p.owned_content(data,entry) and p.owned_content(data[:20],entry)
    assert not p.owned_content(b'unrelated',entry)
    assert not p.owned_content(data.replace(nonce,b'x'*16),entry)
    print('p4 speaker PCM: capture checksum and ownership guards ok')


if __name__=='__main__':main()
