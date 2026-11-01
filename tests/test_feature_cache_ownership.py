#!/usr/bin/env python3
"""Reproduce late writes/races in extracted production code, then check a fix.

Default: ASan/UBSan and deterministic late-write schedules. --thread-sanitize
expects the reference overlap schedules to report a data race; candidate must
pass. Before a candidate exists, --reference-only records the positive control.
--ring-candidate adds the stable-PCM-window repair as a third variant.
--parity checks 104 input/offset cases, including long-phrase cached tails.
Optional --evidence PRIVATE_DIR retains sanitizer diagnostics privately.
"""
import argparse
import os
import re
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--thread-sanitize',action='store_true')
p.add_argument('--ring-candidate',action='store_true',help='also test the separate stable-PCM-window repair; bind current source to it')
p.add_argument('--parity',action='store_true',help='104 input/offset cases for all enabled worker variants')
p.add_argument('--ring-audit',action='store_true',help='reproduce the separate live-ring copy/read race in both current workers')
p.add_argument('--reference-only',action='store_true');p.add_argument('--evidence',type=Path)
p.add_argument('--hardwareone',type=Path,help='also bind extracted loops to the actual checkout and aa6508fd baseline')
a=p.parse_args()
if a.parity and a.ring_audit:p.error("choose parity or ring-audit")
if a.reference_only and a.ring_candidate:p.error("reference-only cannot select a repair candidate")
if a.hardwareone:
    def function(source,name):
        start=re.search(r'static (?:void|bool) '+name+r'\(',source).start();at=source.index('{',start)+1;depth=1
        while depth:
            depth+=(source[at]=='{')-(source[at]=='}');at+=1
        return source[start:at]+'\n'
    current=(a.hardwareone/'components/hardwareone/System_STT.cpp').read_text()
    # A separately committed P4 probe can pause only its synthetic run before
    # DSP. Strip that exact scheduling hook; it does not publish/wipe cache data.
    hook='#if HW1_STT_SPEAKER_DIAGNOSTICS\n      sttFeatureProbeGate(run);\n#endif\n'
    current=current.replace(hook,'')
    baseline=subprocess.check_output(['git','show','aa6508fd:components/hardwareone/System_STT.cpp'],cwd=a.hardwareone,text=True)
    folder=root/'tools/device_tests/feature_cache'
    cache_source=subprocess.check_output(['git','show','3fff3013:components/hardwareone/System_STT.cpp'],cwd=a.hardwareone,text=True) if a.ring_candidate else current
    variants=[('reference',baseline),('candidate',cache_source)]+([('ring_candidate',current)] if a.ring_candidate else [])
    for tag,source in variants:
        if tag=='candidate' and a.reference_only:continue
        expected=function(source,'sttFeatureWorker').replace('hw1::stt::log_mel_frame_ring(','observed_log_mel_frame_ring(')
        assert (folder/f'worker_{tag}.inc').read_text().split('\n',1)[1]==expected,tag
    assert function(baseline,'sttFeatureRingWrite')==function(cache_source,'sttFeatureRingWrite')
    if a.ring_candidate:
        assert (folder/'ring_writer_candidate.inc').read_text().split('\n',1)[1]==function(current,'sttFeatureRingWrite')
        assert (folder/'ring_snapshot_candidate.inc').read_text().split('\n',2)[2]==function(current,'sttFeatureSnapshot')
        assert 'constexpr size_t kFeWindowSamples = 512;' in current
    assert (folder/'ring_writer_reference.inc').read_text().split('\n',1)[1]==function(baseline,'sttFeatureRingWrite')
    retired=''.join(function(baseline,n) for n in ('sttWipe','sttFeatureRetireOrphans','sttFeatureRelease'))
    assert retired==(folder/'retirement_reference.inc').read_text().split('\n',1)[1]
    assert (a.hardwareone/'components/hardwareone/stt/quartznet_frontend.cpp').read_bytes()==(root/'firmware/components/hw1_stt/stt/quartznet_frontend.cpp').read_bytes()
    assert 'kStreamReadSamples = 1024;' in current
    print('feature ownership: extracted paths bound to production sources')
if a.evidence:
    if 'private' not in a.evidence.parts:p.error('evidence must be private')
    a.evidence.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='feature-ownership-') as tmp:
    binary=Path(tmp)/'audit';src=root/'firmware/components/hw1_stt'
    flags=(['-DHAVE_CANDIDATE'] if not a.reference_only else [])+(['-DHAVE_RING_CANDIDATE'] if a.ring_candidate else [])
    subprocess.run([os.environ.get('CXX','clang++'),'-std=c++17','-pthread','-O1','-g',
        '-ffp-contract=off','-Wall','-Wextra','-Werror',
        '-fsanitize='+('thread' if a.thread_sanitize else 'address,undefined'),'-fno-omit-frame-pointer',
        *flags,'-I'+str(src),'-I'+str(root/'tools/device_tests/feature_cache'),
        str(root/'tests/feature_cache_ownership_test.cpp'),str(src/'stt/quartznet_frontend.cpp'),'-o',str(binary)],check=True)
    for variant in ([0] if a.reference_only else ([0,1,2] if a.ring_candidate else [0,1])):
        fixed=variant>0;ring_fixed=variant==2
        for kind in (('parity',) if a.parity else ('ring_overlap',) if a.ring_audit else ('orphan','attached','live','failed_dsp')):
            attached=kind=='attached';ring_overlap=kind=='ring_overlap';live=kind in ('live','failed_dsp','ring_overlap')
            args=(['--ring-candidate'] if ring_fixed else ['--candidate'] if fixed else [])+(['--parity'] if kind=='parity' else [])+(['--attached'] if attached else [])+(['--ring-overlap'] if ring_overlap else (['--live'] if live else []))+(['--fail-dsp'] if kind=='failed_dsp' else [])+(['--overlap'] if a.thread_sanitize and not live else [])
            env={**os.environ,'TSAN_OPTIONS':'halt_on_error=1:abort_on_error=0:exitcode=66:symbolize=0:ignore_interceptors_accesses=0'}
            result=subprocess.run([str(binary),*args],env=env,capture_output=True,text=True)
            if a.evidence:
                tag=f'{"ring_candidate" if ring_fixed else "candidate" if fixed else "reference"}-{kind}-{"tsan" if a.thread_sanitize else "asan"}'
                with (a.evidence/(tag+'.txt')).open('x') as f:f.write(result.stdout+result.stderr)
            if a.thread_sanitize and ((ring_overlap and not ring_fixed) or (not fixed and not live and kind!='parity')):
                assert result.returncode==66 and 'ThreadSanitizer: data race' in result.stderr,(result.returncode,result.stderr)
                print(f'feature ownership: candidate={int(fixed)} attached={int(attached)} ring_overlap={int(ring_overlap)} data_race_detected=1')
            else:
                if result.returncode:raise RuntimeError(result.stdout+result.stderr)
                assert 'ThreadSanitizer' not in result.stderr
                print(result.stdout.strip())
