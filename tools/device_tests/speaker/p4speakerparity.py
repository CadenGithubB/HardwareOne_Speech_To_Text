#!/usr/bin/env python3
"""P4 speaker-fixture parity trials; no flashing or model-file writes.

prepare FIXTURE OUTDIR exclusively creates the named temporary test fixture on
SD, uploads it and verifies it. cleanup FIXTURE OUTDIR removes only the owned,
content-matching fixture. run FIXTURE OUTDIR --trials 5 reads it before
each trial, starts normal STT on PDM, waits for diagnostic vector output, stops
and drains. It requires the explicitly labelled diagnostic app, not production.
Credentials come only from STT_TEST_USER/STT_TEST_PASSWORD. Raw logs/vectors
stay private; stdout contains status/counters/cosines only.
"""
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import time

MAC='e8:f6:0a:e3:a7:68'
FIXTURE='/sd/STT Models/codex_speaker_parity.bin'


def parse_fixture(data):
    if len(data)<8:raise ValueError('short fixture header')
    samples,dim=struct.unpack_from('<II',data)
    if not 257<=samples<=500000 or not 1<=dim<=1024 or len(data)!=8+2*samples+4*dim:
        raise ValueError('fixture dimensions/size invalid')
    vector=struct.unpack_from('<'+'f'*dim,data,8+samples*2)
    if not all(math.isfinite(v) for v in vector) or sum(v*v for v in vector)<=0:
        raise ValueError('invalid reference vector')
    return samples,vector


def cosine(a,b):
    if len(a)!=len(b):raise ValueError('dimension mismatch')
    return sum(x*y for x,y in zip(a,b))/math.sqrt(sum(x*x for x in a)*sum(y*y for y in b))


def diagnostic_vector(lines):
    dim=None;parts={}
    for line in lines:
        line=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',line)
        m=re.search(r'TL spk_fixture_dim n=(\d+)',line)
        if m:
            dim=int(m.group(1));parts={}
            if not 1<=dim<=1024:raise ValueError('bad diagnostic dimension')
        m=re.search(r'TL spk_fixture_part i=(\d+) v=([-+0-9.eE ]+) end(?:\s|$)',line)
        if m and dim is not None:
            i=int(m.group(1));values=[float(v) for v in m.group(2).split()]
            if i%8 or i>=dim or len(values)!=min(8,dim-i) or not all(math.isfinite(v) for v in values):
                raise ValueError('invalid/truncated fixture chunk')
            if i in parts and parts[i]!=values:raise ValueError('conflicting fixture chunk')
            parts[i]=values
    if dim is None or len(parts)!=(dim+7)//8:return None
    vector=[v for i in range(0,dim,8) for v in parts[i]]
    if not .99999<=sum(v*v for v in vector)<=1.00001:raise ValueError('fixture vector not unit length')
    return vector


def fixture_summary_cosine(lines):
    for line in reversed(lines):
        m=re.search(r'TL spk_load .*fixture_cos=([-+0-9.]+)',line)
        if m:return float(m.group(1))
    return None


def trial_ready(types,lines):
    return all(k in types for k in ('warm','capture_start')) and fixture_summary_cosine(lines) is not None


