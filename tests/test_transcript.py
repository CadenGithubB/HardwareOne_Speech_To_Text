#!/usr/bin/env python3
"""Compile portable production code with memory/undefined behavior sanitizers."""
from pathlib import Path
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='hw1-transcript-') as tmp:
    exe = str(Path(tmp) / 'test')
    src = ROOT / 'firmware/components/hw1_transcript'
    subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    '-I', str(src), str(src / 'transcript.cpp'),
                    str(ROOT / 'tests/transcript_test.cpp'), '-o', exe], check=True)
    subprocess.run([exe], check=True)
