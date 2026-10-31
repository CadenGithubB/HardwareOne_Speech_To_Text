"""Run actual standalone speaker submit/poll code with bounded queue fakes.
Verifies nonblocking ownership and receipt routing, not embedding accuracy.
"""
from pathlib import Path
import subprocess,tempfile
from cpp_extract import extract_block
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'firmware/examples/p4_eye_captions/main/speaker_adapter.cpp').read_text()
unit=r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <deque>
#include <vector>
#include <string>
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGI(...) ((void)0)
constexpr int pdTRUE=1;
namespace product {
struct Receipt {uint32_t note=0,sequence=0;};
struct Label {Receipt receipt;int8_t speaker;};
std::vector<Label> labels;
void speaker(Receipt r,int8_t label){labels.push_back({r,label});}
}
struct Job {product::Receipt receipt;size_t samples=0,phrase_samples=0;uint32_t submitted=0;};
struct Result {product::Receipt receipt;int8_t speaker=-1;uint32_t elapsed=0,lag=0;};
struct Queue {size_t bytes,capacity;std::deque<std::vector<uint8_t>> items;};
int xQueueReceive(Queue* q,void* out,int wait){assert(wait==0);if(q->items.empty())return 0;std::memcpy(out,q->items.front().data(),q->bytes);q->items.pop_front();return pdTRUE;}
int xQueueSend(Queue* q,const void* in,int wait){assert(wait==0);if(q->items.size()==q->capacity)return 0;const auto* p=static_cast<const uint8_t*>(in);q->items.emplace_back(p,p+q->bytes);return pdTRUE;}
struct State {size_t span=4;int16_t pcmStorage[16]{};int16_t* pcm=pcmStorage;Job jobs[4];Queue *ready,*free,*results;};
State* state=nullptr;
uint32_t milliseconds(){return 123;}
'''
unit+='\n'+extract_block(source,'void submit(')+'\n'+extract_block(source,'void poll(')
unit+=r'''
int main(){
 int16_t pcm[]={1,2,3,4,5,6,7,8};
 submit({1,1},pcm,8);assert(product::labels.empty());
 Queue free{1,4,{}},ready{1,4,{}},results{sizeof(Result),12,{}};
 State s;s.free=&free;s.ready=&ready;s.results=&results;state=&s;
 for(uint8_t i=0;i<4;++i)xQueueSend(&free,&i,0);
 for(uint32_t seq=1;seq<=4;++seq)submit({42,seq},pcm,8);
 assert(free.items.empty()&&ready.items.size()==4);
 for(int i=0;i<4;++i){assert(s.jobs[i].receipt.note==42&&s.jobs[i].receipt.sequence==uint32_t(i+1));assert(s.jobs[i].samples==4&&s.jobs[i].phrase_samples==8);assert(!std::memcmp(s.pcm+i*4,pcm+2,8));}
 submit({42,5},pcm,8);assert(product::labels.back().receipt.sequence==5&&product::labels.back().speaker==-1);
 // Publication failure returns the PCM slot and erases its copied audio.
 uint8_t slot=0;xQueueSend(&free,&slot,0);submit({43,6},pcm,8);
 assert(free.items.size()==1&&product::labels.back().receipt.note==43);
 for(int i=0;i<4;++i)assert(s.pcm[i]==0);
 Result r{{42,2},3,100,200};xQueueSend(&results,&r,0);poll();
 assert(results.items.empty()&&product::labels.back().receipt.sequence==2&&product::labels.back().speaker==3);
 submit({},pcm,8);submit({1,1},nullptr,8);submit({1,1},pcm,0);
}
'''
with tempfile.TemporaryDirectory(prefix='stt-speaker-adapter-') as temp:
    cpp,exe=Path(temp)/'test.cpp',Path(temp)/'test'
    cpp.write_text(unit)
    subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(cpp),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
print('Speaker queue: bounded PCM ownership, centre crop, overflow, failed publication and receipt routing passed')
