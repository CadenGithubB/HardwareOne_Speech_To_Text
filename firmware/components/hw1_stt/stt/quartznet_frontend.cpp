#include "quartznet_frontend.h"
#include "quartznet_constants.h"
#include <cmath>
#include <cstring>
namespace hw1::stt {
namespace {
constexpr float kPreemphasis=0.97f, kDither=1e-5f, kLogGuard=0x1p-24f;
struct Gaussian {
    uint32_t state;
    float spare=0;
    bool has_spare=false;
    uint32_t next() { state^=state<<13; state^=state>>17; state^=state<<5; return state; }
    float uniform() { return static_cast<float>((static_cast<double>((next()>>8)+1))/16777217.0); }
    float sample() {
        if (has_spare) { has_spare=false; return spare; }
        const float u1=uniform(), u2=uniform();
        const float radius=std::sqrt(-2.0f*std::log(u1));
        const float angle=0x1.921fb6p+2f*u2;
        spare=radius*std::sin(angle); has_spare=true;
        return radius*std::cos(angle);
    }
};
// Power spectrum of the real 512-sample frame in w.real (w.imag ignored) via
// one 256-point complex FFT plus the standard real-input split: half the
// butterflies of the 512-point complex FFT, same result to float rounding.
void real_power_spectrum(FrontendWorkspace& w) {
    for (size_t n=0;n<256;++n) w.imag[n]=w.real[2*n+1];
    for (size_t n=0;n<256;++n) w.real[n]=w.real[2*n];   // forward: reads 2n >= n
    for (size_t i=0;i<256;++i) {                          // 8-bit reverse = 9-bit table >> 1
        const size_t j=constants::bit_reverse[i]>>1;
        if (j>i) {
            float t=w.real[i]; w.real[i]=w.real[j]; w.real[j]=t;
            t=w.imag[i]; w.imag[i]=w.imag[j]; w.imag[j]=t;
        }
    }
    for (size_t width=2;width<=256;width*=2) {
        const size_t half=width/2, step=512/width;          // W256^j == W512^(2j)
        for (size_t base=0;base<256;base+=width) for (size_t j=0;j<half;++j) {
            const size_t a=base+j,b=a+half,t=j*step;
            const float tr=constants::twiddle_real[t]*w.real[b]-constants::twiddle_imag[t]*w.imag[b];
            const float ti=constants::twiddle_real[t]*w.imag[b]+constants::twiddle_imag[t]*w.real[b];
            const float ar=w.real[a],ai=w.imag[a];
            w.real[a]=ar+tr; w.imag[a]=ai+ti;
            w.real[b]=ar-tr; w.imag[b]=ai-ti;
        }
    }
    // X[k] = E[k] + W512^k O[k], E=(Z[k]+conj Z[256-k])/2, O=(Z[k]-conj Z[256-k])/(2i)
    for (size_t k=0;k<=256;++k) {
        const size_t a=k&255, b=(256-k)&255;
        const float zr=w.real[a], zi=w.imag[a], cr=w.real[b], ci=-w.imag[b];
        const float er=0.5f*(zr+cr), ei=0.5f*(zi+ci);
        const float or_=0.5f*(zi-ci), oi=-0.5f*(zr-cr);
        const float wr=k<256?constants::twiddle_real[k]:-1.0f, wi=k<256?constants::twiddle_imag[k]:0.0f;
        const float xr=er+wr*or_-wi*oi, xi=ei+wr*oi+wi*or_;
        w.power[k]=xr*xr+xi*xi;
    }
}
size_t reflect(int index, size_t samples) {
    if (index<0) return static_cast<size_t>(-index);
    if (static_cast<size_t>(index)>=samples) return 2*samples-2-static_cast<size_t>(index);
    return static_cast<size_t>(index);
}
// One row without dither, from any sample source (log_mel_frame and
// log_mel_frame_ring). Must stay the exact operation sequence of
// compute_features' loop body: s(i)=pcm[i]*(1/32768),
// conditioned(i)=i ? s(i)-0.97*s(i-1) : s(i), window, power, mel, log.
template<typename Source>
void mel_row(const Source& source,size_t samples,size_t frame,float* out,FrontendWorkspace& w) {
    const size_t center=frame*160;
    std::memset(w.real,0,sizeof(w.real)); std::memset(w.imag,0,sizeof(w.imag));
    for (size_t k=0;k<320;++k) {
        const size_t input=reflect(static_cast<int>(center+k)-160,samples);
        const float sample=static_cast<float>(source(input))*(1.0f/32768.0f);
        float conditioned=sample;
        if (input) {
            const float previous=static_cast<float>(source(input-1))*(1.0f/32768.0f);
            conditioned=sample-kPreemphasis*previous;
        }
        w.real[96+k]=conditioned*constants::window[k];
    }
    real_power_spectrum(w);
    for (size_t m=0;m<kMelBins;++m) {
        float value=0;
        for (size_t j=0;j<constants::mel_count[m];++j)
            value+=constants::mel_weight[constants::mel_offset[m]+j]*w.power[constants::mel_start[m]+j];
        out[m]=std::log(value+kLogGuard);
    }
}
bool valid_score_extent(size_t frames,size_t stride) {
    // The caller still owns the score allocation; reject arithmetic overflow before reads.
    return frames<=kMaxSamples/160 && stride>=kCtcClasses &&
        (frames==0 || stride<=(SIZE_MAX-kCtcClasses)/(frames>1?frames-1:1));
}
constexpr char kVocabulary[]=" abcdefghijklmnopqrstuvwxyz'";
template<typename Score>
Status feed(CtcState* state,const Score* scores,size_t frames,size_t stride,char* text,size_t capacity) {
    if (!state||!text||!capacity||(!scores&&frames)||!valid_score_extent(frames,stride)||
        state->frames>kMaxSamples/160||frames>kMaxSamples/160-state->frames||
        state->written>=capacity||text[state->written]!='\0') return Status::InvalidArgument;
    if (state->finished) return Status::AlreadyFinished;
    for (size_t frame=0;frame<frames;++frame) {
        const Score* row=scores+frame*stride;
        size_t best=0;
        for (size_t i=1;i<kCtcClasses;++i) if (row[i]>row[best]) best=i;
        if (best!=kCtcBlank&&static_cast<int>(best)!=state->previous) {
            const char value=kVocabulary[best];
            if (!(state->written==0&&value==' ')) {
                if (state->written+1<capacity&&!state->truncated) {
                    text[state->written++]=value; text[state->written]='\0';
                } else state->truncated=true;
            }
        }
        state->previous=static_cast<int>(best); ++state->frames;
    }
    return state->truncated?Status::OutputTooSmall:Status::Ok;
}
}
size_t feature_frames(size_t samples) { return samples>=kMinSamples&&samples<=kMaxSamples?(samples+159)/160:0; }
Status compute_features(const int16_t* pcm,size_t samples,float* output,size_t capacity,
                        FrontendWorkspace* workspace,uint32_t seed,bool dither,FrontendTiming* timing) {
    const auto now=[timing]() -> uint64_t { return timing&&timing->now_us?timing->now_us():0; };
    const size_t frames=feature_frames(samples);
    if (!pcm||!output||!workspace||!frames||(dither&&!seed)) return Status::InvalidArgument;
    if (capacity<frames*kMelBins) return Status::OutputTooSmall;
    auto& w=*workspace;
    Gaussian rng{seed};
    size_t generated=0;
    float previous=0;
    for (size_t frame=0;frame<frames;++frame) {
        const uint64_t t0=now();
        const size_t center=frame*160;
        size_t required=center+159;
        if (required<160) required=160;
        if (required>=samples) required=samples-1;
        while (generated<=required) {
            float sample=static_cast<float>(pcm[generated])*(1.0f/32768.0f);
            if (dither) sample+=kDither*rng.sample();
            w.conditioned[generated%512]=generated?sample-kPreemphasis*previous:sample;
            previous=sample; ++generated;
        }
        std::memset(w.real,0,sizeof(w.real)); std::memset(w.imag,0,sizeof(w.imag));
        for (size_t k=0;k<320;++k) {
            const size_t input=reflect(static_cast<int>(center+k)-160,samples);
            w.real[96+k]=w.conditioned[input%512]*constants::window[k];
        }
        const uint64_t t1=now();
        real_power_spectrum(w);
        const uint64_t t2=now();
        for (size_t m=0;m<kMelBins;++m) {
            float value=0;
            for (size_t j=0;j<constants::mel_count[m];++j)
                value+=constants::mel_weight[constants::mel_offset[m]+j]*w.power[constants::mel_start[m]+j];
            output[frame*kMelBins+m]=std::log(value+kLogGuard);
        }
        if (timing&&timing->now_us) {
            const uint64_t t3=now();
            timing->conditionUs+=uint32_t(t1-t0); timing->fftUs+=uint32_t(t2-t1); timing->melUs+=uint32_t(t3-t2);
        }
    }
    return normalize_features(output,frames,workspace,timing);
}
Status normalize_features(float* output,size_t frames,FrontendWorkspace* workspace,FrontendTiming* timing) {
    const auto now=[timing]() -> uint64_t { return timing&&timing->now_us?timing->now_us():0; };
    if (!output||!workspace||!frames) return Status::InvalidArgument;
    auto& w=*workspace;
    const uint64_t normStart=now();
    // Per-utterance CMVN, row-wise over the [frames,64] matrix (cache-friendly)
    // in float: the P4 has no double FPU, and the previous column-wise float64
    // passes cost 0.15-0.37 s per 8 s segment. Values are shifted by frame 0
    // first (exact for nearby floats), so near-constant bins such as silence
    // keep the precision the double version had; sums are Kahan-compensated.
    float shift[kMelBins], sum[kMelBins]={}, carry[kMelBins]={};
    for (size_t m=0;m<kMelBins;++m) shift[m]=output[m];
    for (size_t t=0;t<frames;++t) {
        const float* row=output+t*kMelBins;
        for (size_t m=0;m<kMelBins;++m) {
            const float y=(row[m]-shift[m])-carry[m], s=sum[m]+y;
            carry[m]=(s-sum[m])-y; sum[m]=s;
        }
    }
    float mean[kMelBins], var[kMelBins]={};
    for (size_t m=0;m<kMelBins;++m) { mean[m]=sum[m]/static_cast<float>(frames); carry[m]=0; }
    for (size_t t=0;t<frames;++t) {
        const float* row=output+t*kMelBins;
        for (size_t m=0;m<kMelBins;++m) {
            const float d=(row[m]-shift[m])-mean[m], y=d*d-carry[m], s=var[m]+y;
            carry[m]=(s-var[m])-y; var[m]=s;
        }
    }
    float stddev[kMelBins];
    for (size_t m=0;m<kMelBins;++m) {
        stddev[m]=std::sqrt(var[m]/static_cast<float>(frames-1))+1e-5f;
        mean[m]+=shift[m];   // the float-rounded mean, as the reference applies it
        w.means[m]=mean[m]; w.variances[m]=stddev[m];
    }
    for (size_t t=0;t<frames;++t) {
        float* row=output+t*kMelBins;
        for (size_t m=0;m<kMelBins;++m) row[m]=(row[m]-mean[m])/stddev[m];
    }
    if (timing&&timing->now_us) timing->normUs+=uint32_t(now()-normStart);
    return Status::Ok;
}
Status log_mel_frame(const int16_t* pcm,size_t samples,size_t frame,float* out64,FrontendWorkspace* workspace) {
    if (!pcm||!out64||!workspace||frame>=feature_frames(samples)) return Status::InvalidArgument;
    mel_row([pcm](size_t i) { return pcm[i]; },samples,frame,out64,*workspace);
    return Status::Ok;
}
Status log_mel_frame_ring(const int16_t* ring,size_t ring_mask,uint64_t start,size_t samples,size_t frame,
                          float* out64,FrontendWorkspace* workspace) {
    if (!ring||!out64||!workspace||frame>=feature_frames(samples)||(ring_mask&(ring_mask+1))) return Status::InvalidArgument;
    mel_row([ring,ring_mask,start](size_t i) { return ring[static_cast<size_t>((start+i)&ring_mask)]; },
            samples,frame,out64,*workspace);
    return Status::Ok;
}
Status ctc_reset(CtcState* state,char* text,size_t capacity) {
    if (!state||!text||!capacity) return Status::InvalidArgument;
    *state=CtcState{}; text[0]='\0'; return Status::Ok;
}
Status ctc_feed(CtcState* state,const float* scores,size_t frames,size_t stride,char* text,size_t capacity) {
    if (!state||!text||!capacity||(!scores&&frames)||!valid_score_extent(frames,stride)||
        state->frames>kMaxSamples/160||frames>kMaxSamples/160-state->frames) return Status::InvalidArgument;
    for (size_t t=0;t<frames;++t) for(size_t c=0;c<kCtcClasses;++c)
        if (!std::isfinite(scores[t*stride+c])) return Status::NonFinite;
    return feed(state,scores,frames,stride,text,capacity);
}
Status ctc_feed(CtcState* state,const int8_t* scores,size_t frames,size_t stride,char* text,size_t capacity) {
    return feed(state,scores,frames,stride,text,capacity);
}
Status ctc_finish(CtcState* state,char* text,size_t capacity) {
    if (!state||!text||!capacity||state->written>=capacity||text[state->written]!='\0') return Status::InvalidArgument;
    if (state->finished) return Status::AlreadyFinished;
    while(state->written&&text[state->written-1]==' ') --state->written;
    text[state->written]='\0'; state->finished=true;
    return state->truncated?Status::OutputTooSmall:Status::Ok;
}
}
