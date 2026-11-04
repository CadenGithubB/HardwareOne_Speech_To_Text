// Minimal on-device captions for the ESP32-P4X-EYE.
//
//   PDM microphone -> phrase segmenter -> QuartzNet 15x5 (ESP-DL int8) + word LM -> USB serial console
//
// No network, no accounts, no display: the whole speech-to-text path of the HardwareOne
// firmware reduced to what it needs. Put the model and language model on a FAT microSD card:
//   /STT Models/quartznet15x5-gen2-25397.p4.stt   (the packed model this build is pinned to)
//   /STT Models/meeting.lm                         (optional; without it decoding is greedy)
// then build, flash, open the serial console and talk.
#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <sys/stat.h>

#include "driver/gpio.h"
#include "driver/i2s_pdm.h"
#include "driver/sdmmc_host.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_vfs_fat.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "sd_pwr_ctrl_by_on_chip_ldo.h"
#include "sdmmc_cmd.h"

#include "stt/quartznet_runtime.h"
#include "stt/stt_lm.h"
#include "stt/stt_stream.h"
#include "product.h"
#include "speaker_adapter.h"

#ifndef CONFIG_CAPTIONS_DRAFTS
#define CONFIG_CAPTIONS_DRAFTS 0
#endif
#ifndef CONFIG_CAPTIONS_SPECULATIVE_FINAL
#define CONFIG_CAPTIONS_SPECULATIVE_FINAL 0
#endif

