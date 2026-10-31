#include "stt_stream.h"
#include <algorithm>
#include <cstring>
#include <cstdio>
#include <limits>
namespace hw1::stt {
bool StreamPipeline::begin(const StreamConfig& c, const StreamBuffers& b, StreamLock l) {
  if (initialized_ || !b.capture || b.capacity < 320 || (bool(l.lock) != bool(l.unlock))) return false;
  for (auto* p : b.slots)
    if (!p) return false;
  if (c.tail_samples >= c.segmentation.end_silence_samples ||
      !segmenter_.reset(b.capture, b.capacity, c.segmentation))
    return false;
  config_ = c;
  buffers_ = b;
  lock_ = l;
  initialized_ = true;
  return true;
}
uint32_t StreamPipeline::newId() {
  if (++serial_ == 0) ++serial_;
  return serial_;
}
void StreamPipeline::retire(int idx) {
  if (idx < 0) return;
  auto& c = caches_[idx];
  c.state = CacheState::Retired;
  if (!c.pins) {
    std::memset(c.rows, 0, buffers_.capacity / 160 * 64 * sizeof(float));
    c.state = CacheState::Free;
    ++c.generation;
    c.frames = 0;
  }
}
void StreamPipeline::unpin(int idx) {
  if (idx < 0) return;
  auto& c = caches_[idx];
  if (c.pins) --c.pins;
  if (c.state == CacheState::Retired && !c.pins) retire(idx);
}
bool StreamPipeline::pendingFinal() const {
  for (const auto& s : slots_)
    if (s.state == SlotState::Ready) return true;
  return false;
}
bool StreamPipeline::validSpec(uint32_t id) const {
  if (!id) return false;
  if (live_spec_ == id) return true;
  for (const auto& s : slots_)
    if (s.state != SlotState::Free && s.spec == id) return true;
  return false;
}
size_t StreamPipeline::inputSamples(const SpeechSegment& s) const {
  size_t n = s.samples;
  if (config_.tail_samples && s.end != SegmentEnd::HardLimit && s.voiced_end_samples)
    n = std::min(n, s.voiced_end_samples + config_.tail_samples);
  return std::max<size_t>(320, n);
}
void StreamPipeline::prefix(StreamWork& w, int idx) {
  if (idx < 0 || w.samples < 320) return;
  auto& c = caches_[idx];
  if (c.start != w.start_sample) return;
  w.features = {c.rows, std::min(c.frames, w.samples / 160)};
  if (w.features.count) {
    ++c.pins;
    active_cache_ = idx;
  }
}
void StreamPipeline::updateLive() {
  uint64_t start = 0;
  size_t len = 0;
  const bool live = !finished_ && segmenter_.live_view(&start, &len);
  if (live_cache_ >= 0 && (!live || caches_[live_cache_].start != start)) {
    retire(live_cache_);
    live_cache_ = -1;
  }
  if (live && ring_) {
    if (live_cache_ < 0)
      for (size_t i = 0; i < kStreamCaches; ++i)
        if (caches_[i].state == CacheState::Free) {
          live_cache_ = int(i);
          auto& c = caches_[i];
          c.state = CacheState::Live;
          c.start = start;
          c.length = len;
          c.frames = 0;
          c.overrun = false;
          ++c.generation;
          break;
        }
    if (live_cache_ >= 0) caches_[live_cache_].length = len;
  }
  uint64_t ss = 0;
  size_t ve = 0, n = 0;
  const bool speculate = live && config_.speculative && config_.tail_samples && buffers_.snapshot &&
                         segmenter_.speculation(config_.tail_samples, &ss, &ve, &n);
  if (!speculate) {
    live_spec_ = 0;
    return;
  }
  if (!live_spec_ || spec_start_ != ss || spec_voiced_ != ve) {
    live_spec_ = newId();
    spec_start_ = ss;
    spec_voiced_ = ve;
    spec_samples_ = n;
  }
}
void StreamPipeline::queue(uint32_t now) {
  const auto* s = segmenter_.segment();
  if (!s) return;
  // Count dropped phrases in sequence space; a missing result never relabels
  // a later draft or speaker as if it belonged to that dropped phrase.
  Slot* slot = nullptr;
  for (auto& candidate : slots_)
    if (candidate.state == SlotState::Free) {
      slot = &candidate;
      break;
    }
  if (next_sequence_ == std::numeric_limits<uint64_t>::max()) {
    stopped_ = true;
    return;
  }
  const auto sequence = next_sequence_++;
  if (!slot) {
    ++counters_.dropped;
    if (live_cache_ >= 0) retire(live_cache_);
    live_cache_ = -1;
    live_spec_ = 0;
    segmenter_.release();
    return;
  }
  const size_t idx = size_t(slot - slots_);
  std::memcpy(buffers_.slots[idx], s->pcm, s->samples * sizeof(int16_t));
  if (s->samples < 320)
    std::memset(buffers_.slots[idx] + s->samples, 0, (320 - s->samples) * sizeof(int16_t));
  slot->segment = *s;
  slot->segment.pcm = buffers_.slots[idx];
  slot->sequence = sequence;
  slot->closed = now;
  slot->cache = -1;
  slot->spec = live_spec_ && s->end == SegmentEnd::Pause && s->start_sample == spec_start_ &&
                       s->voiced_end_samples == spec_voiced_ && spec_samples_ <= s->samples
                   ? live_spec_
                   : 0;
  if (live_cache_ >= 0) {
    auto& c = caches_[live_cache_];
    if (c.start == s->start_sample && s->samples >= 320) {
      c.state = CacheState::Attached;
      slot->cache = live_cache_;
    } else
      retire(live_cache_);
    live_cache_ = -1;
  }
  slot->state = SlotState::Ready;
  live_spec_ = 0;
  segmenter_.release();
}
bool StreamPipeline::push(const int16_t* pcm, size_t count, uint32_t now) {
  Guard guard(lock_);
  if (!initialized_ || stopped_ || finished_ || (!pcm && count)) return false;
  size_t offset = 0;
  while (offset < count) {
    const size_t n = std::min<size_t>(160, count - offset);
    const auto start = segmenter_.samples_seen();
    if (ring_)
      for (size_t i = 0; i < n; ++i) ring_[(start + i) & (ring_size_ - 1)] = pcm[offset + i];
    ring_head_ = start + n;
    const auto fed = segmenter_.push(pcm + offset, n);
    offset += fed.consumed;
    if (fed.status == SegmentStatus::Ready)
      queue(now);
    else if (fed.status != SegmentStatus::Ok || !fed.consumed) {
      stopped_ = true;
      return false;
    }
    updateLive();
    if (stopped_) return false;
  }
  return true;
}
bool StreamPipeline::finish(uint32_t now) {
  Guard guard(lock_);
  if (!initialized_ || stopped_ || finished_) return false;
  finished_ = true;
  live_spec_ = 0;
  const auto result = segmenter_.finish();
  if (result == SegmentStatus::Ready)
    queue(now);
  else if (result != SegmentStatus::Finished)
    return false;
  updateLive();
  return true;
}
void StreamPipeline::cancel() {
  Guard guard(lock_);
  stopped_ = true;
  live_spec_ = held_spec_ = 0;
  std::memset(held_text_, 0, sizeof(held_text_));
  for (auto& s : slots_)
    if (s.state == SlotState::Ready) {
      retire(s.cache);
      std::memset(const_cast<int16_t*>(s.segment.pcm), 0, s.segment.samples * sizeof(int16_t));
      s.state = SlotState::Free;
    }
  if (live_cache_ >= 0) retire(live_cache_);
  live_cache_ = -1;
}
bool StreamPipeline::take(StreamWork& w, uint32_t now) {
  Guard guard(lock_);
  if (!initialized_ || stopped_ || busy_) return false;
  w = {};
  active_slot_ = active_cache_ = -1;
  Slot* slot = nullptr;
  for (auto& s : slots_)
    if (s.state == SlotState::Ready && (!slot || s.sequence < slot->sequence)) slot = &s;
  if (slot) {
    active_slot_ = int(slot - slots_);
    slot->state = SlotState::Running;
    w.kind = StreamWorkKind::Final;
    w.pcm = slot->segment.pcm;
    w.samples = inputSamples(slot->segment);
    w.captured_samples = slot->segment.samples;
    w.sequence = slot->sequence;
    w.start_sample = slot->segment.start_sample;
    w.closed_ms = slot->closed;
    w.hard_limit = slot->segment.end == SegmentEnd::HardLimit;
    prefix(w, slot->cache);
    if (slot->spec && held_spec_ == slot->spec) {
      w.promoted = true;
      std::memcpy(w.promoted_text, held_text_, sizeof(w.promoted_text));
      w.promoted_stats = held_stats_;
      ++counters_.promotions;
    }
  } else {
    if (finished_ || !buffers_.snapshot) return false;
    updateLive();
    if (live_spec_ && held_spec_ == live_spec_) return false;
    const int16_t* pcm = nullptr;
    size_t n = 0;
    uint64_t start = 0;
    size_t liveLen = 0;
    if (!segmenter_.in_progress(&pcm, &n) || !segmenter_.live_view(&start, &liveLen)) return false;
    if (live_spec_) {
      w.kind = StreamWorkKind::Speculative;
      n = spec_samples_;
      w.id = live_spec_;
    } else {
      const size_t pace = std::max<size_t>(kSampleRate, size_t(last_draft_duration_) * 16);
      const size_t previous = last_draft_sequence_ == next_sequence_ ? last_draft_samples_ : 0;
      if (!config_.drafts || n < previous + pace ||
          uint32_t(now - last_draft_ms_) < config_.draft_interval_ms)
        return false;
      w.kind = StreamWorkKind::Draft;
      last_draft_ms_ = now;
      last_draft_samples_ = n;
      last_draft_sequence_ = next_sequence_;
    }
    std::memcpy(buffers_.snapshot, pcm, n * sizeof(int16_t));
    w.pcm = buffers_.snapshot;
    w.samples = n;
    w.captured_samples = liveLen;
    w.sequence = next_sequence_;
    w.start_sample = start;
    prefix(w, live_cache_);
    snapshot_sequence_ = next_sequence_;
  }
  if (!w.id) w.id = newId();
  active_id_ = w.id;
  busy_ = true;
  return true;
}
bool StreamPipeline::cancelled(const StreamWork& w) {
  Guard guard(lock_);
  if (stopped_ || !busy_ || w.id != active_id_) return true;
  if (w.kind == StreamWorkKind::Final) return false;
  if (w.kind == StreamWorkKind::Speculative) return !validSpec(w.id);
  return finished_ || pendingFinal() || live_spec_ || snapshot_sequence_ != next_sequence_;
}
void StreamPipeline::complete(const StreamWork& w, bool ok, const char* text, const STTLocalStats& stats,
                              uint32_t elapsed) {
  Guard guard(lock_);
  if (!busy_ || w.id != active_id_) return;
  bool valid = !stopped_;
  if (w.kind == StreamWorkKind::Speculative) valid = valid && validSpec(w.id);
  if (w.kind == StreamWorkKind::Draft)
    valid = valid && !finished_ && !pendingFinal() && !live_spec_ && snapshot_sequence_ == next_sequence_;
  if (w.kind == StreamWorkKind::Speculative && ok && valid) {
    held_spec_ = w.id;
    std::snprintf(held_text_, sizeof(held_text_), "%s", text ? text : "");
    held_stats_ = stats;
  }
  if (w.kind == StreamWorkKind::Draft) {
    if (ok && valid)
      ++counters_.drafts;
    else
      ++counters_.canceled;
    last_draft_duration_ = elapsed;
  }
  unpin(active_cache_);
  active_cache_ = -1;
  if (active_slot_ >= 0) {
    auto& s = slots_[active_slot_];
    retire(s.cache);
    std::memset(buffers_.slots[active_slot_], 0, std::max<size_t>(320, s.segment.samples) * sizeof(int16_t));
    if (held_spec_ == s.spec) {
      held_spec_ = 0;
      std::memset(held_text_, 0, sizeof(held_text_));
    }
    s.state = SlotState::Free;
  } else {
    std::memset(buffers_.snapshot, 0, w.samples * sizeof(int16_t));
  }
  busy_ = false;
  active_slot_ = -1;
  if (held_spec_ && !validSpec(held_spec_)) {
    held_spec_ = 0;
    std::memset(held_text_, 0, sizeof(held_text_));
  }
}
bool StreamPipeline::enableFeatures(int16_t* ring, size_t size, float* first, float* second) {
  Guard guard(lock_);
  if (!initialized_ || ring_ || !ring || size < 512 || (size & (size - 1)) || !first || !second ||
      segmenter_.samples_seen())
    return false;
  ring_ = ring;
  ring_size_ = size;
  caches_[0].rows = first;
  caches_[1].rows = second;
  std::memset(ring, 0, size * sizeof(int16_t));
  std::memset(first, 0, buffers_.capacity / 160 * 64 * sizeof(float));
  std::memset(second, 0, buffers_.capacity / 160 * 64 * sizeof(float));
  return true;
}
bool StreamPipeline::featureTake(StreamFeatureWork& w) {
  Guard guard(lock_);
  if (stopped_ || live_cache_ < 0) return false;
  auto& c = caches_[live_cache_];
  if (c.state != CacheState::Live || c.overrun || c.length < 320 || c.frames >= c.length / 160) return false;
  const size_t frame = c.frames;
  const uint64_t low = c.start + (frame * 160 > 161 ? frame * 160 - 161 : 0),
                 high = c.start + std::max<size_t>(161, (frame + 1) * 160);
  if (high > ring_head_) return false;
  if (ring_head_ - low > ring_size_) {
    c.overrun = true;
    ++counters_.feature_overruns;
    return false;
  }
  w.cache = live_cache_;
  w.generation = c.generation;
  w.start = c.start;
  w.samples = c.length;
  w.frame = frame;
  for (uint64_t i = low; i < high; ++i) w.ring[i & 511] = ring_[i & (ring_size_ - 1)];
  return true;
}
void StreamPipeline::featureComplete(const StreamFeatureWork& w, const float* row, bool ok) {
  Guard guard(lock_);
  if (w.cache < 0 || size_t(w.cache) >= kStreamCaches) return;
  auto& c = caches_[w.cache];
  if (c.generation != w.generation || c.state != CacheState::Live || c.frames != w.frame) return;
  if (!ok || !row) {
    c.overrun = true;
    ++counters_.feature_overruns;
    return;
  }
  std::memcpy(c.rows + c.frames * 64, row, 64 * sizeof(float));
  ++c.frames;
}
StreamCounters StreamPipeline::counters() {
  Guard guard(lock_);
  return counters_;
}
uint16_t StreamPipeline::level() {
  Guard guard(lock_);
  return segmenter_.current_rms();
}
uint16_t StreamPipeline::noise() {
  Guard guard(lock_);
  return segmenter_.noise_rms();
}
bool StreamPipeline::calibrated() {
  Guard guard(lock_);
  return segmenter_.calibrated();
}
}  // namespace hw1::stt
