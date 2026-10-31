// The Python driver inserts actual headers/container/runtime below. Only the
// external dependencies are fakes. Never copy the production cache algorithm here.
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdarg>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <map>
#include <memory>
#include <regex>
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
    std::vector<size_t> runFrames;
    std::vector<size_t> prepareFrames;  // prepared-args passes (resident model only)
    int reshapes=0;
    bool oddTensor=false;
    size_t modelInternalBytes=0;
    int unrelatedBuildDelta=0;
    struct Meta { size_t size; int kind; bool psram; };
    std::map<void*,Meta> meta;          // blocks from ESP-DL's metadata allocator (fake vendor model)
    struct Ps { size_t size; std::string tag; bool psram; };
    std::map<void*,Ps> ps;              // sttPsramAlloc blocks (the runtime's resident bookkeeping)
    bool hookInstalled=false; int installs=0;
    bool psramRefuses=false;            // metadata and resident blocks land in internal RAM
    size_t metaPsram=0, metaInternal=0, psPsram=0, psInternal=0;
    uint32_t allocs[11]={}, bytes[11]={}, internal[11]={}, internalBytes[11]={}, failed[11]={}, frees=0;
    int modelNews=0, failModelAt=0;     // fail the n-th Model allocation (1-based; 0: never)
    int psAllocs=0, failPsAt=0;         // fail the n-th sttPsramAlloc (1-based; 0: never)
    uint32_t foreignObjects=0;
    std::vector<std::string> lines;     // captured log lines
    bool failGraph=false, missingTensor=false, ioMismatch=false;
} state;
void clean() {
    assert(state.allocations.empty()); assert(state.models==0);
    assert(state.meta.empty() && state.ps.empty() && !state.metaInternal && !state.psInternal);
    const bool installed=state.hookInstalled;  // installed once, stays installed (process-wide)
    state=State{}; state.hookInstalled=installed;
}
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
    assert(state.meta.empty() && state.ps.empty());  // no vendor metadata or resident block outlives its model
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
// where ESP-DL keeps a model's long-lived metadata, and the runtime's own
// long-lived blocks (quartznet_runtime.cpp, HW1_STT_RESIDENT_MODEL=1).
//
// ESP-DL (tree-local esp-dl, dl_tool_metadata.hpp) asks one allocator for every
// block a dl::Model keeps for its lifetime: the Model, context, loader and
// flatbuffer objects, module and tensor objects, per-channel exponent arrays,
// tensor shapes, module index vectors and Conv attributes, the tensor lists and
// execution plan, and the tensor-name map with its keys. installDlMetadataAllocator()
// makes that allocator an explicit PSRAM request:
//  - ps_alloc(size, AllocPolicy::PreferPSRAM, "stt.dl.<kind>") for blocks that
//    need no more than the heap's own 4-byte alignment (System_MemUtil: falls
//    back to internal RAM, counted in gPsAllocFallbacks and logged);
//  - for the few kinds ESP-DL aligns to 8 or 16 bytes (Model; module, tensor and
//    exponent blocks, as upstream's malloc_aligned did), heap_caps_aligned_alloc
//    with MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT, then internal RAM, counted the same
//    way. Never MALLOC_CAP_SIMD: that pads every block to the L2 cache line.
// Every block is returned through ps_free (any heap block is accepted, so
// objects prebuilt code allocated are freed correctly too). Nothing global
// changes: no malloc interception, no CONFIG_SPIRAM_MALLOC_ALWAYSINTERNAL
// threshold change. No metadata block is read by DMA or with the cache
// disabled: ESP-DL runs in tasks only, from flash, with the cache on.
//
// The hook is process-wide once installed (it stays until reboot): it also
// places the metadata of per-call STT models and of any ESP-DL model ESP-SR
// builds after it (WakeNet constructs this tree's dl::Model).





