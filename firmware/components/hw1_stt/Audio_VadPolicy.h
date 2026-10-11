#pragma once
#include <cstdint>

namespace hw1::audio {
// Amplitudes share the caller's units (for example mean absolute level or RMS).
// The caller owns measurement, ambient-window/peak updates, latch lifetime and
// timing. PCM is never changed here. Nonnegative int16 PCM amplitudes (0..32768)
// keep the floor doubling below int32 limits; floorBefore=-1 means unseeded.
struct AdaptiveVadConfig {
  int32_t speechFloor = 120;
  int32_t silenceFloor = 45;
};
struct AdaptiveVadDecision {
  int32_t trimCut = 0;
  int32_t stopCut = 0;
  bool latch = false;
  bool heardSpeech = false;
  bool stopSilent = false;
  bool trimSilent = false;
};

// Preserve the recorder's two distinct gates. The ambient-relative gate decides
// whether quiet tails may be withheld; peak/8 only influences endpoint timing.
// The current frame is already included in floorAfter and peak. Requiring a
// previously seeded floor prevents the first ambient frame from latching speech.
inline constexpr AdaptiveVadDecision adaptiveVadDecision(
    int32_t level, int32_t floorBefore, int32_t floorAfter, int32_t peak,
    bool heardSpeech, AdaptiveVadConfig config = {}) {
  AdaptiveVadDecision result;
  result.trimCut = config.silenceFloor;
  if (2 * floorAfter > result.trimCut) result.trimCut = 2 * floorAfter;
  result.stopCut = result.trimCut;
  if (peak / 8 > result.stopCut) result.stopCut = peak / 8;
  result.latch = !heardSpeech && floorBefore >= 0 &&
                 level >= result.stopCut && level >= config.speechFloor;
  result.heardSpeech = heardSpeech || result.latch;
  result.stopSilent = result.heardSpeech && level < result.stopCut;
  result.trimSilent = result.heardSpeech && level < result.trimCut;
  return result;
}
} // namespace hw1::audio
