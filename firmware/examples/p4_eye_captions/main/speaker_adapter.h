#pragma once
#include "product.h"
#include <cstddef>
#include <cstdint>
// Optional bounded background labels. The model is never on the caption path;
// a full queue produces an explicit unknown label rather than blocking capture.
namespace captions_speaker {
void begin(size_t caption_reserve, size_t contiguous);
void submit(product::Receipt, const int16_t* pcm, size_t samples);
void poll();  // application-owner thread only; serial/storage stay out of worker
}  // namespace captions_speaker
