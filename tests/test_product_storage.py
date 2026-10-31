#!/usr/bin/env python3
"""Actual product.cpp persistence/command code with host SD and narrow SDK stubs.
Uses unmodified cJSON from CJSON_DIR, an ESP-IDF checkout (IDF_PATH), or the handoff dependency folder.
Does not emulate the FAT driver, flash/NVS transactions, microphone or model.
"""
from pathlib import Path
import json, os, subprocess, tempfile
ROOT = Path(__file__).resolve().parents[1]
candidates = []
if os.environ.get('CJSON_DIR'): candidates.append(Path(os.environ['CJSON_DIR']))
if os.environ.get('IDF_PATH'): candidates.append(Path(os.environ['IDF_PATH']) / 'components/json/cJSON')
candidates.append(ROOT.parent / 'dependencies/cjson')
CJSON = next((p for p in candidates if (p/'cJSON.c').is_file() and (p/'cJSON.h').is_file()), None)
if CJSON is None:
    raise SystemExit('Set IDF_PATH to ESP-IDF or CJSON_DIR to the folder containing cJSON.c and cJSON.h. The portable handoff includes dependencies/cjson.')
with tempfile.TemporaryDirectory(prefix='hw1-storage-') as tmp:
    temp = Path(tmp); sd = temp / 'sd'; (sd / 'STT Models').mkdir(parents=True)
    common = ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    obj = temp / 'cJSON.o'; exe = temp / 'test'
    subprocess.run(['clang',*common,'-Wno-deprecated-declarations','-c',str(CJSON/'cJSON.c'),'-o',str(obj)],check=True)
    includes = [ROOT/'tests/product_stubs',CJSON,ROOT/'firmware/components/hw1_transcript',ROOT/'firmware/components/hw1_stt',ROOT/'firmware/examples/p4_eye_captions/main']
    sources = [ROOT/'tests/product_storage_test.cpp',ROOT/'firmware/examples/p4_eye_captions/main/product.cpp',ROOT/'firmware/components/hw1_transcript/transcript.cpp',ROOT/'firmware/components/hw1_stt/stt/stt_lm.cpp']
    subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror',*common,f'-DHW1_PRODUCT_SD_ROOT="{sd}"',*[v for p in includes for v in ('-I',str(p))],*map(str,sources),str(obj),'-o',str(exe)],check=True)
    def run(**env):
        output = subprocess.check_output([str(exe)],env={**os.environ,**env},text=True)
        return [json.loads(l[10:]) for l in output.splitlines() if l.startswith('STT_EVENT ')]
    events=run()
    files=list((sd/'STT Notes').glob('*.jsonl')); assert len(files)==1
    records=[json.loads(l) for l in files[0].read_text().splitlines()]
    assert [r['type'] for r in records]==['start','final','final','end']
    assert records[1]['rawText']=='i use hardwareone' and records[1]['text']=='I use HardwareOne'
    assert records[2]['rawText']=="and i'd like openai" and records[2]['text']=="and I'd like OpenAI"
    assert records[0]['clockKnown'] is True  # host clock; embedded date may be unavailable
    assert events[-1]['bootNumber']=='2' and events[-1]['bootDurable']
    assert (sd/'STT Models/user_vocab.tsv').read_text()=='OpenAI\topenai\n'
    assert any(e['type']=='message' and not e['ok'] for e in events)
    # Simulated interrupted promotion: old backup is recovered when main is absent.
    words=sd/'STT Models/user_vocab.tsv'; words.unlink()
    recovered=run(LOAD_ONLY='1')
    vocab=next(e for e in recovered if e['type']=='vocabulary')
    assert {w['spoken'] for w in vocab['words']}=={'hardwareone','openai'}
    large=run(LARGE_RECORD='1')
    archived=[e['record'] for e in large if e['type']=='archive']
    assert [e['type'] for e in archived]==['start','final','end']
    assert len(archived[1]['text'])==4095 and archived[1]['formatted']
    assert len(json.dumps(archived[1]))>8192
    assert not any('Incomplete recording line' in e.get('text','') for e in large)
    failed=run(FAIL_NVS='1')
    assert not failed[-1]['bootDurable'] and failed[-1]['bootNumber']=='0'
    print('product storage/commands: raw preservation, LM words, failed validation, finalization, unsaved isolation, backup recovery and counter failure passed')