namespace {
constexpr const char* TAG = "captions";

// Files on the card. The model file must be the one stt/stt_model_identity.h was generated
// for (the engine checks its size and SHA-256); a different model needs a new identity header
// (tools/stt_p4/pack_model.py writes both).
constexpr const char* kMountPoint = "/sd";
constexpr const char* kModelPath = "/sd/STT Models/quartznet15x5-gen2-25397.p4.stt";
constexpr const char* kLmPath = "/sd/STT Models/meeting.lm";

// P4X-EYE wiring (components/hardwareone/System_Board_P4X_EYE.h and System_BuildConfig.h).
// microSD: SDMMC slot 0, 4-bit, 40 MHz; the card's LDO is channel 4; GPIO46 switches card power (low = on).
constexpr int kSdSlot = 0;
constexpr gpio_num_t kSdClk = GPIO_NUM_43, kSdCmd = GPIO_NUM_44;
constexpr gpio_num_t kSdD0 = GPIO_NUM_39, kSdD1 = GPIO_NUM_40, kSdD2 = GPIO_NUM_41, kSdD3 = GPIO_NUM_42;
constexpr gpio_num_t kSdDetect = GPIO_NUM_45;  // low = card present
constexpr gpio_num_t kSdPower = GPIO_NUM_46;   // low = on
constexpr int kSdLdoChannel = 4;
constexpr int kSdMaxFreqKhz = 40000;
// PDM microphone (MSM261D) on I2S0. GPIO12 powers the peripheral rail shared by the mic, camera, LCD
// and IMU: it is switched on here and never switched off.
constexpr gpio_num_t kMicClk = GPIO_NUM_22, kMicData = GPIO_NUM_21, kMicPower = GPIO_NUM_12;

constexpr uint32_t kSampleRate = 16000;
constexpr size_t kPhraseSamples = 10 * kSampleRate;  // a phrase is at most 10 s
constexpr size_t kReadSamples = 1024;                // one PDM DMA block
// Full-audio mode remains the default for the board microphone. Enable the
// 500 ms tail and exact speculative finals through menuconfig when qualifying
// the HardwareOne latency policy on a particular audio source.
constexpr size_t kMaxText = hw1::stt::kStreamText;
constexpr size_t kRingSamples = 65536;
hw1::stt::StreamPipeline gPipeline;
hw1::stt::StreamBuffers gBuffers;
SemaphoreHandle_t gPipelineMutex = nullptr;
void streamLock(void*) { xSemaphoreTake(gPipelineMutex, portMAX_DELAY); }
void streamUnlock(void*) { xSemaphoreGive(gPipelineMutex); }
uint32_t nowMs() { return uint32_t(esp_timer_get_time() / 1000); }

// ---------------------------------------------------------------- microSD
sdmmc_card_t* gCard = nullptr;
sd_pwr_ctrl_handle_t gSdPower = nullptr;
const char* gStorageFailure = "SD initialization failed";

bool mountCard() {
  gpio_config_t pins = {};
  pins.pin_bit_mask = 1ULL << kSdPower;
  pins.mode = GPIO_MODE_OUTPUT;
  gpio_set_level(kSdPower, 1);  // off until the LDO is up
  if (gpio_config(&pins) != ESP_OK) return false;
  pins = {};
  pins.pin_bit_mask = 1ULL << kSdDetect;
  pins.mode = GPIO_MODE_INPUT;
  pins.pull_up_en = GPIO_PULLUP_ENABLE;
  if (gpio_config(&pins) != ESP_OK) return false;

  sd_pwr_ctrl_ldo_config_t ldo = {};
  ldo.ldo_chan_id = kSdLdoChannel;
  const esp_err_t powerError = sd_pwr_ctrl_new_on_chip_ldo(&ldo, &gSdPower);
  if (powerError != ESP_OK) {
    gStorageFailure = esp_err_to_name(powerError);
    return false;
  }
  vTaskDelay(pdMS_TO_TICKS(20));
  gpio_set_level(kSdPower, 0);
  vTaskDelay(pdMS_TO_TICKS(20));
  if (gpio_get_level(kSdDetect) != 0) {
    gStorageFailure = "No microSD card detected on GPIO45; insert/reseat the model card and reset";
    ESP_LOGE(TAG, "No microSD card detected");
    return false;
  }

  sdmmc_host_t host = SDMMC_HOST_DEFAULT();
  host.slot = kSdSlot;
  host.max_freq_khz = kSdMaxFreqKhz;
  host.flags = SDMMC_HOST_FLAG_4BIT | SDMMC_HOST_FLAG_1BIT;
  host.pwr_ctrl_handle = gSdPower;

  sdmmc_slot_config_t slot = SDMMC_SLOT_CONFIG_DEFAULT();
  slot.clk = kSdClk;
  slot.cmd = kSdCmd;
  slot.d0 = kSdD0;
  slot.d1 = kSdD1;
  slot.d2 = kSdD2;
  slot.d3 = kSdD3;
  slot.d4 = slot.d5 = slot.d6 = slot.d7 = GPIO_NUM_NC;
  slot.cd = kSdDetect;
  slot.wp = SDMMC_SLOT_NO_WP;
  slot.width = 4;
  slot.flags = 0;  // the board has bus pull-ups; 3.3 V SDR

  esp_vfs_fat_sdmmc_mount_config_t mount = {};
  mount.format_if_mount_failed = false;
  mount.max_files = 4;
  mount.allocation_unit_size = 16 * 1024;
  const esp_err_t err = esp_vfs_fat_sdmmc_mount(kMountPoint, &host, &slot, &mount, &gCard);
  if (err != ESP_OK) {
    gStorageFailure = esp_err_to_name(err);
    ESP_LOGE(TAG, "Card mount failed: %s", esp_err_to_name(err));
    return false;
  }
  return true;
}

// ---------------------------------------------------------------- microphone
i2s_chan_handle_t gMic = nullptr;

bool startMic() {
  // Set the latch first, then drive the pin, so the shared rail never dips.
  gpio_set_level(kMicPower, 1);
  if (gpio_set_direction(kMicPower, GPIO_MODE_OUTPUT) != ESP_OK) return false;

  i2s_chan_config_t chan = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
  chan.dma_desc_num = 4;
  chan.dma_frame_num = kReadSamples;
  if (i2s_new_channel(&chan, nullptr, &gMic) != ESP_OK) return false;

  i2s_pdm_rx_slot_config_t slot =
#ifdef I2S_PDM_RX_SLOT_PCM_FMT_DEFAULT_CONFIG
      I2S_PDM_RX_SLOT_PCM_FMT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO);
#else
      I2S_PDM_RX_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO);
#endif
  i2s_pdm_rx_config_t cfg = {
      .clk_cfg = I2S_PDM_RX_CLK_DEFAULT_CONFIG(kSampleRate),
      .slot_cfg = slot,
      .gpio_cfg =
          {
              .clk = kMicClk,
              .din = kMicData,
              .invert_flags = {.clk_inv = false},
          },
  };
  // 16 kHz x 64 = 1.024 MHz lies in the microphone's gap between its low-power and standard
  // clock bands; DSR16 doubles the PDM clock and keeps the 16 kHz PCM rate.
  cfg.clk_cfg.dn_sample_mode = I2S_PDM_DSR_16S;
  if (i2s_channel_init_pdm_rx_mode(gMic, &cfg) != ESP_OK) return false;
  if (i2s_channel_enable(gMic) != ESP_OK) return false;

  // Let the microphone settle: discard the first three blocks.
  static int16_t warm[kReadSamples];
  for (int i = 0; i < 3; ++i) {
    size_t bytes = 0;
    i2s_channel_read(gMic, warm, sizeof(warm), &bytes, 500);
  }
  return true;
}

