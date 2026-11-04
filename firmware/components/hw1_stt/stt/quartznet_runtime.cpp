#include "quartznet_runtime.h"
#include "stt_internal_memory.h"
#include "quartznet_frontend.h"
#include "stt_model_identity.h"
#include "stt_model_container.h"
#include "dl_model_base.hpp"
#if HW1_STT_RESIDENT_MODEL
// The tree-local ESP-DL (tools/p4/prepare_esp_dl.py) provides the metadata
// allocator hook; stt_dl_metadata.h installs a PSRAM one.
#include "dl_tool_metadata.hpp"
#include "stt_dl_metadata.h"
#endif
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "sdkconfig.h"
#if defined(ESP_PLATFORM) && CONFIG_SPIRAM_ALLOW_BSS_SEG_EXTERNAL_MEMORY
#include "esp_attr.h"
#define STT_PROFILE_BSS EXT_RAM_BSS_ATTR
#else
#define STT_PROFILE_BSS
#endif
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include "miniz.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <map>
#include <memory>
#include <new>
#include <string>
#include <vector>
#if HW1_STT_RESIDENT_MODEL
// The tree-local ESP-DL's prepared-args pass (dl_module_conv.hpp).
extern "C" int hw1_dl_prepare_mode;
extern "C" uint32_t hw1_dl_prepare_gen;
#endif
namespace hw1::stt {
// Per-stage inference time accumulated across segments (sttperf stages).
static constexpr int kStageProfileMax = 256;
STT_PROFILE_BSS static uint32_t gStageTotalUs[kStageProfileMax];
static uint32_t gStageSegments = 0;
size_t stageProfile(uint32_t* totalUs, size_t cap, uint32_t* segments) {
    const size_t n = std::min<size_t>(cap, std::min<int>(identity::kNodeCount, kStageProfileMax));
    for (size_t i = 0; i < n; ++i) totalUs[i] = gStageTotalUs[i];
    if (segments) *segments = gStageSegments;
    return n;
}
void stageProfileReset() {
    for (auto& v : gStageTotalUs) v = 0;
    gStageSegments = 0;
}
namespace {
static_assert(kSampleRate==identity::kSampleRate && kMaxSamples==identity::kMaxSamples);
uint32_t millis() { return uint32_t(esp_timer_get_time()/1000); }
// Do not reconfigure the global watchdog around inference. Both cores retain
// their subscriptions; the bounded stage loop blocks periodically after the
// multicore kernel has joined, letting idle tasks run without unsubscribe races.
bool cancelled(const STTLocalControl& c) { return c.cancelled && c.cancelled(c.context); }
void progress(const STTLocalControl& c, STTLocalPhase phase) { if(c.progress)c.progress(c.context,phase); }
struct Buffer {
    void* p = nullptr;
    size_t bytes = 0;
    bool sensitive = false;
    explicit Buffer(size_t n, bool secret=false):bytes(n),sensitive(secret) {
        p=heap_caps_aligned_alloc(16,n,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    }
    ~Buffer() { if(sensitive && p) { volatile uint8_t* d=static_cast<volatile uint8_t*>(p); for(size_t i=0;i<bytes;++i)d[i]=0; } heap_caps_free(p); }
    void* release() { void* value=p; p=nullptr; return value; }
    Buffer(const Buffer&)=delete;
    Buffer& operator=(const Buffer&)=delete;
};
bool readExact(ModelReader& r, void* dest, size_t size) {
    auto p=static_cast<uint8_t*>(dest);
    while(size) { size_t n=r.read(r.context,p,size); if(!n || n>size)return false; p+=n;size-=n; }
    return true;
}
bool digest(const void* data, size_t bytes, uint8_t* hash) {
    return mbedtls_sha256(static_cast<const unsigned char*>(data),bytes,hash,0)==0;
}
// ROM streaming inflate uses a non-wrapping output buffer of exactly the pinned
// size. No untrusted length reaches ESP-DL's unchecked flatbuffer parser.
// Time spent inside reader calls during the current load (card/file I/O only).
int64_t gLoadReadUs = 0;
bool timedRead(ModelReader& r, void* dest, size_t size) {
    const int64_t start=esp_timer_get_time();
    const bool ok=readExact(r,dest,size);
    gLoadReadUs+=esp_timer_get_time()-start;
    return ok;
}
// Stored (codec 0) graph: read straight into the final buffer in large blocks.
// A 20 MB graph in 4 KB reads spends most of its time in per-call file-system
// and SDMMC overhead; 256 KB transfers let the driver stream multi-block DMA.
bool readStoredModel(ModelReader& r, uint8_t* raw, const STTLocalControl& control) {
    constexpr size_t kBlock=256*1024;
    for(size_t done=0;done<identity::kRawBytes;) {
        if(cancelled(control))return false;
        const size_t n=std::min(kBlock,identity::kRawBytes-done);
        if(!timedRead(r,raw+done,n))return false;
        done+=n;
        vTaskDelay(1);
    }
    return true;
}
bool inflateModel(ModelReader& r, uint8_t* raw, const STTLocalControl& control) {
    Buffer workspace(sizeof(tinfl_decompressor)+4096);
    if(!workspace.p)return false;
    auto dec=static_cast<tinfl_decompressor*>(workspace.p);
    auto in=reinterpret_cast<uint8_t*>(dec+1);
    tinfl_init(dec);
    size_t left=identity::kCompressedBytes, available=0, offset=0, output=0, chunks=0;
    for(;;) {
        if(cancelled(control))return false;
        if(available==offset && left) {
            available=std::min(left,size_t(4096));offset=0;
            if(!timedRead(r,in,available))return false;
            left-=available;
        }
        size_t n=available-offset, out=identity::kRawBytes-output;
        uint32_t flags=TINFL_FLAG_PARSE_ZLIB_HEADER|TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF;
        if(left)flags|=TINFL_FLAG_HAS_MORE_INPUT;
        tinfl_status status=tinfl_decompress(dec,in+offset,&n,raw,raw+output,&out,flags);
        offset+=n;output+=out;
        if(status==TINFL_STATUS_DONE)return output==identity::kRawBytes && !left && offset==available;
        if(status<0 || (n==0 && out==0) || output>=identity::kRawBytes)return false;
        if(!left && offset==available && status==TINFL_STATUS_NEEDS_MORE_INPUT)return false;
        if(++chunks%32==0)vTaskDelay(1);
    }
}
bool tensor(dl::TensorBase* t, size_t frames, size_t channels, int exponent) {
    return t && t->data && t->dtype==dl::DATA_TYPE_INT8 && t->exponent.is_valid()
        && !t->exponent.is_per_channel() && int(t->exponent)==exponent
        && t->shape==std::vector<int>({1,int(frames),1,int(channels)})
        && t->get_bytes()==int(frames*channels);
}
}
#if HW1_STT_RESIDENT_MODEL
// ---- HW1_STT_RESIDENT_MODEL: one resident vendor model per session ----
// Built once at the broker's 20 s cap (STT_MAX_CAPTURE_MS; the broker never
// sends more) and re-shaped for every later call. ESP-DL modules keep no
// shape state (Conv rebuilds its arguments from the live tensor shapes on each
// forward), TensorBase::set_shape never reallocates, and the greedy plan gave
// each tensor its max-length extent, so a call runs on a prefix of the same
// arena: same kernels, same arithmetic, no per-call load()/build().
constexpr size_t kResidentMaxSamples=10*kSampleRate;  // the broker's continuous phrases are capped at 10 s
constexpr size_t kResidentCallMargin=256*1024;    // per-call PSRAM beyond the frontend
// Reusing the pinned resident graph does not rebuild model/arena metadata.
// Keep a separate 128 KiB admission reserve for kernel scratch, small SDK
// allocations and concurrent system work. Cold construction still requires
// 150 KiB below. This policy needs hardware peak qualification; it is not a
// measured scratch bound or a credit from another task's heap delta.

constexpr size_t kResidentKeepFree=2u<<20;         // PSRAM left free after the build
// Everything the resident model keeps between phrases is requested
// explicitly from PSRAM where it is allocated. The vendor model's own objects
// and containers come from ESP-DL's metadata allocator, which transcribe()
// points at PSRAM before the first model is built (installDlMetadataAllocator,
// stt_dl_metadata.h: ps_alloc PreferPSRAM). The model object itself is one of
// those blocks (dl::Model's class operator new/delete, so unique_ptr's delete
// returns it), and this bookkeeping is ps_alloc'd too (class operator
// new/delete below, PsramStlAllocator for the tensor list). No malloc
// interception, no task-gated window, no heap threshold change.
struct ModelCache::Resident {
    struct Entry { dl::TensorBase* tensor; int channels; bool fullRate; };
    std::unique_ptr<dl::Model> model;
    std::vector<Entry,PsramStlAllocator<Entry>> tensors;  // every activation tensor, once
    dl::TensorBase* input=nullptr;
    dl::TensorBase* output=nullptr;
    size_t frames=0;             // feature frames of the current shapes
    // Only new(std::nothrow): a plain new Resident does not compile.
    static void* operator new(size_t n,const std::nothrow_t&) noexcept {
        static_assert(alignof(Resident)<=sizeof(void*),"the heap aligns blocks to the pointer size");
        return sttPsramAlloc(n,"stt.resident");
    }
    static void operator delete(void* p) noexcept { sttPsramFree(p); }
    static void operator delete(void* p,const std::nothrow_t&) noexcept { sttPsramFree(p); }
};
namespace {
// Lists every activation tensor with the rate it runs at: feature frames for
// the graph input, output frames after the stride-2 first layer. Any tensor
// whose shape cannot be re-derived that way refuses the resident model.
// Heap snapshots around construction are diagnostic only; other tasks may
// allocate or free memory during the build.
ModelCache::Resident* buildResident(const void* raw,const char*& why) {
    const size_t maxFrames=feature_frames(kResidentMaxSamples), maxOutputs=(maxFrames+1)/2;
    std::unique_ptr<ModelCache::Resident> r(new(std::nothrow) ModelCache::Resident);
    if(!r) { why="alloc"; return nullptr; }
    std::map<std::string,std::vector<int>> shapes{{identity::kInputName,{1,int(maxFrames),1,64}}};
    r->model.reset(new(std::nothrow) dl::Model(static_cast<const char*>(raw),fbs::MODEL_LOCATION_IN_FLASH_RODATA,0,
        dl::MEMORY_MANAGER_GREEDY,nullptr,false,shapes));
    if(!r->model) { why="model"; return nullptr; }
    r->input=r->model->get_input(identity::kInputName);
    r->output=r->model->get_output(identity::kOutputName);
    if(!tensor(r->input,maxFrames,64,identity::kInputExponent) || !tensor(r->output,maxOutputs,29,identity::kOutputExponent)) {
        why="io"; return nullptr;
    }
    fbs::FbsModel* graph=r->model->get_fbs_model();
    if(!graph) { why="graph"; return nullptr; }
    graph->load_map();
    std::vector<std::string> names=graph->get_graph_inputs();
    std::vector<std::string> inputs,outputs;
    bool listed=true;
    for(const std::string& node:graph->topological_sort()) {
        if(graph->get_operation_inputs_and_outputs(node,inputs,outputs)!=ESP_OK) { listed=false; break; }
        names.insert(names.end(),outputs.begin(),outputs.end());
    }
    graph->clear_map();
    if(!listed) { why="graph"; return nullptr; }
    r->tensors.reserve(names.size());  // one block, no growth copies
    for(const std::string& name:names) {
        dl::TensorBase* t=name.empty() ? nullptr : r->model->get_intermediate(name);
        if(!t) { why="tensor"; return nullptr; }
        bool seen=false;
        for(const auto& e:r->tensors) if(e.tensor==t) { seen=true; break; }
        if(seen) continue;
        const auto& s=t->shape;
        if(s.size()!=4 || s[0]!=1 || s[2]!=1 || s[3]<1 || t->dtype!=dl::DATA_TYPE_INT8
           || (s[1]!=int(maxFrames) && s[1]!=int(maxOutputs))) { why="shape"; return nullptr; }
        r->tensors.push_back({t,s[3],s[1]==int(maxFrames)});
    }
    r->frames=maxFrames;
    return r.release();
}
bool shapeResident(ModelCache::Resident& r,size_t frames,size_t outputs) {
    if(r.frames!=frames) {
        for(const auto& e:r.tensors) e.tensor->set_shape({1,int(e.fullRate ? frames : outputs),1,e.channels});
        r.frames=frames;
    }
    return tensor(r.input,frames,64,identity::kInputExponent) && tensor(r.output,outputs,29,identity::kOutputExponent);
}
}
#endif  // HW1_STT_RESIDENT_MODEL
ModelCache::~ModelCache() { reset(); }
#if HW1_STT_RESIDENT_MODEL
// The resident model references the weights zero-copy: destroy it first.
void ModelCache::reset() { dropResident(); heap_caps_free(raw_); raw_=nullptr; }
// Its arena still holds the last call's activations and quantized input:
// freed whenever the session changes hands (STTLocalSession::moveTo), and the
// next owner's first call may build a fresh one.
void ModelCache::dropResident() { delete resident_; resident_=nullptr; residentTried_=false; }
#else
void ModelCache::reset() { heap_caps_free(raw_); raw_=nullptr; }
#endif
#if HW1_STT_RUNTIME_DIAGNOSTICS
bool ModelCache::verify() const {
    uint8_t hash[32];
    return raw_ && digest(raw_,identity::kRawBytes,hash) && !memcmp(hash,identity::kRawSha,32);
}
#endif

// Mirrors transcribe()'s admission below (arenaBudget, frontendBytes,
// metadataMargin and the resident model's call budget); test_quartznet_cache
// checks that a call is admitted at exactly this much free PSRAM and refused
// one byte below.
size_t callBudget(size_t samples, const ModelCache* cache, size_t* contiguous) {
    const size_t frames=feature_frames(samples), outputs=(frames+1)/2;
    const size_t arenaBudget=2048*outputs+64*1024;
    const size_t frontendBytes=frames*kMelBins*sizeof(float)+sizeof(FrontendWorkspace);
    constexpr size_t metadataMargin=1024*1024;
#if HW1_STT_RESIDENT_MODEL
    if(cache && cache->raw_ && cache->resident_ && samples<=kResidentMaxSamples) {
        if(contiguous)*contiguous=frames*kMelBins*sizeof(float)+kResidentCallMargin;
        return frontendBytes+kResidentCallMargin;
    }
#else
    (void)cache;
#endif
    if(contiguous)*contiguous=arenaBudget+metadataMargin;
    return arenaBudget+frontendBytes+metadataMargin;
}

bool transcribe(ModelReader reader, const int16_t* pcm, size_t samples,
                char* text, size_t capacity, const STTLocalControl& control,
                STTLocalStats& stats, char* error, size_t errorCapacity,
                Diagnostics* diagnostics, ModelCache* cache, const Decoder* decoder,
                const STTFeaturePrefix* prefix) {
    InternalMemoryScope internalMemory;
    stats={}; if(text && capacity)text[0]=0;if(error && errorCapacity)error[0]=0;
#if HW1_STT_RUNTIME_DIAGNOSTICS
    if(diagnostics)*diagnostics={};
#else
    (void)diagnostics;
#endif
    auto fail=[&](const char* why) { if(text && capacity)text[0]=0; if(error && errorCapacity)snprintf(error,errorCapacity,"%s",why);return false; };
#if HW1_STT_RESIDENT_MODEL
    // Before this process builds its first STT model, point ESP-DL's
    // metadata allocator at PSRAM (stt_dl_metadata.h). Idempotent; it stays
    // installed, so per-call models (the warm-up, calls beyond the resident
    // length) keep their metadata in PSRAM too.
    installDlMetadataAllocator();
#endif
    if(!pcm || !text || capacity<2 || !reader.read || samples<kMinSamples || samples>kMaxSamples)return fail("Invalid STT audio buffer");
    if(cancelled(control))return fail("Cancelled");
    const size_t frames=feature_frames(samples), outputs=(frames+1)/2;
    stats.samples=samples;stats.featureFrames=frames;stats.outputFrames=outputs;
    if(!container::valid_size(reader.bytes))return fail("STT model size does not match this firmware");
    progress(control,STTLocalPhase::Loading);uint32_t start=millis();
    if(!container::read_header(reader.context,reader.bytes,reader.read))return fail("STT model identity mismatch");
    // This pinned graph's 16-byte greedy arena is 2048*ceil(T/2), including
    // residual lifetimes/fragmentation. Keep extra alignment and metadata/
    // kernel-scratch margins: vendor constructors do not report every OOM.
    const size_t arenaBudget=2048*outputs+64*1024;
    const size_t frontendBytes=frames*kMelBins*sizeof(float)+sizeof(FrontendWorkspace);
    constexpr size_t metadataMargin=1024*1024;
    const size_t remainingBudget=arenaBudget+frontendBytes+metadataMargin;
    // A null cache keeps one-shot calls self-contained. Continuous sessions
    // retain this allocation only until their worker has joined/closed.
    ModelCache temporary;
    ModelCache& weights=cache ? *cache : temporary;
    const bool reused=weights.raw_!=nullptr;
    const size_t newWeights=reused ? 0 : identity::kRawBytes;
#if HW1_STT_RESIDENT_MODEL
    // The resident path already owns its arena and metadata. Its remaining
    // allocation budget is independent of cold construction and of allocations
    // made by unrelated HTTP/Bluetooth tasks while that model was built.
    ModelCache::Resident* const resident=reused && weights.resident_ && samples<=kResidentMaxSamples
        ? weights.resident_ : nullptr;
    const size_t callBudget=resident ? frontendBytes+kResidentCallMargin : remainingBudget;
    const size_t callLargest=resident ? frames*kMelBins*sizeof(float)+kResidentCallMargin : arenaBudget+metadataMargin;
    const auto internalBudget=internalMemoryBudget(resident!=nullptr);
    const size_t callInternal=internalBudget.total;
    // Optional decoder memory (a cached LM) yields before any refusal.
    auto shed=[&] { return decoder && decoder->release && decoder->release(decoder->context); };
    auto psramAdmitted=[&] {
        return heap_caps_get_free_size(MALLOC_CAP_SPIRAM)>=newWeights+callBudget
            && (reused || heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM)>=identity::kRawBytes);
    };
#else
    // Optional decoder memory (a cached LM) yields before any refusal.
    auto shed=[&] { return decoder && decoder->release && decoder->release(decoder->context); };
    auto psramAdmitted=[&] {
        return heap_caps_get_free_size(MALLOC_CAP_SPIRAM)>=newWeights+remainingBudget
            && (reused || heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM)>=identity::kRawBytes);
    };
    const auto internalBudget=internalMemoryBudget(false);
    const size_t callInternal=internalBudget.total;
#endif
    // Releasing a PSRAM language model cannot satisfy an internal SRAM floor.
    // Do not churn that cache or degrade decoding for unrelated SRAM pressure.
    if(!psramAdmitted()) (void)shed();
    if(!psramAdmitted() || heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)<callInternal ||
       heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)<internalBudget.contiguous) {
#if HW1_STT_RESIDENT_MODEL
        const size_t requiredInternal=callInternal, requiredPsram=newWeights+callBudget;
#else
        const size_t requiredInternal=callInternal, requiredPsram=newWeights+remainingBudget;
#endif
        const size_t internalFree=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
        const size_t internalLargest=heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
        const size_t psramFree=heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
        const size_t largest=heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
        ESP_LOGW("STT","admission refused: internal=%u need=%u psram=%u need=%u largest=%u weights=%u internal_largest=%u block_need=%u",
                 unsigned(internalFree),unsigned(requiredInternal),unsigned(psramFree),
                 unsigned(requiredPsram),unsigned(largest),unsigned(newWeights),unsigned(internalLargest),unsigned(internalBudget.contiguous));
        return fail(internalFree<requiredInternal ? "Not enough internal SRAM for speech" :
                    internalLargest<internalBudget.contiguous ? "No contiguous internal SRAM block for speech" :
                    psramFree<requiredPsram ? "Not enough PSRAM for speech" :
                    "No contiguous PSRAM block for speech model");
    }
    if(!reused) {
        Buffer candidate(identity::kRawBytes);
        if(!candidate.p)return fail("Cannot allocate STT model");
        gLoadReadUs=0;
        const int64_t loadStart=esp_timer_get_time();
        const bool loaded=identity::kCodec==0
            ? readStoredModel(reader,static_cast<uint8_t*>(candidate.p),control)
            : inflateModel(reader,static_cast<uint8_t*>(candidate.p),control);
        if(!loaded)return fail(cancelled(control)?"Cancelled":"STT model read failed");
        const int64_t hashStart=esp_timer_get_time();
        uint8_t hash[32];
        if(!digest(candidate.p,identity::kRawBytes,hash) || memcmp(hash,identity::kRawSha,32))return fail("STT model checksum mismatch");
        const int64_t hashEnd=esp_timer_get_time();
        // Once per session (weights are cached after this), so always logged.
        ESP_LOGI("STT","model %u bytes %s: read %lu ms, inflate %lu ms, sha256 %lu ms, total %lu ms",
                 unsigned(identity::kRawBytes),identity::kCodec==0?"stored":"zlib",
                 (unsigned long)(gLoadReadUs/1000),
                 (unsigned long)((hashStart-loadStart-gLoadReadUs)/1000),
                 (unsigned long)((hashEnd-hashStart)/1000),
                 (unsigned long)((hashEnd-loadStart)/1000));
        if(cancelled(control))return fail("Cancelled");
        weights.raw_=candidate.release(); // publish only fully verified weights
    }
    // Cached weights were fully verified (SHA-256) when this session loaded
    // them. Re-hashing all 7.2 MB before every segment cost ~0.6 s per
    // segment on the P4 (sttperf), so production reuse trusts that check;
    // diagnostics probes keep the per-segment re-validation.
