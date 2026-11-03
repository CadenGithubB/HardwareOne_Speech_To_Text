"""Compile the actual experimental gate: deadline, clearing and clock rollover."""
from pathlib import Path
import tempfile,subprocess
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp);(p/'test.cpp').write_text(r'''
#include "speaker_draft_gate.h"
#include <cassert>
using hw1::stt::speaker::DraftGate;
int main() {
 DraftGate a;
 assert(!a.defer(false,0,0));
 assert(a.defer(true,1,0));assert(a.defer(true,999999,0));
 assert(!a.defer(false,1000000,0));assert(!a.waiting);
 DraftGate b;
 assert(b.defer(true,0,100));assert(b.defer(true,99,100));
 assert(!b.defer(true,100,100));assert(!b.waiting);
 assert(b.defer(true,101,100));
 assert(!b.defer(false,110,100));assert(b.defer(true,120,100));
 assert(b.defer(true,219,100));assert(!b.defer(true,220,100));
 DraftGate c;
 assert(c.defer(true,0xfffffff0u,100));
 assert(c.defer(true,83,100));assert(!c.defer(true,84,100));
 c.reset();assert(!c.waiting);
}
''')
 subprocess.run(['c++','-std=c++17','-fsanitize=address,undefined','-I'+str(root/'firmware/components/hw1_stt/stt'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('speaker draft gate checks passed')
