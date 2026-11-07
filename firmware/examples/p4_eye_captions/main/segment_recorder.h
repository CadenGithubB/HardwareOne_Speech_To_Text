#pragma once
#include "product.h"
#include "stt/stt_stream.h"
// Test-only: saves every final segment's 16 kHz PCM to the card with a JSONL index, so device
// microphone audio can be re-scored on the host bit-exactly. Off until "pcm save on". Never on the
// caption path: called after the caption (and gate) for a Final, before the work slot is completed.
// Files: /sd/STT PCM/b<boot>/s<stream sequence>.pcm (int16 LE mono) and index.jsonl in that folder.
namespace captions_pcm {
void setEnabled(bool on);
bool enabled();
void save(const hw1::stt::StreamWork& work, product::Receipt receipt, bool captioned);
}  // namespace captions_pcm
