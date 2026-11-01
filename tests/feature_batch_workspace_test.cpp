#include "stt/quartznet_frontend.h"
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
using namespace hw1::stt;
struct Guarded {uint64_t before=0xabcdef1234567890;FrontendWorkspace w{};uint64_t after=0x0123456789abcdef;};
int main() {
    constexpr size_t cap=65536,batch=8;
    static_assert(sizeof(FrontendWorkspace::conditioned)==batch*kMelBins*sizeof(float));
    size_t rows_checked=0,cases=0;uint32_t rng=17;
    for(size_t n:{size_t(320),size_t(1280),size_t(1297),size_t(16000),size_t(47840)})
    for(uint64_t start:{uint64_t(0),uint64_t(127),uint64_t(65520)}) {
        std::vector<int16_t> ring(cap),pcm(n);
        for(size_t i=0;i<n;++i) {rng=rng*1664525u+1013904223u;pcm[i]=int16_t(rng>>16);ring[(start+i)&(cap-1)]=pcm[i];}
        const size_t frames=n/160;
        std::vector<float> reference(frames*kMelBins),staged(reference.size()),direct(reference.size());
        Guarded normal,aliased,plain;
        for(size_t r=0;r<frames;++r) {
            assert(log_mel_frame_ring(ring.data(),cap-1,start,n,r,reference.data()+r*kMelBins,&normal.w)==Status::Ok);
            assert(log_mel_frame(pcm.data(),n,r,direct.data()+r*kMelBins,&plain.w)==Status::Ok);
        }
        assert(!memcmp(reference.data(),direct.data(),reference.size()*sizeof(float)));
        for(size_t first=0;first<frames;first+=batch) {
            const size_t end=std::min(first+batch,frames);
            for(size_t r=first;r<end;++r)
                assert(log_mel_frame_ring(ring.data(),cap-1,start,n,r,aliased.w.conditioned+(r-first)*kMelBins,&aliased.w)==Status::Ok);
            memcpy(staged.data()+first*kMelBins,aliased.w.conditioned,(end-first)*kMelBins*sizeof(float));
        }
        assert(!memcmp(reference.data(),staged.data(),reference.size()*sizeof(float)));
        assert(aliased.before==0xabcdef1234567890 && aliased.after==0x0123456789abcdef);
        // The non-ring incremental entry supports the same explicit alias.
        for(size_t first=0;first<frames;first+=batch) {
            const size_t end=std::min(first+batch,frames);
            for(size_t r=first;r<end;++r)
                assert(log_mel_frame(pcm.data(),n,r,aliased.w.conditioned+(r-first)*kMelBins,&aliased.w)==Status::Ok);
            assert(!memcmp(reference.data()+first*kMelBins,aliased.w.conditioned,(end-first)*kMelBins*sizeof(float)));
        }
        rows_checked+=frames;++cases;
    }
    std::printf("feature batch workspace: %zu cases, %zu rows, ring/direct/staged byte-exact; no added workspace ok\n",cases,rows_checked);
}