// ---------------------------------------------------------------- portable streaming adapters
void captureTask(void*) {
  static int16_t block[kReadSamples];
  for (;;) {
    size_t bytes = 0;
    const esp_err_t err = i2s_channel_read(gMic, block, sizeof(block), &bytes, 200);
    if (err != ESP_OK && err != ESP_ERR_TIMEOUT) {
      vTaskDelay(pdMS_TO_TICKS(100));
      continue;
    }
    if (bytes && !gPipeline.push(block, bytes / sizeof(int16_t), nowMs())) {
      ESP_LOGE(TAG, "Streaming capture rejected input");
      std::memset(block, 0, sizeof(block));
      vTaskDelete(nullptr);
      return;
    }
  }
}

#if CONFIG_CAPTIONS_CAPTURE_FEATURES
void featureTask(void* context) {
  auto* workspace = static_cast<hw1::stt::FrontendWorkspace*>(context);
  hw1::stt::StreamFeatureWork work;
  float row[64];
  for (;;) {
    if (!gPipeline.featureTake(work)) {
      vTaskDelay(pdMS_TO_TICKS(10));
      continue;
    }
    const bool ok = hw1::stt::log_mel_frame_ring(work.ring, 511, work.start, work.samples, work.frame, row,
                                                 workspace) == hw1::stt::Status::Ok;
    gPipeline.featureComplete(work, row, ok);
    // Lower priority than capture and inference; periodically admit idle tasks.
    if ((work.frame & 7) == 7) vTaskDelay(1);
  }
}

#endif

void startFeatures(hw1::stt::ModelCache& weights) {
#if CONFIG_CAPTIONS_CAPTURE_FEATURES
  constexpr size_t rowsBytes = 2 * (kPhraseSamples / 160) * 64 * sizeof(float);
  constexpr size_t poolBytes =
      rowsBytes + kRingSamples * sizeof(int16_t) + sizeof(hw1::stt::FrontendWorkspace);
  size_t contiguous = 0;
  const size_t keep =
      std::max<size_t>(2u << 20, hw1::stt::callBudget(kPhraseSamples, &weights, &contiguous) + (1u << 20));
  if (heap_caps_get_free_size(MALLOC_CAP_SPIRAM) < poolBytes + keep) {
    ESP_LOGW(TAG, "Feature cache disabled: preserving inference/LM reserve");
    return;
  }
  auto* ring = static_cast<int16_t*>(heap_caps_malloc(kRingSamples * sizeof(int16_t), MALLOC_CAP_SPIRAM));
  auto* rows = static_cast<float*>(heap_caps_malloc(rowsBytes, MALLOC_CAP_SPIRAM));
  auto* work = static_cast<hw1::stt::FrontendWorkspace*>(
      heap_caps_malloc(sizeof(hw1::stt::FrontendWorkspace), MALLOC_CAP_SPIRAM));
  if (!ring || !rows || !work || heap_caps_get_free_size(MALLOC_CAP_SPIRAM) < keep ||
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM) < contiguous) {
    heap_caps_free(ring);
    heap_caps_free(rows);
    heap_caps_free(work);
    ESP_LOGW(TAG, "Feature cache disabled: allocation/contiguous reserve");
    return;
  }
  // Create the idle task before publishing its pool, so task allocation
  // failure cannot leave the scheduler pointing at freed memory.
  TaskHandle_t task = nullptr;
  // featureTake returns false until the pool is installed; capture has not started.
  if (xTaskCreatePinnedToCore(featureTask, "stt_features", 4096, work, 1, &task, 0) != pdPASS) {
    heap_caps_free(ring);
    heap_caps_free(rows);
    heap_caps_free(work);
    return;
  }
  if (!gPipeline.enableFeatures(ring, kRingSamples, rows, rows + rowsBytes / (2 * sizeof(float)))) {
    vTaskDelete(task);
    heap_caps_free(ring);
    heap_caps_free(rows);
    heap_caps_free(work);
    return;
  }
  ESP_LOGI(TAG, "Capture feature pool: %u bytes; reserve %u bytes", unsigned(poolBytes), unsigned(keep));
#else
  (void)weights;
#endif
}

