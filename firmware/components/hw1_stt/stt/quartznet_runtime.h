#pragma once
#include "System_STTLocal.h"
#include <cstddef>
#include <cstdint>
// Tensor hashes and vendor memory profiling are probe-only; production keeps
// its user-facing timings/status without retaining this optional code.
#ifndef HW1_STT_RUNTIME_DIAGNOSTICS
#define HW1_STT_RUNTIME_DIAGNOSTICS 0
#endif
// The resident model: one dl::Model per session, built after the session's
// first call and re-shaped for every later call, instead of building and
// freeing a model and its arena on every call (measured on the P4 with the
// 15x5: a phrase's per-call load()/build() was most of its non-inference
// time). Its metadata (about 97 KB that would otherwise stay in internal RAM
// between phrases) is requested explicitly from PSRAM at ESP-DL's own
// allocation sites (the tree-local ESP-DL's metadata allocator hook,
// stt_dl_metadata.h, which uses ps_alloc), so internal RAM between phrases
// stays as with per-call models. Default ON. =0 restores per-call models and
// the 150 KB internal-RAM admission floor, and never installs the hook (ESP-DL
// then places its metadata exactly as upstream). The component CMake passes
// the value (-DHW1_STT_RESIDENT_MODEL=0 at configure time turns it off) for
// the whole hardwareone component, never a features file: ModelCache's layout
// depends on it, so every translation unit must see the same value.
#ifndef HW1_STT_RESIDENT_MODEL
#define HW1_STT_RESIDENT_MODEL 1
#endif
namespace hw1::stt {
// A read-only stream already opened by the caller's storage/auth boundary.
struct ModelReader {
    void* context;
    size_t bytes;
    size_t (*read)(void*, void*, size_t);
};
// Ignored unless the runtime is compiled with HW1_STT_RUNTIME_DIAGNOSTICS=1.
struct Diagnostics {
    uint8_t inputSha[32]{}, outputSha[32]{};
    size_t activationPsramBytes = 0;
    size_t activationInternalBytes = 0;
    size_t freePsramAtInference = 0;
    size_t freeInternalAtInference = 0;
};
// Optional replacement for greedy CTC over the final int8 logits [frames x 29]
// (value = q * 2^exponent), e.g. the HW1LM1 beam search. Decoded: text holds
// a NUL-terminated result. Fallback: greedy runs exactly as with no decoder.
// Cancelled fails the call. release frees optional decoder memory (true if
// any); the runtime tries it before reporting a PSRAM shortfall, so a cached
// language model can never be why a call is refused.
enum class DecodeResult : uint8_t { Decoded, Fallback, Cancelled };
struct Decoder {
    void* context = nullptr;
    DecodeResult (*decode)(void* context, const int8_t* logits, size_t frames, int exponent,
                           char* text, size_t capacity, const STTLocalControl& control) = nullptr;
    bool (*release)(void* context) = nullptr;
};
// Retains the pinned, verified raw weights and, with HW1_STT_RESIDENT_MODEL,
// the session's resident model (its arena holds the last call's activations
// until the session ends or changes hands: dropResident). Without it each call
// constructs a fresh shape-specific model/arena; vendor resize/rebuild is
// never reused. One worker owns this object. Destroy/reset only after
// transcribe returns.
class ModelCache;
// PSRAM one transcribe() call of `samples` needs beside `cache`'s verified
// weights, by the same rule transcribe() admits it with (a per-call model:
// arena, frontend and metadata margin; with HW1_STT_RESIDENT_MODEL and a built
// resident model: the frontend only). *contiguous is the part that must be one
// free block. The broker sizes optional per-session pools against it.
size_t callBudget(size_t samples, const ModelCache* cache, size_t* contiguous);
class ModelCache {
 public:
    ModelCache() = default;
    ~ModelCache();
    void reset();
    bool loaded() const { return raw_ != nullptr; }
#if HW1_STT_RESIDENT_MODEL
    // One vendor model per session, built at the broker's 20 s cap after the
    // session's first call and re-shaped for every later call, its metadata
    // and this bookkeeping requested from PSRAM (quartznet_runtime.cpp,
    // stt_dl_metadata.h). Destroyed before the weights.
    struct Resident;
    // Frees the resident model and its arena (the weights stay); the next
    // call may build a new one. For a session that changes hands.
    void dropResident();
#endif
#if HW1_STT_RUNTIME_DIAGNOSTICS
    // Probe integrity after the vendor model and arena have been destroyed.
    bool verify() const;
#endif
    ModelCache(const ModelCache&) = delete;
    ModelCache& operator=(const ModelCache&) = delete;
 private:
    void* raw_ = nullptr;
#if HW1_STT_RESIDENT_MODEL
    Resident* resident_ = nullptr;
    bool residentTried_ = false;  // one build attempt per session
#endif
    friend bool transcribe(ModelReader, const int16_t*, size_t, char*, size_t,
                           const STTLocalControl&, STTLocalStats&, char*, size_t,
                           Diagnostics*, ModelCache*, const Decoder*, const STTFeaturePrefix*);
    friend size_t callBudget(size_t, const ModelCache*, size_t*);
};
// Per-stage inference time summed over segments since the last reset
// (single STT worker writes; readers accept a racy snapshot for profiling).
size_t stageProfile(uint32_t* totalUs, size_t cap, uint32_t* segments);
void stageProfileReset();
bool transcribe(ModelReader reader, const int16_t* pcm, size_t samples,
                char* text, size_t capacity, const STTLocalControl& control,
                STTLocalStats& stats, char* error, size_t errorCapacity,
                Diagnostics* diagnostics = nullptr, ModelCache* cache = nullptr,
                const Decoder* decoder = nullptr, const STTFeaturePrefix* prefix = nullptr);
}