#if HW1_STT_RUNTIME_DIAGNOSTICS
    else {
        uint8_t hash[32];
        if(!digest(weights.raw_,identity::kRawBytes,hash) || memcmp(hash,identity::kRawSha,32)) {
            weights.reset();
            return fail("Cached STT model checksum mismatch");
        }
    }
#endif
    stats.modelBytes=identity::kRawBytes;
    stats.weightsReused=reused;
    if(cancelled(control))return fail("Cancelled");
    // Raw model allocation can split the largest block. Check again before
    // the vendor constructor requests a contiguous arena and creates metadata.
#if HW1_STT_RESIDENT_MODEL
    auto contiguous=[&] {
        return heap_caps_get_free_size(MALLOC_CAP_SPIRAM)>=callBudget
            && heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM)>=callLargest;
    };
    if(!contiguous()) (void)shed();
    if(heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)<callInternal)
        return fail("Not enough internal SRAM for speech");
    if(heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)<internalBudget.contiguous)
        return fail("No contiguous internal SRAM block for speech");
    if(!contiguous())
        return fail("Not enough contiguous memory for STT activations");
    // A fresh model per utterance avoids Model::build's resize allocation leak.
    // Aligned EDL2+ in PSRAM allows zero-copy parameters; weights outlive model.
    // Later calls of a session use the resident model instead.
    std::unique_ptr<dl::Model> perCall;
    dl::Model* model=nullptr;
    dl::TensorBase* input=nullptr;
    dl::TensorBase* output=nullptr;
    if(resident) {
        if(!shapeResident(*resident,frames,outputs))return fail("STT runtime tensor mismatch");
        model=resident->model.get(); input=resident->input; output=resident->output;
    } else {
        std::map<std::string,std::vector<int>> shapes{{identity::kInputName,{1,int(frames),1,64}}};
        perCall.reset(new(std::nothrow) dl::Model(
            static_cast<const char*>(weights.raw_),fbs::MODEL_LOCATION_IN_FLASH_RODATA,0,
            dl::MEMORY_MANAGER_GREEDY,nullptr,false,shapes));
        if(!perCall)return fail("Cannot create STT model");
        model=perCall.get();
        input=model->get_input(identity::kInputName);output=model->get_output(identity::kOutputName);
        if(!tensor(input,frames,64,identity::kInputExponent) || !tensor(output,outputs,29,identity::kOutputExponent))return fail("STT runtime tensor mismatch");
    }
