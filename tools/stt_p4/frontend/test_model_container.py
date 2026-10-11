#!/usr/bin/env python3
"""Host ASan/UBSan check of the exact shared runtime envelope validator."""
import argparse
from pathlib import Path
import subprocess
import tempfile
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,default=HERE.parent/'private/full-portable-v2/quartznet5x5.p4.stt')
    args=parser.parse_args()
    production=ROOT/'components/hardwareone/stt'
    with tempfile.TemporaryDirectory(prefix='hw1-stt-container-') as temporary:
        binary=Path(temporary)/'check'
        subprocess.run(['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(HERE/'test_model_container.cpp'),'-I'+str(production),'-o',str(binary)],check=True)
        subprocess.run([str(binary),str(args.model)],check=True)
    source=(production/'quartznet_runtime.cpp').read_text()
    gate=source.index('container::read_header(')
    inflate=source.index('if(!inflateModel(')
    checksum=source.index('if(!digest(raw.p,')
    constructor=source.index('new(std::nothrow) dl::Model(')
    if not gate<inflate<checksum<constructor:raise AssertionError('Envelope/checksum no longer precede vendor parser')
    print('Canonical production validator tested; envelope, decompression, checksum and vendor-constructor order verified')
if __name__=='__main__':main()
