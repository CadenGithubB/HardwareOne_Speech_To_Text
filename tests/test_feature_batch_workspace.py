#!/usr/bin/env python3
"""Actual incremental frontend scratch-alias contract under ASan/UBSan."""
import os
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1];src=root/'firmware/components/hw1_stt'
with tempfile.TemporaryDirectory(prefix='feature-batch-workspace-') as tmp:
    exe=Path(tmp)/'audit'
    subprocess.run([os.environ.get('CXX','clang++'),'-std=c++17','-O2','-g','-ffp-contract=off',
        '-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',
        '-I'+str(src),str(root/'tests/feature_batch_workspace_test.cpp'),
        str(src/'stt/quartznet_frontend.cpp'),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
