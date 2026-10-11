#!/usr/bin/env python3
"""Test the actual staged/production local Dictation functions with fake STT."""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'components/hardwareone/test/host'))
from test_espsr_runtime import function

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--production',action='store_true')
    p.add_argument('--sanitize',action='store_true')
    args=p.parse_args()
    base=ROOT/'components/hardwareone' if args.production else HERE/'components/hardwareone'
    source=(base/'System_Dictation.cpp').read_text()
    stt_header=(base/'System_STT.h').read_text()
    local_header=(ROOT/'components/hardwareone/System_STTLocal.h').read_text()
    headers=re.sub(r'^#include.*\n|^#pragma once\n','',local_header+'\n'+stt_header,flags=re.M)
    controls=source[source.index('struct DictationPublishedCapture'):source.index('// Capability is deliberately')]
    local=source[source.index('#if ENABLE_LOCAL_STT\n// A local exchange'):source.index('#endif // ENABLE_LOCAL_STT',source.index('// A local exchange'))]+'\n#endif\n'
    harness=(HERE/'local_provider_harness.cpp').read_text()
    harness=harness.replace('// INSERT_HEADERS',headers)
    harness=harness.replace('// INSERT_CONTROL',controls)
    harness=harness.replace('// INSERT_LOCAL',local)
    harness=harness.replace('// INSERT_DRAIN',function(source,'bool dictationTakeTextFor('))
    harness=harness.replace('// INSERT_STOP',function(source,'void dictationRequestStopFor('))
    # Verify the old host body remains selected by the compile-time provider
    # branch, and local tokens cannot enter either UART completion operation.
    assert 'return dictationBeginLocal(displaySource, displayEpoch);\n#endif' in function(source,'bool dictationBeginFor(')
    assert 'gDict.requestHostEpoch != 0' in function(source,'static const char* dictDeliver(')
    assert 'gDict.requestHostEpoch != 0' in function(source,'static const char* dictationHandleArgs(')
    with tempfile.TemporaryDirectory(prefix='hw1-local-dictation-') as tmp:
        unit=Path(tmp)/'test.cpp';exe=Path(tmp)/'test';unit.write_text(harness)
        cmd=['clang++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-missing-field-initializers',str(unit),'-o',str(exe),'-I',str(ROOT/'components/hardwareone')]
        if args.sanitize:cmd[1:1]=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        subprocess.run(cmd,check=True);subprocess.run([str(exe)],check=True)

if __name__=='__main__':main()
