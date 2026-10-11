#include "speaker_frontend.h"
#include <cmath>
#include <cstring>
#ifdef ESP_PLATFORM
#include "esp_timer.h"
static inline int64_t spk_now_us() { return esp_timer_get_time(); }
#else
#include <chrono>
static inline int64_t spk_now_us() { return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count(); }
#endif

namespace hw1::stt::speaker {
namespace {
constexpr double kPi=3.14159265358979323846;
bool pow2(size_t n) { return n && !(n&(n-1)); }
double hz_to_mel(double f) { return 2595.0*std::log10(1.0+f/700.0); }
double mel_to_hz(double m) { return 700.0*(std::pow(10.0,m/2595.0)-1.0); }
size_t reflect(long i,size_t n) {
    if(n==1)return 0;
    while(i<0 || i>=long(n))i=i<0 ? -i : 2*long(n)-2-i;
    return size_t(i);
}
}  // namespace

bool valid(const FeatureSpec& s) {
    return s.n_mels>=8 && s.n_mels<=128 && pow2(s.n_fft) && s.n_fft>=64 && s.n_fft<=2048 && s.win>=16 &&
           s.win<=s.n_fft && s.hop>=16 && s.hop<=s.win && s.window_frames>=8 && s.window_frames<=2000 &&
           s.f_min>=0 && s.f_max>s.f_min && s.f_max<=8000.0f && s.log_eps>0 && s.norm_eps>0;
}

// The frontend only ever looks at the centre (window_frames - 1) * hop samples.
size_t workspace_floats(const FeatureSpec& s,size_t) {
    if(!valid(s))return 0;
    const size_t bins=s.n_fft/2+1;
    // window + mel weights (bound: every band dense) + frames + fft scratch + twiddles
    return size_t(s.win)+size_t(s.n_mels)*bins+size_t(s.window_frames)*s.n_mels+(2*size_t(s.n_fft)+size_t(s.n_fft)/2+1)+size_t(s.n_fft);
}

bool Frontend::init(const FeatureSpec& s,size_t max_samples,float* w) {
    if(!valid(s) || !w || !max_samples)return false;
    spec_=s; maxSamples_=max_samples; bins_=s.n_fft/2+1; maxFrames_=s.window_frames;
    window_=w; w+=s.win;
    mel_=w; w+=size_t(s.n_mels)*bins_;
    frames_=w; w+=maxFrames_*s.n_mels;
    fft_=w; w+=2*size_t(s.n_fft)+size_t(s.n_fft)/2+1;   // frame n, re n/2, im n/2, power n/2+1
    twiddle_=w;
    const size_t half=s.n_fft/2;
    for(size_t k=0;k<s.win;++k)window_[k]=float(0.54-0.46*std::cos(2.0*kPi*double(k)/double(s.win)));
    for(size_t k=0;k<half;++k) {
        twiddle_[k]=float(std::cos(2.0*kPi*double(k)/double(s.n_fft)));
        twiddle_[half+k]=float(-std::sin(2.0*kPi*double(k)/double(s.n_fft)));
    }
    size_t bits=0; while((size_t(1)<<bits)<half)++bits;
    for(size_t i=0;i<half;++i) {
        size_t r=0; for(size_t b=0;b<bits;++b)if(i&(size_t(1)<<b))r|=size_t(1)<<(bits-1-b);
        bitrev_[i]=uint16_t(r);
    }
    // torchaudio melscale_fbanks(n_freqs, f_min, f_max, n_mels, sample_rate=16000, norm=None, mel_scale='htk')
    const double mmin=hz_to_mel(s.f_min), mmax=hz_to_mel(s.f_max);
    uint32_t off=0;
    for(size_t m=0;m<s.n_mels;++m) {
        const double f0=mel_to_hz(mmin+(mmax-mmin)*double(m)/double(s.n_mels+1));
        const double f1=mel_to_hz(mmin+(mmax-mmin)*double(m+1)/double(s.n_mels+1));
        const double f2=mel_to_hz(mmin+(mmax-mmin)*double(m+2)/double(s.n_mels+1));
        long first=-1,last=-1;
        for(size_t b=0;b<bins_;++b) {
            const double f=8000.0*double(b)/double(bins_-1);
            const double v=std::fmin((f-f0)/(f1-f0),(f2-f)/(f2-f1));
            if(v>0) { if(first<0)first=long(b); last=long(b); }
        }
        melStart_[m]=uint16_t(first<0 ? 0 : first);
        melCount_[m]=uint16_t(first<0 ? 0 : last-first+1);
        melOffset_[m]=off;
        for(size_t j=0;j<melCount_[m];++j) {
            const double f=8000.0*double(melStart_[m]+j)/double(bins_-1);
            const double v=std::fmin((f-f0)/(f1-f0),(f2-f)/(f2-f1));
            mel_[off+j]=v>0 ? float(v) : 0.0f;
        }
        off+=melCount_[m];
    }
    return true;
}

bool Frontend::compute(const int16_t* pcm,size_t samples,float* out) const {
    if(!pcm || !out || !samples || samples>maxSamples_ || !window_)return false;
    const FeatureSpec& s=spec_;
    const size_t n=s.n_fft, hop=s.hop, W=s.window_frames;
    // Centre crop to exactly W frames when the phrase is longer.
    const size_t span=(W-1)*hop;
    timing_=Timing{};
    timing_.cropped=samples>span;
    if(samples>span) { pcm+=(samples-span)/2; samples=span; }
    const size_t T=1+samples/hop;                     // <= W
    const size_t half=n/2;
    float* frame=fft_; float* re=fft_+n; float* im=re+half; float* power=im+half;
    const float* twr=twiddle_; const float* twi=twiddle_+half;
    const long pad=long(n/2), lead=long((n-s.win)/2);
    timing_.frames=uint32_t(T);
    int64_t fftUs=0, melUs=0;
    for(size_t t=0;t<T;++t) {
        const int64_t f0=spk_now_us();
        for(size_t k=0;k<n;++k)frame[k]=0;
        const long base=long(t*hop)-pad+lead;
        if(base>=0 && base+long(s.win)<=long(samples)) {
            const int16_t* p=pcm+base;
            for(size_t k=0;k<s.win;++k)frame[size_t(lead)+k]=float(p[k])*(1.0f/32768.0f)*window_[k];
        } else {
            for(size_t k=0;k<s.win;++k)
                frame[size_t(lead)+k]=float(pcm[reflect(base+long(k),samples)])*(1.0f/32768.0f)*window_[k];
        }
        // Real n-point FFT as one n/2-point complex FFT (z[m] = x[2m] + i x[2m+1]) plus the split.
        for(size_t m=0;m<half;++m) { const size_t r=bitrev_[m]; re[r]=frame[2*m]; im[r]=frame[2*m+1]; }
        for(size_t width=2;width<=half;width*=2) {
            const size_t hw=width/2, step=n/width;          // W_{n/2}^j == W_n^{2j}
            for(size_t b0=0;b0<half;b0+=width)
                for(size_t j=0;j<hw;++j) {
                    const size_t a=b0+j, b=a+hw, k=j*step;
                    const float tr=twr[k]*re[b]-twi[k]*im[b], ti=twr[k]*im[b]+twi[k]*re[b];
                    const float ar=re[a], ai=im[a];
                    re[a]=ar+tr; im[a]=ai+ti; re[b]=ar-tr; im[b]=ai-ti;
                }
        }
        for(size_t k=0;k<=half;++k) {
            const size_t a=k&(half-1), b=(half-k)&(half-1);
            const float zr=re[a], zi=im[a], cr=re[b], ci=-im[b];
            const float er=0.5f*(zr+cr), ei=0.5f*(zi+ci), orr=0.5f*(zi-ci), oi=-0.5f*(zr-cr);
            const float wr=k<half ? twr[k] : -1.0f, wi=k<half ? twi[k] : 0.0f;
            const float xr=er+wr*orr-wi*oi, xi=ei+wr*oi+wi*orr;
            power[k]=xr*xr+xi*xi;
        }
        const int64_t f1=spk_now_us();
        float* row=frames_+t*s.n_mels;
        for(size_t m=0;m<s.n_mels;++m) {
            const float* wm=mel_+melOffset_[m];
            const float* pw=power+melStart_[m];
            float v=0;
            for(size_t j=0;j<melCount_[m];++j)v+=wm[j]*pw[j];
            row[m]=std::log(v+s.log_eps);
        }
        fftUs+=f1-f0; melUs+=spk_now_us()-f1;
    }
    const int64_t n0=spk_now_us();
    // per-band normalisation over the T frames, then [mel][W] with repetition
    for(size_t m=0;m<s.n_mels;++m) {
        double sum=0, sq=0;
        for(size_t t=0;t<T;++t) { const double v=frames_[t*s.n_mels+m]; sum+=v; sq+=v*v; }
        const double mean=sum/double(T);
        const double var=std::fmax(sq/double(T)-mean*mean,0.0);
        const float inv=float(1.0/std::sqrt(var+double(s.norm_eps)));
        float* o=out+m*W;
        for(size_t t=0;t<W;++t)o[t]=(frames_[(t%T)*s.n_mels+m]-float(mean))*inv;
    }
    timing_.fftUs=uint32_t(fftUs); timing_.melUs=uint32_t(melUs); timing_.normUs=uint32_t(spk_now_us()-n0);
    return true;
}

}  // namespace hw1::stt::speaker
