// The Python driver inserts actual headers/container/runtime below. Only the
// external dependencies are fakes. Never copy the production cache algorithm here.
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <map>
#include <memory>
#include <new>
#include <string>
#include <vector>

// INSERT_INTERFACE

namespace hw1::stt::identity {
inline constexpr size_t kSampleRate=16000, kMaxSamples=480000;
// Large enough that a warm free-memory budget cannot accidentally include a
// second copy; compressed input crosses the runtime's 4096-byte read boundary.
inline constexpr size_t kRawBytes=2*1024*1024, kCompressedBytes=5000;
inline constexpr int kInputExponent=-4, kOutputExponent=-2, kNodeCount=3;
inline constexpr uint32_t kCodec=1;  // deployed-tree identity field (zlib path is the faked one)
inline constexpr const char* kInputName="input";
inline constexpr const char* kOutputName="output";
inline constexpr uint8_t kRawSha[32]={
    0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,
    0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42};
inline constexpr uint8_t kFrontendSha[32]={0x73};
}
// INSERT_CONTAINER

namespace fake {
struct Allocation { size_t size; bool sensitive; };
struct State {
    std::map<void*,Allocation> allocations;
    std::vector<std::string> events;
    std::vector<size_t> modelFrames;
    std::vector<int> runStages;
    size_t allocated=0, allocationCalls=0, failAllocation=0;
    size_t psramTotal=32*1024*1024, internalFree=1024*1024, internalLargest=1024*1024;
    size_t largest=32*1024*1024;
    bool fragmentAfterRaw=false;
    int rawAllocations=0, rawFrees=0, models=0, created=0, destroyed=0;
    int inflates=0, rawHashes=0, failHash=0, wrongHash=0;
    bool inflateError=false, inflateShort=false, frontendError=false;
    bool modelAllocationError=false, tensorError=false, decodeError=false, truncate=false;
    bool cancel=false, cancelAfterHash=false, cancelAfterStage=false;
    int cancelAtPhase=-1;
    STTLocalPhase phase=STTLocalPhase::Loading;
    bool mutateInDestructor=false;
    uint8_t* lastRaw=nullptr;
    int greedyFeeds=0;
    size_t melRows=0, normalizes=0;
    const int8_t* lastOutput=nullptr;
} state;
void clean() { assert(state.allocations.empty()); assert(state.models==0); state=State{}; }
bool hasRaw(const void* p) {
    auto found=state.allocations.find(const_cast<void*>(p));
    return found!=state.allocations.end() && found->second.size==hw1::stt::identity::kRawBytes;
}
size_t rawLive() {
    size_t result=0;
    for(const auto& item:state.allocations)if(item.second.size==hw1::stt::identity::kRawBytes)++result;
    return result;
}
void settled(size_t expectedRaw) {
    assert(state.models==0);
    assert(rawLive()==expectedRaw);
    assert(state.allocations.size()==expectedRaw); // no temporary/workspace leak
}
bool cancelled(void*) { return state.cancel; }
void progress(void*,STTLocalPhase phase) {
    state.phase=phase;
    if(state.cancelAtPhase==int(phase))state.cancel=true;
}
STTLocalControl control() { return {nullptr,cancelled,progress}; }
}
constexpr unsigned MALLOC_CAP_SPIRAM=1, MALLOC_CAP_8BIT=2, MALLOC_CAP_INTERNAL=4;
void* heap_caps_aligned_alloc(size_t alignment,size_t bytes,unsigned caps) {
    assert(alignment==16 && caps==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    ++fake::state.allocationCalls;
    if(fake::state.allocationCalls==fake::state.failAllocation)return nullptr;
    void* p=nullptr;
    if(posix_memalign(&p,alignment,bytes))return nullptr;
    std::memset(p,0xcd,bytes);
    fake::state.allocations.emplace(p,fake::Allocation{bytes,fake::state.phase==STTLocalPhase::Frontend});
    fake::state.allocated+=bytes;
    if(bytes==hw1::stt::identity::kRawBytes) {
        ++fake::state.rawAllocations;fake::state.lastRaw=static_cast<uint8_t*>(p);
        fake::state.events.push_back("allocate weights");
    }
    return p;
}
void heap_caps_free(void* p) {
    if(!p)return;
    auto found=fake::state.allocations.find(p);
    assert(found!=fake::state.allocations.end()); // double-free / unowned pointer
    if(found->second.size==hw1::stt::identity::kRawBytes) {
        assert(fake::state.models==0); // vendor weights cannot outlive backing
        ++fake::state.rawFrees;fake::state.events.push_back("free weights");
    }
    if(found->second.sensitive) {
        auto bytes=static_cast<const uint8_t*>(p);
        for(size_t i=0;i<found->second.size;++i)assert(bytes[i]==0);
    }
    fake::state.allocated-=found->second.size;
    fake::state.allocations.erase(found);std::free(p);
}
size_t heap_caps_get_free_size(unsigned caps) {
    if(caps&MALLOC_CAP_INTERNAL)return fake::state.internalFree;
    assert(caps==MALLOC_CAP_SPIRAM);
    return fake::state.psramTotal>fake::state.allocated?fake::state.psramTotal-fake::state.allocated:0;
}
size_t heap_caps_get_largest_free_block(unsigned caps) {
    if(caps&MALLOC_CAP_INTERNAL)return fake::state.internalLargest;
    assert(caps==MALLOC_CAP_SPIRAM);
    if(fake::state.fragmentAfterRaw && fake::rawLive())return 1024;
    return fake::state.largest;
}
int64_t esp_timer_get_time() { static int64_t clock=0; return clock+=1000; }
void vTaskDelay(int ticks) { assert(ticks==1); }
#define taskYIELD() ((void)0)  // non-blocking yield between 5-stage groups
int mbedtls_sha256(const unsigned char* input,size_t size,unsigned char* output,int is224) {
    assert(is224==0);
    if(size==hw1::stt::identity::kRawBytes) {
        ++fake::state.rawHashes;
        assert(fake::hasRaw(input));
        if(fake::state.rawHashes==fake::state.failHash)return -1;
        bool valid=true;for(size_t i=0;i<size;++i)if(input[i]!=0x5a){valid=false;break;}
        if(fake::state.rawHashes==fake::state.wrongHash)valid=false;
        std::memset(output,valid?0x42:0x43,32);
        if(fake::state.cancelAfterHash)fake::state.cancel=true;
    } else std::memset(output,0x77,32);
    return 0;
}
struct tinfl_decompressor { unsigned calls; };
enum tinfl_status { TINFL_STATUS_FAILED=-1,TINFL_STATUS_DONE=0,TINFL_STATUS_NEEDS_MORE_INPUT=1 };
constexpr unsigned TINFL_FLAG_PARSE_ZLIB_HEADER=1,TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF=2,TINFL_FLAG_HAS_MORE_INPUT=4;
void tinfl_init(tinfl_decompressor* d) { d->calls=0; }
tinfl_status tinfl_decompress(tinfl_decompressor* d,const uint8_t* input,size_t* in,
                              uint8_t* base,uint8_t* output,size_t* out,unsigned flags) {
    ++d->calls;++fake::state.inflates;
    assert(fake::hasRaw(base));assert(*in>0);
    for(size_t i=0;i<*in;++i)assert(input[i]==0xa7);
    if(fake::state.inflateError)return TINFL_STATUS_FAILED;
    const bool more=flags&TINFL_FLAG_HAS_MORE_INPUT;
    const size_t count=more?std::min(*out,size_t(128)):*out-(fake::state.inflateShort?1:0);
    std::memset(output,0x5a,count);*out=count;
    return more?TINFL_STATUS_NEEDS_MORE_INPUT:TINFL_STATUS_DONE;
}
namespace fbs { constexpr int MODEL_LOCATION_IN_FLASH_RODATA=1; }
namespace dl {
constexpr int DATA_TYPE_INT8=1,MEMORY_MANAGER_GREEDY=1,RUNTIME_MODE_MULTI_CORE=1;
struct Exponent { int value; bool is_valid()const{return true;} bool is_per_channel()const{return false;} explicit operator int()const{return value;} };
struct TensorBase {
    std::vector<int> shape;
    std::vector<int8_t> storage;
    void* data=nullptr;
    int dtype=DATA_TYPE_INT8;
    Exponent exponent{0};
    void init(size_t frames,size_t channels,int exp) {
        shape={1,int(frames),1,int(channels)};storage.resize(frames*channels);data=storage.data();exponent.value=exp;
    }
    int get_bytes()const{return int(storage.size());}
};
struct Memory { size_t psram,internal; };
class Model {
    const void* weights;
    TensorBase input,output;
 public:
    static void* operator new(size_t n,const std::nothrow_t&)noexcept {
        return fake::state.modelAllocationError?nullptr:std::malloc(n);
    }
    static void operator delete(void* p)noexcept {std::free(p);}
    static void operator delete(void* p,const std::nothrow_t&)noexcept {std::free(p);}
    Model(const char* raw,int location,int index,int manager,void* unused,bool copy,
          const std::map<std::string,std::vector<int>>& shapes):weights(raw) {
        assert(fake::hasRaw(raw));assert(location==fbs::MODEL_LOCATION_IN_FLASH_RODATA);
        assert(index==0 && manager==MEMORY_MANAGER_GREEDY && !unused && !copy);
        assert(fake::state.models==0);++fake::state.models;++fake::state.created;
        fake::state.events.push_back("create model");
        const auto shape=shapes.at(hw1::stt::identity::kInputName);
        assert(shape[0]==1 && shape[2]==1 && shape[3]==64);
        const size_t frames=size_t(shape[1]);fake::state.modelFrames.push_back(frames);
        input.init(frames,64,hw1::stt::identity::kInputExponent);
        output.init((frames+1)/2,29,hw1::stt::identity::kOutputExponent);
    }
    ~Model() {
        assert(fake::hasRaw(weights));
        if(fake::state.mutateInDestructor)static_cast<uint8_t*>(const_cast<void*>(weights))[17]^=1;
        --fake::state.models;++fake::state.destroyed;fake::state.events.push_back("destroy model");
    }
    TensorBase* get_input(const char*) { if(fake::state.tensorError)input.exponent.value=99;return &input; }
    TensorBase* get_output(const char*) {fake::state.lastOutput=static_cast<const int8_t*>(output.data);return &output;}
    std::map<std::string,Memory> get_memory_info()const{return {{"variable",{4096,512}}};}
    void run(int count,int stage,int mode) {
        assert(fake::hasRaw(weights));assert(count==hw1::stt::identity::kNodeCount && mode==RUNTIME_MODE_MULTI_CORE);
        fake::state.runStages.push_back(stage);
        if(fake::state.cancelAfterStage)fake::state.cancel=true;
    }
};
}
namespace hw1::stt {
size_t feature_frames(size_t samples) {return (samples+159)/160;}
Status compute_features(const int16_t*,size_t samples,float* output,size_t count,FrontendWorkspace*,uint32_t,bool,FrontendTiming*) {
    assert(count==feature_frames(samples)*kMelBins);
    if(fake::state.frontendError)return Status::NonFinite;
    for(size_t i=0;i<count;++i)output[i]=float(int(i%5)-2)*0.0625f;
    return Status::Ok;
}
// capture-time features: cached-prefix frontend. Rows are a pure function of the row
// index, so a prefix built by the test equals what the runtime computes.
float fakeRow(size_t row,size_t m) {return float(int((row*kMelBins+m)%7)-3)*0.03125f;}
Status log_mel_frame(const int16_t* pcm,size_t samples,size_t frame,float* out,FrontendWorkspace* w) {
    assert(pcm && out && w && frame<feature_frames(samples));
    ++fake::state.melRows;
    for(size_t m=0;m<kMelBins;++m)out[m]=fakeRow(frame,m);
    return Status::Ok;
}
Status normalize_features(float* output,size_t frames,FrontendWorkspace* w,FrontendTiming*) {
    assert(output && w && frames);
    ++fake::state.normalizes;
    for(size_t r=0;r<frames;++r)for(size_t m=0;m<kMelBins;++m)assert(output[r*kMelBins+m]==fakeRow(r,m));
    return Status::Ok;
}
Status ctc_reset(CtcState* state,char* text,size_t cap) {assert(cap>2);*state={};text[0]=0;return Status::Ok;}
Status ctc_feed(CtcState* state,const int8_t*,size_t frames,size_t stride,char* text,size_t cap) {
    assert(stride==29 && cap>2 && frames>0);
    ++fake::state.greedyFeeds;
    if(fake::state.decodeError)return Status::InvalidArgument;
    state->truncated=fake::state.truncate;std::strcpy(text,"ok");return Status::Ok;
}
Status ctc_finish(CtcState* state,char*,size_t) {state->finished=true;return Status::Ok;}
}

// Host stand-in for the ROM CRC-32 (little-endian, IEEE polynomial).
uint32_t esp_rom_crc32_le(uint32_t crc,const uint8_t* p,uint32_t n) {
    crc=~crc;for(uint32_t i=0;i<n;++i){crc^=p[i];for(int k=0;k<8;++k)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}return ~crc;
}
// Host stand-ins: evaluate and format-check the arguments, print the line.
#define ESP_LOGI(tag, fmt, ...) ((void)std::printf("I %s: " fmt "\n", tag, __VA_ARGS__))
#define ESP_LOGW(tag, fmt, ...) ((void)std::printf("W %s: " fmt "\n", tag, __VA_ARGS__))
// INSERT_RUNTIME

namespace test {
using namespace hw1::stt;
struct Reader {
    std::vector<uint8_t> data;
    size_t offset=0, bytesRead=0, calls=0, maxRead=73, stopAt=std::numeric_limits<size_t>::max();
    Reader():data(container::kHeaderBytes+identity::kCompressedBytes,0xa7) {
        std::fill(data.begin(),data.begin()+container::kHeaderBytes,0);
        std::memcpy(data.data(),"HW1STT1\0",8);
        word(8,1);word(12,1);word(16,identity::kRawBytes);word(20,identity::kCompressedBytes);
        word(24,identity::kSampleRate);word(28,identity::kMaxSamples);
        std::memcpy(data.data()+32,identity::kRawSha,32);std::memcpy(data.data()+64,identity::kFrontendSha,32);
    }
    void word(size_t offset,uint32_t value) {for(unsigned i=0;i<4;++i)data[offset+i]=uint8_t(value>>(8*i));}
    static size_t read(void* context,void* dest,size_t size) {
        auto& self=*static_cast<Reader*>(context);++self.calls;
        if(self.offset>=self.stopAt)return 0;
        size=std::min({size,self.maxRead,self.data.size()-self.offset,self.stopAt-self.offset});
        std::memcpy(dest,self.data.data()+self.offset,size);self.offset+=size;self.bytesRead+=size;return size;
    }
    ModelReader model() {return {this,data.size(),read};}
};
struct Result { bool ok;STTLocalStats stats;std::string text,error; };
Result call(ModelCache* cache,Reader& reader,size_t samples=320) {
    std::vector<int16_t> pcm(samples,42);char text[64],error[128];STTLocalStats stats;
    Diagnostics diagnostics;
    const bool ok=transcribe(reader.model(),pcm.data(),samples,text,sizeof(text),fake::control(),stats,error,sizeof(error),&diagnostics,cache);
    if(ok) {assert(std::string(text)=="ok");assert(!error[0]);assert(stats.samples==samples);}
    else {assert(!text[0]);assert(error[0]);}
    return {ok,stats,text,error};
}
size_t remainingBudget(size_t samples) {
    const size_t frames=feature_frames(samples),outputs=(frames+1)/2;
    return 2048*outputs+64*1024+frames*kMelBins*sizeof(float)+sizeof(FrontendWorkspace)+1024*1024;
}
constexpr int kWarmHash = HW1_STT_RUNTIME_DIAGNOSTICS ? 1 : 0;
void coldWarmShapes() {
    fake::clean();
    {
        ModelCache cache;
        Reader a;auto first=call(&cache,a);
        assert(first.ok && !first.stats.weightsReused && first.stats.featureFrames==2 && first.stats.outputFrames==1);
        assert(a.bytesRead==a.data.size());
        assert(fake::state.inflates==2 && fake::state.rawHashes==1);fake::settled(1);
        Reader b;auto second=call(&cache,b,480);
        assert(second.ok && second.stats.weightsReused && second.stats.featureFrames==3 && second.stats.outputFrames==2);
        assert(b.bytesRead==container::kHeaderBytes && fake::state.inflates==2 && fake::state.rawHashes==1+kWarmHash); // verified once per session load (+probe re-check)
        Reader c;auto third=call(&cache,c);
        assert(third.ok && third.stats.weightsReused && third.stats.featureFrames==2 && third.stats.outputFrames==1);
        assert(c.bytesRead==container::kHeaderBytes);
        assert(fake::state.modelFrames==std::vector<size_t>({2,3,2}));
        assert(fake::state.created==3 && fake::state.destroyed==3 && fake::state.rawAllocations==1);
        assert(fake::state.rawHashes==1+2*kWarmHash);fake::settled(1);
        cache.reset();fake::settled(0);assert(fake::state.rawFrees==1);
        cache.reset();assert(fake::state.rawFrees==1);
    }
    assert(fake::state.rawFrees==1);fake::settled(0);
}
void oneShotOrder() {
    fake::clean();
    for(int i=0;i<2;++i){Reader reader;auto result=call(nullptr,reader);assert(result.ok && !result.stats.weightsReused);fake::settled(0);}
    assert(fake::state.rawAllocations==2 && fake::state.rawFrees==2 && fake::state.inflates==4);
    const std::vector<std::string> expected={"allocate weights","create model","destroy model","free weights",
                                           "allocate weights","create model","destroy model","free weights"};
    assert(fake::state.events==expected);
}
void failuresBeforePublish() {
    // Failure at the source envelope, allocation, compressed read, inflate or
    // digest boundary must never publish unverified weights into the cache.
    for(int scenario=0;scenario<11;++scenario) {
        fake::clean();ModelCache cache;Reader reader;
        switch(scenario) {
            case 0:reader.data[0]^=1;break;
            case 1:reader.data.pop_back();break;
            case 2:fake::state.failAllocation=1;break;
            case 3:fake::state.failAllocation=2;break;
            case 4:reader.stopAt=container::kHeaderBytes+4200;break;
            case 5:fake::state.inflateError=true;break;
            case 6:fake::state.inflateShort=true;break;
            case 7:fake::state.failHash=1;break;
            case 8:fake::state.wrongHash=1;break;
            case 9:fake::state.cancelAfterHash=true;break;
            case 10:fake::state.cancel=true;break;
        }
        auto result=call(&cache,reader);assert(!result.ok);assert(fake::state.created==0);fake::settled(0);
        fake::state.failAllocation=0;fake::state.inflateError=false;fake::state.inflateShort=false;
        fake::state.failHash=0;fake::state.wrongHash=0;fake::state.cancelAfterHash=false;fake::state.cancel=false;
        Reader retry;auto recovered=call(&cache,retry);assert(recovered.ok && !recovered.stats.weightsReused);
        assert(retry.bytesRead==retry.data.size());cache.reset();fake::settled(0);
    }
}
void failuresAfterPublish() {
    for(int scenario=0;scenario<11;++scenario) {
        fake::clean();ModelCache cache;Reader reader;
        switch(scenario) {
            case 0:fake::state.fragmentAfterRaw=true;break;
            case 1:fake::state.modelAllocationError=true;break;
            case 2:fake::state.tensorError=true;break;
            case 3:fake::state.failAllocation=3;break;
            case 4:fake::state.failAllocation=4;break;
            case 5:fake::state.frontendError=true;break;
            case 6:fake::state.decodeError=true;break;
            case 7:fake::state.truncate=true;break;
            case 8:fake::state.cancelAtPhase=int(STTLocalPhase::Frontend);break;
            case 9:fake::state.cancelAfterStage=true;break;
            case 10:fake::state.cancelAtPhase=int(STTLocalPhase::Decoding);break;
        }
        auto result=call(&cache,reader);assert(!result.ok);fake::settled(1);
        assert(fake::state.rawHashes==1 && fake::state.rawFrees==0);
        fake::state.fragmentAfterRaw=false;fake::state.modelAllocationError=false;fake::state.tensorError=false;
        fake::state.failAllocation=0;fake::state.frontendError=false;fake::state.decodeError=false;fake::state.truncate=false;
        fake::state.cancelAtPhase=-1;fake::state.cancelAfterStage=false;fake::state.cancel=false;
        Reader retry;auto recovered=call(&cache,retry);assert(recovered.ok && recovered.stats.weightsReused);
        assert(retry.bytesRead==container::kHeaderBytes && fake::state.rawHashes==1+kWarmHash);
        cache.reset();fake::settled(0);assert(fake::state.rawFrees==1);
    }
    // A one-shot post-publish failure must also release the retained temporary.
    fake::clean();fake::state.frontendError=true;Reader reader;assert(!call(nullptr,reader).ok);fake::settled(0);
    assert(fake::state.rawFrees==1 && fake::state.destroyed==1);
}
#if HW1_STT_RUNTIME_DIAGNOSTICS
void corruptedAndFailedHash() {
    for(int scenario=0;scenario<3;++scenario) {
        fake::clean();ModelCache cache;Reader cold;assert(call(&cache,cold).ok);
        const int created=fake::state.created;
        if(scenario==0)fake::state.lastRaw[17]^=1;
        if(scenario==1)fake::state.failHash=2;
        if(scenario==2)fake::state.wrongHash=2;
        Reader warm;auto result=call(&cache,warm);
        assert(!result.ok && result.error=="Cached STT model checksum mismatch");
        assert(fake::state.created==created && fake::state.inflates==2 && warm.bytesRead==container::kHeaderBytes);
        assert(fake::state.rawHashes==2 && fake::state.rawFrees==1);fake::settled(0);
        fake::state.failHash=0;fake::state.wrongHash=0;
        Reader retry;assert(call(&cache,retry).ok);assert(retry.bytesRead==retry.data.size());
        assert(fake::state.rawAllocations==2);cache.reset();assert(fake::state.rawFrees==2);
    }
}
#else
void corruptedAndFailedHash() {
    // Weights are SHA-verified once when a session loads them; warm segments
    // do not re-hash 7.2 MB (sttperf measured ~0.6 s per segment on the P4).
    fake::clean();
    {
        ModelCache cache;Reader cold;assert(call(&cache,cold).ok && fake::state.rawHashes==1);
        fake::state.failHash=2;fake::state.wrongHash=2;
        Reader warm;auto result=call(&cache,warm);
        assert(result.ok && result.stats.weightsReused && warm.bytesRead==container::kHeaderBytes);
        assert(fake::state.rawHashes==1 && fake::state.inflates==2);
        fake::state.failHash=0;fake::state.wrongHash=0;
        cache.reset();fake::settled(0);assert(fake::state.rawFrees==1);
    }
    // A cold load still rejects weights whose hash does not match.
    for(int scenario=0;scenario<2;++scenario) {
        fake::clean();
        if(scenario==0)fake::state.failHash=1; else fake::state.wrongHash=1;
        ModelCache cache;Reader bad;auto result=call(&cache,bad);
        assert(!result.ok && result.error=="STT model checksum mismatch");
        fake::settled(0);
        fake::state.failHash=0;fake::state.wrongHash=0;
        test::Reader retry;assert(test::call(&cache,retry).ok);cache.reset();fake::settled(0);
    }
}
#endif
void warmBudgetAndEnvelope() {
    fake::clean();ModelCache cache;Reader cold;assert(call(&cache,cold).ok);
    // Free memory admits activations/frontend, but cannot fit a second weights
    // copy. Largest block is similarly smaller than the pinned raw model.
    fake::state.psramTotal=identity::kRawBytes+remainingBudget(320)+1024;
    fake::state.largest=remainingBudget(320)+1024;
    assert(fake::state.largest<identity::kRawBytes);
    Reader warm;assert(call(&cache,warm).ok);assert(warm.bytesRead==container::kHeaderBytes);
    // A changed/invalid current file envelope is still rejected on a cache hit.
    const int created=fake::state.created,hashes=fake::state.rawHashes;
    Reader bad;bad.data[32]^=1;assert(!call(&cache,bad).ok);
    assert(fake::state.created==created && fake::state.rawHashes==hashes);fake::settled(1);
    // Warm calls still enforce temporary-memory guards without throwing away
    // already verified weights; recovery must remain a header-only cache hit.
    fake::state.internalFree=150*1024-1;
    Reader lowInternal;assert(!call(&cache,lowInternal).ok);fake::settled(1);
    assert(fake::state.created==created && fake::state.rawHashes==hashes);
    fake::state.internalFree=1024*1024;
    Reader recovered;auto resumed=call(&cache,recovered);
    assert(resumed.ok && resumed.stats.weightsReused && recovered.bytesRead==container::kHeaderBytes);
    cache.reset();
    const int beforeDenied=fake::state.created;
    fake::state.psramTotal=remainingBudget(320)+1024;
    Reader denied;assert(!call(&cache,denied).ok);assert(fake::state.created==beforeDenied);fake::settled(0);
}
void diagnosticsAfterModelDestruction() {
#if HW1_STT_RUNTIME_DIAGNOSTICS
    fake::clean();ModelCache cache;
    assert(!cache.verify() && fake::state.rawHashes==0);
    Reader cold;assert(call(&cache,cold).ok);assert(fake::state.models==0 && fake::state.destroyed==1);
    assert(cache.verify() && fake::state.rawHashes==2);fake::settled(1);
    // A vendor destructor may be the last writer. The probe must verify after
    // transcribe returns, not merely trust the next call's pre-parse hash.
    fake::state.mutateInDestructor=true;
    Reader warm;assert(call(&cache,warm).ok);assert(fake::state.destroyed==2);
    assert(!cache.verify() && fake::state.rawHashes==4);fake::settled(1);
    assert(fake::state.rawFrees==0); // verify is observational, never resets
    Reader rejected;assert(!call(&cache,rejected).ok);
    assert(fake::state.created==2 && fake::state.rawFrees==1);fake::settled(0);
    assert(!cache.verify() && fake::state.rawHashes==5);
    fake::state.mutateInDestructor=false;
    Reader retry;auto result=call(&cache,retry);assert(result.ok && !result.stats.weightsReused);
    assert(cache.verify());cache.reset();assert(!cache.verify());fake::settled(0);
#endif
}
void guardLimitsAndDestruction() {
    for(int scenario=0;scenario<3;++scenario) {
        fake::clean();ModelCache cache;Reader reader;
        if(scenario==0)fake::state.psramTotal=identity::kRawBytes+remainingBudget(320)-1;
        if(scenario==1)fake::state.largest=identity::kRawBytes-1;
        if(scenario==2)fake::state.internalFree=150*1024-1;
        assert(!call(&cache,reader).ok);assert(fake::state.rawAllocations==0);fake::settled(0);
    }
    fake::clean();
    {ModelCache cache;Reader reader;assert(call(&cache,reader).ok);fake::settled(1);}
    fake::settled(0);assert(fake::state.rawFrees==1);
}
}
namespace test {
// Optional decoder hook: its result replaces greedy only when Decoded and
// NUL-terminated; Fallback leaves the greedy path unchanged; Cancelled fails.
struct FakeDecoder {
    DecodeResult result=DecodeResult::Decoded;
    bool unterminated=false;
    int decodes=0, releases=0;
    size_t frames=0, capacity=0; int exponent=0; const int8_t* logits=nullptr;
    void* lm=nullptr; size_t lmBytes=0;   // PSRAM a real LM would keep resident
    static DecodeResult decode(void* c,const int8_t* logits,size_t frames,int exponent,char* text,size_t cap,const STTLocalControl& control) {
        auto& d=*static_cast<FakeDecoder*>(c);++d.decodes;
        assert(fake::state.phase==STTLocalPhase::Decoding && !control.cancelled(control.context));
        d.frames=frames;d.exponent=exponent;d.capacity=cap;d.logits=logits;
        if(d.unterminated)std::memset(text,'x',cap); else std::snprintf(text,cap,"%s","language model");
        return d.result;
    }
    static bool release(void* c) {
        auto& d=*static_cast<FakeDecoder*>(c);++d.releases;
        if(!d.lm)return false;
        heap_caps_free(d.lm);d.lm=nullptr;return true;
    }
    Decoder hook() {return {this,decode,release};}
};
Result callWith(ModelCache* cache,const Decoder* decoder,size_t samples=320) {
    Reader reader;std::vector<int16_t> pcm(samples,42);char text[64],error[128];STTLocalStats stats;
    const bool ok=transcribe(reader.model(),pcm.data(),samples,text,sizeof(text),fake::control(),stats,error,sizeof(error),nullptr,cache,decoder);
    if(!ok) {assert(!text[0]);assert(error[0]);}
    return {ok,stats,text,error};
}
void decoderHook() {
    for(int scenario=0;scenario<5;++scenario) {
        fake::clean();ModelCache cache;FakeDecoder fd;Decoder hook=fd.hook();
        if(scenario==1)fd.result=DecodeResult::Fallback;
        if(scenario==2)fd.result=DecodeResult::Cancelled;
        if(scenario==3)fd.unterminated=true;
        if(scenario==4)hook.decode=nullptr;
        auto r=callWith(&cache,&hook,480);
        if(scenario==0) {
            assert(r.ok && r.text=="language model" && fake::state.greedyFeeds==0);
        } else if(scenario==2) {
            assert(!r.ok && r.error=="Cancelled" && fake::state.greedyFeeds==0);
        } else {
            assert(r.ok && r.text=="ok" && fake::state.greedyFeeds==1); // byte-identical greedy result
        }
        if(scenario!=4) {
            assert(fd.decodes==1 && fd.frames==2 && fd.exponent==identity::kOutputExponent && fd.capacity==64);
            assert(fd.logits==fake::state.lastOutput);
        }
        assert(fd.releases==0 && r.stats.outputFrames==2);
        fake::settled(1);cache.reset();fake::settled(0);
    }
    // Absent decoder: exactly the previous greedy path.
    fake::clean();{ModelCache cache;auto r=callWith(&cache,nullptr);assert(r.ok && r.text=="ok" && fake::state.greedyFeeds==1);}
    fake::settled(0);
}
void decoderReleasesMemory() {
    // A resident LM that would refuse the call is released first, then the
    // call proceeds (cold: raw weights + budget; warm: budget only).
    for(int warm=0;warm<2;++warm) {
        fake::clean();ModelCache cache;
        if(warm) {Reader reader;assert(call(&cache,reader).ok);}
        FakeDecoder fd;fd.lmBytes=3*1024*1024;fd.lm=heap_caps_aligned_alloc(16,fd.lmBytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
        fake::state.psramTotal=(warm?2:1)*identity::kRawBytes+remainingBudget(320)+1024;
        const Decoder hook=fd.hook();
        auto r=callWith(&cache,&hook);
        assert(r.ok && r.text=="language model" && fd.releases==1 && !fd.lm && fd.decodes==1);
        fake::settled(1);cache.reset();fake::settled(0);
    }
    // Nothing to release, or not enough even after release: refused as before.
    for(int scenario=0;scenario<2;++scenario) {
        fake::clean();ModelCache cache;FakeDecoder fd;
        if(scenario) {fd.lmBytes=1024;fd.lm=heap_caps_aligned_alloc(16,fd.lmBytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);}
        fake::state.psramTotal=identity::kRawBytes+remainingBudget(320)-1; // short even after release
        const Decoder hook=fd.hook();
        auto r=callWith(&cache,&hook);
        assert(!r.ok && r.error=="Not enough PSRAM for speech");
        assert(fd.releases==1 && fd.decodes==0 && !fd.lm && fake::state.rawAllocations==0);
        fake::settled(0);
    }
    // Enough memory: release is never consulted.
    fake::clean();{ModelCache cache;FakeDecoder fd;const Decoder hook=fd.hook();assert(callWith(&cache,&hook).ok && fd.releases==0);}
    fake::settled(0);
}
}
namespace test {
Result callPrefix(ModelCache* cache,size_t samples,size_t cached) {
    Reader reader;std::vector<int16_t> pcm(samples,42);char text[64],error[128];STTLocalStats stats;
    std::vector<float> rows(std::max<size_t>(cached,1)*kMelBins);
    for(size_t r=0;r<cached;++r)for(size_t m=0;m<kMelBins;++m)rows[r*kMelBins+m]=fakeRow(r,m);
    const STTFeaturePrefix prefix{rows.data(),cached};
    const bool ok=transcribe(reader.model(),pcm.data(),samples,text,sizeof(text),fake::control(),stats,error,sizeof(error),
                             nullptr,cache,nullptr,cached?&prefix:nullptr);
    if(!ok) {assert(!text[0]);assert(error[0]);}
    return {ok,stats,text,error};
}
// callBudget() (the feature pool's sizing) is exactly the admission rule: a warm
// call is admitted at that much free PSRAM and that largest block, and refused
// one byte below either (per-call model; with HW1_STT_RESIDENT_MODEL=1 and a
// resident model, the resident call budget).
void callBudgetMatchesAdmission() {
    fake::clean();
    {
        ModelCache cache;
        Reader cold;assert(call(&cache,cold,8000).ok);   // warm-up (builds the resident model)
        for(size_t n:{size_t(480),size_t(64000),size_t(320000)}) {
            size_t contiguous=0;
            const size_t need=callBudget(n,&cache,&contiguous);
#if !HW1_STT_RESIDENT_MODEL
            assert(need==remainingBudget(n) && contiguous==2048*((feature_frames(n)+1)/2)+64*1024+1024*1024);
#endif
            assert(contiguous<=need);
            fake::state.psramTotal=fake::state.allocated+need;fake::state.largest=contiguous;
            Reader a;assert(call(&cache,a,n).ok);
            fake::state.psramTotal=fake::state.allocated+need-1;
            Reader b;auto refused=call(&cache,b,n);
            assert(!refused.ok && refused.error=="Not enough PSRAM for speech");
            fake::state.psramTotal=fake::state.allocated+need;fake::state.largest=contiguous-1;
            Reader c;auto split=call(&cache,c,n);
            assert(!split.ok && split.error=="Not enough contiguous memory for STT activations");
            fake::state.psramTotal=32*1024*1024;fake::state.largest=32*1024*1024;
        }
        // No session cache: the per-call rule.
        size_t contiguous=0;
        assert(callBudget(64000,nullptr,&contiguous)==remainingBudget(64000));
        cache.reset();fake::settled(0);
    }
    fake::settled(0);
}
void perCallSession() {
#if !HW1_STT_RESIDENT_MODEL
    // With HW1_STT_RESIDENT_MODEL=0: a session never keeps a model.
    // Each call creates its own (at its own length) and destroys it before
    // returning, after the warm-up as before it, as in the deployed firmware.
    fake::clean();
    {
        ModelCache cache;
        const size_t lengths[]={8000,64000,480,320,64000,106000,40000};
        int calls=0;
        for(size_t n:lengths) {
            Reader r;auto res=call(&cache,r,n);++calls;
            assert(res.ok && res.stats.weightsReused==(calls>1));
            assert(fake::state.created==calls && fake::state.destroyed==calls && fake::state.models==0);
            assert(fake::state.modelFrames.back()==feature_frames(n));
            fake::settled(1);  // weights only: no model, arena or metadata survives a call
        }
        // cached-feature prefix: copied rows + computed tail + CMVN, same per-call model.
        const size_t melBefore=fake::state.melRows;
        auto cachedCall=callPrefix(&cache,480,2);           // 3 frames, 2 cached
        assert(cachedCall.ok && cachedCall.stats.featureCachedFrames==2);
        assert(fake::state.melRows==melBefore+1 && fake::state.normalizes==1);
        assert(fake::state.created==calls+1 && fake::state.models==0);
        auto shortPrefix=callPrefix(&cache,1600,3);          // 10 frames, 3 cached: under a third, batch path
        assert(shortPrefix.ok && shortPrefix.stats.featureCachedFrames==0 && fake::state.normalizes==1);
        // The deployed 150 KB internal floor on every warm call.
        fake::state.internalFree=150*1024;
        Reader atFloor;assert(call(&cache,atFloor,64000).ok);
        fake::state.internalFree=150*1024-1;
        Reader below;auto refused=call(&cache,below,64000);
        assert(!refused.ok && refused.error=="Not enough internal SRAM for speech");
        fake::state.internalFree=1024*1024;
        assert(fake::state.models==0);
        cache.reset();fake::settled(0);
    }
    fake::settled(0);
#endif
}
}
int main() {
    {
        fake::clean();
        hw1::stt::ModelCache cache;test::Reader reader;
        fake::state.internalLargest=32767;
        auto denied=test::call(&cache,reader);
        assert(!denied.ok && denied.error=="No contiguous internal SRAM block for speech");
        assert(!cache.loaded());
        fake::state.internalLargest=1024*1024;
        test::Reader retry;assert(test::call(&cache,retry).ok);cache.reset();fake::settled(0);
    }

    test::callBudgetMatchesAdmission();
    test::perCallSession();
    test::decoderHook();test::decoderReleasesMemory();
    test::coldWarmShapes();test::oneShotOrder();test::failuresBeforePublish();test::failuresAfterPublish();
    test::corruptedAndFailedHash();test::warmBudgetAndEnvelope();test::guardLimitsAndDestruction();
    test::diagnosticsAfterModelDestruction();
    fake::clean();
    std::printf("QuartzNet actual runtime cache tests passed (diagnostics=%d resident=%d)\n",HW1_STT_RUNTIME_DIAGNOSTICS,HW1_STT_RESIDENT_MODEL);
}
