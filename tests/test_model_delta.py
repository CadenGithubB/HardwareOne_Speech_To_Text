"""Exercise the actual bounded diagnostic delta decoder under ASan/UBSan."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

parser=argparse.ArgumentParser()
parser.add_argument('--base',type=Path)
parser.add_argument('--delta',type=Path)
parser.add_argument('--target',type=Path)
args=parser.parse_args()
paths=[args.base,args.delta,args.target]
if any(paths):
    assert all(paths),'Provide all three private model paths'
    patch=args.delta.read_bytes()
    assert len(patch)>=88
    assert hashlib.sha256(args.base.read_bytes()).digest()==patch[24:56]
    assert hashlib.sha256(args.target.read_bytes()).digest()==patch[56:88]
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='stt-model-delta-') as temp:
    exe=Path(temp)/'delta'
    subprocess.run(['clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined','-fno-omit-frame-pointer',
                    '-I'+str(root/'tools/device_tests/stream'),
                    str(root/'tests/model_delta_test.cpp'),'-o',str(exe)],check=True)
    subprocess.run([str(exe),*([str(p) for p in paths] if all(paths) else [])],check=True)
