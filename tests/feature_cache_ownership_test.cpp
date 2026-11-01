// Production HardwareOne worker/retirement code with host task/lock adapters.
// The actual production DSP is used. Only its entry is gated to reproduce a
// preemption window; no audio, feature values or transcript text are printed.
#include "stt/quartznet_frontend.h"
#include <algorithm>
#include <cassert>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <thread>
#include <vector>
constexpr size_t kFeRingSamples=65536,kFeMaxRows=1000,kFeBatchRows=8,kFeRowFloats=64,kStreamReadSamples=1024;
constexpr int kFeCaches=2;
constexpr bool pdTRUE=true;
constexpr unsigned pdMS_TO_TICKS(unsigned x){return x;}
enum class FeState:uint8_t {Free,Live,Attached,Orphan};
struct FeCache {
    float* rows=nullptr;uint64_t start=0;size_t frames=0;
    uint32_t gen=0;FeState state=FeState::Free;bool overrun=false;
};
struct ProducerPosition {
    uint64_t seen=1600;
    uint64_t samples_seen() const {return seen;}
};
struct StreamRun {
    ProducerPosition segmenter;
    bool feRingStarted=true; uint64_t feRingStart=0;
    FeCache fe[2];int feLive=0;bool feStop=false,feRunning=true;
    uint64_t feRingHead=1600;size_t feLiveLen=1600;
    int16_t* feRing=nullptr;hw1::stt::FrontendWorkspace* feWork=nullptr;
    uint32_t feRowsComputed=0,feOverruns=0;
};
std::mutex gSTTMux;
#define portENTER_CRITICAL(p) (p)->lock()
#define portEXIT_CRITICAL(p) (p)->unlock()
StreamRun* activeRun=nullptr;
unsigned ulTaskNotifyTake(bool,unsigned) {
    thread_local unsigned calls=0;
    if(calls++) {std::lock_guard<std::mutex> guard(gSTTMux);activeRun->feStop=true;}
    return 1;
}
void vTaskDelete(void*) {}
std::mutex gateMutex;std::condition_variable gateCv;
bool entered=false,allowed=false,invalidFirstRow=false;size_t dspCalls=0;
hw1::stt::Status observed_log_mel_frame_ring(const int16_t* ring,size_t mask,uint64_t start,
        size_t samples,size_t frame,float* out,hw1::stt::FrontendWorkspace* work) {
    if(dspCalls++==0) {
        std::unique_lock<std::mutex> guard(gateMutex);
        entered=true;gateCv.notify_one();gateCv.wait(guard,[]{return allowed;});
    }
    return hw1::stt::log_mel_frame_ring(ring,mask,start,invalidFirstRow && frame==0 ? 0 : samples,frame,out,work);
}
namespace reference {
#include "retirement_reference.inc"
#include "worker_reference.inc"
}
#include "ring_writer_reference.inc"
#ifdef HAVE_CANDIDATE
namespace candidate {
#include "retirement_reference.inc"
#include "worker_candidate.inc"
}
#endif
#ifdef HAVE_RING_CANDIDATE
namespace ring_candidate {
#include "ring_snapshot_candidate.inc"
#include "retirement_reference.inc"
#include "ring_writer_candidate.inc"
#include "worker_ring_candidate.inc"
}
#endif
using FeatureWorker=void(*)(void*);
static void parityCases(FeatureWorker worker,unsigned variant) {
    const size_t lengths[]={320,321,479,480,511,512,1280,1297,16000,44560,64000,100000,160000};
    const uint64_t starts[]={0,1,350,511,65088,65520,65535,131073};
    size_t cases=0,equal=0;
    allowed=true;
    for(const auto samples:lengths)for(const auto start:starts) {
        std::vector<int16_t> ring(kFeRingSamples);
        for(size_t i=0;i<samples;++i)ring[(start+i)&(kFeRingSamples-1)]=int16_t(int((i*73+19)%15001)-7500);
        std::vector<float> rows(kFeMaxRows*64);
        hw1::stt::FrontendWorkspace work{},compare{};
        StreamRun run;activeRun=&run;run.feRing=ring.data();run.feWork=&work;
        run.feRingHead=start+samples;run.feLiveLen=samples;
        const size_t initial=samples>64351 ? (samples-64351+159)/160 : 0;
        run.fe[0].rows=rows.data();run.fe[0].state=FeState::Live;run.fe[0].gen=13;
        run.fe[0].start=start;run.fe[0].frames=initial;
        dspCalls=0;entered=false;
        std::thread task([&]{worker(&run);});task.join();
        const size_t end=std::min(samples/160,kFeMaxRows);
        assert(!run.feRunning && run.fe[0].frames==end && run.feRowsComputed==end-initial && run.feOverruns==0);
        float expected[64];
        for(size_t i=initial;i<end;++i) {
            assert(hw1::stt::log_mel_frame_ring(ring.data(),kFeRingSamples-1,start,samples,i,expected,&compare)==hw1::stt::Status::Ok);
            assert(!memcmp(expected,rows.data()+i*64,sizeof(expected)));++equal;
        }
        ++cases;
    }
    std::printf("feature PCM windows: variant=%u cases=%zu equal_rows=%zu first_and_last_rows=1 physical_and_private_wrap=1\n",variant,cases,equal);
}
int main(int argc,char** argv) {
    bool overlap=false,attached=false,fixed=false,live=false,ringOverlap=false,ringFixed=false,parity=false;
    for(int i=1;i<argc;++i) {
        if(!strcmp(argv[i],"--parity"))parity=true;
        else if(!strcmp(argv[i],"--ring-candidate")){ringFixed=true;fixed=true;}
        else if(!strcmp(argv[i],"--overlap"))overlap=true;
        else if(!strcmp(argv[i],"--attached"))attached=true;
        else if(!strcmp(argv[i],"--candidate"))fixed=true;
        else if(!strcmp(argv[i],"--live"))live=true;
        else if(!strcmp(argv[i],"--ring-overlap")){live=true;ringOverlap=true;}
        else if(!strcmp(argv[i],"--fail-dsp"))invalidFirstRow=true;
        else return 2;
    }
    std::vector<int16_t> ring(kFeRingSamples);
    for(size_t i=0;i<ring.size();++i)ring[i]=int16_t(int((i*73)%15001)-7500);
    std::vector<float> rows[2]={std::vector<float>(kFeMaxRows*64),std::vector<float>(kFeMaxRows*64)};
    hw1::stt::FrontendWorkspace work{};StreamRun run;activeRun=&run;
    run.feRing=ring.data();run.feWork=&work;
    for(unsigned i=0;i<2;++i) {run.fe[i].rows=rows[i].data();run.fe[i].gen=13;}
    run.fe[0].state=FeState::Live;
    auto worker=reference::sttFeatureWorker;
    auto retire=reference::sttFeatureRetireOrphans;
    auto release=reference::sttFeatureRelease;
#ifdef HAVE_CANDIDATE
    if(fixed) {worker=candidate::sttFeatureWorker;retire=candidate::sttFeatureRetireOrphans;release=candidate::sttFeatureRelease;}
#else
    if(fixed)return 2;
#endif
    auto producer=sttFeatureRingWrite;
#ifdef HAVE_RING_CANDIDATE
    if(ringFixed) {worker=ring_candidate::sttFeatureWorker;retire=ring_candidate::sttFeatureRetireOrphans;release=ring_candidate::sttFeatureRelease;producer=ring_candidate::sttFeatureRingWrite;}
#else
    if(ringFixed)return 2;
#endif
    if(parity){parityCases(worker,ringFixed?2:fixed?1:0);return 0;}
    std::thread feature([&]{worker(&run);});
    {std::unique_lock<std::mutex> guard(gateMutex);gateCv.wait(guard,[]{return entered;});}
    if(!live) {std::lock_guard<std::mutex> guard(gSTTMux);run.fe[0].state=attached?FeState::Attached:FeState::Orphan;run.feLive=-1;}
    auto allow=[&] {std::lock_guard<std::mutex> guard(gateMutex);allowed=true;gateCv.notify_one();};
    // Late schedule proves the wipe can be overwritten after cache retirement.
    // Overlap schedule has no happens-before between the two raw writes, for
    // the independent ThreadSanitizer check. Retirement helpers are unchanged.
    if(ringOverlap) {
        // The DSP took its head snapshot before this forced preemption.
        // Approach wrap while paused; the first resumed producer block writes
        // the same physical samples that row zero reads. All copies use the
        // unchanged production ring writer, not a sanitizer-only replacement.
        int16_t block[kStreamReadSamples];
        for(size_t i=0;i<kStreamReadSamples;++i)block[i]=int16_t(i*13);
        for(unsigned i=0;i<62;++i) {
            producer(run,ring.data(),block,kStreamReadSamples);
            run.segmenter.seen+=kStreamReadSamples;
        }
        allow();
        for(unsigned i=62;i<192;++i) {
            producer(run,ring.data(),block,kStreamReadSamples);
            run.segmenter.seen+=kStreamReadSamples;
        }
    }
    else if(live)allow();
    else {
        if(overlap)allow();
        if(attached)release(run,0,13);else retire(run);
        if(!overlap)allow();
    }
    feature.join();
    const size_t nonzero=std::count_if(rows[0].begin(),rows[0].end(),[](float x){return x!=0;});
    assert(!run.feRunning);
    if(ringOverlap) {
        assert(run.fe[0].state==FeState::Live && run.fe[0].gen==13);
        assert(run.fe[0].frames==0 && run.feRowsComputed==0 && run.feOverruns==1);
    }
    else if(live) {
        assert(run.fe[0].state==FeState::Live && run.fe[0].gen==13);
        if(invalidFirstRow && fixed) {
            assert(run.fe[0].frames==0 && run.feRowsComputed==0 && run.feOverruns==1 && nonzero==0);
        } else {
            assert(run.fe[0].frames==10 && run.feRowsComputed==10);
            hw1::stt::FrontendWorkspace compare{};float expected[64];size_t mismatches=0;
            for(size_t r=0;r<10;++r) {
                assert(hw1::stt::log_mel_frame_ring(ring.data(),kFeRingSamples-1,0,1600,r,expected,&compare)==hw1::stt::Status::Ok);
                mismatches+=memcmp(expected,rows[0].data()+r*64,sizeof(expected))!=0;
            }
            assert(mismatches==size_t(invalidFirstRow));
        }
    } else {
        assert(run.fe[0].state==FeState::Free && run.fe[0].gen==14);
        assert(run.fe[0].frames==0 && run.feRowsComputed==0);
        if(fixed)assert(nonzero==0);
        else if(!overlap)assert(nonzero>0);
    }
    std::printf("feature ownership: candidate=%u attached=%u overlap=%u live=%u failed_dsp=%u dsp_calls=%zu nonzero=%zu committed_rows=%u overruns=%u ring_overlap=%u ring_fixed=%u\n",
        unsigned(fixed),unsigned(attached),unsigned(overlap),unsigned(live),unsigned(invalidFirstRow),dspCalls,nonzero,run.feRowsComputed,run.feOverruns,unsigned(ringOverlap),unsigned(ringFixed));
}
