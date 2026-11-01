#!/usr/bin/env python3
"""Exercise the actual diagnostic lease/release header with a synthetic CPU."""
import argparse,subprocess,tempfile
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('hardwareone',type=Path);a=ap.parse_args()
header=(a.hardwareone/'components/hardwareone/stt/heap_trigger_lease.h').resolve()
source=r'''#include "HEADER"
#include <cassert>
using namespace hw1::stt;
struct Cpu {
 inline static unsigned chosen=2,irq=7,writes=0,debug=0,ctl=0;
 inline static HeapTriggerSlot slots[3]={{0,kHeapTriggerReset,0,0},{1,kHeapTriggerReset,0,0},{2,kHeapTriggerReset,0,0}};
 static unsigned core(){return 1;}
 static unsigned debugger(){return debug;}
 static unsigned maskInterrupts(){auto old=irq;irq=15;return old;}
 static void restoreInterrupts(unsigned v){irq=v;}
 static unsigned select(){return chosen;}
 static void select(unsigned v){chosen=v;}
 static unsigned control(){return ctl;}
 static unsigned data1(){return slots[chosen].data1;}
 static unsigned data2(){return slots[chosen].data2;}
 static unsigned data3(){return slots[chosen].data3;}
 static void writeData1(unsigned v){++writes;slots[chosen].data1=kHeapTriggerReset|v;}
 static void writeData2(unsigned v){++writes;slots[chosen].data2=v;}
 static void writeData3(unsigned v){++writes;slots[chosen].data3=v;}
 static void writeControl(unsigned v){++writes;ctl=v;}
};
int main(){
 auto r=readHeapTriggers<Cpu>();assert(heapTriggersIdle(r,1));
 assert(heapTriggerRelease<Cpu>(1,0x50100000) && Cpu::writes==0 && Cpu::irq==7 && Cpu::chosen==2);
 assert(!heapTriggersIdle(r,0));r.debugger=1;assert(!heapTriggersIdle(r,1));r.debugger=0;
 r.slots[1].data3=1;assert(!heapTriggersIdle(r,1));r.slots[1].data3=0;
 Cpu::slots[0].data1=kHeapTriggerStore4;Cpu::slots[0].data2=0x50100001;Cpu::ctl=0x88;
 r=readHeapTriggers<Cpu>();assert(heapTriggerOwned(r,1,0x50100000));
 assert(!heapTriggerOwned(r,0,0x50100000));assert(!heapTriggerOwned(r,1,0x50100004));
 assert(!heapTriggerOwned(r,1,0x50100001));
 for(unsigned bad=0;bad<6;++bad){
   const auto saved=Cpu::slots[0];const auto ctl=Cpu::ctl;
   if(bad==0)Cpu::slots[0].data2+=4;
   if(bad==1)Cpu::slots[0].data3=1;
   if(bad==2)Cpu::slots[0].data1^=1;
   if(bad==3)Cpu::ctl|=1;
   if(bad==4)Cpu::debug=1;
   if(bad==5)Cpu::slots[1].data1=kHeapTriggerStore4;
   assert(!heapTriggerRelease<Cpu>(1,0x50100000));assert(!Cpu::writes && Cpu::irq==7 && Cpu::chosen==2);
   Cpu::slots[0]=saved;Cpu::ctl=ctl;Cpu::debug=0;Cpu::slots[1].data1=kHeapTriggerReset;
 }
 Cpu::slots[0].data1|=kHeapTriggerHit;Cpu::ctl=0x80;
 assert(heapTriggerRelease<Cpu>(1,0x50100000));assert(Cpu::writes==4 && Cpu::irq==7 && Cpu::chosen==2);
 assert(heapTriggersIdle(readHeapTriggers<Cpu>(),1));
}
'''.replace('HEADER',str(header))
with tempfile.TemporaryDirectory(prefix='heap-trigger-lease-') as d:
 p=Path(d);(p/'test.cpp').write_text(source)
 subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('heap trigger lease: owner refusal, exact release, hit state and IRQ restoration ok')
