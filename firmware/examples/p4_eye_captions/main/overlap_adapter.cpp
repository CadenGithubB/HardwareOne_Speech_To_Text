#include "overlap_adapter.h"
#include "capture_diagnostics.h"
#ifndef CONFIG_CAPTIONS_OVERLAP_GATE
#define CONFIG_CAPTIONS_OVERLAP_GATE 0
#endif
#if HW1_OVERLAP_GATE && CONFIG_CAPTIONS_OVERLAP_GATE
#include "stt/overlap_gate.h"
#include "stt/quartznet_frontend.h"
#include "stt/stt_dl_metadata.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <new>
#include <sys/stat.h>
extern "C" int hw1_dl_log_kernel_binds;   // patched ESP-DL: log each distinct kernel binding once (TL kbind)
namespace captions_overlap {
namespace {
using namespace hw1::stt;
// Longest segment the gate scores: the frontend's maximum (30 s) -> 1500 output frames.
constexpr size_t kMaxMarks = (kMaxSamples / 160 + 1) / 2;
struct State {
  overlap::Gate gate;
  overlap::Rule rule;
  uint8_t* blob = nullptr;
  FrontendWorkspace* workspace = nullptr;   // tail rows the recognizer computed but did not cache
  uint8_t marks[kMaxMarks];
  int8_t logits[kMaxMarks * overlap::kClasses];   // raw int8 output of every chunk, for the STT_OVERLAP log
  char hex[2 * kMaxMarks * overlap::kClasses + 1];
  int8_t silence = -128;
  bool enabled = true, frameLog = true;
  ~State() {
    gate.reset();
    sttPsramFree(workspace);
    heap_caps_free(blob);
  }
};
State* state = nullptr;
}  // namespace

void begin(size_t reserve) {
  if (state) return;
  constexpr const char* path = "/sd/STT Models/overlap_gate.espdl";
  struct stat info{};
  if (stat(path, &info) || info.st_size < 1024 || info.st_size > (1 << 20)) {
    ESP_LOGW("captions", "Optional overlap_gate.espdl missing or invalid size");
    return;
  }
  const size_t bytes = size_t(info.st_size);
  if (heap_caps_get_free_size(MALLOC_CAP_SPIRAM) < bytes + (1u << 20) + reserve) {
    ESP_LOGW("captions", "Overlap gate skipped: preserving caption reserve");
    return;
  }
  // Memory cost of the gate, measured directly: free heap just before and after everything it owns.
  const size_t psram0 = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
  const size_t internal0 = heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  const size_t largest0 = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  hw1_dl_log_kernel_binds = 1;
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
#if HW1_STT_STREAM_METRICS
  if (ok) captions_perf::modelIdentity("overlap", s->blob, bytes);
#endif
  overlap::LoadStatus status = overlap::LoadStatus::BadModel;
  if (ok) {
    status = s->gate.load(s->blob, bytes, true);
    ok = status == overlap::LoadStatus::Ok;
  }
  if (ok) {
    s->workspace = static_cast<FrontendWorkspace*>(sttPsramAlloc(sizeof(FrontendWorkspace), "stt.overlap"));
    // Pad frames carry the raw log-mel of digital silence, log(2^-24): saturates to -128 at exponent -3.
    s->silence = overlap::quantize_bin(std::log(std::ldexp(1.0f, -24)), s->gate.inputExponent());
    ok = s->workspace != nullptr;
  }
  if (ok)
    ok = heap_caps_get_free_size(MALLOC_CAP_SPIRAM) >= reserve &&
         heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT) >= 140 * 1024;
  if (!ok) {
    ESP_LOGW("captions", "Overlap gate unavailable (%s); captions continue", overlap::describe(status));
    s->~State();
    heap_caps_free(s);
    return;
  }
  state = s;
  const auto& r = s->gate.loadReport();
  const size_t psram1 = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
  const size_t internal1 = heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  const size_t largest1 = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  ESP_LOGI("captions",
           "TL overlap_load bytes=%u modules=%u arena_psram=%u arena_internal=%u in_exp=%d out_exp=%d build_us=%u "
           "test=%d test_us=%u rule=%.2f/%u/%.3f",
           unsigned(bytes), unsigned(r.modules), unsigned(r.arenaPsram), unsigned(r.arenaInternal), r.inputExponent,
           r.outputExponent, unsigned(r.buildUs), r.testResult, unsigned(r.testUs), double(s->rule.frame_threshold),
           unsigned(s->rule.min_run), double(s->rule.segment_threshold));
  ESP_LOGI("captions",
           "TL overlap_mem psram_before=%u psram_after=%u psram_cost=%d internal_before=%u internal_after=%u "
           "internal_cost=%d largest_internal_before=%u largest_internal_after=%u",
           unsigned(psram0), unsigned(psram1), int(psram0) - int(psram1), unsigned(internal0), unsigned(internal1),
           int(internal0) - int(internal1), unsigned(largest0), unsigned(largest1));
}