#else
    auto contiguous=[&] {
        return heap_caps_get_free_size(MALLOC_CAP_SPIRAM)>=remainingBudget
            && heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM)>=arenaBudget+metadataMargin;
    };
    if(!contiguous()) (void)shed();
    if(heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)<callInternal)
        return fail("Not enough internal SRAM for speech");
    if(heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)<internalBudget.contiguous)
        return fail("No contiguous internal SRAM block for speech");
    if(!contiguous())
        return fail("Not enough contiguous memory for STT activations");
    // A fresh model per utterance avoids Model::build's resize allocation leak.
    // Aligned EDL2+ in PSRAM allows zero-copy parameters; weights outlive model.
    std::map<std::string,std::vector<int>> shapes{{identity::kInputName,{1,int(frames),1,64}}};
    std::unique_ptr<dl::Model> model(new(std::nothrow) dl::Model(
        static_cast<const char*>(weights.raw_),fbs::MODEL_LOCATION_IN_FLASH_RODATA,0,
        dl::MEMORY_MANAGER_GREEDY,nullptr,false,shapes));
    if(!model)return fail("Cannot create STT model");
    auto input=model->get_input(identity::kInputName);auto output=model->get_output(identity::kOutputName);
    if(!tensor(input,frames,64,identity::kInputExponent) || !tensor(output,outputs,29,identity::kOutputExponent))return fail("STT runtime tensor mismatch");
