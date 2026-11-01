#!/usr/bin/env python3
"""Build the real frontend against a frozen reference; optionally benchmark or sanitize."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group();g.add_argument('--bench',action='store_true');g.add_argument('--sanitize',action='store_true');a=p.parse_args()
flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if a.sanitize else ['-O2']
with tempfile.TemporaryDirectory(prefix='speaker-frontend-equivalence-') as tmp:
    binary=Path(tmp)/'equivalence'
    subprocess.run([os.environ.get('CXX','c++'),'-std=c++17',*flags,'-I'+str(root/'firmware/components/hw1_stt/stt'),'-I'+str(root/'tests'),
        str(root/'tests/test_speaker_frontend_equivalence.cpp'),str(root/'tests/reference/speaker_frontend_92b028c.cpp'),
        str(root/'firmware/components/hw1_stt/stt/speaker_frontend.cpp'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)]+(['--bench'] if a.bench else []),check=True)