class Device:
    def __init__(self,out):self.out=out;self.ser=None;self.rd=None;self.token=None
    def __enter__(self):
        import run_session as h
        if os.environ.get('UNIT_MAC',MAC)!=MAC:raise RuntimeError('wrong authorized MAC')
        os.environ['UNIT_MAC']=MAC
        self.h=h
        self.out.mkdir(parents=True,exist_ok=False,mode=0o700)
        try:
            self.ser,self.rd,self.boot=h.open_and_boot(h.resolve_port(),self.out)
            time.sleep(20)
            user,password=os.environ.get('STT_TEST_USER'),os.environ.get('STT_TEST_PASSWORD')
            if not user or not password or any(c.isspace() for c in user+password):raise RuntimeError('credentials missing/invalid')
            self.command(f'login {user} {password}',r'Login successful',20)
            self.command('loglink on',r'loglink ON',20)
            self.free_before=self.free()
            self.command('log status',r'System logging is INACTIVE')
            source=self.command('micsource',r'Mic source: preference=(\w+), active=(\w+)').group(1)
            if source!='pdm':raise RuntimeError('PDM preference required')
            return self
        except BaseException:
            self.__exit__(None,None,None);raise
    def command(self,command,pattern,timeout=20):
        return self.h.production_command(self.ser,self.rd,command,pattern,timeout)
    def free(self):
        n=int(self.command('fsusage json',r'"freeBytes":(\d+)').group(1))
        if n<2097152:raise RuntimeError('LittleFS below 2 MiB')
        return n
    def fixture(self,validate=True):
        data=bytearray();size=None
        while size is None or len(data)<size:
            offset=len(data)
            # Asynchronous CLI/debug output can interrupt the JSON data string
            # while leaving valid JSON. Never strip/repair bytes or accept a
            # partial chunk: reissue the same read with strict validation.
            for attempt in range(3):
                m=self.command(f'fileread "{FIXTURE}" {offset} 2048 b64',r'\{"success":(?:true|false),[^\r\n]*\}')
                try:
                    obj=json.loads(m.group(0))
                    if not obj.get('success'):raise RuntimeError('fixture absent or inaccessible')
                    chunk=base64.b64decode(obj['data'],validate=True)
                    if obj['offset']!=offset or len(chunk)!=obj['len']:
                        raise ValueError('invalid file-read chunk')
                    if size is not None and obj['size']!=size:
                        raise ValueError('fixture size changed')
                    if obj['size']>1048576 or offset+len(chunk)>obj['size']:
                        raise ValueError('oversized/inconsistent file-read chunk')
                    if not chunk and not (not validate and offset==0 and obj['size']==0):
                        raise ValueError('empty file-read chunk')
                    break
                except (ValueError,KeyError,TypeError):
                    if attempt==2:raise RuntimeError('fixture read framing failed after three attempts') from None
            if obj['size']==0 and offset==0 and not chunk and not validate:return b''
            if size is None:size=obj['size']
            data.extend(chunk)
        if validate:parse_fixture(data)
        return bytes(data)
    def start(self):
        self.command('sttperf log on',r'STT perf live log: ON')
        self.token=self.command('stt start',r'"accepted":true,"id":"([0-9a-f]{16})"').group(1)
    def stop(self):
        if not self.token:return
        token=self.token
        self.command(f'stt stop {token}',r'STT request accepted',20)
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            self.h.production_drain_one(self.ser,self.rd,token)
            m=self.command(f'stt status {token}',r'\{[^\r\n]*"state":[^\r\n]*\}')
            obj=json.loads(m.group(0))
            if obj.get('state') in ('done','failed','cancelled'):
                self.token=None
                if obj.get('state')!='done' or obj.get('audioOverruns',0) or obj.get('error'):
                    raise RuntimeError('STT terminal fault/overrun')
                return obj
            time.sleep(.25)
        raise RuntimeError('STT drain timed out')
    def __exit__(self,*_):
        try:
            if self.token:self.stop()
        finally:
            if self.rd:self.rd.stop()
            if self.ser:self.ser.close()