#endif
#if HW1_STT_RUNTIME_DIAGNOSTICS
    if(diagnostics) {
        const auto memory=model->get_memory_info();
        const auto variable=memory.find("variable");
        if(variable!=memory.end()) {
            diagnostics->activationPsramBytes=variable->second.psram;
            diagnostics->activationInternalBytes=variable->second.internal;
        }
    }
#endif
    stats.loadMs=millis()-start;
    if(cancelled(control))return fail("Cancelled");
    progress(control,STTLocalPhase::Frontend);start=millis();
    {
        Buffer features(frames*64*sizeof(float),true), workspace(sizeof(FrontendWorkspace),true);
        if(!features.p || !workspace.p)return fail("Cannot allocate STT frontend");
        auto f=static_cast<float*>(features.p);
        FrontendTiming timing;
        timing.now_us=[]() -> uint64_t { return static_cast<uint64_t>(esp_timer_get_time()); };
        // No dither on device: the microphone noise floor is ~10x its 1e-5
        // amplitude, and the Gaussian generator cost ~1.2 s per 8 s segment.
        // Rows computed during capture (HW1_STT_CAPTURE_FEATURES) are copied,
        // only the rest are computed here (log_mel_frame: the same per-row
        // arithmetic), then the same CMVN. Bit-identical to compute_features
        // on this PCM. A row computed alone re-conditions its whole
        // 320-sample window (about 1.4x a batch row), so a cache covering
        // under a third of the rows falls back to the unchanged batch frontend.
        auto* ws=static_cast<FrontendWorkspace*>(workspace.p);
        if(prefix && prefix->rows && prefix->count && prefix->count<=frames && prefix->count*3>=frames) {
            const int64_t copyStart=esp_timer_get_time();
            memcpy(f,prefix->rows,prefix->count*64*sizeof(float));
            const int64_t tailStart=esp_timer_get_time();
            for(size_t row=prefix->count;row<frames;++row)
                if(log_mel_frame(pcm,samples,row,f+row*64,ws)!=Status::Ok)return fail("STT frontend failed");
            timing.conditionUs=static_cast<uint32_t>(tailStart-copyStart);   // copy of cached rows
            timing.fftUs=static_cast<uint32_t>(esp_timer_get_time()-tailStart);  // rows computed here
            if(normalize_features(f,frames,ws,&timing)!=Status::Ok)return fail("STT frontend failed");
            stats.featureCachedFrames=static_cast<uint32_t>(prefix->count);
        } else if(compute_features(pcm,samples,f,frames*64,ws,
                            kDitherSeed,false,&timing)!=Status::Ok)return fail("STT frontend failed");
        stats.frontendConditionUs=timing.conditionUs; stats.frontendFftUs=timing.fftUs;
        stats.frontendMelUs=timing.melUs; stats.frontendNormUs=timing.normUs;
        const int64_t quantizeStart=esp_timer_get_time();
        auto q=static_cast<int8_t*>(input->data);
        const float scale=std::ldexp(1.0f,-identity::kInputExponent);
        for(size_t i=0;i<frames*64;++i) {
            // nearest-even, matching ESP-PPQ/P4 quantization, independent of
            // ambient FPU rounding mode (roundf would round ties away).
            float x=f[i]*scale, lo=std::floor(x), part=x-lo;
            int value=part>0.5f?int(lo)+1:part<0.5f?int(lo):(int(lo)&1)?int(lo)+1:int(lo);
            q[i]=static_cast<int8_t>(std::max(-128,std::min(127,value)));
        }
        stats.quantizeUs=static_cast<uint32_t>(esp_timer_get_time()-quantizeStart);
    }
    stats.frontendMs=millis()-start;
