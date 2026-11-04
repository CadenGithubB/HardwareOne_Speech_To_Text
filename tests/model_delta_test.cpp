#include "model_delta.h"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <vector>
using namespace hw1::diagnostic;
namespace {
void word(std::vector<uint8_t>& p,size_t at,uint32_t value) {
    for(unsigned i=0;i<4;++i)p.at(at+i)=uint8_t(value>>(8*i));
}
std::vector<uint8_t> patch() {
    std::vector<uint8_t> p(88+32+3);std::memcpy(p.data(),"HW1DLT1\0",8);
    word(p,8,6);word(p,12,6);word(p,16,2);word(p,20,3);
    word(p,88,0);word(p,92,1);word(p,96,3);word(p,100,UINT32_MAX);
    word(p,104,3);word(p,108,UINT32_MAX);word(p,112,3);word(p,116,0);
    std::memcpy(p.data()+120,"XYZ",3);return p;
}
size_t read(void* context,size_t at,void* output,size_t bytes) {
    auto& base=*static_cast<std::vector<uint8_t>*>(context);
    if(at>base.size()||bytes>base.size()-at)return 0;
    std::memcpy(output,base.data()+at,bytes);return bytes;
}
size_t shortRead(void*,size_t,void*,size_t n) {return n-1;}
std::vector<uint8_t> file(const char* path) {
    std::ifstream f(path,std::ios::binary);assert(f);
    return {std::istreambuf_iterator<char>(f),std::istreambuf_iterator<char>()};
}
}
int main(int argc,char** argv) {
    uint8_t hash[32]{};auto p=patch();ModelDelta delta;
    assert(parseModelDelta(p.data(),p.size(),6,hash,hash,6,delta));
    std::vector<uint8_t> base{'a','b','c','d','e','f'},output(8,0x5a);
    assert(applyModelDelta(delta,read,&base,output.data(),6));
    assert(!std::memcmp(output.data(),"bcdXYZ",6)&&output[6]==0x5a&&output[7]==0x5a);
    std::fill(output.begin(),output.end(),0x5a);
    assert(!applyModelDelta(delta,read,&base,output.data(),5));
    assert(std::all_of(output.begin(),output.end(),[](uint8_t b){return b==0x5a;}));
    assert(!applyModelDelta(delta,shortRead,nullptr,output.data(),6));
    unsigned rejected=0;
    for(unsigned test=0;test<12;++test) {
        auto bad=p;
        switch(test) {
        case 0:bad[0]='?';break;
        case 1:bad[24]=1;break;
        case 2:bad[56]=1;break;
        case 3:word(bad,16,UINT32_MAX);break;
        case 4:word(bad,96,0);break;
        case 5:word(bad,104,4);break;
        case 6:word(bad,92,5);break;
        case 7:word(bad,116,2);break;
        case 8:bad.pop_back();break;
        case 9:bad.push_back(0);break;
        case 10:word(bad,112,UINT32_MAX);break;
        case 11:word(bad,100,0);break;
        }
        assert(!parseModelDelta(bad.data(),bad.size(),6,hash,hash,6,delta));
        assert(!delta.bytes);++rejected;
    }
    for(size_t n=0;n<88;++n)assert(!parseModelDelta(p.data(),n,6,hash,hash,6,delta));
    if(argc==4) {
        auto realBase=file(argv[1]),realPatch=file(argv[2]),target=file(argv[3]);
        assert(realPatch.size()>=88);
        assert(parseModelDelta(realPatch.data(),realPatch.size(),realBase.size(),
                               realPatch.data()+24,realPatch.data()+56,target.size(),delta));
        std::vector<uint8_t> actual(target.size());
        assert(applyModelDelta(delta,read,&realBase,actual.data(),actual.size()));
        assert(actual==target);puts("Actual model delta: reconstructed bytes equal target");
    } else assert(argc==1);
    printf("Model delta: exact reconstruction, guards, short-read handling and %u malformed plans rejected\n",rejected);
}