// ---------------------------------------------------------------- language model
struct LanguageModel {
  uint8_t* blob = nullptr;
  hw1::stt::lm::Lm view;
  bool tried = false;
};

void loadLanguageModel(LanguageModel& m) {
  namespace lm = hw1::stt::lm;
  struct stat st = {};
  if (stat(kLmPath, &st) != 0) {
    printf("No %s: decoding greedily (no language model)\n", kLmPath);
    return;
  }
  const size_t bytes = size_t(st.st_size);
  constexpr size_t kReserve = 6u << 20;  // PSRAM a 10 s phrase needs beside the LM
  if (bytes < 96 || bytes > (32u << 20) || heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM) < bytes ||
      heap_caps_get_free_size(MALLOC_CAP_SPIRAM) < bytes + kReserve) {
    printf("Language model %s skipped (%u bytes; not enough PSRAM)\n", kLmPath, unsigned(bytes));
    return;
  }
  m.blob = static_cast<uint8_t*>(heap_caps_aligned_alloc(16, bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  FILE* f = m.blob ? fopen(kLmPath, "rb") : nullptr;
  bool ok = f != nullptr;
  for (size_t done = 0; ok && done < bytes;) {
    const size_t n = fread(m.blob + done, 1, std::min<size_t>(bytes - done, 64 * 1024), f);
    if (!n) ok = false;
    done += n;
  }
  if (f) fclose(f);
  const lm::LoadStatus status = ok ? m.view.open(m.blob, bytes) : lm::LoadStatus::InvalidArgument;
  if (status != lm::LoadStatus::Ok) {
    printf("Language model %s rejected: %s; decoding greedily\n", kLmPath, lm::describe(status));
    m.view = lm::Lm{};
    heap_caps_free(m.blob);
    m.blob = nullptr;
    return;
  }
  printf("Language model: %u words, %u bigrams, %u trigrams, beam %u (%u bytes)\n", unsigned(m.view.vocab()),
         unsigned(m.view.bigrams()), unsigned(m.view.trigrams()), unsigned(m.view.beamWidth()),
         unsigned(bytes));
}

hw1::stt::DecodeResult decodeWithLanguageModel(void* context, const int8_t* logits, size_t frames,
                                               int exponent, char* text, size_t capacity,
                                               const STTLocalControl& control) {
  namespace lm = hw1::stt::lm;
  auto& m = *static_cast<LanguageModel*>(context);
  if (!m.tried) {  // loaded at the first decode, when the model's own memory already exists
    m.tried = true;
    loadLanguageModel(m);
  }
  if (!m.view.valid()) return hw1::stt::DecodeResult::Fallback;
  lm::DecodeStats details;
  const lm::DecodeStatus status =
      lm::decode(logits, frames, exponent, m.view, product::customWords(), text, capacity,
                 {control.context, control.cancelled}, 0, &details, product::lmStrength());
  ESP_LOGI(TAG, "LM strength=%.3f history_start=%d history_end=%d status=%u", double(product::lmStrength()),
           details.startHistoryWords == UINT8_MAX ? -1 : int(details.startHistoryWords),
           details.endHistoryWords == UINT8_MAX ? -1 : int(details.endHistoryWords), unsigned(status));
  if (status == lm::DecodeStatus::Ok) return hw1::stt::DecodeResult::Decoded;
  if (status == lm::DecodeStatus::Cancelled) return hw1::stt::DecodeResult::Cancelled;
  return hw1::stt::DecodeResult::Fallback;  // e.g. no workspace memory: greedy decides
}

// The engine frees the LM through this if it needs the memory for a phrase.
bool releaseLanguageModel(void* context) {
  auto& m = *static_cast<LanguageModel*>(context);
  if (!m.blob) return false;
  m.view = hw1::stt::lm::Lm{};
  heap_caps_free(m.blob);
  m.blob = nullptr;
  printf("Language model released to make room; decoding greedily from now on\n");
  return true;
}

// ---------------------------------------------------------------- transcription
hw1::stt::ModelCache gWeights;  // the verified model stays resident between phrases
LanguageModel gLm;
const hw1::stt::Decoder gDecoder{&gLm, decodeWithLanguageModel, releaseLanguageModel};

struct ModelFile {
  FILE* file;
  size_t bytes = 0, calls = 0;
  uint64_t readUs = 0;
};
size_t readModel(void* context, void* dest, size_t bytes) {
  auto& f = *static_cast<ModelFile*>(context);
  const int64_t begin = esp_timer_get_time();
  const size_t n = fread(dest, 1, bytes, f.file);
  f.readUs += esp_timer_get_time() - begin;
  f.bytes += n;
  ++f.calls;
  return n;
}
bool transcribe(const int16_t* pcm, size_t samples, char* text, size_t capacity, STTLocalStats& stats,
                char* error, size_t errorCapacity, const STTLocalControl& control = {},
                const STTFeaturePrefix* prefix = nullptr) {
  stats = {};
  const int64_t opened = esp_timer_get_time();
  FILE* f = fopen(kModelPath, "rb");
  if (!f) {
    snprintf(error, errorCapacity, "cannot open %s", kModelPath);
    return false;
  }
  struct stat st = {};
  if (fstat(fileno(f), &st) != 0) {
    fclose(f);
    snprintf(error, errorCapacity, "cannot stat model");
    return false;
  }
  const uint64_t openUs = esp_timer_get_time() - opened;
  ModelFile file{f};
  const hw1::stt::ModelReader reader{&file, size_t(st.st_size), readModel};
  const bool ok = hw1::stt::transcribe(reader, pcm, samples, text, capacity, control, stats, error,
                                       errorCapacity, nullptr, &gWeights, &gDecoder, prefix);
  fclose(f);
  ESP_LOGI(TAG, "SD logical model bytes=%u calls=%u read_us=%llu open_stat_us=%llu", unsigned(file.bytes),
           unsigned(file.calls), (unsigned long long)file.readUs, (unsigned long long)openUs);
  return ok;
}
struct ActiveWork {
  const hw1::stt::StreamWork* work;
};
bool cancelWork(void* ctx) { return gPipeline.cancelled(*static_cast<ActiveWork*>(ctx)->work); }

void halt(const char* why) {
  product::status("error", why);
  for (;;) {
    product::poll();
    vTaskDelay(pdMS_TO_TICKS(100));
  }
}
}  // namespace

