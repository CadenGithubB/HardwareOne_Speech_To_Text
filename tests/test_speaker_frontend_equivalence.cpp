#include "speaker_frontend.h"
#include "reference/speaker_frontend_92b028c.h"
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>
#include <cstdint>
#include <cstdlib>
namespace A=hw1::stt::speaker;
namespace B=hw1::stt::speaker_reference;
int main(int argc,char** argv) {
    const bool bench=argc>1 && std::strcmp(argv[1],"--bench")==0;
    std::vector<A::FeatureSpec> specs(3);
    specs[1].n_mels=8;specs[1].n_fft=64;specs[1].win=32;specs[1].hop=16;specs[1].window_frames=8;
    specs[2].n_mels=64;specs[2].n_fft=1024;specs[2].win=800;specs[2].hop=320;specs[2].window_frames=300;
    uint32_t seed=13;size_t checked=0;
    for(auto s:specs) {
        B::FeatureSpec r{s.n_mels,s.n_fft,s.win,s.hop,s.window_frames,s.f_min,s.f_max,s.log_eps,s.norm_eps};
        std::vector<float> aw(A::workspace_floats(s,160000)),bw(B::workspace_floats(r,160000));
        A::Frontend a;B::Frontend b;
        if(!a.init(s,160000,aw.data()) || !b.init(r,160000,bw.data()))return 1;
        std::vector<float> x(size_t(s.n_mels)*s.window_frames),y(x.size());
        for(int mode=0;mode<5;++mode)for(size_t n:{size_t(1),size_t(2),size_t(257),size_t(400),size_t(1599),size_t(16000),size_t(47839),size_t(47840),size_t(47841),size_t(160000)}) {
            std::vector<int16_t> pcm(n);
            for(size_t i=0;i<n;++i) {
                seed=1664525u*seed+1013904223u;
                pcm[i]=mode==0?0:mode==1?int16_t(1234):mode==2?(i%2?32767:-32768):mode==3?int16_t(seed>>16):int16_t(10000*std::sin(double(i)*.07));
            }
            if(!a.compute(pcm.data(),n,x.data()) || !b.compute(pcm.data(),n,y.data()) || std::memcmp(x.data(),y.data(),x.size()*sizeof(float))) {
                std::fprintf(stderr,"feature mismatch mode=%d samples=%zu fft=%u\n",mode,n,unsigned(s.n_fft));return 2;
            }
            ++checked;
        }
        if(bench && s.n_fft==512) {
            std::vector<int16_t> pcm(47840);
            for(auto& v:pcm) {seed=1664525u*seed+1013904223u;v=int16_t(seed>>16);}
            for(int warm=0;warm<60;++warm) {
                if(!a.compute(pcm.data(),pcm.size(),x.data()) || !b.compute(pcm.data(),pcm.size(),y.data()))return 3;
            }
            for(int run=0;run<10;++run) {
                auto measure=[&](auto& f,auto& out) {
                    auto t=std::chrono::steady_clock::now();
                    for(int j=0;j<30;++j)if(!f.compute(pcm.data(),pcm.size(),out.data()))std::abort();
                    return std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-t).count()/30;
                };
                double old_us,new_us;
                if(run%2) {new_us=measure(a,x);old_us=measure(b,y);}
                else {old_us=measure(b,y);new_us=measure(a,x);}
                std::printf("{\"run\":%d,\"reference_us\":%.3f,\"candidate_us\":%.3f}\n",run,old_us,new_us);
            }
        }
    }
    std::printf("frontend bit-exact cases: %zu\n",checked);
}