namespace hw1::stt {

struct DlMetadataStats {
  uint32_t allocs = 0;         // blocks the hook served
  uint32_t bytes = 0;          // bytes requested for them
  uint32_t internal = 0;       // of those, blocks that landed in internal RAM (PSRAM refused or bypassed)
  uint32_t internalBytes = 0;  // bytes requested for those
  uint32_t failed = 0;         // requests neither heap could serve
  uint32_t frees = 0;          // non-null blocks returned through the hook
};
inline constexpr size_t kDlMetadataKinds = 11;  // dl::tool::kMetadataKinds (static_assert in the .cpp)

// Idempotent; call before building any model. Returns true once installed.
bool installDlMetadataAllocator();
bool dlMetadataAllocatorInstalled();
// Cumulative since boot, over all kinds or one kind (dl::tool::MetadataKind
// value). Updated atomically; a snapshot pair brackets one build, but another
// task building an ESP-DL model at the same time is counted too.
DlMetadataStats dlMetadataStats();
DlMetadataStats dlMetadataStats(size_t kind);
// The difference of two snapshots (after - before), field by field.
DlMetadataStats dlMetadataDelta(const DlMetadataStats& before, const DlMetadataStats& after);

// The runtime's own long-lived blocks (the resident model's bookkeeping):
// ps_alloc(size, AllocPolicy::PreferPSRAM, tag) / ps_free, counted in the
// same System_MemUtil fallback counter. Heap alignment (4 bytes on the P4).
void* sttPsramAlloc(size_t size, const char* tag);
void sttPsramFree(void* ptr);

// Out of memory where nullptr cannot be returned (a container): aborts, as ::operator new does.
[[noreturn]] void sttPsramBadAlloc(size_t size);

// std allocator over sttPsramAlloc (tag "stt.resident"); stateless.
template <class T>
struct PsramStlAllocator {
  using value_type = T;
  PsramStlAllocator() noexcept = default;
  template <class U>
  constexpr PsramStlAllocator(const PsramStlAllocator<U>&) noexcept {}
  T* allocate(size_t n) {
    static_assert(alignof(T) <= sizeof(void*), "the heap aligns blocks to the pointer size");
    if (n > std::numeric_limits<size_t>::max() / sizeof(T)) sttPsramBadAlloc(std::numeric_limits<size_t>::max());
    void* p = sttPsramAlloc(n * sizeof(T), "stt.resident");
    if (!p) sttPsramBadAlloc(n * sizeof(T));
    return static_cast<T*>(p);
  }
  void deallocate(T* p, size_t) noexcept { sttPsramFree(p); }
  friend bool operator==(const PsramStlAllocator&, const PsramStlAllocator&) noexcept { return true; }
  friend bool operator!=(const PsramStlAllocator&, const PsramStlAllocator&) noexcept { return false; }
};

}  // namespace hw1::stt

