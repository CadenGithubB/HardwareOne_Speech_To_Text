#pragma once
// Overlap gate decision rule, portable (no ESP-DL, no heap): the part of the device rule that a
// host test can pin exactly. docs/STT_OVERLAP_GATE_PHASE4_PLAN.md section 8:
//   per 20 ms frame, softmax over the three int8 logits (scale 2^exponent); mark when
//   P(two or more) >= frame_threshold; drop marked runs shorter than min_run frames over the
//   whole segment; fraction = remaining marked / segment frames; flag when >= segment_threshold.
// Logits arrive chunk by chunk ([frame][class], 3 classes, class 2 = two or more); the run filter
// runs once over the whole segment, so runs crossing a chunk boundary count.
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace hw1::stt::overlap {

inline constexpr size_t kClasses = 3, kOverlapClass = 2;

struct Rule {
    float frame_threshold = 0.5f;
    uint32_t min_run = 10;
    float segment_threshold = 0.360f;
};

struct Decision {
    uint32_t frames = 0, marked = 0;
    float fraction = 0.0f;
    bool flag = false;
};

// P(class 2) for one frame from its three int8 logits at scale 2^exponent.
inline float overlap_posterior(const int8_t* logits, int exponent) {
    const float scale = std::ldexp(1.0f, exponent);
    float z[kClasses];
    float best = -1e30f;
    for (size_t c = 0; c < kClasses; ++c) { z[c] = float(logits[c]) * scale; if (z[c] > best) best = z[c]; }
    float sum = 0.0f;
    for (size_t c = 0; c < kClasses; ++c) { z[c] = std::exp(z[c] - best); sum += z[c]; }
    return z[kOverlapClass] / sum;
}

// Collects per-frame marks for one segment, then decides. Capacity is the caller's: marks[capacity].
class Accumulator {
 public:
    Accumulator(uint8_t* marks, size_t capacity) : marks_(marks), capacity_(capacity) {}
    void reset() { frames_ = 0; overflow_ = false; }
    // Append `frames` frames of logits ([frame][3]); frames beyond capacity are counted but unmarked.
    void add(const int8_t* logits, size_t frames, int exponent, const Rule& rule) {
        for (size_t t = 0; t < frames; ++t) {
            const bool mark = overlap_posterior(logits + t * kClasses, exponent) >= rule.frame_threshold;
            if (frames_ < capacity_) marks_[frames_] = mark ? 1 : 0; else overflow_ = true;
            ++frames_;
        }
    }
    bool overflow() const { return overflow_; }
    Decision decide(const Rule& rule) const {
        Decision d;
        d.frames = uint32_t(frames_);
        const size_t n = frames_ < capacity_ ? frames_ : capacity_;
        size_t i = 0, kept = 0;
        while (i < n) {
            if (!marks_[i]) { ++i; continue; }
            size_t j = i;
            while (j < n && marks_[j]) ++j;
            if (j - i >= rule.min_run) kept += j - i;
            i = j;
        }
        d.marked = uint32_t(kept);
        d.fraction = frames_ ? float(kept) / float(frames_) : 0.0f;
        d.flag = d.fraction >= rule.segment_threshold;
        return d;
    }

 private:
    uint8_t* marks_;
    size_t capacity_, frames_ = 0;
    bool overflow_ = false;
};

// int8 value a raw log-mel bin takes at scale 2^exponent, as the model input expects.
inline int8_t quantize_bin(float value, int exponent) {
    const float v = std::nearbyint(value * std::ldexp(1.0f, -exponent));
    return int8_t(v > 127.f ? 127.f : (v < -128.f ? -128.f : v));
}

}  // namespace hw1::stt::overlap
