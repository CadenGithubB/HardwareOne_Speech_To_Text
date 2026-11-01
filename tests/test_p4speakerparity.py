#!/usr/bin/env python3
"""Synthetic fixture framing and diagnostic parsing, no device/model needed."""
import math
from pathlib import Path
import struct
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/device_tests/speaker'))
import p4speakerparity as p


def reject(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('invalid fixture accepted')


def main():
    data=struct.pack('<II',257,4)+b'\0'*514+struct.pack('<4f',.5,.5,.5,.5)
    n,e=p.parse_fixture(data);assert n==257 and len(e)==4
    reject(lambda:p.parse_fixture(data[:-1]))
    reject(lambda:p.parse_fixture(b'bad'))
    lines=['[9] I (100) STT: TL spk_fixture_dim n=4','I (101) STT: TL spk_fixture_part i=0 v=0.5 0.5 0.5 0.5 end']
    assert p.diagnostic_vector(lines)==[.5]*4
    assert p.diagnostic_vector(['\x1b[32m'+x+'\x1b[0m' for x in lines])==[.5]*4
    unit=1/math.sqrt(24)
    chunks=['TL spk_fixture_dim n=24']+[f'TL spk_fixture_part i={i} v='+
        ' '.join([str(unit)]*8)+' end' for i in (16,0,8)]
    assert len(p.diagnostic_vector(chunks))==24
    assert p.diagnostic_vector(chunks[:-1]) is None
    assert p.diagnostic_vector(lines[:1]) is None
    assert p.diagnostic_vector([lines[0],lines[1].removesuffix(' end')]) is None
    # A truncated last float can leave the expected token count: reject it.
    assert p.diagnostic_vector([lines[0],lines[1].replace('0.5 end','0.')]) is None
    assert p.diagnostic_vector(lines+lines[1:])==[.5]*4
    assert math.isclose(p.cosine(e,p.diagnostic_vector(lines)),1)
    reject(lambda:p.diagnostic_vector(lines+['TL spk_fixture_part i=0 v=0 0 0 1 end']))
    reject(lambda:p.diagnostic_vector(['TL spk_fixture_dim n=4','TL spk_fixture_part i=0 v=0.5 0.5 end']))
    reject(lambda:p.diagnostic_vector(['TL spk_fixture_dim n=1025']))
    reject(lambda:p.diagnostic_vector(['TL spk_fixture_dim n=4','TL spk_fixture_part i=0 v=1 1 1 1 end']))
    # Vector output precedes the load summary: readiness must await that line.
    ready={'warm':1,'capture_start':2}
    assert not p.trial_ready(ready,lines)
    summary='[12] STT: TL spk_load ok=1 fixture_cos=0.9928 psram_free=3000000'
    assert p.trial_ready(ready,lines+[summary])
    assert not p.trial_ready({'warm':1},lines+[summary])
    assert p.fixture_summary_cosine(lines+[summary])==0.9928
    print('p4 speaker parity: fixture framing and parser ok')


if __name__=='__main__':main()