namespace fake {
// ESP-DL's metadata allocator as the runtime installs it: PSRAM (ps_alloc PreferPSRAM),
// internal RAM when PSRAM refuses.
void* metaAlloc(size_t n,int kind) {
    assert(kind>=0 && kind<11);
    void* p=std::malloc(n);
    const bool psram=!state.psramRefuses;
    state.meta.emplace(p,State::Meta{n,kind,psram});
    ++state.allocs[kind];state.bytes[kind]+=uint32_t(n);
    if(psram) state.metaPsram+=n;
    else {state.metaInternal+=n;state.internalFree-=n;++state.internal[kind];state.internalBytes[kind]+=uint32_t(n);}
    return p;
}
void metaFree(void* p) {
    if(!p)return;
    auto it=state.meta.find(p);
    assert(it!=state.meta.end());  // only the allocator's own blocks come back here in this fake
    if(it->second.psram) state.metaPsram-=it->second.size;
    else {state.metaInternal-=it->second.size;state.internalFree+=it->second.size;}
    ++state.frees;state.meta.erase(it);std::free(p);
}
// Captured logging: format-checked, stored, printed.
__attribute__((format(printf,2,3))) void log(char level,const char* fmt,...) {
    char line[1024];
    va_list ap;va_start(ap,fmt);std::vsnprintf(line,sizeof(line),fmt,ap);va_end(ap);
    state.lines.push_back(line);
    std::printf("%c %s\n",level,line);
}
// tl_capture.py keeps only lines that are entirely numeric fields after the tag.
bool numericTL(const std::string& line) {
    static const std::regex tl("^STT: TL [a-z_0-9]+(?: [a-z0-9_]+=-?[0-9]+(?:MHz)?)*$");
    return std::regex_match(line,tl);
}
std::vector<std::string> linesWith(const std::string& prefix) {
    std::vector<std::string> found;
    for(const auto& l:state.lines) if(l.rfind(prefix,0)==0) found.push_back(l);
    return found;
}
long field(const std::string& line,const std::string& key) {
    const std::string k=" "+key+"=";
    const size_t at=line.find(k);
    assert(at!=std::string::npos);
    return std::strtol(line.c_str()+at+k.size(),nullptr,10);
}
}
namespace hw1::stt {
bool installDlMetadataAllocator() { fake::state.hookInstalled=true;++fake::state.installs;return true; }
bool dlMetadataAllocatorInstalled() { return fake::state.hookInstalled; }
DlMetadataStats dlMetadataStats(size_t k) {
    DlMetadataStats s;
    if(k>=kDlMetadataKinds)return s;
    s.allocs=fake::state.allocs[k];s.bytes=fake::state.bytes[k];s.internal=fake::state.internal[k];
    s.internalBytes=fake::state.internalBytes[k];s.failed=fake::state.failed[k];
    return s;
}
DlMetadataStats dlMetadataStats() {
    DlMetadataStats t;
    for(size_t k=0;k<kDlMetadataKinds;++k) {
        const DlMetadataStats s=dlMetadataStats(k);
        t.allocs+=s.allocs;t.bytes+=s.bytes;t.internal+=s.internal;t.internalBytes+=s.internalBytes;t.failed+=s.failed;
    }
    t.frees=fake::state.frees;
    return t;
}
DlMetadataStats dlMetadataDelta(const DlMetadataStats& a,const DlMetadataStats& b) {
    DlMetadataStats d;
    d.allocs=b.allocs-a.allocs;d.bytes=b.bytes-a.bytes;d.internal=b.internal-a.internal;
    d.internalBytes=b.internalBytes-a.internalBytes;d.failed=b.failed-a.failed;d.frees=b.frees-a.frees;
    return d;
}
void* sttPsramAlloc(size_t n,const char* tag) {
    assert(fake::state.hookInstalled);           // installed before anything is placed
    if(++fake::state.psAllocs==fake::state.failPsAt)return nullptr;
    void* p=std::malloc(n);
    const bool psram=!fake::state.psramRefuses;
    fake::state.ps.emplace(p,fake::State::Ps{n,tag,psram});
    if(psram) fake::state.psPsram+=n; else {fake::state.psInternal+=n;fake::state.internalFree-=n;}
    return p;
}
void sttPsramFree(void* p) {
    if(!p)return;
    auto it=fake::state.ps.find(p);
    assert(it!=fake::state.ps.end());
    if(it->second.psram) fake::state.psPsram-=it->second.size;
    else {fake::state.psInternal-=it->second.size;fake::state.internalFree+=it->second.size;}
    fake::state.ps.erase(it);std::free(p);
}
void sttPsramBadAlloc(size_t) { throw std::bad_alloc(); }  // the device aborts, as ::operator new
}
namespace dl::tool {
struct MetadataForeignStats { uint32_t objects, internal; };
MetadataForeignStats metadata_foreign_stats() { return {fake::state.foreignObjects,0}; }
}
constexpr int ESP_OK=0, ESP_FAIL=-1;
namespace fbs {
constexpr int MODEL_LOCATION_IN_FLASH_RODATA=1;
// Graph: input -conv0(stride 2)-> a -conv1-> b -add(in place over a)-> c -head-> output
struct FbsModel {
    bool mapped=false;
    void load_map() {mapped=true;}
    void clear_map() {mapped=false;}
    std::vector<std::string> get_graph_inputs() {assert(mapped);return {"input"};}
    std::vector<std::string> topological_sort() {assert(mapped);return {"conv0","conv1","add","head"};}
    int get_operation_inputs_and_outputs(std::string node,std::vector<std::string>& in,std::vector<std::string>& out) {
        assert(mapped);
        if(fake::state.failGraph)return ESP_FAIL;
        if(node=="conv0") {in={"input","w0"};out={"a"};}
        else if(node=="conv1") {in={"a","w1"};out={"b"};}
        else if(node=="add") {in={"a","b"};out={"c"};}
        else if(node=="head") {in={"c","w2"};out={"output"};}
        else return ESP_FAIL;
        return ESP_OK;
    }
};
}
// The tree-local ESP-DL's prepared-args pass (dl_module_base.cpp): while the
// mode is set no layer computes, so the fake model only records that pass.
extern "C" { int hw1_dl_prepare_mode=0; uint32_t hw1_dl_prepare_gen=0; }
namespace dl {
constexpr int DATA_TYPE_INT8=1,MEMORY_MANAGER_GREEDY=1,RUNTIME_MODE_MULTI_CORE=1;
struct Exponent { int value; bool is_valid()const{return true;} bool is_per_channel()const{return false;} explicit operator int()const{return value;} };
struct TensorBase {
    std::vector<int> shape;
    std::vector<int8_t> storage;
    void* data=nullptr;
    size_t capacity=0;   // fixed at creation, like the greedy arena extent
    int dtype=DATA_TYPE_INT8;
    Exponent exponent{0};
    void init(size_t frames,size_t channels,int exp) {
        shape={1,int(frames),1,int(channels)};storage.resize(frames*channels);data=storage.data();
        capacity=storage.size();exponent.value=exp;
    }
    void alias(const TensorBase& other,size_t frames,size_t channels,int exp) {
        shape={1,int(frames),1,int(channels)};data=other.data;capacity=other.capacity;exponent.value=exp;
    }
    int get_bytes()const {size_t n=1;for(int d:shape)n*=size_t(d);return int(n);}
    TensorBase& set_shape(const std::vector<int> s) {
        size_t n=1;for(int d:s){assert(d>=1);n*=size_t(d);}
        assert(n<=capacity);   // never past the allocation: set_shape does not reallocate
        shape=s;++fake::state.reshapes;return *this;
    }
};
struct Memory { size_t psram,internal; };
class Model {
    const void* weights;
    TensorBase input,a,b,c,output;
    fbs::FbsModel graph;
    std::vector<void*> blocks;  // this model's metadata blocks
 public:
    // dl::Model's class operator new/delete go through the metadata allocator
    // (MetadataKind::Model); the throwing form exists too, so only the nothrow form is used here.
    static void* operator new(size_t n,const std::nothrow_t&)noexcept {
        ++fake::state.modelNews;
        if(fake::state.modelAllocationError || fake::state.modelNews==fake::state.failModelAt) {
            ++fake::state.failed[0];return nullptr;
        }
        return fake::metaAlloc(n,0);
    }
    static void operator delete(void* p)noexcept {fake::metaFree(p);}
    static void operator delete(void* p,const std::nothrow_t&)noexcept {fake::metaFree(p);}
    void get_arena_size(size_t* psram,size_t* internal) {
        if(psram)*psram=2048*input.capacity/64/2;  // 2048 * ceil(T/2) as the pinned graph's arena
        if(internal)*internal=0;
    }
    Model(const char* raw,int location,int index,int manager,void* unused,bool copy,
          const std::map<std::string,std::vector<int>>& shapes):weights(raw) {
        assert(fake::hasRaw(raw));assert(location==fbs::MODEL_LOCATION_IN_FLASH_RODATA);
        assert(index==0 && manager==MEMORY_MANAGER_GREEDY && !unused && !copy);
        assert(fake::state.models<=1);   // a resident model plus at most one per-call model
        ++fake::state.models;++fake::state.created;
        if(fake::state.created==2) fake::state.internalFree-=fake::state.unrelatedBuildDelta;
        fake::state.events.push_back("create model");
        const auto shape=shapes.at(hw1::stt::identity::kInputName);
        assert(shape[0]==1 && shape[2]==1 && shape[3]==64);
        const size_t frames=size_t(shape[1]),half=(frames+1)/2;fake::state.modelFrames.push_back(frames);
        input.init(frames,64,hw1::stt::identity::kInputExponent);
        a.init(half,256,0);b.init(fake::state.oddTensor?half+3:half,256,0);c.alias(a,half,256,0);
        output.init(half,29,hw1::stt::identity::kOutputExponent);
        // the allocator is installed before the first model (flag 1), never with flag 0.
        assert(fake::state.hookInstalled==bool(HW1_STT_RESIDENT_MODEL));
        // Metadata: module objects, tensors, exponent arrays and the name map, as four
        // blocks of the allocator (Module, Tensor, Exponent, Names); 3 prebuilt parameter objects.
        const size_t total=fake::state.modelInternalBytes;
        const size_t parts[4]={total/2,total/4,total/8,total-total/2-total/4-total/8};
        const int kinds[4]={4,5,6,10};
        for(int i=0;i<4;++i) if(parts[i]) blocks.push_back(fake::metaAlloc(parts[i],kinds[i]));
        fake::state.foreignObjects+=3;
        if(fake::state.ioMismatch && frames==1000)input.exponent.value=99;
    }
    ~Model() {
        assert(fake::hasRaw(weights));
        if(fake::state.mutateInDestructor)static_cast<uint8_t*>(const_cast<void*>(weights))[17]^=1;
        for(void* b:blocks) fake::metaFree(b);
        --fake::state.models;++fake::state.destroyed;fake::state.events.push_back("destroy model");
    }
    TensorBase* get_input(const char*) { if(fake::state.tensorError)input.exponent.value=99;return &input; }
    TensorBase* get_output(const char*) {fake::state.lastOutput=static_cast<const int8_t*>(output.data);return &output;}
    TensorBase* get_intermediate(const std::string& n) {
        if(fake::state.missingTensor && n=="b")return nullptr;
        if(n=="input")return &input; if(n=="a")return &a; if(n=="b")return &b; if(n=="c")return &c;
        if(n=="output")return &output; return nullptr;
    }
    fbs::FbsModel* get_fbs_model() {return &graph;}
    std::map<std::string,Memory> get_memory_info()const{return {{"variable",{4096,512}}};}
    void run(int count,int stage,int mode) {
        assert(fake::hasRaw(weights));assert(count==hw1::stt::identity::kNodeCount && mode==RUNTIME_MODE_MULTI_CORE);
        if(hw1_dl_prepare_mode){
            assert(hw1_dl_prepare_gen!=0);
            if(stage==0)fake::state.prepareFrames.push_back(size_t(input.shape[1]));
            return;
        }
        // Every activation tensor carries this call's shape, and data never moved.
        const int frames=input.shape[1],half=(frames+1)/2;
        for(const TensorBase* t:{&a,&b,&c})
            if(t!=&b || !fake::state.oddTensor) assert(t->shape==std::vector<int>({1,half,1,256}));
        assert(output.shape==std::vector<int>({1,half,1,29}) && c.data==a.data);
        if(stage==0)fake::state.runFrames.push_back(size_t(frames));
        fake::state.lastOutput=static_cast<const int8_t*>(output.data);
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

// Host stand-ins: evaluate and format-check the arguments, print the line.
#define ESP_LOGI(tag, fmt, ...) fake::log('I', "%s: " fmt, tag, __VA_ARGS__)
#define ESP_LOGW(tag, fmt, ...) fake::log('W', "%s: " fmt, tag, __VA_ARGS__)
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

namespace resident {
using namespace hw1::stt;
using test::Reader; using test::call; using test::callWith; using test::FakeDecoder;
constexpr size_t kMax=10*16000;   // the broker's cap: resident model is built at 1000 frames
void assertResident(int created,int destroyed) {
    assert(fake::state.models==1 && fake::state.created==created && fake::state.destroyed==destroyed);
}
void lifecycle() {
    fake::clean();
    {
        ModelCache cache;
        Reader a;auto first=call(&cache,a,320);           // the warm-up: per-call model, then the build
        assert(first.ok && !first.stats.weightsReused);
        assert(fake::state.modelFrames==std::vector<size_t>({2,1000}));
        assertResident(2,1);
        const std::vector<std::string> events={"allocate weights","create model","destroy model","create model"};
        assert(fake::state.events==events);              // per-call model gone before the resident build
        Reader b;auto second=call(&cache,b,480);
        assert(second.ok && second.stats.weightsReused && second.stats.featureFrames==3 && second.stats.outputFrames==2);
        assert(b.bytesRead==container::kHeaderBytes);
        Reader c;auto third=call(&cache,c,320);
        assert(third.ok && third.stats.featureFrames==2);
        Reader d;auto longest=call(&cache,d,kMax);         // exactly the build length
        assert(longest.ok && longest.stats.featureFrames==1000 && longest.stats.outputFrames==500);
        assertResident(2,1);                              // no model built for any of these
        assert(fake::state.runFrames==std::vector<size_t>({2,3,2,1000}));
        assert(fake::state.prepareFrames==std::vector<size_t>({3,2,1000}));  // not the warm-up's per-call model
        // Longer than the resident length (one-shot sizes only): per-call model beside it.
        Reader e;auto beyond=call(&cache,e,kMax+160);
        assert(beyond.ok && beyond.stats.featureFrames==1001 && fake::state.modelFrames.back()==1001);
        assertResident(3,2);
        Reader f;assert(call(&cache,f,640).ok);assertResident(3,2);
        assert(fake::state.runFrames==std::vector<size_t>({2,3,2,1000,1001,4}));
        assert(fake::state.prepareFrames==std::vector<size_t>({3,2,1000,4}));
        const int reshapes=fake::state.reshapes;
        Reader g;assert(call(&cache,g,640).ok);
        assert(fake::state.reshapes==reshapes);          // same length: shapes left as they are
        cache.reset();                                    // resident destroyed before the weights (fake asserts)
        assert(fake::state.models==0 && fake::state.rawFrees==1);fake::settled(0);
        // A new session (after reset) gets a fresh build after its first call.
        Reader h;assert(call(&cache,h,320).ok);assertResident(5,4);
        cache.reset();fake::settled(0);
    }
    fake::settled(0);
}
void refusals() {
    // A tensor whose length cannot be re-derived: no resident model, and no
    // second attempt; every call keeps the per-call path.
    fake::clean();
    {
        ModelCache cache;fake::state.oddTensor=true;
        Reader a;assert(call(&cache,a,320).ok);
        assert(fake::state.models==0 && fake::state.created==2 && fake::state.destroyed==2);
        Reader b;assert(call(&cache,b,480).ok);
        Reader c;assert(call(&cache,c,320).ok);
        assert(fake::state.created==4 && fake::state.modelFrames==std::vector<size_t>({2,1000,3,2}));
        fake::settled(1);cache.reset();fake::settled(0);
    }
    // Not enough PSRAM to build and keep 2 MiB free: refused before any build.
    fake::clean();
    {
        ModelCache cache;
        fake::state.psramTotal=identity::kRawBytes+test::remainingBudget(320)+1024;
        Reader a;assert(call(&cache,a,320).ok);
        assert(fake::state.models==0 && fake::state.created==1);
        fake::state.psramTotal=32*1024*1024;              // memory back: still no retry this session
        Reader b;assert(call(&cache,b,320).ok);
        assert(fake::state.created==2 && fake::state.models==0);
        fake::settled(1);cache.reset();fake::settled(0);
    }
    // Internal RAM at exactly the floor still builds (the per-call model's own
    // use is returned first); below it at build time (here taken while
    // decoding, as a lazily loaded LM could) refuses the build.
    fake::clean();
    {
        ModelCache cache;
        Reader a;fake::state.internalFree=150*1024;fake::state.modelInternalBytes=1024;
        assert(call(&cache,a,320).ok);
        assertResident(2,1);
        cache.reset();fake::settled(0);
    }
    fake::clean();
    {
        struct Squeeze {
            static DecodeResult decode(void*,const int8_t*,size_t,int,char* text,size_t cap,const STTLocalControl&) {
                fake::state.internalFree=150*1024-1;std::snprintf(text,cap,"%s","lm");return DecodeResult::Decoded;
            }
        };
        const Decoder hook{nullptr,Squeeze::decode,nullptr};
        ModelCache cache;
        assert(callWith(&cache,&hook,320).ok);
        assert(fake::state.models==0 && fake::state.created==1);
        fake::state.internalFree=1024*1024;
        cache.reset();fake::settled(0);
    }
    // A failed or cancelled first call does not use up the build attempt.
    fake::clean();
    {
        ModelCache cache;
        fake::state.cancelAtPhase=int(STTLocalPhase::Decoding);
        Reader a;assert(!call(&cache,a,320).ok);
        assert(fake::state.models==0);
        fake::state.cancelAtPhase=-1;fake::state.cancel=false;
        Reader b;assert(call(&cache,b,320).ok);
        assert(fake::state.models==1);
        cache.reset();fake::settled(0);
    }
}
void internalFloor() {
    // A resident graph has a fixed remaining-work reserve, independent of
    // model construction's process-wide heap delta and metadata placement.
    for(bool fallback : {false,true}) for(int unrelated : {-20000,0,20000}) {
        fake::clean();
        fake::state.unrelatedBuildDelta=unrelated;
        ModelCache cache;fake::state.modelInternalBytes=60*1024;fake::state.psramRefuses=fallback;
        Reader a;assert(call(&cache,a,320).ok);assertResident(2,1);
        fake::state.psramRefuses=false;
        for(size_t free : {size_t(149747),size_t(150371),size_t(128*1024)}) {
            fake::state.internalFree=free;
            Reader b;assert(call(&cache,b,320).ok && fake::state.created==2);
        }
        fake::state.internalFree=128*1024-1;
        test::FakeDecoder fd;const Decoder hook=fd.hook();
        auto low=callWith(&cache,&hook,320);
        assert(!low.ok && low.error=="Not enough internal SRAM for speech");
        assert(fd.releases==0); // SRAM pressure must not discard the PSRAM LM.
        fake::state.internalFree=1024*1024;cache.reset();fake::settled(0);
    }
    fake::clean();
    {
        // Cold build still has the original reserve; a cached weights-only
        // path also must build the graph rather than use the resident budget.
        Reader a;fake::state.internalFree=150*1024-1;
        assert(!call(nullptr,a,320).ok);fake::settled(0);
    }
}

void handOver() {
    // A session that changes hands (STTLocalSession::moveTo, keep-warm park
    // and adopt) drops its resident model: the arena with the last call's
    // activations is freed, the verified weights stay, and the next owner's
    // first call builds a fresh resident model (the attempt is not spent).
    fake::clean();
    {
        ModelCache cache;
        Reader a;assert(call(&cache,a,320).ok);assertResident(2,1);   // warm-up, then the build
        Reader b;auto resident=call(&cache,b,480);
        assert(resident.ok && resident.stats.weightsReused);assertResident(2,1);
        cache.dropResident();
        assert(fake::state.models==0 && fake::state.created==2 && fake::state.destroyed==2);
        assert(cache.loaded() && fake::state.rawFrees==0);           // weights kept
        cache.dropResident();                                          // idempotent
        assert(fake::state.models==0 && fake::state.destroyed==2);
        Reader c;auto next=call(&cache,c,480);                         // per-call model, then a rebuild
        assert(next.ok && next.stats.weightsReused && c.bytesRead==container::kHeaderBytes);
        assertResident(4,3);
        Reader d;assert(call(&cache,d,480).ok);assertResident(4,3);   // served by the new one
        cache.reset();fake::settled(0);
    }
}
void decoderOnResident() {
    // Decoding reads the resident model's output for this call's frames.
    fake::clean();
    {
        ModelCache cache;FakeDecoder fd;const Decoder hook=fd.hook();
        assert(callWith(&cache,&hook,320).ok);           // warm-up builds the resident model
        auto r=callWith(&cache,&hook,480);
        assert(r.ok && r.text=="language model" && fd.decodes==2 && fd.frames==2 && fd.logits==fake::state.lastOutput);
        assertResident(2,1);
        cache.reset();fake::settled(0);
    }
}
}

namespace placement {
using namespace hw1::stt;
using test::Reader; using test::call;
constexpr size_t kMeta=97804;  // the resident model's metadata (resident model's internal RAM on the device)
std::string tlE3() {
    const auto e3=fake::linesWith("STT: TL e3 resident=1");
    assert(e3.size()==1);
    return e3[0];
}
void everyTLLineNumeric() {
    for(const auto& l:fake::state.lines) if(l.rfind("STT: TL ",0)==0 && l.find("resident=0")==std::string::npos)
        assert(fake::numericTL(l));
}
void placement() {
    // The allocator is installed by the first call, before its per-call model; the
    // resident model's object, metadata and bookkeeping are all PSRAM blocks; internal RAM
    // is the same before and after the build; the fixed 128 KiB reserve applies to every
    // resident call; everything goes back to the allocator at session end.
    fake::clean();
    {
        ModelCache cache;fake::state.modelInternalBytes=kMeta;
        const size_t internal=fake::state.internalFree;
        Reader a;assert(call(&cache,a,320).ok);
        assert(fake::state.hookInstalled && fake::state.installs>=1);
        assert(fake::state.models==1 && fake::state.created==2);
        assert(fake::state.meta.size()==5 && fake::state.metaPsram==kMeta+sizeof(dl::Model) && !fake::state.metaInternal);
        assert(fake::state.ps.size()==2 && !fake::state.psInternal);  // Resident + its tensor list
        for(const auto& b:fake::state.ps) assert(b.second.tag=="stt.resident" && b.second.psram);
        assert(fake::state.internalFree==internal);
        const std::string e3=tlE3();
        assert(fake::numericTL(e3));
        assert(fake::field(e3,"int_used")==0 && fake::field(e3,"fallback")==0 && fake::field(e3,"fallback_bytes")==0);
        assert(fake::field(e3,"meta_failed")==0 && fake::field(e3,"meta_n")==5 && fake::field(e3,"meta_frees")==0);
        assert(fake::field(e3,"meta_bytes")==long(kMeta+sizeof(dl::Model)) && fake::field(e3,"tensors")==5);
        assert(fake::field(e3,"arena")==2048*500 && fake::field(e3,"arena_int")==0);
        assert(fake::field(e3,"param_objs")==3 && fake::field(e3,"param_int")==0);
        const auto m=fake::linesWith("STT: TL e3m ");
        assert(m.size()==1 && fake::numericTL(m[0]) && fake::field(m[0],"model")==long(sizeof(dl::Model)));
        assert(fake::field(m[0],"module")==long(kMeta/2) && fake::field(m[0],"names")>0 && fake::field(m[0],"shape")==0);
        everyTLLineNumeric();
        fake::state.internalFree=128*1024;
        Reader b;assert(call(&cache,b,480).ok && fake::state.created==2);
        fake::state.internalFree=128*1024-1;
        Reader c;auto low=call(&cache,c,480);
        assert(!low.ok && low.error=="Not enough internal SRAM for speech");
        fake::state.internalFree=internal;
        // Longer than the resident length: a per-call model, its metadata through the
        // same allocator, all of it returned when the call ends.
        const size_t blocks=fake::state.meta.size();
        Reader d;assert(call(&cache,d,10*16000+160).ok);
        assert(fake::state.meta.size()==blocks && fake::state.created==3);
        cache.reset();
        assert(fake::state.meta.empty() && fake::state.ps.empty() && fake::state.internalFree==internal);
        fake::settled(0);
        // Next session (a Conversate restart): built again, freed again.
        fake::state.lines.clear();
        Reader e;assert(call(&cache,e,320).ok && fake::state.models==1 && tlE3().size());
        cache.reset();
        assert(fake::state.meta.empty() && fake::state.ps.empty() && fake::state.internalFree==internal);
        fake::settled(0);
    }
    fake::settled(0);
}
void restarts() {
    // Ten sessions back to back, each with its own ModelCache (as each Conversate restart
    // gets a new STTLocalSession): one resident model per session, all of it (weights,
    // arena, metadata, bookkeeping) returned at each session end. Nothing accumulates.
    fake::clean();
    const size_t internal=fake::state.internalFree;
    for(int n=1;n<=10;++n) {
        {
            ModelCache cache;fake::state.modelInternalBytes=kMeta;
            Reader a;assert(call(&cache,a,320).ok);
            Reader b;assert(call(&cache,b,64000).ok);
            Reader c;assert(call(&cache,c,160000).ok);
            assert(fake::state.models==1 && fake::state.meta.size()==5 && fake::state.ps.size()==2);
            assert(fake::state.metaPsram==kMeta+sizeof(dl::Model));
        }   // ~ModelCache: as STTLocalSession::reset() at the worker's end
        assert(fake::state.models==0 && fake::state.meta.empty() && fake::state.ps.empty());
        assert(fake::state.internalFree==internal && !fake::state.metaPsram && !fake::state.psPsram);
        fake::settled(0);
    }
    assert(fake::state.created==20 && fake::state.destroyed==20);
    assert(fake::state.frees==20*5);  // every block of every model returned through the allocator
    assert(fake::linesWith("STT: TL e3 resident=1").size()==10);
    everyTLLineNumeric();
}
void failedBuilds() {
    // Every way the resident build can fail returns everything it had (model object,
    // metadata, Resident) before the TL resident model line; the session continues with per-call
    // models, never retrying the build.
    for(int scenario=0;scenario<7;++scenario) {
        fake::clean();
        {
            ModelCache cache;fake::state.modelInternalBytes=kMeta;
            const char* reason="";
            switch(scenario) {
                case 0:fake::state.failModelAt=2;reason="model";break;   // the resident Model object
                case 1:fake::state.ioMismatch=true;reason="io";break;
                case 2:fake::state.failGraph=true;reason="graph";break;
                case 3:fake::state.missingTensor=true;reason="tensor";break;
                case 4:fake::state.oddTensor=true;reason="shape";break;
                case 5:fake::state.failPsAt=1;reason="alloc";break;      // the Resident object
                case 6:fake::state.psramRefuses=false;reason="memory";
                       fake::state.psramTotal=identity::kRawBytes+test::remainingBudget(320)+1024;break;
            }
            const size_t internal=fake::state.internalFree;
            Reader a;assert(call(&cache,a,320).ok);
            assert(fake::state.models==0 && fake::state.meta.empty() && fake::state.ps.empty());
            assert(fake::state.internalFree==internal);
            const auto w=fake::linesWith("STT: TL e3 resident=0");
            assert(w.size()==1 && w[0].find(std::string("reason=")+reason+" ")!=std::string::npos);
            fake::state.failModelAt=0;fake::state.failPsAt=0;fake::state.psramTotal=32*1024*1024;
            Reader b;assert(call(&cache,b,480).ok);
            assert(fake::state.models==0 && fake::linesWith("STT: TL e3").size()==1);  // no retry
            cache.reset();fake::settled(0);
        }
    }
    // The tensor list's PSRAM block refused: the runtime aborts on the device (as
    // ::operator new does); here it throws, and unwinding still returns every block.
    fake::clean();
    {
        ModelCache cache;fake::state.modelInternalBytes=kMeta;fake::state.failPsAt=2;
        Reader a;bool threw=false;
        try {(void)call(&cache,a,320);} catch(const std::bad_alloc&) {threw=true;}
        assert(threw && fake::state.models==0 && fake::state.meta.empty() && fake::state.ps.empty());
        cache.reset();fake::settled(0);
    }
}
void featurePoolBudget() {
    // The broker sizes its pool after the warm-up against callBudget(10 s): the resident call.
    fake::clean();
    {
        ModelCache cache;
        size_t contiguous=0;
        const size_t frames=feature_frames(160000);
        const size_t perCall=test::remainingBudget(160000);
        Reader a;assert(call(&cache,a,8000).ok);
        assert(fake::state.models==1);
        const size_t resident=callBudget(160000,&cache,&contiguous);
        assert(resident==frames*kMelBins*sizeof(float)+sizeof(FrontendWorkspace)+kResidentCallMargin);
        assert(contiguous==frames*kMelBins*sizeof(float)+kResidentCallMargin && resident<perCall);
        cache.reset();fake::settled(0);
        assert(callBudget(160000,&cache,&contiguous)==perCall);
    }
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

    test::callBudgetMatchesAdmission();resident::lifecycle();resident::refusals();resident::internalFloor();resident::handOver();resident::decoderOnResident();
    placement::placement();placement::restarts();placement::failedBuilds();placement::featurePoolBudget();placement::everyTLLineNumeric();
    fake::clean();
    std::printf("QuartzNet resident-model (metadata requested from PSRAM) runtime tests passed (diagnostics=%d)\n",HW1_STT_RUNTIME_DIAGNOSTICS);
}