#if HW1_STT_RUNTIME_DIAGNOSTICS
    if(diagnostics) {
        digest(input->data,input->get_bytes(),diagnostics->inputSha);
        diagnostics->freePsramAtInference=heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
        diagnostics->freeInternalAtInference=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
    }
#endif
    if(cancelled(control))return fail("Cancelled");
    progress(control,STTLocalPhase::Inference);start=millis();
    // Blocking with vTaskDelay(1) every 5 stages cost 41 ticks per 15x5 run
    // (each up to 1 ms: 32-54 ms per phrase). The 5-stage points now only
    // taskYIELD() (round-robin with other priority-2 tasks; the capture task
    // and anything above priority 2 preempt at any time anyway), and one
    // blocking vTaskDelay(1) is kept on an esp_timer clock: at the first
    // 5-stage point at least kYieldBlockUs after the last block. That still
    // lets both idle tasks (watchdog 5 s) and the priority-1 loop run
    // several times a second after the multicore workers have joined. Drafts stay
    // preemptible: the cancel check still runs before every stage.
#if HW1_STT_RESIDENT_MODEL
    // On the resident model, first build every Conv layer's args in one pass
    // (no layer computes), so their setup code and tensor metadata come into
    // the caches once instead of after every layer's weights flushed them;
    // each layer then runs on its prepared args. Same args, bit-identical
    // output. The prepared blocks are PSRAM metadata the resident model
    // keeps. Per-call models (the warm-up) skip the pass, so the LM, which
    // the warm-up loads lazily at its decode, sees the same PSRAM as before.
    if(resident) {
#if CONFIG_HW1_STT_MODEL_LOCAL_PREPARE
        model->prepare_args(dl::RUNTIME_MODE_MULTI_CORE);
#else
        if(++hw1_dl_prepare_gen==0)++hw1_dl_prepare_gen;
        hw1_dl_prepare_mode=1;
        for(int stage=0;stage<identity::kNodeCount;++stage)model->run(identity::kNodeCount,stage,dl::RUNTIME_MODE_MULTI_CORE);
        hw1_dl_prepare_mode=0;
#endif
    }
