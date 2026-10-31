#pragma once
#include <cstddef>
#include <cstdint>
#include "transcript.h"
#include "stt/stt_lm.h"

// Single owner: app_main, between inference calls. No serial/storage work in
// microphone callback or model worker. Raw captions remain independent of saving.
namespace product {
void platformBegin();
void begin();
void poll();
const hw1::stt::lm::CustomWords* customWords();
void caption(const char* raw, uint64_t startSample, uint64_t endSample, bool forcedBoundary,
             uint32_t droppedPhrases);
void status(const char* state, const char* detail = "");
}
