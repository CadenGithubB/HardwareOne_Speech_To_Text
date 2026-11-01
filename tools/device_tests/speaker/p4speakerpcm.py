#!/usr/bin/env python3
"""Own, fetch and remove bounded diagnostic speaker-PCM files (private output only).

Firmware writes only explicitly pre-armed files, identified by a fresh nonce.
This tool does not flash, play audio, enable logging or change model/policy.
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

from p4speakerparity import Device

DIR='/sd/logging_captures'
LIMIT=47840
ARM=struct.Struct('<8s16sII')
HEADER=struct.Struct('<8s16sIIII')


def arm_bytes(seq,nonce):
    if seq not in range(1,7) or len(nonce)!=16 or not any(nonce):raise ValueError('invalid arm identity')
    return ARM.pack(b'SPKARM1\0',nonce,seq,LIMIT)


def parse_capture(data,seq,nonce):
    if len(data)<HEADER.size+32:raise ValueError('short capture')
    magic,token,n,retained,samples,dim=HEADER.unpack_from(data)
    if magic!=b'SPKPCM1\0' or token!=nonce or n!=seq:raise ValueError('capture identity mismatch')
    if not 0<samples<=LIMIT or retained<samples or not 1<=dim<=1024:raise ValueError('capture dimensions invalid')
    if len(data)!=HEADER.size+samples*2+dim*4+32:raise ValueError('capture size invalid')
    if hashlib.sha256(data[:-32]).digest()!=data[-32:]:raise ValueError('capture checksum mismatch')
    embedding=struct.unpack_from('<'+'f'*dim,data,HEADER.size+samples*2)
    if not all(math.isfinite(v) for v in embedding) or sum(v*v for v in embedding)<=0:
        raise ValueError('invalid capture embedding')
    return {'seq':n,'retained_samples':retained,'model_samples':samples,'dim':dim,'embedding':embedding,
            'pcm_bytes':data[HEADER.size:HEADER.size+samples*2]}


def read_file(d,path):
    data=bytearray();size=None
    while size is None or len(data)<size:
        off=len(data)
        m=d.command(f'fileread "{path}" {off} 2048 b64',r'\{"success":(?:true|false),[^\r\n]*\}')
        obj=json.loads(m.group(0))
        if not obj.get('success'):raise RuntimeError('owned capture absent/inaccessible')
        part=base64.b64decode(obj['data'],validate=True)
        if obj['offset']!=off or len(part)!=obj['len']:raise RuntimeError('bad capture read framing')
        if size is None:size=obj['size']
        if obj['size']!=size or size>HEADER.size+2*LIMIT+4096+32 or off+len(part)>size:
            raise RuntimeError('capture changed/oversized')
        if not part and off<size:raise RuntimeError('empty capture read')
        data.extend(part)
    return bytes(data)


def owned_content(data,entry):
    nonce=bytes.fromhex(entry['nonce']);arm=arm_bytes(entry['seq'],nonce)
    # Empty/interrupted initial arm upload, untouched arm, or our nonce-bearing
    # capture (including interrupted capture output). No unrelated file qualifies.
    if len(data)<=len(arm) and data==arm[:len(data)]:return True
    prefix=b'SPKPCM1\0'+nonce
    return (data==prefix[:len(data)] if len(data)<len(prefix) else data.startswith(prefix)) and len(data)<=HEADER.size+2*LIMIT+4096+32


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('command',choices=['prepare','fetch','cleanup']);ap.add_argument('outdir')
    a=ap.parse_args();root=Path(a.outdir)
    if 'private' not in root.parts:ap.error('private output required')
    root.mkdir(parents=True,exist_ok=True,mode=0o700);marker=root/'pcm-ownership.json'
    if a.command=='prepare':
        if marker.exists():raise RuntimeError('ownership marker exists; recover first')
        own={'files':[],'folder_created':False};marker.write_text(json.dumps(own))
        with Device(root/time.strftime('prepare-%Y%m%d-%H%M%S')) as d:
            m=d.command(f'mkdir "{DIR}"',r'(?:Created folder|Folder already exists): '+re.escape(DIR))
            own['folder_created']=m.group(0).startswith('Created');marker.write_text(json.dumps(own))
            for seq in (1,2,3,4):
                path=f'{DIR}/codex_spk_pcm_{seq}.bin';nonce=os.urandom(16);payload=arm_bytes(seq,nonce)
                d.command(f'filecreate "{path}"',r'Created file: '+re.escape(path))
                entry={'seq':seq,'path':path,'nonce':nonce.hex(),'removed':False};own['files'].append(entry);marker.write_text(json.dumps(own))
                encoded=base64.b64encode(payload).decode()
                m=d.command(f'filewrite "{path}" 0 {encoded} final',r'\{"success":(?:true|false),[^\r\n]*\}')
                obj=json.loads(m.group(0))
                if not obj.get('success') or read_file(d,path)!=payload:raise RuntimeError('arm upload failed')
            print(json.dumps({'armed_sequences':[e['seq'] for e in own['files']],'littlefs_before':d.free_before,'littlefs_after':d.free()}))
        return
    own=json.loads(marker.read_text());results=[]
    if not own['files']:raise RuntimeError('no owned files')
    with Device(root/time.strftime(a.command+'-%Y%m%d-%H%M%S')) as d:
        for entry in own['files']:
            if entry['removed']:continue
            path=entry['path']
            if path!=f'{DIR}/codex_spk_pcm_{entry["seq"]}.bin':raise RuntimeError('ownership path mismatch')
            data=read_file(d,path)
            if not owned_content(data,entry):raise RuntimeError('capture no longer matches ownership nonce')
            if a.command=='fetch':
                target=root/f'capture-seq{entry["seq"]}.bin'
                with target.open('xb') as f:f.write(data)
                if data==arm_bytes(entry['seq'],bytes.fromhex(entry['nonce'])):
                    row={'seq':entry['seq'],'captured':False}
                else:
                    row=parse_capture(data,entry['seq'],bytes.fromhex(entry['nonce']));row.pop('pcm_bytes');row.pop('embedding')
                    row.update(captured=True,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
                results.append(row);print(json.dumps(row),flush=True)
            else:
                # Preserve any incomplete capture before removing our file.
                target=root/f'cleanup-recovery-seq{entry["seq"]}.bin'
                if not (root/f'capture-seq{entry["seq"]}.bin').exists():
                    with target.open('xb') as f:f.write(data)
                else:
                    if (root/f'capture-seq{entry["seq"]}.bin').read_bytes()!=data:raise RuntimeError('capture changed after fetch')
                d.command(f'filedelete "{path}" confirm',r'Deleted file: '+re.escape(path))
                entry['removed']=True;marker.write_text(json.dumps(own))
        if a.command=='cleanup' and own['folder_created']:
            m=d.command(f'rmdir "{DIR}"',r'(?:Removed folder|Error: Failed to remove folder[^\r\n]*): '+re.escape(DIR))
            own['folder_removed']=m.group(0).startswith('Removed');marker.write_text(json.dumps(own))
        print(json.dumps({'command_complete':a.command,'littlefs_before':d.free_before,'littlefs_after':d.free()}),flush=True)
    if a.command=='fetch':(root/'captures.json').write_text(json.dumps(results,indent=2))


if __name__=='__main__':main()