#endif
    constexpr int64_t kYieldBlockUs=250000;
    int64_t lastBlockUs=esp_timer_get_time();
    for(int stage=0;stage<identity::kNodeCount;++stage) {
        if(cancelled(control))return fail("Cancelled");
        const int64_t stageStart=esp_timer_get_time();
        model->run(identity::kNodeCount,stage,dl::RUNTIME_MODE_MULTI_CORE);
        const int64_t stageEnd=esp_timer_get_time();
        // Keep the three slowest stages (sorted, slowest first) for sttperf.
        uint32_t us=static_cast<uint32_t>(stageEnd-stageStart);
        uint16_t index=static_cast<uint16_t>(stage);
        for(int k=0;k<3;++k) if(stats.slowStage[k]==0xffff || us>stats.slowStageUs[k]) {
            std::swap(us,stats.slowStageUs[k]); std::swap(index,stats.slowStage[k]);
        }
        if(stage<kStageProfileMax){ gStageTotalUs[stage]+=static_cast<uint32_t>(stageEnd-stageStart); }
        // Yield every 5 stages (was every stage: 201 x ~1 ms on the 15x5);
        // block only on the timer above, otherwise a non-blocking yield.
        if((stage+1)%5==0 || stage+1==identity::kNodeCount) {
            if(stageEnd-lastBlockUs>=kYieldBlockUs) {
                vTaskDelay(1);
                lastBlockUs=esp_timer_get_time();
                ++stats.inferenceBlocks;
            } else {
                taskYIELD();
            }
            stats.inferenceYieldUs+=static_cast<uint32_t>(esp_timer_get_time()-stageEnd);
        }
    }
    ++gStageSegments;
    stats.inferenceMs=millis()-start;
    if(cancelled(control))return fail("Cancelled");
    progress(control,STTLocalPhase::Decoding);start=millis();
