#pragma once
#include <cstddef>
#include <cstdint>
#include "transcript.h"
#include "stt/stt_lm.h"

// Single owner: app_main, between inference calls. No serial/storage work in
// microphone callback or model worker. Raw captions remain independent of saving.
namespace product {
struct Receipt {uint32_t note=0,sequence=0;};
Receipt receipt();
void speaker(Receipt,int8_t label);
// Overlap gate flag for a final caption (metadata beside the speaker label; caption text unchanged).
void overlap(Receipt,bool flag,float fraction,uint32_t frames);
// Test/diagnostic commands owned by other modules: the hook sees each USB command first and returns
// true when it handled it. reply() emits a normal STT_EVENT message. bootNumber(): persistent boot count.
void setCommandHook(bool (*hook)(const char* command));
void reply(const char* text, bool ok = true);
uint64_t bootNumber();
void platformBegin();
void begin();
void poll();
const hw1::stt::lm::CustomWords* customWords();
void caption(const char* raw, uint64_t startSample, uint64_t endSample, bool forcedBoundary,
             uint32_t droppedPhrases);
float lmStrength();
void draft(const char* raw);
void clearDraft();
void status(const char* state, const char* detail = "");
}
