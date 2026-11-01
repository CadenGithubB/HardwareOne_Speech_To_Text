#!/usr/bin/env python3
"""Compile the production trigger-read helper with synthetic CPU services."""
import argparse
from pathlib import Path
import subprocess
import tempfile
ap=argparse.ArgumentParser();ap.add_argument('hardwareone',type=Path);a=ap.parse_args()
header=a.hardwareone/'components/hardwareone/stt/heap_trigger_read.h';assert header.exists()
source='''#include "HEADER"
#include <cassert>
#include <vector>
struct Cpu {
 inline static unsigned chosen=2,irq=7,restored=99,reads=0;
 inline static bool deny=false,controlChanges=false;
 inline static std::vector<unsigned> writes;
 static unsigned core(){return 1;}
 static unsigned debugger(){return 1;}
 static unsigned maskInterrupts(){unsigned old=irq;irq=15;return old;}
 static void restoreInterrupts(unsigned old){restored=old;irq=old;}
 static unsigned select(){return chosen;}
 static void select(unsigned x){writes.push_back(x);chosen=(deny && x==1)?0:x;}
 static unsigned control(){return controlChanges && reads++ ? 0x89:0x88;}
 static unsigned data1(){return 0x20000000+chosen;}
 static unsigned data2(){return 100+chosen;}
 static unsigned data3(){return 1000+chosen;}
};
int main(){
 auto r=hw1::stt::readHeapTriggers<Cpu>();
 assert(r.core==1 && r.debugger==1 && r.restored && r.selected);
 assert(r.before==2 && r.after==2 && Cpu::chosen==2 && Cpu::irq==7 && Cpu::restored==7);
 assert((Cpu::writes==std::vector<unsigned>{0,1,2,2}));
 for(unsigned i=0;i<3;++i)assert(r.slots[i].selected==i && r.slots[i].data1==0x20000000+i && r.slots[i].data2==100+i && r.slots[i].data3==1000+i);
 Cpu::deny=true;Cpu::writes.clear();r=hw1::stt::readHeapTriggers<Cpu>();
 assert(!r.selected && r.restored && Cpu::chosen==2 && Cpu::irq==7);
 Cpu::deny=false;Cpu::controlChanges=true;Cpu::reads=0;r=hw1::stt::readHeapTriggers<Cpu>();
 assert(!r.restored && r.controlBefore==0x88 && r.controlAfter==0x89 && Cpu::chosen==2 && Cpu::irq==7);
}
'''.replace('HEADER',str(header.resolve()))
with tempfile.TemporaryDirectory(prefix='heap-trigger-read-') as tmp:
 p=Path(tmp);(p/'test.cpp').write_text(source)
 subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('heap trigger read: slot/IRQ restoration and changed-state rejection ok')