#if HW1_STT_RUNTIME_DIAGNOSTICS
    if(diagnostics)digest(output->data,output->get_bytes(),diagnostics->outputSha);
#endif
    // Any decoder failure other than cancellation decodes greedily instead.
    const auto logits=static_cast<const int8_t*>(output->data);
    DecodeResult decoded=decoder && decoder->decode
        ? decoder->decode(decoder->context,logits,outputs,identity::kOutputExponent,text,capacity,control)
        : DecodeResult::Fallback;
    if(decoded==DecodeResult::Cancelled)return fail("Cancelled");
    if(decoded==DecodeResult::Decoded && !memchr(text,0,capacity))decoded=DecodeResult::Fallback;
    if(decoded!=DecodeResult::Decoded) {
        CtcState ctc;
        if(ctc_reset(&ctc,text,capacity)!=Status::Ok
           || ctc_feed(&ctc,logits,outputs,29,text,capacity)!=Status::Ok
           || ctc_finish(&ctc,text,capacity)!=Status::Ok || ctc.truncated)return fail("STT transcript exceeds result capacity");
    }
    stats.lmUsed=decoded==DecodeResult::Decoded;
    stats.decodeMs=millis()-start;
    if(cancelled(control))return fail("Cancelled");
#if HW1_STT_RESIDENT_MODEL
    // Build the session's resident model once, after the session's first
    // call (the warm-up) has decoded, so a lazily loaded LM already took its
    // PSRAM, and after this call's own model and arena are gone. It needs the
    // budget of a 20 s per-call build and must leave kResidentKeepFree.
    if(cache && !cache->resident_ && !cache->residentTried_) {
        cache->residentTried_=true;
        perCall.reset();
        const size_t maxOutputs=(feature_frames(kResidentMaxSamples)+1)/2;
        const size_t need=2048*maxOutputs+64*1024+metadataMargin;
        const size_t internal0=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
        const size_t psram0=heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
        const char* why="memory";
        const uint32_t buildStart=millis();
        DlMetadataStats kind0[kDlMetadataKinds];
        for(size_t k=0;k<kDlMetadataKinds;++k)kind0[k]=dlMetadataStats(k);
        const DlMetadataStats meta0=dlMetadataStats();
        const dl::tool::MetadataForeignStats foreign0=dl::tool::metadata_foreign_stats();
        if(psram0>=need+kResidentKeepFree && heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM)>=need
           && internal0>=internalMemoryBudget(false).total
           && heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)>=internalMemoryBudget(false).contiguous)
            cache->resident_=buildResident(cache->raw_,why);
        // Global heap delta is diagnostic, not model-owned memory. Network
        // tasks can change it in either direction; it never changes admission.
        const size_t internal1=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
        const DlMetadataStats meta=dlMetadataDelta(meta0,dlMetadataStats());
        const dl::tool::MetadataForeignStats foreign1=dl::tool::metadata_foreign_stats();
        // int_used/psram_used are process-wide positive heap deltas, not
        // ownership attribution. Kept as diagnostic fields for existing tools;
        // meta_n / meta_bytes are the blocks (and bytes) ESP-DL requested
        // through the metadata allocator during the build (growth copies
        // included; meta_frees of them were returned), fallback /
        // fallback_bytes those that landed in internal RAM (PSRAM refused),
        // meta_failed those neither heap could serve. param_objs are the
        // parameter tensor objects prebuilt libfbs_model allocated itself
        // (heap order puts them in PSRAM), param_int how many of them are in
        // internal RAM. TL e3m: bytes requested per metadata kind. All
        // numeric, so tl_capture.py records both lines.
        if(cache->resident_) {
            size_t arenaPsram=0,arenaInternal=0;
            cache->resident_->model->get_arena_size(&arenaPsram,&arenaInternal);
            ESP_LOGI("STT","TL e3 resident=1 t=%lu build_ms=%lu tensors=%u int_used=%u psram_used=%u int_free=%u psram_free=%u"
                     " arena=%u arena_int=%u meta_n=%u meta_bytes=%u meta_frees=%u fallback=%u fallback_bytes=%u"
                     " meta_failed=%u param_objs=%u param_int=%u",
                     (unsigned long)millis(),(unsigned long)(millis()-buildStart),unsigned(cache->resident_->tensors.size()),
                     unsigned(internal0>internal1 ? internal0-internal1 : 0),
                     unsigned(psram0-std::min(psram0,heap_caps_get_free_size(MALLOC_CAP_SPIRAM))),
                     unsigned(heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),
                     unsigned(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)),
                     unsigned(arenaPsram),unsigned(arenaInternal),unsigned(meta.allocs),unsigned(meta.bytes),
                     unsigned(meta.frees),unsigned(meta.internal),unsigned(meta.internalBytes),unsigned(meta.failed),
                     unsigned(foreign1.objects-foreign0.objects),unsigned(foreign1.internal-foreign0.internal));
            uint32_t kindBytes[kDlMetadataKinds];
            for(size_t k=0;k<kDlMetadataKinds;++k)kindBytes[k]=dlMetadataDelta(kind0[k],dlMetadataStats(k)).bytes;
            static_assert(kDlMetadataKinds==11,"TL e3m lists every metadata kind");
            ESP_LOGI("STT","TL e3m model=%u ctx=%u loader=%u fbs=%u module=%u tensor=%u exp=%u shape=%u index=%u list=%u names=%u",
                     unsigned(kindBytes[0]),unsigned(kindBytes[1]),unsigned(kindBytes[2]),unsigned(kindBytes[3]),
                     unsigned(kindBytes[4]),unsigned(kindBytes[5]),unsigned(kindBytes[6]),unsigned(kindBytes[7]),
                     unsigned(kindBytes[8]),unsigned(kindBytes[9]),unsigned(kindBytes[10]));
        } else {
            ESP_LOGW("STT","TL e3 resident=0 reason=%s int_free=%u psram_free=%u psram_largest=%u meta_n=%u fallback=%u; per-call models",
                     why,unsigned(heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),
                     unsigned(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)),
                     unsigned(heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM)),
                     unsigned(meta.allocs),unsigned(meta.internal));
        }
    }
#endif
#if HW1_STT_RESIDENT_MODEL
    internalMemory.success(resident!=nullptr);
#else
    internalMemory.success(false);
#endif
    // Model destructor releases its arena before temporary weights are freed.
    // Session weights remain immutable and are rechecked on the next call.
    return true;
}
}