bool command(const char* cmd) {
  if (std::strncmp(cmd, "overlap", 7) || (cmd[7] && cmd[7] != ' ')) return false;
  const char* arg = cmd[7] ? cmd + 8 : "status";
  if (!state) { product::reply("Overlap gate not loaded", false); return true; }
  if (!std::strcmp(arg, "on")) state->enabled = true;
  else if (!std::strcmp(arg, "off")) state->enabled = false;
  else if (!std::strcmp(arg, "log on")) state->frameLog = true;
  else if (!std::strcmp(arg, "log off")) state->frameLog = false;
  else if (std::strcmp(arg, "status")) { product::reply("overlap on | off | log on | log off | status", false); return true; }
  char text[128];
  std::snprintf(text, sizeof(text), "Overlap gate %s, frame log %s, rule %.2f/%u/%.3f", state->enabled ? "on" : "off",
                state->frameLog ? "on" : "off", double(state->rule.frame_threshold), unsigned(state->rule.min_run),
                double(state->rule.segment_threshold));
  product::reply(text, true);
  return true;
}

void run(product::Receipt receipt, const StreamWork& work) {
  if (!state || !state->enabled || !receipt.sequence || !work.pcm || work.samples < kMinSamples) return;
  auto& s = *state;
  size_t logged = 0;
  const int64_t t0 = esp_timer_get_time();
  const size_t frames = feature_frames(work.samples);
  const size_t cached = std::min(work.features.count, frames);
  const int exponent = s.gate.inputExponent();
  overlap::Accumulator acc(s.marks, kMaxMarks);
  size_t tail = 0;
  bool ok = true;
  for (size_t start = 0; ok && start < frames; start += overlap::kChunkFrames) {
    int8_t* in = s.gate.input();
    for (size_t t = 0; t < overlap::kChunkFrames; ++t) {
      const size_t frame = start + t;
      int8_t* row = in + t * overlap::kMelBins;
      if (frame >= frames) {
        std::memset(row, s.silence, overlap::kMelBins);
      } else if (frame < cached) {
        const float* src = work.features.rows + frame * overlap::kMelBins;
        for (size_t m = 0; m < overlap::kMelBins; ++m) row[m] = overlap::quantize_bin(src[m], exponent);
      } else {
        float raw[overlap::kMelBins];
        if (log_mel_frame(work.pcm, work.samples, frame, raw, s.workspace) != Status::Ok) { ok = false; break; }
        ++tail;
        for (size_t m = 0; m < overlap::kMelBins; ++m) row[m] = overlap::quantize_bin(raw[m], exponent);
      }
    }
    if (!ok) break;
    const int8_t* logits = s.gate.run();
    if (!logits) { ok = false; break; }
    const size_t valid = std::min<size_t>(overlap::kChunkOutputs, (frames - start + 1) / 2);
    acc.add(logits, valid, s.gate.outputExponent(), s.rule);
    const size_t room = std::min(valid, kMaxMarks - logged);
    std::memcpy(s.logits + logged * overlap::kClasses, logits, room * overlap::kClasses);
    logged += room;
  }
  const uint32_t ms = uint32_t((esp_timer_get_time() - t0) / 1000);
  if (!ok) {
    ESP_LOGW("captions", "TL overlap seq=%u failed; no flag emitted", unsigned(receipt.sequence));
    return;
  }
  const overlap::Decision d = acc.decide(s.rule);
  product::overlap(receipt, d.flag, d.fraction, d.frames);
  ESP_LOGI("captions", "TL overlap seq=%u frames=%u marked=%u fraction=%.4f flag=%d cached_rows=%u tail_rows=%u ms=%u",
           unsigned(receipt.sequence), unsigned(d.frames), unsigned(d.marked), double(d.fraction), d.flag ? 1 : 0,
           unsigned(cached), unsigned(tail), unsigned(ms));
  if (s.frameLog) {
    // Raw int8 logits, [frame][3] hex, so any rule or threshold can be re-evaluated on the host.
    static const char digits[] = "0123456789abcdef";
    const size_t n = logged * overlap::kClasses;
    for (size_t i = 0; i < n; ++i) {
      const uint8_t v = uint8_t(s.logits[i]);
      s.hex[2 * i] = digits[v >> 4];
      s.hex[2 * i + 1] = digits[v & 15];
    }
    s.hex[2 * n] = 0;
    std::printf("STT_OVERLAP {\"sequence\":%u,\"note\":%u,\"stream_sequence\":%llu,\"start_sample\":%llu,\"samples\":%u,"
                "\"frames\":%u,\"exponent\":%d,\"fraction\":%.6f,\"flag\":%s,\"ms\":%u,\"logits\":\"",
                unsigned(receipt.sequence), unsigned(receipt.note), (unsigned long long)work.sequence,
                (unsigned long long)work.start_sample, unsigned(work.samples), unsigned(logged), s.gate.outputExponent(),
                double(d.fraction), d.flag ? "true" : "false", unsigned(ms));
    std::fwrite(s.hex, 1, 2 * n, stdout);
    std::fputs("\"}\n", stdout);
  }
}
}  // namespace captions_overlap
#else
namespace captions_overlap {
void begin(size_t) {}
void run(product::Receipt, const hw1::stt::StreamWork&) {}
bool command(const char*) { return false; }
}  // namespace captions_overlap
#endif
