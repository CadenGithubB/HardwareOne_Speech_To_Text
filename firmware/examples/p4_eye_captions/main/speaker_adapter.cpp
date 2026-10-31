#include "speaker_adapter.h"
#if HW1_STT_SPEAKER_LABELS
#include "stt/speaker_model.h"
#include "stt/speaker_cluster.h"
#include "stt/stt_dl_metadata.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <new>
#include <sys/stat.h>
namespace captions_speaker {
namespace {
constexpr int kJobs = 4;
struct Job {
  product::Receipt receipt;
  size_t samples = 0, phrase_samples = 0;
  uint32_t submitted = 0;
};
struct Result {
  product::Receipt receipt;
  int8_t speaker = -1;
  uint32_t elapsed = 0, lag = 0;
};
struct State {
  hw1::stt::speaker::Model model;
  hw1::stt::speaker::Clusters clusters;
  hw1::stt::speaker::ClusterConfig config;
  uint8_t* blob = nullptr;
  float* centroids = nullptr;
  float* embedding = nullptr;
  int16_t* pcm = nullptr;
  size_t span = 0;
  Job jobs[kJobs];
  QueueHandle_t ready = nullptr, free = nullptr, results = nullptr;
  uint32_t cluster_note = 0;
  ~State() {
    model.reset();
    heap_caps_free(pcm);
    heap_caps_free(embedding);
    heap_caps_free(centroids);
    heap_caps_free(blob);
    if (ready) vQueueDelete(ready);
    if (free) vQueueDelete(free);
    if (results) vQueueDelete(results);
  }
};
State* state = nullptr;
uint32_t milliseconds() { return uint32_t(esp_timer_get_time() / 1000); }
void worker(void* pointer) {
  auto& s = *static_cast<State*>(pointer);
  for (;;) {
    uint8_t slot = 0;
    if (xQueueReceive(s.ready, &slot, portMAX_DELAY) != pdTRUE) continue;
    const Job job = s.jobs[slot];
    const uint32_t started = milliseconds();
    if (s.cluster_note != job.receipt.note) {
      s.clusters.reset(s.centroids, s.model.info().dim, s.config);
      s.cluster_note = job.receipt.note;
    }
    int8_t label = -1;
    if (s.model.embed(s.pcm + size_t(slot) * s.span, job.samples, s.embedding)) {
      const auto assignment = s.clusters.assign(s.embedding, job.phrase_samples);
      label = assignment.speaker;
    }
    Result result{job.receipt, label, milliseconds() - started, milliseconds() - job.submitted};
    if (xQueueSend(s.results, &result, 0) != pdTRUE)
      ESP_LOGW("captions", "Speaker result queue full; result omitted");
    std::memset(s.pcm + size_t(slot) * s.span, 0, job.samples * sizeof(int16_t));
    xQueueSend(s.free, &slot, 0);
    vTaskDelay(1);
  }
}
}  // namespace
void begin(size_t reserve, size_t contiguous) {
  if (state) return;
  constexpr const char* path = "/sd/STT Models/speaker.spk";
  struct stat info{};
  if (stat(path, &info) || info.st_size < 192 || info.st_size > (16 << 20)) {
    ESP_LOGW("captions", "Optional speaker.spk missing or invalid size");
    return;
  }
  const size_t bytes = size_t(info.st_size);
  if (heap_caps_get_free_size(MALLOC_CAP_SPIRAM) < bytes + (1u << 20) + reserve) {
    ESP_LOGW("captions", "Speaker labels skipped: preserving caption reserve");
    return;
  }
  void* memory = heap_caps_malloc(sizeof(State), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (!memory) return;
  auto* s = new (memory) State;
  s->blob = static_cast<uint8_t*>(heap_caps_aligned_alloc(16, bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  FILE* f = s->blob ? fopen(path, "rb") : nullptr;
  bool ok = f != nullptr;
  for (size_t read = 0; ok && read < bytes;) {
    const size_t n = fread(s->blob + read, 1, std::min<size_t>(bytes - read, 65536), f);
    if (!n) ok = false;
    read += n;
  }
  if (f) fclose(f);
  // Bound PCM/workspace to the same model-defined centre window as HardwareOne.
  constexpr size_t maxSamples = 10 * 16000;
  if (ok)
    ok = s->model.load(s->blob, bytes, maxSamples, hw1::stt::sttPsramAlloc, hw1::stt::sttPsramFree) ==
         hw1::stt::speaker::LoadStatus::Ok;
  if (ok) {
    const auto& m = s->model.info();
    s->span = std::min<size_t>(maxSamples, size_t(m.features.window_frames - 1) * m.features.hop);
    s->centroids = static_cast<float*>(heap_caps_malloc(8 * m.dim * sizeof(float), MALLOC_CAP_SPIRAM));
    s->embedding = static_cast<float*>(heap_caps_malloc(m.dim * sizeof(float), MALLOC_CAP_SPIRAM));
    s->pcm = static_cast<int16_t*>(heap_caps_malloc(kJobs * s->span * sizeof(int16_t), MALLOC_CAP_SPIRAM));
    s->config.threshold = m.threshold;
    s->config.min_new_samples = size_t(m.minNewMs) * 16;
    s->config.max_speakers = 8;
    s->ready = xQueueCreate(kJobs, sizeof(uint8_t));
    s->free = xQueueCreate(kJobs, sizeof(uint8_t));
    s->results = xQueueCreate(2 * kJobs + 4, sizeof(Result));
    ok = s->span && s->centroids && s->embedding && s->pcm && s->ready && s->free && s->results &&
         s->clusters.reset(s->centroids, m.dim, s->config);
  }
  if (ok)
    ok = heap_caps_get_free_size(MALLOC_CAP_SPIRAM) >= reserve &&
         heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT) >= 140 * 1024 &&
         heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM) >= contiguous;
  if (ok) {
    for (uint8_t i = 0; i < kJobs; ++i) xQueueSend(s->free, &i, 0);
    s->model.setMultiCore(false);
    ok = xTaskCreatePinnedToCore(worker, "stt_speaker", 8192, s, 1, nullptr, 1) == pdPASS;
  }
  if (!ok) {
    s->~State();
    heap_caps_free(s);
    ESP_LOGW("captions", "Speaker labels unavailable; captions continue");
    return;
  }
  state = s;
  ESP_LOGI("captions", "Optional background speaker labels ready");
}
void submit(product::Receipt receipt, const int16_t* pcm, size_t samples) {
  if (!state || !receipt.sequence || !pcm || !samples) return;
  uint8_t slot = 0;
  if (xQueueReceive(state->free, &slot, 0) != pdTRUE) {
    product::speaker(receipt, -1);
    ESP_LOGW("captions", "Speaker queue full; unknown label");
    return;
  }
  const size_t n = std::min(samples, state->span), offset = (samples - n) / 2;
  std::memcpy(state->pcm + size_t(slot) * state->span, pcm + offset, n * sizeof(int16_t));
  state->jobs[slot] = {receipt, n, samples, milliseconds()};
  if (xQueueSend(state->ready, &slot, 0) != pdTRUE) {
    std::memset(state->pcm + size_t(slot) * state->span, 0, n * sizeof(int16_t));
    xQueueSend(state->free, &slot, 0);
    product::speaker(receipt, -1);
  }
}
void poll() {
  if (!state) return;
  Result result;
  while (xQueueReceive(state->results, &result, 0) == pdTRUE) {
    product::speaker(result.receipt, result.speaker);
    ESP_LOGI("captions", "TL speaker seq=%u note=%u label=%d wall_ms=%u lag_ms=%u",
             unsigned(result.receipt.sequence), unsigned(result.receipt.note), int(result.speaker),
             unsigned(result.elapsed), unsigned(result.lag));
  }
}
}  // namespace captions_speaker
#else
namespace captions_speaker {
void begin(size_t, size_t) {}
void submit(product::Receipt, const int16_t*, size_t) {}
void poll() {}
}  // namespace captions_speaker
#endif