def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    f=sub.add_parser('fetch');f.add_argument('outdir')
    for command in ('prepare','cleanup'):
        f=sub.add_parser(command);f.add_argument('fixture');f.add_argument('outdir')
    r=sub.add_parser('run');r.add_argument('fixture');r.add_argument('outdir');r.add_argument('--trials',type=int,default=5)
    a=ap.parse_args();root=Path(a.outdir)
    if 'private' not in root.parts:ap.error('outputs must be under ignored private storage')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if a.command in ('prepare','cleanup'):
        data=Path(a.fixture).read_bytes();parse_fixture(data)
        marker=root/'fixture-ownership.json'
        if a.command=='prepare':
            if marker.exists():raise RuntimeError('ownership marker already exists; recover/cleanup first')
            with Device(root/time.strftime('prepare-%Y%m%d-%H%M%S')) as d:
                d.command(f'filecreate "{FIXTURE}"',r'Created file: '+re.escape(FIXTURE))
                marker.write_text(json.dumps({'created':True,'path':FIXTURE,'sha256':hashlib.sha256(data).hexdigest()}))
                for offset in range(0,len(data),1024):
                    part=data[offset:offset+1024];final=offset+len(part)==len(data)
                    encoded=base64.b64encode(part).decode()
                    m=d.command(f'filewrite "{FIXTURE}" {offset} {encoded}'+(' final' if final else ''),
                                r'\{"success":(?:true|false),[^\r\n]*\}')
                    obj=json.loads(m.group(0))
                    if not obj.get('success') or obj.get('size')!=offset+len(part):raise RuntimeError('test fixture upload failed')
                    if offset%8192==0:d.free()
                if d.fixture()!=data:raise RuntimeError('uploaded fixture verification failed')
                free=d.free();print(json.dumps({'prepared_bytes':len(data),'littlefs_before':d.free_before,'littlefs_after':free}))
        else:
            own=json.loads(marker.read_text())
            if not own.get('created') or own['path']!=FIXTURE or own['sha256']!=hashlib.sha256(data).hexdigest():
                raise RuntimeError('test fixture ownership mismatch')
            with Device(root/time.strftime('cleanup-%Y%m%d-%H%M%S')) as d:
                current=d.fixture(validate=False)
                if current!=data[:len(current)] or len(current)>len(data):raise RuntimeError('test fixture content changed; refusing delete')
                d.command(f'filedelete "{FIXTURE}" confirm',r'Deleted file: '+re.escape(FIXTURE))
                own['removed']=True;marker.write_text(json.dumps(own))
                print(json.dumps({'removed_test_fixture':True,'littlefs_before':d.free_before,'littlefs_after':d.free()}))
        return
    if a.command=='fetch':
        with Device(root/time.strftime('fetch-%Y%m%d-%H%M%S')) as d:
            data=d.fixture();samples,e=parse_fixture(data);free=d.free()
            target=root/'device-fixture.bin'
            with target.open('xb') as f:f.write(data)
            print(json.dumps({'fixture_bytes':len(data),'samples':samples,'dim':len(e),
                              'sha256':hashlib.sha256(data).hexdigest(),'littlefs_before':d.free_before,'littlefs_after':free}))
        return
    if a.trials<1:ap.error('--trials must be positive')
    if (root/'results.json').exists():raise RuntimeError('refusing to overwrite completed trials')
    fixture=Path(a.fixture).read_bytes();samples,expected=parse_fixture(fixture)
    rows=[]
    for i in range(a.trials):
        out=root/(time.strftime('trial-%Y%m%d-%H%M%S')+f'-{i}')
        with Device(out) as d:
            if d.fixture()!=fixture:raise RuntimeError('device fixture changed since download')
            d.start();deadline=time.monotonic()+90;vector=None
            while time.monotonic()<deadline:
                with d.rd.lock:history=list(d.rd.history)
                if d.rd.fatal or len(d.rd.boot_marks)>d.h.allowed_boots(d.boot):raise RuntimeError('device fault')
                vector=diagnostic_vector(history)
                if vector is not None:break
                time.sleep(.1)
            if vector is None:raise RuntimeError('no diagnostic fixture vector; diagnostic app required')
            # Preserve the measured vector even if subsequent lifecycle checks fail.
            (out/'embedding.json').write_text(json.dumps({'device_unit':vector,
                'cosine_vs_fixture_reference':cosine(vector,expected)}))
            if not d.h.wait_for(lambda: trial_ready(d.rd.first_tl,list(d.rd.history)),180):
                raise RuntimeError('normal STT warm/capture readiness timed out')
            with d.rd.lock:history=list(d.rd.history)
            fixture_cos=fixture_summary_cosine(history)
            if fixture_cos is None or abs(fixture_cos-cosine(vector,expected))>0.00006:
                raise RuntimeError('emitted vector disagrees with firmware fixture cosine')
            snapshot=json.loads(d.command(f'stt status {d.token}',r'\{[^\r\n]*"state":[^\r\n]*\}').group(0))
            if snapshot.get('source')!='pdm' or snapshot.get('transcriptEnabled'):
                raise RuntimeError('unexpected capture source or transcript saving enabled')
            state=d.stop();free=d.free();d.command('log status',r'System logging is INACTIVE')
            row={'trial':i,'samples':samples,'dim':len(vector),'cosine_vs_fixture_reference':cosine(vector,expected),'firmware_fixture_cosine':fixture_cos,
                 'littlefs_before':d.free_before,'littlefs_after':free,'audio_overruns':state.get('audioOverruns',0),
                 'watchdog_warnings':len(d.rd.watchdogs),'fatal_markers':len(d.rd.fatal),'device_unit':vector}
            (out/'result.json').write_text(json.dumps(row));rows.append(row)
            print(json.dumps({k:v for k,v in row.items() if k!='device_unit'}),flush=True)
    (root/'results.json').write_text(json.dumps({'fixture_sha256':hashlib.sha256(fixture).hexdigest(),'trials':rows}))


if __name__=='__main__':main()
