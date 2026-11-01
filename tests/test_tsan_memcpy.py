#!/usr/bin/env python3
"""Calibrate TSAN copy visibility before interpreting a clean ring test."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
ap=argparse.ArgumentParser();ap.add_argument('--evidence',type=Path);a=ap.parse_args()
if a.evidence:
    if 'private' not in a.evidence.parts:ap.error('evidence must stay private')
    a.evidence.mkdir(parents=True,exist_ok=True)
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='tsan-copy-') as temp:
    binary=Path(temp)/'control'
    subprocess.run([os.environ.get('CXX','clang++'),'-std=c++17','-O1','-g','-pthread','-fsanitize=thread',str(root/'tests/tsan_memcpy_control.cpp'),'-o',str(binary)],check=True)
    for ignored,locked in ((True,False),(False,False),(False,True)):
        options=f'halt_on_error=1:abort_on_error=0:exitcode=66:symbolize=0:ignore_interceptors_accesses={int(ignored)}'
        r=subprocess.run([str(binary)]+(['--locked'] if locked else []),env={**os.environ,'TSAN_OPTIONS':options},capture_output=True,text=True,timeout=60)
        detected='ThreadSanitizer: data race' in r.stderr
        expected=not ignored and not locked
        if a.evidence:
            with (a.evidence/f'ignore-{int(ignored)}-locked-{int(locked)}.txt').open('x') as f:f.write(r.stdout+r.stderr)
        assert r.returncode==(66 if expected else 0) and detected==expected,(ignored,locked,r.returncode)
        print(f'tsan memcpy: ignore_interceptors={int(ignored)} locked={int(locked)} race_detected={int(detected)}')
print('tsan memcpy: positive and negative controls ok')
