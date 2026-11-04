#pragma once
// Portable, bounded PCM-to-work scheduler. Derived from HardwareOne's continuous
// pipeline: capture-time features, preemptible drafts and exact early finals.
// One producer, one transcription consumer and one optional feature consumer.
// All public methods serialize through caller-provided lock/unlock callbacks;
// never call inference, I/O or application callbacks while holding that lock.
#include "stt_segmenter.h"
#include "quartznet_frontend.h"
#include "../System_STTLocal.h"
#include "stt_stream_metrics.h"
namespace hw1::stt {
inline constexpr size_t kStreamSlots = 3, kStreamCaches = 2, kStreamText = 512;
enum class DraftPacing : uint8_t { Legacy, X2FastFirst };
struct StreamConfig {
  SegmenterConfig segmentation;
  size_t tail_samples = 0;  // full audio by default; 8000 = HardwareOne's 500 ms tail
  bool drafts = true, speculative = true;
  uint32_t draft_interval_ms = 1000;
  // X2FastFirst uses compute-scaled audio growth and resets for each phrase.
  // Set draft_interval_ms=0 to use that policy without an extra wall-clock floor.
  DraftPacing draft_pacing = DraftPacing::Legacy;
  // Experimental: caches start zero and only committed rows are dirtied.
  // Keep disabled until target qualification; does not change PCM ownership.
  bool clear_committed_features = false;
};
struct StreamBuffers {
  int16_t* capture = nullptr;
  int16_t* slots[kStreamSlots]{};
  int16_t* snapshot = nullptr;  // optional: no drafts/speculation without it
  size_t capacity = 0;
};
struct StreamLock {
  void* context = nullptr;
  void (*lock)(void*) = nullptr;
  void (*unlock)(void*) = nullptr;
  // Optional tagged synchronization pair; takes precedence over the legacy
  // pair. These have the same locking contract and must not invoke the engine.
  void (*tagged_lock)(void*, StreamOperation) = nullptr;
  void (*tagged_unlock)(void*, StreamOperation) = nullptr;
};
enum class StreamWorkKind : uint8_t { Final, Draft, Speculative };
struct StreamWork {
  StreamWorkKind kind = StreamWorkKind::Final;
  const int16_t* pcm = nullptr;
  size_t samples = 0, captured_samples = 0;
  uint64_t sequence = 0, start_sample = 0;
  uint32_t id = 0, closed_ms = 0;
  bool hard_limit = false, promoted = false;
  STTFeaturePrefix features;
  char promoted_text[kStreamText + 1]{};
  STTLocalStats promoted_stats;
};
struct StreamFeatureWork {
  int cache = -1;
  uint32_t generation = 0;
  uint64_t start = 0;
  size_t samples = 0, frame = 0;
  int16_t ring[512]{};  // private stable window; no reads racing the producer
};
struct StreamCounters {
  uint32_t dropped = 0, drafts = 0, canceled = 0, promotions = 0, feature_overruns = 0;
};
class StreamPipeline {
 public:
  bool begin(const StreamConfig&, const StreamBuffers&, StreamLock = {});
  bool push(const int16_t*, size_t, uint32_t now_ms);
  bool finish(uint32_t now_ms);  // seals/drains; no speculative promotion for session-end
  void cancel();                 // invalidates pending work; caller still joins active workers
  bool take(StreamWork&, uint32_t now_ms);
  bool cancelled(const StreamWork&);
  // Complete releases work ownership. Copy/emit final text before calling this.
  void complete(const StreamWork&, bool ok, const char* text, const STTLocalStats&, uint32_t elapsed_ms);
  bool enableFeatures(int16_t* ring, size_t ring_samples, float* first, float* second);
  bool featureTake(StreamFeatureWork&);
  void featureComplete(const StreamFeatureWork&, const float* row, bool ok);
  StreamCounters counters();
  uint16_t level();
  uint16_t noise();
  bool calibrated();
#if HW1_STT_STREAM_METRICS
  StreamDiagnostics diagnostics();
  // Small pages keep the device reporter's temporary storage bounded.
  StreamStateDiagnostics diagnosticsState();
  StreamMemoryDiagnostics memoryDiagnostics(StreamMemoryOperation);
#endif

 private:
  struct Guard {
    StreamPipeline& p;
    StreamOperation operation;
    explicit Guard(StreamPipeline& v, StreamOperation op) : p(v), operation(op) {
      if (p.lock_.tagged_lock) p.lock_.tagged_lock(p.lock_.context, op);
      else if (p.lock_.lock) p.lock_.lock(p.lock_.context);
#if HW1_STT_STREAM_METRICS
      p.operation_ = op;
#endif
    }
    ~Guard() {
      if (p.lock_.tagged_unlock) p.lock_.tagged_unlock(p.lock_.context, operation);
      else if (p.lock_.unlock) p.lock_.unlock(p.lock_.context);
    }
  };
  enum class SlotState : uint8_t { Free, Ready, Running };
  enum class CacheState : uint8_t { Free, Live, Attached, Retired };
  struct Slot {
    SlotState state = SlotState::Free;
    SpeechSegment segment;
    uint64_t sequence = 0;
    uint32_t closed = 0, spec = 0;
    int cache = -1;
  };
  struct Cache {
    float* rows = nullptr;
    CacheState state = CacheState::Free;
    uint32_t generation = 0;
    uint64_t start = 0;
    size_t length = 0, frames = 0, pins = 0;
    bool overrun = false;
  };
  StreamConfig config_;
  StreamBuffers buffers_;
  StreamLock lock_;
  Segmenter segmenter_;
  Slot slots_[kStreamSlots];
  Cache caches_[kStreamCaches];
  StreamCounters counters_;
  bool initialized_ = false, stopped_ = false, finished_ = false, busy_ = false;
  uint64_t next_sequence_ = 1, snapshot_sequence_ = 0;
  uint32_t serial_ = 0, active_id_ = 0, last_draft_ms_ = 0, last_draft_duration_ = 0, live_spec_ = 0,
           held_spec_ = 0;
  size_t last_draft_samples_ = 0;
  uint64_t last_draft_sequence_ = 0;
  uint64_t spec_start_ = 0;
  size_t spec_voiced_ = 0, spec_samples_ = 0;
  int active_slot_ = -1, active_cache_ = -1;
  char held_text_[kStreamText + 1]{};
  STTLocalStats held_stats_;
  int live_cache_ = -1;
  int16_t* ring_ = nullptr;
  size_t ring_size_ = 0;
  uint64_t ring_head_ = 0;
  uint32_t newId();
  void copyMemory(void*, const void*, size_t, StreamMemoryOperation);
  void clearMemory(void*, size_t, StreamMemoryOperation);
#if HW1_STT_STREAM_METRICS
  StreamOperation operation_ = StreamOperation::Status;
  StreamDiagnostics diagnostics_;
  void memoryMeasured(StreamMemoryOperation, size_t, uint64_t);
  StreamStateDiagnostics snapshotState() const;  // caller holds the stream lock
#endif
  void updateLive();
  void retire(int);
  void unpin(int);
  void queue(uint32_t);
  bool validSpec(uint32_t) const;
  bool pendingFinal() const;
  void prefix(StreamWork&, int);
  size_t inputSamples(const SpeechSegment&) const;
};
}  // namespace hw1::stt
