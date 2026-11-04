#include "capture_diagnostics.h"
#if HW1_STT_STREAM_METRICS
#include <atomic>
#include <cstdio>
#include "esp_attr.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "mbedtls/sha256.h"
#include "freertos/task.h"
namespace captions_perf {
namespace {
using namespace hw1::stt;
struct LockMetric { StreamTimeHistogram wait, hold; };
struct CaptureMetric {
  StreamTimeHistogram read, interval, push, read_to_push;
  uint64_t reads = 0, bytes = 0, timeouts = 0, errors = 0, short_reads = 0, odd_reads = 0, rejected = 0;
};
SemaphoreHandle_t mutex = nullptr;
StreamPipeline* pipeline = nullptr;
LockMetric locks[kStreamOperations];
uint64_t held_started = 0, previous_read = 0, warm_bytes = 0;
size_t expected_read_bytes = 0;
StreamOperation held_operation = StreamOperation::Status;
CaptureMetric capture;
portMUX_TYPE capture_mux = portMUX_INITIALIZER_UNLOCKED;
DRAM_ATTR std::atomic<uint32_t> dma_bytes{0}, overflow_count{0}, overflow_bytes{0};
std::atomic<bool> requested{false};
struct Level { uint32_t samples = 0, uptime_ms = 0; uint16_t rms = 0, noise = 0; };
Level levels[8];
uint32_t level_write = 0, level_read = 0, level_dropped = 0;
static_assert(std::atomic<uint32_t>::is_always_lock_free, "ISR counters must be lock-free");
static_assert(sizeof(StreamDiagnostics) + sizeof(locks) + sizeof(CaptureMetric) * 2 + sizeof(levels) + 16 + 128 <= 4096,
              "Telemetry plus largest reporting page must stay within the 4 KiB budget");
constexpr const char* operations[] = {"push", "take", "complete", "cancel", "finish", "feature_take", "feature_complete", "enable_features", "status"};
constexpr const char* memory_operations[] = {"queue_copy", "snapshot_copy", "cache_clear", "slot_clear", "snapshot_clear", "cancel_clear", "feature_window", "feature_row", "startup_clear", "padding"};
uint64_t now() { return uint64_t(esp_timer_get_time()); }
bool IRAM_ATTR received(i2s_chan_handle_t, i2s_event_data_t* event, void*) {
  if (event) dma_bytes.fetch_add(uint32_t(event->size), std::memory_order_relaxed);
  return false;
}
bool IRAM_ATTR overflow(i2s_chan_handle_t, i2s_event_data_t* event, void*) {
  overflow_count.fetch_add(1, std::memory_order_relaxed);
  if (event) overflow_bytes.fetch_add(uint32_t(event->size), std::memory_order_relaxed);
  return false;
}
void histogram(const StreamTimeHistogram& h, uint32_t scale_us = 1) {
  printf("{\"count\":%llu,\"sum_us\":%llu,\"max_us\":%llu,\"saturated\":%s,\"scale_us\":%u,\"bins\":[",
         (unsigned long long)h.count, (unsigned long long)h.total_us,
         (unsigned long long)h.max_us, h.saturated ? "true" : "false", unsigned(scale_us));
  for (size_t i = 0; i < kStreamTimeBuckets; ++i) printf("%s%u", i ? "," : "", unsigned(h.buckets[i]));
  printf("]}");
}
void dumpLock(size_t i) {
  xSemaphoreTake(mutex, portMAX_DELAY);
  const LockMetric page = locks[i];
  xSemaphoreGive(mutex);
  printf("STT_PERF {\"type\":\"lock\",\"op\":\"%s\",\"wait\":", operations[i]);
  histogram(page.wait); printf(",\"hold\":"); histogram(page.hold); printf("}\n");
}
void dumpMemory(size_t i) {
  const auto page = pipeline->memoryDiagnostics(StreamMemoryOperation(i));
  printf("STT_PERF {\"type\":\"memory\",\"op\":\"%s\",\"bytes\":%llu,\"time\":",
         memory_operations[i], (unsigned long long)page.metric.bytes);
  histogram(page.metric.time); printf(",\"by_caller\":[");
  for (size_t j = 0; j < kStreamOperations; ++j)
    printf("%s%llu", j ? "," : "", (unsigned long long)page.bytes_by_caller[j]);
  printf("]}\n");
}
void dumpCapture() {
  portENTER_CRITICAL(&capture_mux);
  const CaptureMetric page = capture;
  portEXIT_CRITICAL(&capture_mux);
  printf("STT_PERF {\"type\":\"capture\",\"reads\":%llu,\"bytes\":%llu,\"warm_bytes\":%llu,\"timeouts\":%llu,\"errors\":%llu,\"short_reads\":%llu,\"odd_reads\":%llu,\"rejected\":%llu,\"dma_bytes_u32\":%u,\"overflow_count_u32\":%u,\"overflow_bytes_u32\":%u,\"read\":",
         (unsigned long long)page.reads, (unsigned long long)page.bytes, (unsigned long long)warm_bytes,
         (unsigned long long)page.timeouts, (unsigned long long)page.errors,
         (unsigned long long)page.short_reads, (unsigned long long)page.odd_reads,
         (unsigned long long)page.rejected, unsigned(dma_bytes.load(std::memory_order_relaxed)),
         unsigned(overflow_count.load(std::memory_order_relaxed)), unsigned(overflow_bytes.load(std::memory_order_relaxed)));
  histogram(page.read, 64); printf(",\"interval\":"); histogram(page.interval, 64);
  printf(",\"push\":"); histogram(page.push); printf(",\"read_to_push\":"); histogram(page.read_to_push); printf("}\n");
}
void dumpState() {
  const auto s = pipeline->diagnosticsState();
  const auto c = pipeline->counters();
  printf("STT_PERF {\"type\":\"state\",\"accepted_samples\":%llu,\"cache_unavailable_checks\":%llu,\"ready_high_water\":%u,\"ready\":%u,\"running\":%u,\"free_slots\":%u,\"free_caches\":%u,\"retired_caches\":%u,\"feature_capacity\":%u,\"frames\":[%u,%u],\"pins\":[%u,%u],\"drops\":%u,\"feature_overruns\":%u,\"drafts\":%u,\"canceled\":%u,\"promotions\":%u,\"psram_free\":%u,\"internal_free\":%u,\"internal_largest\":%u,\"owner_stack_min_bytes\":%u,\"psram_largest\":%u,\"psram_min_boot\":%u,\"internal_min_boot\":%u}\n",
         (unsigned long long)s.accepted_samples, (unsigned long long)s.cache_unavailable_checks,
         unsigned(s.ready_high_water), unsigned(s.ready), unsigned(s.running), unsigned(s.free_slots),
         unsigned(s.free_caches), unsigned(s.retired_caches), unsigned(s.feature_capacity), unsigned(s.frames[0]), unsigned(s.frames[1]),
         unsigned(s.pins[0]), unsigned(s.pins[1]), unsigned(c.dropped), unsigned(c.feature_overruns),
         unsigned(c.drafts), unsigned(c.canceled), unsigned(c.promotions),
         unsigned(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)),
         unsigned(heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)),
         unsigned(heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)),
         unsigned(uxTaskGetStackHighWaterMark(nullptr)),
         unsigned(heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM)),
         unsigned(heap_caps_get_minimum_free_size(MALLOC_CAP_SPIRAM)),
         unsigned(heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)));
}
}
void lock(void*, hw1::stt::StreamOperation operation) {
  const uint64_t started = now();
  xSemaphoreTake(mutex, portMAX_DELAY);
  const uint64_t acquired = now();
  locks[size_t(operation)].wait.add(acquired - started);
  held_started = acquired;
  held_operation = operation;
}
void unlock(void*, hw1::stt::StreamOperation operation) {
  configASSERT(operation == held_operation);
  locks[size_t(operation)].hold.add(now() - held_started);
  xSemaphoreGive(mutex);
}
void begin(SemaphoreHandle_t m, hw1::stt::StreamPipeline* p) {
  mutex = m; pipeline = p;
  // Startup-only positive overhead control, before any other stream users exist.
  const uint64_t raw_started = now();
  for (unsigned i = 0; i < 200; ++i) { xSemaphoreTake(mutex, portMAX_DELAY); xSemaphoreGive(mutex); }
  const uint64_t raw_elapsed = now() - raw_started;
  const uint64_t started = now();
  for (unsigned i = 0; i < 200; ++i) { lock(nullptr, StreamOperation::Status); unlock(nullptr, StreamOperation::Status); }
  const uint64_t elapsed = now() - started;
  printf("STT_PERF {\"type\":\"control\",\"iterations\":200,\"raw_wall_us\":%llu,\"wall_us\":%llu,\"hold\":", (unsigned long long)raw_elapsed, (unsigned long long)elapsed);
  histogram(locks[size_t(StreamOperation::Status)].hold); printf("}\n");
  locks[size_t(StreamOperation::Status)] = {};
}
bool attachMic(i2s_chan_handle_t channel, size_t read_bytes, size_t descriptors) {
  expected_read_bytes = read_bytes;
  i2s_chan_info_t info = {};
  if (i2s_channel_get_info(channel, &info) != ESP_OK) return false;
  printf("STT_PERF {\"type\":\"i2s_config\",\"read_bytes\":%u,\"dma_descriptors\":%u,\"driver_queue_slots\":%u,\"total_dma_bytes\":%u}\n",
         unsigned(read_bytes), unsigned(descriptors), unsigned(descriptors ? descriptors - 1 : 0), unsigned(info.total_dma_buf_size));
  i2s_event_callbacks_t callbacks = {};
  callbacks.on_recv = received;
  callbacks.on_recv_q_ovf = overflow;
  return i2s_channel_register_event_callback(channel, &callbacks, nullptr) == ESP_OK;
}
void warmBytes(size_t bytes) { warm_bytes += bytes; }
void captureRead(uint64_t started, uint64_t read, uint64_t push_started, uint64_t done,
                 size_t bytes, esp_err_t error, bool accepted) {
  // All fields below have one capture writer; the short mux protects reporting.
  portENTER_CRITICAL(&capture_mux);
  ++capture.reads; capture.bytes += bytes;
  capture.timeouts += error == ESP_ERR_TIMEOUT;
  capture.errors += error != ESP_OK && error != ESP_ERR_TIMEOUT;
  capture.short_reads += bytes != expected_read_bytes;
  capture.odd_reads += (bytes & 1) != 0;
  capture.rejected += !accepted;
  capture.read.add(read - started, 64);
  if (previous_read) capture.interval.add(started - previous_read, 64);
  if (bytes) { capture.push.add(done - push_started); capture.read_to_push.add(done - read); }
  previous_read = started;
  portEXIT_CRITICAL(&capture_mux);
}
void modelIdentity(const char* name, const void* blob, size_t bytes) {
  unsigned char digest[32];
  if (mbedtls_sha256(static_cast<const unsigned char*>(blob), bytes, digest, 0) != 0) return;
  char hex[65];
  for (size_t i = 0; i < sizeof(digest); ++i) std::snprintf(hex + i * 2, 3, "%02x", digest[i]);
  printf("STT_PERF {\"type\":\"model\",\"name\":\"%s\",\"bytes\":%u,\"sha256\":\"%s\"}\n", name, unsigned(bytes), hex);
}
void level(uint32_t samples, uint32_t uptime_ms, uint16_t rms, uint16_t noise) {
  portENTER_CRITICAL(&capture_mux);
  if (level_write - level_read == 8) ++level_dropped;
  else { levels[level_write & 7] = {samples, uptime_ms, rms, noise}; ++level_write; }
  portEXIT_CRITICAL(&capture_mux);
}
void request() { requested.store(true, std::memory_order_relaxed); }
void poll() {
  for (unsigned i = 0; i < 8; ++i) {
    Level page; bool available = false;
    portENTER_CRITICAL(&capture_mux);
    if (level_read != level_write) { page = levels[level_read & 7]; ++level_read; available = true; }
    portEXIT_CRITICAL(&capture_mux);
    if (!available) break;
    printf("STT_PERF {\"type\":\"level\",\"sample_u32\":%u,\"uptime_ms\":%u,\"rms\":%u,\"noise\":%u}\n", unsigned(page.samples), unsigned(page.uptime_ms), unsigned(page.rms), unsigned(page.noise));
  }
  if (!requested.exchange(false, std::memory_order_relaxed) || !pipeline) return;
  const uint64_t started = now();
  printf("STT_PERF {\"type\":\"begin\",\"schema\":1,\"uptime_us\":%llu,\"telemetry_bytes\":%u,\"largest_page_bytes\":%u,\"bin_upper_us\":[",
         (unsigned long long)started, unsigned(sizeof(StreamDiagnostics) + sizeof(locks) + sizeof(capture) + sizeof(levels) + 16 + 128), unsigned(sizeof(CaptureMetric)));
  for (size_t i = 0; i + 1 < kStreamTimeBuckets; ++i) printf("%s%u", i ? "," : "", unsigned(kStreamTimeBounds[i]));
  printf(",null]}\n");
  for (size_t i = 0; i < kStreamOperations; ++i) dumpLock(i);
  for (size_t i = 0; i < kStreamMemoryOperations; ++i) dumpMemory(i);
  dumpCapture(); dumpState();
  portENTER_CRITICAL(&capture_mux);
  const uint32_t lost_levels = level_dropped;
  portEXIT_CRITICAL(&capture_mux);
  printf("STT_PERF {\"type\":\"level_queue\",\"dropped\":%u}\n", unsigned(lost_levels));
  printf("STT_PERF {\"type\":\"end\",\"uptime_us\":%llu,\"report_us\":%llu}\n", (unsigned long long)now(), (unsigned long long)(now() - started));
}
}
#endif
