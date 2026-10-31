#!/usr/bin/env python3
"""Exercise task-filtered heap hooks and bounded admission accounting."""
from pathlib import Path
import argparse, re, subprocess, tempfile
p=argparse.ArgumentParser();p.add_argument('--sanitize',action='store_true');args=p.parse_args()
root=Path(__file__).resolve().parents[1]/'firmware/components/hw1_stt/stt'
def body(name):
    return re.sub(r'^#include.*\n|^#pragma once\n','',(root/name).read_text(),flags=re.M)
preamble='''
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cassert>
#include <cstdio>
#define IRAM_ATTR
#define ESP_LOGI(...) ((void)0)
using TaskHandle_t=void*;
static TaskHandle_t current=(void*)1;
static bool isr=false;
static void* external=(void*)9999;
bool xPortInIsrContext(){return isr;}
TaskHandle_t xTaskGetCurrentTaskHandle(){return current;}
bool esp_ptr_internal(void* p){return p && p!=external;}
'''
tests='''
int main(){
 using namespace hw1::stt;
 InternalMemoryLedger l;
 l.allocated((void*)10,200);l.allocated((void*)11,100);l.freed((void*)10);
 l.allocated((void*)12,400);assert(l.sample().peak==500 && l.sample().largest==400);
 l.allocated((void*)12,450);assert(l.live==550 && l.peak==550);
 l.freed((void*)11);l.freed((void*)12);assert(l.live==0);
 for(size_t i=1;i<=129;++i)l.allocated((void*)i,1);
 assert(!l.sample().complete);
 InternalMemoryPolicy p;p.observe(false,l.sample());assert(!p.measured[0].complete);
#if CONFIG_HEAP_USE_HOOKS
 {InternalMemoryScope scope;
  esp_heap_trace_alloc_hook((void*)10,200000,0);
  current=(void*)2;esp_heap_trace_alloc_hook((void*)11,900000,0);
  current=(void*)1;esp_heap_trace_alloc_hook(external,900000,0);
  isr=true;esp_heap_trace_alloc_hook((void*)12,900000,0);isr=false;
  esp_heap_trace_free_hook((void*)10);
  esp_heap_trace_alloc_hook((void*)13,100,0);
  scope.success(false);
 }
 assert(internalMemoryBudget(false).total==200000+32768);
 assert(internalMemoryBudget(false).contiguous==201024);
 assert(internalMemoryBudget(true).total==128*1024);
 {InternalMemoryScope cancelled;esp_heap_trace_alloc_hook((void*)14,999999,0);}
 assert(internalMemoryBudget(false).total==232768);
 {InternalMemoryScope nestedOuter;esp_heap_trace_alloc_hook((void*)15,1000,0);
  {InternalMemoryScope nestedInner;nestedInner.success(true);}
  current=(void*)2;
  {InternalMemoryScope otherTask;esp_heap_trace_alloc_hook((void*)17,999999,0);otherTask.success(true);}
  current=(void*)1;
  esp_heap_trace_alloc_hook((void*)16,2000,0);nestedOuter.success(true);}
 assert(policy.measured[1].peak==3000);
#else
 {InternalMemoryScope scope;scope.success(false);}
 assert(internalMemoryBudget(false).total==150*1024);
#endif
 puts("Speech task allocation accounting, fragmentation budgets, overflow and disabled hooks passed");
}
'''
with tempfile.TemporaryDirectory(prefix='hw1-stt-internal-') as tmp:
    unit=Path(tmp)/'test.cpp';unit.write_text(preamble+body('stt_internal_memory.h')+body('stt_internal_memory_core.h')+body('stt_internal_memory.cpp')+tests)
    for enabled in (0,1):
        exe=Path(tmp)/f'test-{enabled}'
        cmd=['clang++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-variable','-Wno-unused-private-field',f'-DCONFIG_HEAP_USE_HOOKS={enabled}',str(unit),'-o',str(exe)]
        if args.sanitize:cmd[1:1]=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        subprocess.run(cmd,check=True);subprocess.run([str(exe)],check=True)
