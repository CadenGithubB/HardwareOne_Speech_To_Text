#!/usr/bin/env python3
"""Exercise production ConvOpArgs and prepared-storage ownership with fake heaps.
No instruction-set kernel is emulated; numerical kernel qualification is on P4.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from cpp_extract import extract_block

HERE = Path(__file__).resolve().parent
DL = HERE.parent / 'firmware/.sdk-overrides/esp32p4/espressif__esp-dl'
if not (DL / 'dl/base/dl_base_conv_args.hpp').is_file():
    print('SKIP: staged ESP-DL override is unavailable')
    sys.exit(77)
args = (DL / 'dl/base/dl_base_conv_args.hpp').read_text()
conv = (DL / 'dl/module/include/dl_module_conv.hpp').read_text()
args = re.sub(r'^#include.*\n|^#pragma once\n', '', args, flags=re.M)
unit = r'''
#include <algorithm>
#include <cassert>
#include <climits>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <map>
#include <new>
#include <vector>
#define CONFIG_PIE_V2_BOOST 1
#define CONFIG_PIE_V1_BOOST 0
#define ESP_LOGE(...) ((void)0)
constexpr int MALLOC_CAP_DEFAULT=0;
using DL_S16_BUFFER_TYPE=int64_t;
static std::map<void*,size_t> live;
static unsigned allocs=0, frees=0;
static bool failNext=false;
static void* allocate(size_t n,size_t alignment){
 if(failNext){failNext=false;return nullptr;}
 void* p=nullptr;assert(!posix_memalign(&p,std::max(alignment,sizeof(void*)),n));
 live[p]=n;++allocs;return p;
}
void heap_caps_free(void* p){if(!p)return;assert(live.erase(p)==1);++frees;std::free(p);}
namespace dl {
enum quant_type_t {QUANT_TYPE_SYMM_8BIT,QUANT_TYPE_SYMM_16BIT,QUANT_TYPE_SYMM_16BIT_8BIT};
enum activation_type_t {Linear,ReLU,LeakyReLU,PReLU};
enum runtime_mode_t {RUNTIME_MODE_AUTO,RUNTIME_MODE_MULTI_CORE,RUNTIME_MODE_SINGLE_CORE};
struct Exponent {
 int value=-5;bool perChannel=false;
 bool is_per_channel() const{return perChannel;}
 int get(int i) const{return value+(i%3);}
 operator int() const{return value;}
};
struct TensorBase {
 std::vector<int> shape;Exponent exponent;
 std::vector<uint8_t> storage=std::vector<uint8_t>(1<<20);
 void* get_element_ptr(){return storage.data();}
};
namespace tool {
enum class MetadataKind {Module};
void* metadata_alloc(size_t n,size_t align,MetadataKind){return allocate(n,align);}
void metadata_free(void* p){heap_caps_free(p);}
[[noreturn]] void metadata_bad_alloc(size_t,MetadataKind){throw std::bad_alloc();}
size_t get_aligned_size(size_t n){return (n+15)&~size_t(15);}
void* calloc_aligned(size_t n,size_t size,int){auto* p=allocate(n*size,16);if(p)memset(p,0,n*size);return p;}
template<class T,MetadataKind K>using meta_vector=std::vector<T>;
}}
int hw1_dl_prepare_mode=1;
uint32_t hw1_dl_prepare_gen=1;
'''
unit += args
unit += '\nnamespace dl { class TestConv { public:\n'
unit += 'quant_type_t quant_type=QUANT_TYPE_SYMM_8BIT;\n'
unit += extract_block(conv, 'struct alignas(16) Prepared') + ';\n'
unit += 'Prepared* m_prepared=nullptr;size_t m_prepared_bytes=0;\n'
for name in ['bool reserve_prepared(', 'void *prepare_factor_scratch(', 'bool keep_prepared(']:
    unit += extract_block(conv, name) + '\n'
unit += '~TestConv(){tool::metadata_free(m_prepared);}\n};}\n'
unit += r'''
using namespace dl;
int main(){
 const std::vector<int> pads{1,1,0,0}, stride{1,1};
 for(auto quant : {QUANT_TYPE_SYMM_8BIT,QUANT_TYPE_SYMM_16BIT,QUANT_TYPE_SYMM_16BIT_8BIT}){
  TestConv c;c.quant_type=quant;
  TensorBase in,out,filter;
  in.shape=out.shape={1,20,1,128};filter.shape={3,1,1,128};
  filter.exponent.perChannel=true;filter.exponent.value=-3;out.exponent.value=-1;
  const size_t bytes=128*base::conv_feature_bytes(quant);
  void* scratch=c.prepare_factor_scratch(&out,&filter);assert(scratch&&!(uintptr_t(scratch)&15));
  const unsigned firstAllocs=allocs;
  for(unsigned pass=0;pass<100;++pass){
   ++hw1_dl_prepare_gen;
   assert(c.prepare_factor_scratch(&out,&filter)==scratch);
   base::ConvOpArgs a(&out,&in,pads,&filter,stride,stride,128,nullptr,Linear,nullptr,
                     RUNTIME_MODE_MULTI_CORE,quant,false,scratch,bytes);
   assert(a.size()==2);
   assert(a.get_args(0).tie_filter_channel_factor==scratch);
   for(int i=0;i<128;++i){
    const int expected=int(out.exponent)-filter.exponent.get(i)-int(in.exponent);
    assert((quant==QUANT_TYPE_SYMM_8BIT ? int(static_cast<int8_t*>(scratch)[i]) : int(static_cast<int16_t*>(scratch)[i]))==expected);
   }
   assert(c.keep_prepared(a,a.size(),&in,&out));
   assert(c.m_prepared->gen==hw1_dl_prepare_gen);
   const auto delta=static_cast<uint8_t*>(a.get_args(1).tie_filter_channel_factor)-static_cast<uint8_t*>(scratch);
   assert(c.m_prepared->args[1].tie_filter_channel_factor==static_cast<uint8_t*>(scratch)+delta);
   assert(allocs==firstAllocs); // no factor/prepared allocation after first use
  }
  assert(live.size()==1); // args destructor never frees the borrowed block
  // An ordinary caller still owns/frees its factors. Prepared copies survive it.
  {
   base::ConvOpArgs a(&out,&in,pads,&filter,stride,stride,128,nullptr,Linear,nullptr,RUNTIME_MODE_MULTI_CORE,quant);
   assert(a.get_args(0).tie_filter_channel_factor!=scratch);
   assert(c.keep_prepared(a,a.size(),&in,&out));
  }
  assert(live.size()==1);
  // Insufficient or unaligned borrow is rejected; no invalid free on destruction.
  for(bool unaligned : {false,true}){
   base::ConvOpArgs a(&out,&in,pads,&filter,stride,stride,128,nullptr,Linear,nullptr,RUNTIME_MODE_MULTI_CORE,
                     quant,false,static_cast<uint8_t*>(scratch)+(unaligned?1:0),unaligned?bytes:bytes-1);
   assert(a.get_args(0).tie_filter_channel_factor!=scratch);
  }
  assert(live.size()==1);
  // Grow transactionally; failure retains the previous allocation for cleanup.
  auto* old=c.m_prepared;const size_t oldBytes=c.m_prepared_bytes;
  failNext=true;assert(!c.reserve_prepared(oldBytes+1024));assert(c.m_prepared==old&&c.m_prepared_bytes==oldBytes);
  assert(c.reserve_prepared(oldBytes+1024));assert(live.size()==1);
  TestConv other;other.quant_type=quant;
  assert(other.prepare_factor_scratch(&out,&filter)!=reinterpret_cast<uint8_t*>(c.m_prepared)+sizeof(TestConv::Prepared));
  hw1_dl_prepare_mode=0;assert(!c.prepare_factor_scratch(&out,&filter));hw1_dl_prepare_mode=1;
 }
 assert(live.empty()&&allocs==frees);
 // Failed first pool allocation falls back to owned factors; retry prepares safely.
 {
  TestConv c;TensorBase in,out,f;in.shape=out.shape={1,20,1,128};f.shape={3,1,1,128};f.exponent.perChannel=true;
  failNext=true;assert(!c.prepare_factor_scratch(&out,&f));
  base::ConvOpArgs a(&out,&in,pads,&f,stride,stride,128,nullptr,Linear,nullptr,RUNTIME_MODE_MULTI_CORE,QUANT_TYPE_SYMM_8BIT);
  assert(c.keep_prepared(a,a.size(),&in,&out));
 }
 assert(live.empty()&&allocs==frees);
}
'''
with tempfile.TemporaryDirectory(prefix='hw1-conv-scratch-') as tmp:
    cpp, exe = Path(tmp)/'test.cpp', Path(tmp)/'test'
    cpp.write_text(unit)
    subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
                    '-Wno-sign-compare','-fsanitize=address,undefined',str(cpp),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
print('Prepared Conv scratch ownership/reuse tests passed')
