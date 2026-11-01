#!/usr/bin/env python3
"""Compile the actual diagnostic probe with host stand-ins for ESP services."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
ap=argparse.ArgumentParser();ap.add_argument('hardwareone',type=Path);a=ap.parse_args()
header=a.hardwareone/'components/hardwareone/stt/teardown_probe.h';assert header.is_file()
with tempfile.TemporaryDirectory(prefix='teardown-probe-') as temp:
    root=Path(temp)
    (root/'esp_heap_caps.h').write_text('''#pragma once
#include <cstddef>
constexpr unsigned MALLOC_CAP_INTERNAL=1,MALLOC_CAP_8BIT=2,MALLOC_CAP_SPIRAM=4;
extern bool healthy;
inline bool heap_caps_check_integrity_all(bool){return healthy;}
inline size_t heap_caps_get_free_size(unsigned){return 100;}
''')
    (root/'esp_timer.h').write_text('#pragma once\n#include <cstdint>\ninline int64_t esp_timer_get_time(){static int64_t t=0;return ++t*1000;}\n')
    (root/'esp_rom_sys.h').write_text('#pragma once\n#include <cstdio>\n#define esp_rom_printf std::printf\n')
    source=root/'probe.cpp'
    source.write_text(f'#include "{header}"\nbool healthy=true;\nint main(int argc,char**){{healthy=argc==1;hw1::stt::teardownProbe(200);std::fflush(stdout);}}\n')
    cc=[os.environ.get('CXX','clang++'),'-std=c++17','-DESP_PLATFORM=1','-I'+str(root),str(source)]
    # Undefined policy is a build error instead of silently compiling out markers.
    r=subprocess.run(cc+['-fsyntax-only'],capture_output=True,text=True)
    assert r.returncode and 'every source uses the same diagnostics policy' in r.stderr
    for enabled in (0,1):
        binary=root/f'probe{enabled}'
        subprocess.run(cc+[f'-DHW1_STT_SPEAKER_DIAGNOSTICS={enabled}','-include','cstdio','-o',str(binary)],check=True)
        r=subprocess.run([str(binary)],capture_output=True,text=True,check=True)
        assert ('event=0' in r.stdout)==bool(enabled)
        assert ('heap_ok=1' in r.stdout)==bool(enabled)
print('teardown probe: enabled, disabled and missing-policy builds ok')
