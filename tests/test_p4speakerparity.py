#!/usr/bin/env python3
"""Synthetic fixture framing and diagnostic parsing, no device/model needed."""
import math
import base64
import json
import re
import threading
from types import SimpleNamespace
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
    # A real post-stop WDT reboot used to become an opaque command timeout and
    # a second stop with an invalid token. Detect it throughout command polling.
    d=p.Device(Path('unused'));d.h=SimpleNamespace(allowed_boots=lambda _:1);d.boot={}
    d.rd=SimpleNamespace(lock=threading.Lock(),boot_marks=[1],fatal=[],error=None)
    d.token='test';d.check_health();assert d.token=='test'
    d.rd.boot_marks.append(2)
    try:d.check_health()
    except RuntimeError as exc:assert 'boots=2' in str(exc) and d.token is None
    else:raise AssertionError('accepted an unexpected reboot')
    closed=[];d.rd.stop=lambda:closed.append('reader');d.ser=SimpleNamespace(close=lambda:closed.append('serial'))
    try:d.__exit__()
    except RuntimeError:assert closed==['reader','serial'] and d.token is None
    else:raise AssertionError('context exit ignored a reset')
    closed.clear();d.rd.boot_marks=[1];d.__exit__();d.check_health()
    assert closed==['reader','serial']
    # A real cleanup read had valid JSON but debug text inside its base64
    # payload. Re-read the identical offset; never remove foreign characters.
    class FakeDevice(p.Device):
        def __init__(self,replies):self.replies=iter(replies);self.commands=[]
        def command(self,command,pattern,timeout=20):
            self.commands.append(command)
            return re.search(pattern,json.dumps(next(self.replies),separators=(',',':')))
    valid={'success':True,'size':len(data),'offset':0,'len':len(data),
           'data':base64.b64encode(data).decode()}
    bad={**valid,'data':valid['data'][:100]+'[9] I (10) STT: debug'+valid['data'][100:]}
    d=FakeDevice([bad,valid]);assert d.fixture()==data
    assert len(d.commands)==2 and d.commands[0]==d.commands[1]
    d=FakeDevice([bad]*3)
    try:d.fixture()
    except RuntimeError:assert len(d.commands)==3
    else:raise AssertionError('accepted persistent interleaving')
    d=FakeDevice([{**valid,'len':len(data)-1},valid]);assert d.fixture()==data
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
