#include "segment_recorder.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_vfs_fat.h"
#include <cerrno>
#include <cinttypes>
#include <cstdio>
#include <cstring>
#include <sys/stat.h>
namespace captions_pcm {
namespace {
constexpr const char* kRoot = "/sd/STT PCM";
constexpr uint64_t kMinFreeBytes = 256ull << 20;   // stop saving before the card fills
bool on = false;
char folder[64]{};
uint32_t saved = 0, failed = 0;
uint64_t freeBytes = 0;
bool refreshFree() {
  uint64_t total = 0, free = 0;
  if (esp_vfs_fat_info("/sd", &total, &free) != ESP_OK) return false;
  freeBytes = free;
  return true;
}
bool ensureFolder() {
  if (folder[0]) return true;
  struct stat st{};
  if (stat(kRoot, &st) && mkdir(kRoot, 0770) && errno != EEXIST) return false;
  char path[64];
  std::snprintf(path, sizeof(path), "%s/b%06" PRIu64, kRoot, product::bootNumber());
  if (stat(path, &st) && mkdir(path, 0770) && errno != EEXIST) return false;
  std::snprintf(folder, sizeof(folder), "%s", path);
  return true;
}
}  // namespace

void setEnabled(bool enable) {
  if (enable) {
    if (!ensureFolder()) { product::reply("PCM save: cannot create folder on the card", false); return; }
    refreshFree();
    if (freeBytes < kMinFreeBytes) { product::reply("PCM save: card nearly full; not enabled", false); return; }
  }
  on = enable;
  char text[160];
  std::snprintf(text, sizeof(text), "PCM save %s folder=%s free_mb=%u saved=%u failed=%u", on ? "on" : "off", folder,
                unsigned(freeBytes >> 20), unsigned(saved), unsigned(failed));
  product::reply(text, true);
}
bool enabled() { return on; }

void save(const hw1::stt::StreamWork& work, product::Receipt receipt, bool captioned) {
  if (!on || !work.pcm || !work.samples) return;
  if (saved % 50 == 0) {
    refreshFree();
    if (freeBytes < kMinFreeBytes) { on = false; product::reply("PCM save stopped: card nearly full", false); return; }
  }
  const int64_t t0 = esp_timer_get_time();
  char path[96];
  std::snprintf(path, sizeof(path), "%s/s%06llu.pcm", folder, (unsigned long long)work.sequence);
  FILE* f = std::fopen(path, "wb");
  bool ok = f != nullptr;
  const uint8_t* bytes = reinterpret_cast<const uint8_t*>(work.pcm);
  const size_t total = work.samples * sizeof(int16_t);
  for (size_t done = 0; ok && done < total;) {
    const size_t n = std::fwrite(bytes + done, 1, total - done < 32768 ? total - done : 32768, f);
    if (!n) ok = false;
    done += n;
  }
  if (f && std::fclose(f)) ok = false;
  const uint32_t ms = uint32_t((esp_timer_get_time() - t0) / 1000);
  char line[320];
  std::snprintf(line, sizeof(line),
                "{\"file\":\"s%06llu.pcm\",\"boot\":%" PRIu64 ",\"stream_sequence\":%llu,\"caption_sequence\":%u,\"note\":%u,"
                "\"captioned\":%s,\"start_sample\":%llu,\"samples\":%u,\"captured\":%u,\"ok\":%s,\"write_ms\":%u}",
                (unsigned long long)work.sequence, product::bootNumber(), (unsigned long long)work.sequence,
                unsigned(captioned ? receipt.sequence : 0), unsigned(receipt.note), captioned ? "true" : "false",
                (unsigned long long)work.start_sample, unsigned(work.samples), unsigned(work.captured_samples),
                ok ? "true" : "false", unsigned(ms));
  if (ok) {
    char index[96];
    std::snprintf(index, sizeof(index), "%s/index.jsonl", folder);
    if (FILE* x = std::fopen(index, "a")) { std::fputs(line, x); std::fputc('\n', x); std::fclose(x); }
    ++saved;
  } else {
    ++failed;
  }
  std::printf("STT_PCM %s\n", line);
}
}  // namespace captions_pcm
