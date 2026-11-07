#pragma once
#include "product.h"
#include "stt/stt_stream.h"
#include <cstddef>
// Optional overlap flag per final caption: runs the small overlap gate on the segment's raw
// log-mel rows after the caption has been emitted. Never on the caption path, never changes text.
// Compiled only with -DHW1_OVERLAP_GATE=ON and CONFIG_CAPTIONS_OVERLAP_GATE; otherwise empty.
namespace captions_overlap {
void begin(size_t caption_reserve);
// Called on the application thread for a Final, before gPipeline.complete(work) frees its rows.
void run(product::Receipt, const hw1::stt::StreamWork& work);
// Test controls (USB "overlap on|off|log on|log off|status"): skip the gate at run time without
// unloading it; print each segment's raw int8 logits as an STT_OVERLAP line (on by default).
bool command(const char* cmd);
}  // namespace captions_overlap
