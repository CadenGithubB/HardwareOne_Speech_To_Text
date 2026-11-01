#!/usr/bin/env python3
"""Compare extracted real baseline/candidate loops under ASan/UBSan.

This proves call/argument equivalence on synthetic rectangles, not the target
assembly kernel's numeric output, cache behavior or inference performance.
"""
import os
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='pointwise-address-') as tmp:
    exe=Path(tmp)/'audit'
    subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-O1','-g',
        '-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',
        '-I'+str(root/'tools/device_tests/kernels'),str(root/'tests/pointwise_address_test.cpp'),
        '-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