extern "C" void app_main() {
  printf("\nP4X-EYE captions: %s\n", kModelPath);
  printf("PSRAM free: %u KB\n", unsigned(heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024));
  product::platformBegin();
  if (!mountCard()) halt(gStorageFailure);
  struct stat st = {};
  if (stat(kModelPath, &st) != 0) halt("Model file missing on the card (see kModelPath in main.cpp).");

  product::begin();

  vTaskPrioritySet(nullptr, 2);
  gPipelineMutex = xSemaphoreCreateMutex();
  if (!gPipelineMutex) halt("No streaming mutex.");
  gBuffers.capacity = kPhraseSamples;
  gBuffers.capture =
      static_cast<int16_t*>(heap_caps_malloc(kPhraseSamples * sizeof(int16_t), MALLOC_CAP_SPIRAM));
  for (auto& p : gBuffers.slots)
    p = static_cast<int16_t*>(heap_caps_malloc(kPhraseSamples * sizeof(int16_t), MALLOC_CAP_SPIRAM));
#if CONFIG_CAPTIONS_DRAFTS || CONFIG_CAPTIONS_SPECULATIVE_FINAL
  gBuffers.snapshot =
      static_cast<int16_t*>(heap_caps_malloc(kPhraseSamples * sizeof(int16_t), MALLOC_CAP_SPIRAM));
#endif
  hw1::stt::StreamConfig cfg;
  cfg.segmentation.adaptive = true;
  cfg.segmentation.min_segment_samples = 4 * kSampleRate;
  cfg.segmentation.max_segment_samples = kPhraseSamples;
  cfg.segmentation.short_close_silence_samples = kSampleRate;
  cfg.segmentation.noise_percentile = 25;
  cfg.segmentation.silence_blip_samples = 3 * hw1::stt::kSegmentAnalysisSamples;
  cfg.segmentation.hard_cut_search_samples = 2 * kSampleRate;
#if CONFIG_CAPTIONS_TRIM_SILENCE
  cfg.tail_samples = kSampleRate / 2;
#endif
  cfg.drafts = CONFIG_CAPTIONS_DRAFTS;
#if CONFIG_CAPTIONS_X2F_DRAFT_PACING
  cfg.draft_pacing = hw1::stt::DraftPacing::X2FastFirst;
  cfg.draft_interval_ms = 0;  // adaptive audio growth supplies the pacing floor
#endif
  cfg.speculative = CONFIG_CAPTIONS_SPECULATIVE_FINAL;
  if (!gPipeline.begin(cfg, gBuffers, {nullptr, streamLock, streamUnlock}))
    halt("Streaming buffers/settings unavailable.");

  // Load and verify the model now (and the language model at its first decode), so the first
  // phrase is not delayed by the 20 MB read.
  static char text[kMaxText + 1];
  static char error[128];
  STTLocalStats stats;
  {
    constexpr size_t kWarmSamples = kSampleRate / 2;
    auto* silence = static_cast<int16_t*>(heap_caps_calloc(kWarmSamples, sizeof(int16_t), MALLOC_CAP_SPIRAM));
    const int64_t t0 = esp_timer_get_time();
    const bool ok =
        silence && transcribe(silence, kWarmSamples, text, sizeof(text), stats, error, sizeof(error));
    heap_caps_free(silence);
    if (!ok) {
      printf("Model load failed: %s\n", error);
      halt("Check that the card holds the exact model this build is pinned to.");
    }
    printf("Model ready in %lld ms (%u bytes). PSRAM free: %u KB\n", (esp_timer_get_time() - t0) / 1000,
           unsigned(stats.modelBytes), unsigned(heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024));
  }

  size_t speakerBlock = 0;
  const size_t speakerReserve =
      std::max<size_t>(3u << 20, hw1::stt::callBudget(kPhraseSamples, &gWeights, &speakerBlock) + (1u << 20));
  captions_speaker::begin(speakerReserve, speakerBlock);
  startFeatures(gWeights);
  if (!startMic()) halt("Microphone start failed.");
  if (xTaskCreatePinnedToCore(captureTask, "capture", 8192, nullptr, 3, nullptr, 1) != pdPASS)
    halt("No capture task.");
  printf("Measuring room noise...\n");
  bool announced = false;
  uint32_t dropped = 0;
  for (;;) {
    captions_speaker::poll();
    product::poll();
    hw1::stt::StreamWork work;
    if (!gPipeline.take(work, nowMs())) {
      if (!announced && gPipeline.calibrated()) {
        announced = true;
        product::status("listening");
        printf("Listening (noise floor %u, level %u).\n", unsigned(gPipeline.noise()),
               unsigned(gPipeline.level()));
      }
      vTaskDelay(pdMS_TO_TICKS(10));
      continue;
    }
    ActiveWork active{&work};
    const STTLocalControl control{&active, cancelWork, nullptr};
    const int64_t t0 = esp_timer_get_time();
    const bool ok = work.promoted ? (stats = work.promoted_stats,
                                     std::snprintf(text, sizeof(text), "%s", work.promoted_text), true)
                                  : transcribe(work.pcm, work.samples, text, sizeof(text), stats, error,
                                               sizeof(error), control, &work.features);
    const uint32_t ms = uint32_t((esp_timer_get_time() - t0) / 1000);
    const uint32_t doneMs = nowMs();
    const bool valid = ok && !gPipeline.cancelled(work);
    if (work.kind == hw1::stt::StreamWorkKind::Final) {
      product::clearDraft();
      if (valid && text[0]) {
        printf("[%7.1f s] %s\n", double(work.start_sample) / kSampleRate, text);
        product::caption(text, work.start_sample, work.start_sample + work.captured_samples, work.hard_limit,
                         gPipeline.counters().dropped);
        captions_speaker::submit(product::receipt(), work.pcm, work.samples);
      } else if (!ok)
        product::status("error", error);
    } else if (work.kind == hw1::stt::StreamWorkKind::Draft && valid)
      product::draft(text);
    ESP_LOGI(TAG,
             "TL stream seq=%llu kind=%u ok=%d promoted=%d samples=%u captured=%u load=%u fe=%u nn=%u lm=%u "
             "cached=%u worker_ms=%u close_ms=%u psram=%u internal=%u largest=%u",
             (unsigned long long)work.sequence, unsigned(work.kind), valid, work.promoted,
             unsigned(work.samples), unsigned(work.captured_samples), unsigned(stats.loadMs),
             unsigned(stats.frontendMs), unsigned(stats.inferenceMs), unsigned(stats.decodeMs),
             unsigned(stats.featureCachedFrames), unsigned(ms),
             work.kind == hw1::stt::StreamWorkKind::Final ? unsigned(doneMs - work.closed_ms) : 0,
             unsigned(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)),
             unsigned(heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)),
             unsigned(heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)));
    gPipeline.complete(work, valid, text, stats, ms);
    const auto counters = gPipeline.counters();
    if (counters.dropped != dropped) {
      printf("%u phrase(s) dropped while transcribing\n", unsigned(counters.dropped - dropped));
      dropped = counters.dropped;
    }
  }
}
