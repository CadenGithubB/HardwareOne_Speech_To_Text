#pragma once
// Experimental opt-in audio selection. Not wired into the production speaker
// path. Uses energy activity, NOT a learned VAD or speaker-change detector.
// Input/output are contiguous 16 kHz PCM. No model, profile or caption changes.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace hw1::stt::speaker {
struct WindowSelection {
    size_t start=0, samples=0, frames=0, active_frames=0, selected_active_frames=0;
    float threshold_rms=0;
};

inline size_t window_frames(size_t samples) {
    return samples>=320 ? 1+(samples-320)/160 : samples ? 1 : 0;
}
inline size_t window_workspace_floats(size_t samples) {
    return 2*window_frames(samples)+1;
}

// policy 0: existing center crop; 1: densest energy-active fixed window;
// 2: additionally trim inactive ends with 100 ms context. No disjoint splicing.
// Fixed before evaluation: 20 ms energy frames/10 ms hop, threshold max(32 PCM
// RMS, 0.1*p90 RMS), 2.99 s maximum. Threshold is utterance-relative; background
// noise or a second speaker can qualify as activity.
inline bool select_window(const int16_t* pcm,size_t samples,unsigned policy,
                          float* workspace,size_t workspace_count,WindowSelection& out) {
    if(!pcm || !samples || policy>2 || !workspace ||
       workspace_count<window_workspace_floats(samples))return false;
    constexpr size_t span=299*160, hop=160, frame=320, context=1600;
    const size_t count=window_frames(samples);
    float* energy=workspace;float* scratch=workspace+count;
    out={};out.frames=count;
    for(size_t i=0;i<count;++i) {
        const size_t a=i*hop, n=std::min(frame,samples-a);
        double sum=0;
        for(size_t j=0;j<n;++j)sum+=double(pcm[a+j])*pcm[a+j];
        energy[i]=scratch[i]=float(std::sqrt(sum/n));
    }
    std::sort(scratch,scratch+count);
    out.threshold_rms=std::max(32.0f,0.1f*scratch[(count-1)*9/10]);
    size_t first=count,last=0;
    for(size_t i=0;i<count;++i)if(energy[i]>=out.threshold_rms) {
        first=std::min(first,i);last=i;++out.active_frames;
    }
    size_t lo=0,hi=samples;
    if(policy==2 && out.active_frames) {
        lo=first*hop>context ? first*hop-context : 0;
        hi=std::min(samples,last*hop+frame+context);
    }
    const size_t length=std::min(span,hi-lo), center=lo+(hi-lo-length)/2;
    out.start=center;out.samples=length;
    // Prefix counts reuse quantile scratch. Frame centers define membership.
    scratch[0]=0;
    for(size_t i=0;i<count;++i)scratch[i+1]=scratch[i]+(energy[i]>=out.threshold_rms ? 1.0f : 0.0f);
    auto active=[&](size_t start) {
        const size_t a=start>frame/2 ? (start-frame/2+hop-1)/hop : 0;
        const size_t end=start+length;
        const size_t b=end>frame/2 ? std::min(count,(end-frame/2+hop-1)/hop) : 0;
        return b>=a ? size_t(scratch[b]-scratch[std::min(a,count)]) : size_t(0);
    };
    out.selected_active_frames=active(center);
    if(!policy || !out.active_frames || hi-lo<=span)return true;
    size_t best=out.selected_active_frames;
    auto consider=[&](size_t start) {
        const size_t score=active(start);
        const size_t distance=start>center ? start-center : center-start;
        const size_t oldDistance=out.start>center ? out.start-center : center-out.start;
        if(score>best || (score==best && distance<oldDistance)) {
            best=score;out.start=start;
        }
    };
    for(size_t start=lo;start<=hi-length;start+=hop)consider(start);
    consider(hi-length);
    out.selected_active_frames=best;
    return true;
}
} // namespace hw1::stt::speaker
