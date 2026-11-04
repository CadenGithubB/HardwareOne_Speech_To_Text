#pragma once
// Bounded value-only telemetry. No allocation, logging or application callbacks.
#include <cstddef>
#include <cstdint>
#include <limits>

#ifndef HW1_STT_STREAM_METRICS
#define HW1_STT_STREAM_METRICS 0
#endif

namespace hw1::stt {
enum class StreamOperation : uint8_t {
  Push, Take, Complete, Cancel, Finish, FeatureTake, FeatureComplete, EnableFeatures, Status, Count
};
enum class StreamMemoryOperation : uint8_t {
  QueueCopy, SnapshotCopy, CacheClear, SlotClear, SnapshotClear, CancelClear,
  FeatureWindow, FeatureRow, StartupClear, Padding, Count
};
inline constexpr size_t kStreamOperations = size_t(StreamOperation::Count);
inline constexpr size_t kStreamMemoryOperations = size_t(StreamMemoryOperation::Count);
// Upper inclusive microsecond bounds; the last bucket is unbounded.
inline constexpr uint32_t kStreamTimeBounds[] = {
  1, 10, 50, 100, 250, 500, 1000, 2000, 4000, 8000, 16000
};
inline constexpr size_t kStreamTimeBuckets = 12;
struct StreamTimeHistogram {
  uint64_t count = 0, total_us = 0, max_us = 0;
  uint32_t buckets[kStreamTimeBuckets]{};
  bool saturated = false;
  void add(uint64_t us, uint32_t bin_scale_us = 1) {
    if (!bin_scale_us) bin_scale_us = 1;
    ++count;
    total_us += us;
    if (us > max_us) max_us = us;
    size_t bin = 0;
    while (bin + 1 < kStreamTimeBuckets && us > uint64_t(kStreamTimeBounds[bin]) * bin_scale_us) ++bin;
    if (buckets[bin] == std::numeric_limits<uint32_t>::max()) saturated = true;
    else ++buckets[bin];
  }
};
struct StreamMemoryMetric {
  StreamTimeHistogram time;
  uint64_t bytes = 0;
};
struct StreamStateDiagnostics {
  uint64_t accepted_samples = 0, cache_unavailable_checks = 0;
  uint32_t ready_high_water = 0;
  uint32_t ready = 0, running = 0, free_slots = 0, free_caches = 0, retired_caches = 0;
  uint32_t frames[2]{}, pins[2]{};
  uint32_t feature_capacity = 0;
};
struct StreamDiagnostics : StreamStateDiagnostics {
  StreamMemoryMetric memory[kStreamMemoryOperations];
  uint64_t bytes_by_caller[kStreamOperations][kStreamMemoryOperations]{};
};
struct StreamMemoryDiagnostics {
  StreamMemoryMetric metric;
  uint64_t bytes_by_caller[kStreamOperations]{};
};
}  // namespace hw1::stt
