#pragma once
// Speaker-embedding model behind a model-agnostic file, speaker.spk:
//   128-byte header (little endian):
//     "HW1SPK1\0", version u32 (1), header bytes u32 (128),
//     feature spec: n_mels, n_fft, win, hop, window_frames, pad (u16 x 6),
//                   f_min, f_max, log_eps, norm_eps (f32 x 4),
//     trunk channels u16, embedding dim u16, pooling u16 (1 = attention
//     pooling, SAP), reserved u16,
//     head offset, head bytes, trunk offset, trunk bytes (u32 x 4),
//     default cluster threshold f32, minimum new-speaker phrase ms u32;
//   head: float32 SAP linear W[C x C], b[C], attention[C], projection W[D x C], b[D];
//   trunk: an ESP-DL model (16-byte aligned) mapping [1, n_mels, frames, 1]
//          features to [1, T', C] frame vectors (int8 or int16 activations);
//   SHA-256 of everything before it (32 bytes).
// Another model needs only a new file: features, sizes, threshold and the
// trunk graph all come from it (the pooling kinds are coded here: SAP now).
#include "speaker_frontend.h"
#include <cstddef>
#include <cstdint>

namespace dl { class Model; class TensorBase; }

namespace hw1::stt::speaker {

enum class LoadStatus : uint8_t { Ok, BadSize, BadHeader, BadHash, BadTrunk, NoMemory };
const char* describe(LoadStatus status);

struct ModelInfo {
    FeatureSpec features;
    uint16_t channels=0, dim=0, pooling=0;
    float threshold=0.6f;
    uint32_t minNewMs=2000;
    size_t trunkBytes=0, headBytes=0;
};

// Per-phrase sections (us). feature = fft + mel + norm (+ crop/copy);
// head = sap + pool + fc.
struct EmbedTiming {
    uint32_t featureUs=0, fftUs=0, melUs=0, normUs=0;
    uint32_t quantUs=0, trunkUs=0, dequantUs=0;
    uint32_t headUs=0, sapUs=0, poolUs=0, fcUs=0;
    uint16_t frames=0;      // feature frames computed (before repetition)
    bool cropped=false;     // phrase longer than the window: centre-cropped
};
// Load-time facts, for the TL spk_load line.
struct LoadReport {
    uint32_t shaUs=0, buildUs=0, testUs=0;
    int testResult=-1;           // ESP-DL Model::test() on the file's own test values: 0 ok, -1 not run
    size_t arenaPsram=0, arenaInternal=0, workspaceBytes=0;
    uint16_t modules=0;
};
// Trunk profile, accumulated over every embed() since load: per execution-plan
// module, its name, calls and total us (layer-by-layer staged run).
struct StageProfile { const char* name; uint32_t calls; uint64_t us; };

class Model {
 public:
    Model()=default;
    ~Model();
    Model(const Model&)=delete;
    Model& operator=(const Model&)=delete;
    // blob: the whole speaker.spk, 16-byte aligned, kept alive by the caller
    // until reset(). maxSamples: longest phrase embed() will see. Allocates its
    // workspace with alloc (PSRAM on the P4) and builds the ESP-DL trunk.
    LoadStatus load(const uint8_t* blob, size_t bytes, size_t maxSamples,
                    void* (*alloc)(size_t bytes, const char* tag), void (*release)(void*));
    void reset();
    bool ready() const { return trunk_!=nullptr; }
    const ModelInfo& info() const { return info_; }
    // embedding: info().dim floats (not normalised). False on bad input.
    bool embed(const int16_t* pcm, size_t samples, float* embedding, EmbedTiming* timing=nullptr);
    const LoadReport& loadReport() const { return report_; }
    size_t stages() const { return modules_; }
    StageProfile stage(size_t i) const;
    uint32_t embeds() const { return embeds_; }
    void resetProfile();
    // Trunk run mode: dual-core (default) or single-core (background labelling task).
    void setMultiCore(bool on) { multiCore_=on; }
    // Diagnostics: per-module internal-RAM dip (heap local minimum) of the next embeds; worst module so far.
    void setRamProbe(bool on) { ramProbe_=on; }
    size_t worstRamDip(size_t* module) const { if(module)*module=worstDipModule_; return worstDip_; }
    // Load-time ESP-DL self-test on the file's test values (slow: one trunk run); off unless asked.
    static void setLoadSelfTest(bool on);

 private:
    ModelInfo info_;
    Frontend frontend_;
    dl::Model* trunk_=nullptr;
    dl::TensorBase* input_=nullptr;
    dl::TensorBase* output_=nullptr;
    const float *sapW_=nullptr, *sapB_=nullptr, *att_=nullptr, *fcW_=nullptr, *fcB_=nullptr;
    float* work_=nullptr;     // frontend workspace + features + frames + scores
    float* features_=nullptr; // n_mels * window_frames
    float* frames_=nullptr;   // T' * C dequantised
    float* scores_=nullptr;   // T'
    float* hidden_=nullptr;   // C
    float* pooled_=nullptr;   // C
    size_t outFrames_=0;
    static constexpr size_t kMaxStages=256;
    size_t modules_=0;
    uint32_t embeds_=0;
    uint32_t stageCalls_[kMaxStages]={};
    uint64_t stageUs_[kMaxStages]={};
    LoadReport report_;
    bool multiCore_=true;
    bool ramProbe_=false;
    size_t worstDip_=0, worstDipModule_=0;
    void (*release_)(void*)=nullptr;
};

}  // namespace hw1::stt::speaker
