#pragma once
// The engine-facing part of HardwareOne's System_STTLocal.h: the control,
// progress, statistics and feature-prefix types quartznet_runtime.h uses. The
// broker that HardwareOne builds on top of these (sessions, warm-up, speaker
// labels) is application code; examples/p4_eye_captions/main/main.cpp is the
// minimal version of it.
#include <stddef.h>
#include <stdint.h>

// Input is 16 kHz mono signed int16 PCM. Cancellation is cooperative: the
// engine polls `cancelled` and returns only after all its work has stopped.
enum class STTLocalPhase : uint8_t { Loading, Frontend, Inference, Decoding };

struct STTLocalControl {
  void* context = nullptr;
  bool (*cancelled)(void*) = nullptr;
  void (*progress)(void*, STTLocalPhase) = nullptr;
};

struct STTLocalStats {
  uint32_t samples = 0;
  uint32_t featureFrames = 0;
  uint32_t outputFrames = 0;
  uint32_t modelBytes = 0;
  bool weightsReused = false;
  uint32_t loadMs = 0;
  uint32_t frontendMs = 0;
  uint32_t inferenceMs = 0;
  uint32_t decodeMs = 0;
  // Profiling detail (P4 runtime only; zero elsewhere).
  uint32_t frontendConditionUs = 0, frontendFftUs = 0, frontendMelUs = 0, frontendNormUs = 0;
  uint32_t quantizeUs = 0, inferenceYieldUs = 0;
  uint16_t inferenceBlocks = 0;      // blocking vTaskDelay(1) yields in this run
  uint32_t featureCachedFrames = 0;  // rows taken from a capture-time feature cache
  uint16_t slowStage[3] = {0xffff, 0xffff, 0xffff};  // three slowest model stages
  uint32_t slowStageUs[3] = {};
  bool lmUsed = false;  // decode used the language model (else greedy)
};

// Log-mel rows already computed during capture for the first `count` 10 ms
// frames of this exact PCM (hw1::stt::log_mel_frame, before CMVN). The
// runtime computes only the remaining rows. Ignored when count is 0 or
// exceeds the call's frames. Optional: pass nullptr to compute everything.
struct STTFeaturePrefix {
  const float* rows = nullptr;
  size_t count = 0;
};
