#!/usr/bin/env python3
"""Exercise the actual QuartzNet runtime's cache ownership with bounded host fakes.

This does not qualify ESP heap behavior, cryptography, decompression correctness,
model numerics or acoustic accuracy. The real runtime, public interfaces and
container reader are compiled unchanged except for removing platform includes;
controlled dependencies expose lifecycle, ordering and failure boundaries.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'firmware/components/hw1_stt'


def no_includes(text):
    return re.sub(r'^#include.*\n', '', text, flags=re.M).replace('#pragma once', '')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize', action='store_true', help='AddressSanitizer and UBSan')
    parser.add_argument('--resident', type=int, choices=(0, 1),
                        help='only this HW1_STT_RESIDENT_MODEL value (default: both)')
    parser.add_argument('--model-local-prepare', type=int, choices=(0, 1),
                        help='only this preparation API setting (default: both)')
    args = parser.parse_args()
    # Per-call models (=0) and the resident model with its PSRAM metadata hook
    # (=1, the firmware default) each have their own harness.
    for resident in ((args.resident,) if args.resident is not None else (0, 1)):
        for local_prepare in ((args.model_local_prepare,) if args.model_local_prepare is not None else (0, 1)):
            run(resident, 'quartznet_cache_harness_resident.cpp' if resident else 'quartznet_cache_harness.cpp',
                args.sanitize, local_prepare)


def run(resident, harness_name, sanitize, local_prepare):
    interface = '\n'.join(no_includes((SOURCE / name).read_text()) for name in (
        'System_STTLocal.h', 'stt/quartznet_runtime.h', 'stt/quartznet_frontend.h',
        'stt/stt_internal_memory.h', 'stt/stt_internal_memory_core.h'))
    interface += '''
namespace hw1::stt {
InternalMemoryBudget internalMemoryBudget(bool resident) { return InternalMemoryPolicy{}.budget(resident); }
InternalMemoryScope::InternalMemoryScope() {}
InternalMemoryScope::~InternalMemoryScope() {}
void InternalMemoryScope::success(bool) {}
}
'''
    runtime = no_includes((SOURCE / 'stt/quartznet_runtime.cpp').read_text())
    container = no_includes((SOURCE / 'stt/stt_model_container.h').read_text())
    harness = (HERE / harness_name).read_text()
    for marker, contents in (('// INSERT_INTERFACE', interface),
                             ('// INSERT_CONTAINER', container),
                             ('// INSERT_RUNTIME', runtime)):
        assert harness.count(marker) == 1, marker
        harness = harness.replace(marker, contents)
    with tempfile.TemporaryDirectory(prefix='hw1-quartznet-cache-') as tmp:
        unit = Path(tmp) / 'test.cpp'
        unit.write_text(harness)
        for diagnostics in (0, 1):
            exe = Path(tmp) / f'test-{diagnostics}'
            cmd = ['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-unused-private-field',
                   f'-DHW1_STT_RUNTIME_DIAGNOSTICS={diagnostics}', f'-DHW1_STT_RESIDENT_MODEL={resident}',
                   f'-DCONFIG_HW1_STT_MODEL_LOCAL_PREPARE={local_prepare}',
                   str(unit), '-o', str(exe)]
            if sanitize:
                cmd[1:1] = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
            subprocess.run(cmd, check=True, timeout=120)
            subprocess.run([str(exe)], check=True, timeout=90)


if __name__ == '__main__':
    main()
