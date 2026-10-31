"""Compile production LM decoder against the independent synthetic reference oracle."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='stt-lm-') as temp:
    exe=Path(temp)/'lm'
    subprocess.run(['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined','-fno-omit-frame-pointer',
                    '-I'+str(ROOT/'firmware/components/hw1_stt'),str(ROOT/'tests/test_stt_lm.cpp'),
                    str(ROOT/'firmware/components/hw1_stt/stt/stt_lm.cpp'),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
