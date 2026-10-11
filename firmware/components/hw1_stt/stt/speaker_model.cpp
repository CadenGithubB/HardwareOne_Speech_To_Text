#include "speaker_model.h"
#include "dl_model_base.hpp"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include <cmath>
#include <cstring>
#include <new>

namespace hw1::stt::speaker {
namespace {
template<typename T> T rd(const uint8_t* p) { T v; std::memcpy(&v,p,sizeof(T)); return v; }
constexpr size_t kHeaderBytes=128, kHashBytes=32;
}  // namespace

const char* describe(LoadStatus s) {
    switch(s) {
        case LoadStatus::Ok: return "ok";
        case LoadStatus::BadSize: return "wrong size";
        case LoadStatus::BadHeader: return "bad header";
        case LoadStatus::BadHash: return "SHA-256 mismatch";
        case LoadStatus::BadTrunk: return "ESP-DL trunk rejected";
        case LoadStatus::NoMemory: return "no memory";
    }
    return "unknown";
}

static bool gLoadSelfTest=false;
void Model::setLoadSelfTest(bool on) { gLoadSelfTest=on; }

Model::~Model() { reset(); }

StageProfile Model::stage(size_t i) const {
    StageProfile p{nullptr,0,0};
    if(trunk_ && i<modules_) { p.name=trunk_->module_name(int(i)); p.calls=stageCalls_[i]; p.us=stageUs_[i]; }
    return p;
}

void Model::resetProfile() {
    embeds_=0;
    for(size_t i=0;i<kMaxStages;++i) { stageCalls_[i]=0; stageUs_[i]=0; }
}

void Model::reset() {
    resetProfile();
    modules_=0; report_=LoadReport{};
    delete trunk_;
    trunk_=nullptr; input_=output_=nullptr;
    if(work_ && release_)release_(work_);
    work_=nullptr;
    info_=ModelInfo{};
}

LoadStatus Model::load(const uint8_t* blob,size_t bytes,size_t maxSamples,void* (*alloc)(size_t,const char*),
                       void (*release)(void*)) {
    reset();
    release_=release;
    if(!blob || bytes<kHeaderBytes+kHashBytes || !alloc || !release)return LoadStatus::BadSize;
    if(std::memcmp(blob,"HW1SPK1\0",8) || rd<uint32_t>(blob+8)!=1 || rd<uint32_t>(blob+12)!=kHeaderBytes)
        return LoadStatus::BadHeader;
    unsigned char hash[32];
    const int64_t sha0=esp_timer_get_time();
    if(mbedtls_sha256(blob,bytes-kHashBytes,hash,0)!=0 || std::memcmp(hash,blob+bytes-kHashBytes,kHashBytes))
        return LoadStatus::BadHash;
    LoadReport rep;
    rep.shaUs=uint32_t(esp_timer_get_time()-sha0);
    ModelInfo in;
    const uint8_t* p=blob+16;
    in.features.n_mels=rd<uint16_t>(p); in.features.n_fft=rd<uint16_t>(p+2); in.features.win=rd<uint16_t>(p+4);
    in.features.hop=rd<uint16_t>(p+6); in.features.window_frames=rd<uint16_t>(p+8);
    in.features.f_min=rd<float>(p+12); in.features.f_max=rd<float>(p+16);
    in.features.log_eps=rd<float>(p+20); in.features.norm_eps=rd<float>(p+24);
    in.channels=rd<uint16_t>(p+28); in.dim=rd<uint16_t>(p+30); in.pooling=rd<uint16_t>(p+32);
    const uint32_t headOff=rd<uint32_t>(p+36), headBytes=rd<uint32_t>(p+40);
    const uint32_t trunkOff=rd<uint32_t>(p+44), trunkBytes=rd<uint32_t>(p+48);
    in.threshold=rd<float>(p+52); in.minNewMs=rd<uint32_t>(p+56);
    in.trunkBytes=trunkBytes; in.headBytes=headBytes;
    const size_t C=in.channels, D=in.dim;
    const size_t body=bytes-kHashBytes;
    if(!valid(in.features) || in.pooling!=1 || !C || C>1024 || !D || D>1024 ||
       headBytes!=(C*C+C+C+D*C+D)*sizeof(float) || headOff<kHeaderBytes || headOff%4 ||
       size_t(headOff)+headBytes>body || trunkOff%16 || trunkOff<headOff+headBytes ||
       size_t(trunkOff)+trunkBytes>body || ((uintptr_t(blob)+trunkOff)&15) ||
       !(in.threshold>-1.0f && in.threshold<1.0f))
        return LoadStatus::BadHeader;
    const float* h=reinterpret_cast<const float*>(blob+headOff);
    sapW_=h; sapB_=h+C*C; att_=sapB_+C; fcW_=att_+C; fcB_=fcW_+D*C;
    // ESP-DL in place on the caller's PSRAM copy (param_copy=false; aligned, so no
    // second copy), internal RAM limited to 0, metadata via the installed
    // PSRAM allocator (stt_dl_metadata.h).
    const int64_t build0=esp_timer_get_time();
    trunk_=new(std::nothrow) dl::Model(reinterpret_cast<const char*>(blob+trunkOff),fbs::MODEL_LOCATION_IN_FLASH_RODATA,
                                        0,dl::MEMORY_MANAGER_GREEDY,nullptr,false);
    if(!trunk_)return LoadStatus::NoMemory;
    rep.buildUs=uint32_t(esp_timer_get_time()-build0);
    modules_=size_t(trunk_->module_count());
    if(!modules_ || modules_>kMaxStages) { reset(); return LoadStatus::BadTrunk; }
    rep.modules=uint16_t(modules_);
    trunk_->get_arena_size(&rep.arenaPsram,&rep.arenaInternal);
    auto& ins=trunk_->get_inputs();
    auto& outs=trunk_->get_outputs();
    if(ins.size()!=1 || outs.size()!=1) { reset(); return LoadStatus::BadTrunk; }
    input_=ins.begin()->second; output_=outs.begin()->second;
    const auto& is=input_->shape; const auto& os=output_->shape;
    const bool dtypes=(input_->dtype==dl::DATA_TYPE_INT16 || input_->dtype==dl::DATA_TYPE_INT8) &&
                      (output_->dtype==dl::DATA_TYPE_INT16 || output_->dtype==dl::DATA_TYPE_INT8);
    if(!dtypes || is.size()!=4 || is[0]!=1 || size_t(is[1])!=in.features.n_mels ||
       size_t(is[2])!=in.features.window_frames || is[3]!=1 || os.size()!=3 || os[0]!=1 || size_t(os[2])!=C ||
       input_->exponent.is_per_channel() || output_->exponent.is_per_channel()) {
        reset(); return LoadStatus::BadTrunk;
    }
    outFrames_=size_t(os[1]);
    const size_t feFloats=workspace_floats(in.features,maxSamples);
    const size_t nFeat=size_t(in.features.n_mels)*in.features.window_frames;
    const size_t total=feFloats+nFeat+outFrames_*C+outFrames_+2*C;
    work_=static_cast<float*>(alloc(total*sizeof(float),"stt.speaker"));
    if(!work_) { reset(); return LoadStatus::NoMemory; }
    if(!frontend_.init(in.features,maxSamples,work_)) { reset(); return LoadStatus::BadHeader; }
    features_=work_+feFloats; frames_=features_+nFeat; scores_=frames_+outFrames_*C;
    hidden_=scores_+outFrames_; pooled_=hidden_+C;
    rep.workspaceBytes=total*sizeof(float);
    // The file's own test input/outputs (esp-ppq export_test_values): proves the
    // 16-bit kernels on this chip reproduce the Mac's quantized trunk.
    if(gLoadSelfTest) {
        const int64_t test0=esp_timer_get_time();
        rep.testResult=int(trunk_->test());
        rep.testUs=uint32_t(esp_timer_get_time()-test0);
    }
    info_=in;
    report_=rep;
    return LoadStatus::Ok;
}

bool Model::embed(const int16_t* pcm,size_t samples,float* e,EmbedTiming* timing) {
    if(!trunk_ || !pcm || !samples || !e)return false;
    const int64_t t0=esp_timer_get_time();
    if(!frontend_.compute(pcm,samples,features_))return false;
    const int64_t tq=esp_timer_get_time();
    const size_t n=size_t(info_.features.n_mels)*info_.features.window_frames;
    // [mel][frame] is the trunk's NHWC [1, mel, frame, 1] order already.
    const float inScale=std::ldexp(1.0f,-int(input_->exponent));
    if(input_->dtype==dl::DATA_TYPE_INT16) {
        auto* q=static_cast<int16_t*>(input_->data);
        for(size_t i=0;i<n;++i) { const float v=std::nearbyint(features_[i]*inScale); q[i]=int16_t(v>32767.f?32767.f:(v<-32768.f?-32768.f:v)); }
    } else {
        auto* q=static_cast<int8_t*>(input_->data);
        for(size_t i=0;i<n;++i) { const float v=std::nearbyint(features_[i]*inScale); q[i]=int8_t(v>127.f?127.f:(v<-128.f?-128.f:v)); }
    }
    const int64_t t1=esp_timer_get_time();
    // Layer by layer: one execution-plan module per stage, each timed. Single-core (background task, priority 1):
    // block one tick every ~100 ms so the core's IDLE task runs (task watchdog: IDLE1 starved at 5 s otherwise).
    int64_t lastBlock=esp_timer_get_time();
    for(size_t i=0;i<modules_;++i) {
        if(!multiCore_ && esp_timer_get_time()-lastBlock>100000) { vTaskDelay(1); lastBlock=esp_timer_get_time(); }
        size_t free0=0;
        if(ramProbe_) {
            free0=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
            heap_caps_monitor_local_minimum_free_size_start();
        }
        const int64_t s0=esp_timer_get_time();
        trunk_->run(int(modules_),int(i),multiCore_ ? dl::RUNTIME_MODE_MULTI_CORE : dl::RUNTIME_MODE_SINGLE_CORE);
        stageUs_[i]+=uint64_t(esp_timer_get_time()-s0); ++stageCalls_[i];
        if(ramProbe_) {
            const size_t low=heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
            heap_caps_monitor_local_minimum_free_size_stop();
            if(free0>low && free0-low>worstDip_) { worstDip_=free0-low; worstDipModule_=i; }
        }
    }
    ++embeds_;
    const int64_t t2=esp_timer_get_time();
    const size_t C=info_.channels, D=info_.dim, T=outFrames_;
    const float outScale=std::ldexp(1.0f,int(output_->exponent));
    if(output_->dtype==dl::DATA_TYPE_INT16) {
        const auto* q=static_cast<const int16_t*>(output_->data);
        for(size_t i=0;i<T*C;++i)frames_[i]=float(q[i])*outScale;
    } else {
        const auto* q=static_cast<const int8_t*>(output_->data);
        for(size_t i=0;i<T*C;++i)frames_[i]=float(q[i])*outScale;
    }
    const int64_t t3=esp_timer_get_time();
    // SAP: score_t = att . tanh(W x_t + b); weights = softmax_t; pooled = sum w_t x_t; e = Wfc pooled + bfc
    float best=-1e30f;
    for(size_t t=0;t<T;++t) {
        const float* x=frames_+t*C;
        float s=0;
        for(size_t o=0;o<C;++o) {
            const float* w=sapW_+o*C;
            float acc=sapB_[o];
            for(size_t i=0;i<C;++i)acc+=w[i]*x[i];
            s+=att_[o]*std::tanh(acc);
        }
        scores_[t]=s;
        if(s>best)best=s;
    }
    const int64_t t4=esp_timer_get_time();
    float sum=0;
    for(size_t t=0;t<T;++t) { scores_[t]=std::exp(scores_[t]-best); sum+=scores_[t]; }
    for(size_t i=0;i<C;++i)pooled_[i]=0;
    for(size_t t=0;t<T;++t) {
        const float w=scores_[t]/sum; const float* x=frames_+t*C;
        for(size_t i=0;i<C;++i)pooled_[i]+=w*x[i];
    }
    const int64_t t5=esp_timer_get_time();
    for(size_t o=0;o<D;++o) {
        const float* w=fcW_+o*C;
        float acc=fcB_[o];
        for(size_t i=0;i<C;++i)acc+=w[i]*pooled_[i];
        e[o]=acc;
    }
    if(timing) {
        const int64_t t6=esp_timer_get_time();
        const auto& ft=frontend_.timing();
        timing->featureUs=uint32_t(tq-t0); timing->fftUs=ft.fftUs; timing->melUs=ft.melUs; timing->normUs=ft.normUs;
        timing->frames=uint16_t(ft.frames); timing->cropped=ft.cropped;
        timing->quantUs=uint32_t(t1-tq); timing->trunkUs=uint32_t(t2-t1); timing->dequantUs=uint32_t(t3-t2);
        timing->sapUs=uint32_t(t4-t3); timing->poolUs=uint32_t(t5-t4); timing->fcUs=uint32_t(t6-t5);
        timing->headUs=uint32_t(t6-t3);
    }
    return true;
}

}  // namespace hw1::stt::speaker
