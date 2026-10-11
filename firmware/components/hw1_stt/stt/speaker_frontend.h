#pragma once
// Speaker-embedding front end, described by the model file (speaker_model.h),
// so another embedding model with other feature settings needs no code change:
// a `win`-sample periodic Hamming window centred in an `n_fft`-point frame every
// `hop` samples (frames = 1 + samples/hop, edges reflected: torch.stft
// center=True), power spectrum, `n_mels` HTK mel triangles over [f_min, f_max]
// (unnormalised, torchaudio's melscale_fbanks), log(x + log_eps), then each mel
// band normalised over the phrase (mean, biased variance + norm_eps), and the
// result cut to a fixed window of `window_frames` frames: centre-cropped when
// longer, the phrase repeated end to end when shorter.
// Output layout: [n_mels][window_frames] (row = mel band), floats.
// Workspace is caller-provided: workspace_floats(spec, max_samples) floats.
#include <cstddef>
#include <cstdint>

namespace hw1::stt::speaker {

struct FeatureSpec {
    uint16_t n_mels=40, n_fft=512, win=400, hop=160, window_frames=300;
    float f_min=0.0f, f_max=8000.0f, log_eps=1e-6f, norm_eps=1e-5f;
};

bool valid(const FeatureSpec& spec);
// Floats of workspace compute() needs for phrases up to max_samples.
size_t workspace_floats(const FeatureSpec& spec, size_t max_samples);

class Frontend {
 public:
    // workspace: workspace_floats(spec, max_samples) floats (kept for the
    // object's lifetime; mel weights and the window live in it too).
    bool init(const FeatureSpec& spec, size_t max_samples, float* workspace);
    // pcm: 16 kHz mono int16, 1 <= samples <= max_samples (others false).
    // out: n_mels * window_frames floats.
    bool compute(const int16_t* pcm, size_t samples, float* out) const;
    // Section timings of the last compute() (us) and its frame count.
    struct Timing { uint32_t fftUs=0, melUs=0, normUs=0, frames=0; bool cropped=false; };
    const Timing& timing() const { return timing_; }
    const FeatureSpec& spec() const { return spec_; }

 private:
    FeatureSpec spec_;
    size_t maxSamples_=0, maxFrames_=0, bins_=0;
    static constexpr size_t kMaxMels=128, kMaxHalf=1024;
    float* window_=nullptr;    // win
    float* mel_=nullptr;       // compact nonzero mel weights, band after band
    float* frames_=nullptr;    // maxFrames * n_mels log mel, frame-major
    float* fft_=nullptr;       // scratch: frame (n_fft), re/im (n_fft/2 each), power (n_fft/2 + 1)
    float* twiddle_=nullptr;   // n_fft/2 cos, then n_fft/2 -sin (e^{-2 pi i k / n_fft})
    uint16_t melStart_[kMaxMels]={}, melCount_[kMaxMels]={};
    uint32_t melOffset_[kMaxMels]={};
    uint16_t bitrev_[kMaxHalf]={};   // n_fft/2-point bit reversal
    mutable Timing timing_;
};

}  // namespace hw1::stt::speaker
