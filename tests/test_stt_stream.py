"""Exercise production portable streaming and frontend code, with no model/device fakes."""
from pathlib import Path
import argparse,os,subprocess,tempfile
parser=argparse.ArgumentParser()
parser.add_argument("--thread-sanitize",action="store_true")
args=parser.parse_args()
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'firmware/components/hw1_stt'
with tempfile.TemporaryDirectory(prefix='stt-stream-') as temp:
    exe=Path(temp)/'stream'
    subprocess.run(['clang++','-std=c++17','-pthread','-O2','-ffp-contract=off','-Wall','-Wextra','-Werror',
                    '-Wno-unused-private-field','-fsanitize='+('thread' if args.thread_sanitize else 'address,undefined'),'-fno-omit-frame-pointer',
                    '-I'+str(SRC),str(ROOT/'tests/stt_stream_test.cpp'),str(SRC/'stt/stt_stream.cpp'),
                    str(SRC/'stt/quartznet_frontend.cpp'),'-o',str(exe)],check=True)
    env=dict(os.environ)
    # Darwin defaults can hide accesses inside memcpy; the copy control test
    # validates this explicit policy before interpreting a clean stream run.
    if args.thread_sanitize:env['TSAN_OPTIONS']='halt_on_error=1:abort_on_error=0:exitcode=66:symbolize=0:ignore_interceptors_accesses=0'
    subprocess.run([str(exe)],env=env,check=True)
