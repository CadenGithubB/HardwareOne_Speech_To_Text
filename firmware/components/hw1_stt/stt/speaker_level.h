#pragma once
// Experimental speaker-input loudness normalization; not enabled in production.
#include <cstddef>
#include <cstdint>
#include <cmath>
namespace hw1::stt::speaker {
inline float normalize_level(int16_t* pcm,size_t samples,float target_rms=1000.0f) {
    if(!pcm || !samples || !std::isfinite(target_rms) || target_rms<=0)return 1.0f;
    double energy=0;
    for(size_t i=0;i<samples;++i)energy+=double(pcm[i])*pcm[i];
    if(!(energy>0))return 1.0f;
    float gain=float(target_rms/std::sqrt(energy/samples));
    gain=gain<0.25f ? 0.25f : gain>4.0f ? 4.0f : gain;
    for(size_t i=0;i<samples;++i) {
        const long v=std::lround(float(pcm[i])*gain);
        pcm[i]=int16_t(v>32767 ? 32767 : v<-32768 ? -32768 : v);
    }
    return gain;
}
}
