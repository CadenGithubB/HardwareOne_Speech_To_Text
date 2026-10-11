#pragma once
#include <cstddef>
#include <cstdint>
namespace hw1::stt {
inline constexpr size_t kSampleRate=16000, kMelBins=64, kMinSamples=320, kMaxSamples=480000;
inline constexpr uint32_t kDitherSeed=0x12345678;
enum class Status : uint8_t { Ok, InvalidArgument, OutputTooSmall, NonFinite, AlreadyFinished };
// All workspace is caller-owned. No heap allocation, microphone or filesystem calls.
// One Workspace may be reused serially, never shared between simultaneous calls.
struct FrontendWorkspace {
    float conditioned[512], real[512], imag[512], power[257];
    double means[kMelBins], variances[kMelBins];
};
size_t feature_frames(size_t samples);
// int16 PCM -> row-major float32 [ceil(N/160),64], without padding.
// Input, output and workspace allocations must not overlap.
// Raw HAL input: no upstream pre-emphasis/CMVN. Samples must be mono16kHz.
// Deterministic Gaussian dither is reset once per utterance, before pre-emphasis.
// Optional profiling (sttperf): microseconds per phase, accumulated when
// now_us is set. Never changes the features.
struct FrontendTiming {
    uint64_t (*now_us)()=nullptr;
    uint32_t conditionUs=0, fftUs=0, melUs=0, normUs=0;
};
Status compute_features(const int16_t* pcm, size_t samples, float* output,
                        size_t output_floats, FrontendWorkspace* workspace,
                        uint32_t seed=kDitherSeed, bool dither=true,
                        FrontendTiming* timing=nullptr);
// Incremental features (the broker computes rows while a phrase is captured,
// HW1_STT_CAPTURE_FEATURES). Row `frame` of
// compute_features(pcm, samples, ..., dither=false) before CMVN, alone: the
// same float operations in the same order (this file keeps -ffp-contract=off),
// so rows are bit-identical. A row reads samples [frame*160-161, frame*160+160)
// (frame 0 also reads sample 160), reflecting at the segment's start and at
// `samples`; a row with (frame+1)*160 <= samples and samples >= 320 never
// reflects at the end, so it is final as soon as those samples exist.
Status log_mel_frame(const int16_t* pcm, size_t samples, size_t frame, float* out64,
                     FrontendWorkspace* workspace);
// The same row, reading segment sample i from ring[(start + i) & ring_mask]
// (ring_mask + 1 a power of two): the stream ring of the capture pipeline.
Status log_mel_frame_ring(const int16_t* ring, size_t ring_mask, uint64_t start, size_t samples,
                          size_t frame, float* out64, FrontendWorkspace* workspace);
// compute_features' per-utterance CMVN over finished rows, in place.
Status normalize_features(float* output, size_t frames, FrontendWorkspace* workspace,
                          FrontendTiming* timing=nullptr);
inline constexpr size_t kCtcClasses=29, kCtcBlank=28;
struct CtcState {
    int previous=-1;
    size_t written=0, frames=0;
    bool truncated=false, finished=false;
};
Status ctc_reset(CtcState* state, char* text, size_t capacity);
// Scores have one common scale per tensor; int8 argmax requires no dequantization.
// Maximum cumulative score frames: 3000. Caller supplies frames*stride scores.
// Feed only valid model frames. State carries repeat/blank collapse across chunks.
Status ctc_feed(CtcState* state, const float* scores, size_t frames, size_t stride,
                char* text, size_t capacity);
Status ctc_feed(CtcState* state, const int8_t* scores, size_t frames, size_t stride,
                char* text, size_t capacity);
// Finalization trims only trailing spaces and seals the output against later feeds.
Status ctc_finish(CtcState* state, char* text, size_t capacity);
}
