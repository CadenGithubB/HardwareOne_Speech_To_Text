#include "quartznet_frontend.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <limits>
#include <string>
#include <vector>
using namespace hw1::stt;
static void ctc_tests() {
    const std::vector<int> tokens={0,0,1,1,28,1,2,2,0,0,27,28,27,0};
    std::vector<float> floats(tokens.size()*29,-10);
    std::vector<int8_t> quantized(tokens.size()*29,-100);
    for(size_t t=0;t<tokens.size();++t) { floats[t*29+tokens[t]]=10; quantized[t*29+tokens[t]]=100; }
    char text[32]; CtcState s;
    assert(ctc_reset(&s,text,sizeof(text))==Status::Ok);
    assert(ctc_feed(&s,floats.data(),tokens.size(),29,text,sizeof(text))==Status::Ok);
    assert(ctc_finish(&s,text,sizeof(text))==Status::Ok);
    assert(std::string(text)=="aab ''");
    assert(ctc_feed(&s,floats.data(),1,29,text,sizeof(text))==Status::AlreadyFinished);
    for(size_t split=0;split<=tokens.size();++split) {
        assert(ctc_reset(&s,text,sizeof(text))==Status::Ok);
        assert(ctc_feed(&s,quantized.data(),split,29,text,sizeof(text))==Status::Ok);
        assert(ctc_feed(&s,quantized.data()+split*29,tokens.size()-split,29,text,sizeof(text))==Status::Ok);
        assert(ctc_finish(&s,text,sizeof(text))==Status::Ok);
        assert(std::string(text)=="aab ''");
    }
    char tiny[3]; ctc_reset(&s,tiny,sizeof(tiny));
    assert(ctc_feed(&s,quantized.data(),tokens.size(),29,tiny,sizeof(tiny))==Status::OutputTooSmall);
    assert(s.truncated&&std::string(tiny)=="aa"&&tiny[2]=='\0');
    assert(ctc_finish(&s,tiny,sizeof(tiny))==Status::OutputTooSmall);
    ctc_reset(&s,text,sizeof(text)); floats[7]=std::numeric_limits<float>::quiet_NaN();
    assert(ctc_feed(&s,floats.data(),tokens.size(),29,text,sizeof(text))==Status::NonFinite);
    assert(s.frames==0&&text[0]=='\0');
    assert(ctc_feed(&s,quantized.data(),1,28,text,sizeof(text))==Status::InvalidArgument);
    assert(ctc_feed(&s,quantized.data(),3,SIZE_MAX,text,sizeof(text))==Status::InvalidArgument);
    assert(ctc_feed(&s,floats.data(),3,SIZE_MAX,text,sizeof(text))==Status::InvalidArgument);
    s.frames=3000;
    assert(ctc_feed(&s,quantized.data(),1,29,text,sizeof(text))==Status::InvalidArgument);
    ctc_reset(&s,text,sizeof(text));
    std::vector<int8_t> tied(29,0); // Torch argmax chooses first index: leading space omitted.
    assert(ctc_feed(&s,tied.data(),1,29,text,sizeof(text))==Status::Ok&&text[0]=='\0');
    puts("CTC chunk boundaries, ties, float/int8 parity, overflow and finalization passed");
}
int main(int argc,char** argv) {
    ctc_tests();
    if(argc==1) return 0;
    if(argc!=3&&argc!=4) return 2;
    std::ifstream input(argv[1],std::ios::binary|std::ios::ate);
    if(!input) return 3;
    const auto bytes=input.tellg();
    if(bytes<0||static_cast<size_t>(bytes)%2||static_cast<size_t>(bytes)>kMaxSamples*2) return 4;
    std::vector<int16_t> pcm(static_cast<size_t>(bytes)/2); input.seekg(0);
    input.read(reinterpret_cast<char*>(pcm.data()),bytes); if(!input) return 5;
    const size_t frames=feature_frames(pcm.size());
    std::vector<float> result(frames*64+2,12345.0f);
    FrontendWorkspace workspace;
    const auto status=compute_features(pcm.data(),pcm.size(),result.data()+1,frames*64,&workspace,kDitherSeed,argc==3);
    if(status!=Status::Ok) return 6;
    assert(result.front()==12345.0f&&result.back()==12345.0f);
    assert(compute_features(pcm.data(),pcm.size(),result.data()+1,frames*64-1,&workspace)==Status::OutputTooSmall);
    assert(compute_features(pcm.data(),319,result.data()+1,frames*64,&workspace)==Status::InvalidArgument);
    assert(compute_features(pcm.data(),480001,result.data()+1,frames*64,&workspace)==Status::InvalidArgument);
    assert(compute_features(pcm.data(),pcm.size(),result.data()+1,frames*64,&workspace,0)==Status::InvalidArgument);
    std::ofstream output(argv[2],std::ios::binary); output.write(reinterpret_cast<const char*>(result.data()+1),frames*64*sizeof(float));
    if(!output) return 7;
    std::ofstream stats(std::string(argv[2])+".stats",std::ios::binary);
    stats.write(reinterpret_cast<const char*>(workspace.means),sizeof(workspace.means));
    stats.write(reinterpret_cast<const char*>(workspace.variances),sizeof(workspace.variances));
    printf("frames=%zu workspace_bytes=%zu\n",frames,sizeof(workspace));
}
