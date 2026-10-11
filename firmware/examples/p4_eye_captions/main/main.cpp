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
#include "freertos/queue.h"
#include "freertos/task.h"
#include "sd_pwr_ctrl_by_on_chip_ldo.h"
#include "sdmmc_cmd.h"

#include "stt/quartznet_runtime.h"
#include "stt/stt_lm.h"
#include "stt/stt_segmenter.h"

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
constexpr size_t kPhraseSamples = 10 * kSampleRate;   // a phrase is at most 10 s
constexpr size_t kReadSamples = 1024;                 // one PDM DMA block
// Trailing-silence trim: with a value N > 0, a phrase that ended on a pause is cut N ms after
// its last voiced frame before it goes to the model, which saves inference time (HardwareOne
// uses 200 on its glasses microphone). Off by default: with a quiet speaker the energy gate
// can place that frame before a soft final word and the word is lost; the whole phrase costs
// about 0.3 s more per second of trailing silence and never drops a word.
#ifndef CAPTIONS_TRIM_TAIL_MS
#define CAPTIONS_TRIM_TAIL_MS 0
#endif
constexpr size_t kTrimTailSamples = kSampleRate * CAPTIONS_TRIM_TAIL_MS / 1000;
constexpr size_t kMaxText = 512;
constexpr int kSlots = 2;  // phrases waiting for the transcriber

// ---------------------------------------------------------------- microSD
sdmmc_card_t* gCard = nullptr;
sd_pwr_ctrl_handle_t gSdPower = nullptr;

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
  if (sd_pwr_ctrl_new_on_chip_ldo(&ldo, &gSdPower) != ESP_OK) return false;
  vTaskDelay(pdMS_TO_TICKS(20));
  gpio_set_level(kSdPower, 0);
  vTaskDelay(pdMS_TO_TICKS(20));
  if (gpio_get_level(kSdDetect) != 0) {
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
      .gpio_cfg = {
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

// ---------------------------------------------------------------- phrases from the capture task
struct Phrase {
  int16_t* pcm = nullptr;
  size_t samples = 0;
  size_t voicedEnd = 0;  // offset of the last voiced frame's end, 0 if unknown
  bool hardLimit = false;
  uint64_t startSample = 0;
};
Phrase gSlots[kSlots];
QueueHandle_t gReady = nullptr, gFree = nullptr;  // slot indices
std::atomic<bool> gCalibrated{false};
std::atomic<uint32_t> gDropped{0};
std::atomic<uint16_t> gLevel{0}, gNoise{0};

void captureTask(void*) {
  static int16_t block[kReadSamples];
  auto* work = static_cast<int16_t*>(heap_caps_malloc(kPhraseSamples * sizeof(int16_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (!work) {
    ESP_LOGE(TAG, "No PSRAM for the capture buffer");
    vTaskDelete(nullptr);
  }
  // The settings HardwareOne uses for this microphone: adaptive energy endpointing, phrases
  // closed after 4 s plus a 600 ms pause (short replies after 1 s of silence), the room noise
  // floor tracked at its lower quartile, and a 10 s phrase cut at its quietest point.
  hw1::stt::SegmenterConfig cfg;
  cfg.adaptive = true;
  cfg.min_segment_samples = 4 * kSampleRate;
  cfg.max_segment_samples = kPhraseSamples;
  cfg.short_close_silence_samples = kSampleRate;
  cfg.noise_percentile = 25;
  cfg.silence_blip_samples = 3 * hw1::stt::kSegmentAnalysisSamples;
  cfg.hard_cut_search_samples = 2 * kSampleRate;
  hw1::stt::Segmenter segmenter;
  if (!segmenter.reset(work, kPhraseSamples, cfg)) {
    ESP_LOGE(TAG, "Invalid segmenter settings");
    vTaskDelete(nullptr);
  }
  for (;;) {
    size_t bytes = 0;
    const esp_err_t err = i2s_channel_read(gMic, block, sizeof(block), &bytes, 200);
    if (err != ESP_OK && err != ESP_ERR_TIMEOUT) {
      vTaskDelay(pdMS_TO_TICKS(100));
      continue;
    }
    const size_t count = bytes / sizeof(int16_t);
    size_t offset = 0;
    while (offset < count) {
      const auto fed = segmenter.push(block + offset, count - offset);
      offset += fed.consumed;
      if (fed.status == hw1::stt::SegmentStatus::Ready) {
        const hw1::stt::SpeechSegment* s = segmenter.segment();
        int slot = -1;
        if (xQueueReceive(gFree, &slot, 0) == pdTRUE) {
          Phrase& p = gSlots[slot];
          memcpy(p.pcm, s->pcm, s->samples * sizeof(int16_t));
          p.samples = s->samples;
          p.voicedEnd = s->voiced_end_samples;
          p.hardLimit = s->end == hw1::stt::SegmentEnd::HardLimit;
          p.startSample = s->start_sample;
          xQueueSend(gReady, &slot, 0);
        } else {
          gDropped.fetch_add(1);  // the transcriber is behind; this phrase is lost
        }
        segmenter.release();
      } else if (fed.status != hw1::stt::SegmentStatus::Ok || !fed.consumed) {
        segmenter.reset_session();
        break;
      }
    }
    gCalibrated.store(segmenter.calibrated());
    gLevel.store(segmenter.current_rms());
    gNoise.store(segmenter.noise_rms());
  }
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
         unsigned(m.view.bigrams()), unsigned(m.view.trigrams()), unsigned(m.view.beamWidth()), unsigned(bytes));
}

hw1::stt::DecodeResult decodeWithLanguageModel(void* context, const int8_t* logits, size_t frames, int exponent,
                                               char* text, size_t capacity, const STTLocalControl& control) {
  namespace lm = hw1::stt::lm;
  auto& m = *static_cast<LanguageModel*>(context);
  if (!m.tried) {  // loaded at the first decode, when the model's own memory already exists
    m.tried = true;
    loadLanguageModel(m);
  }
  if (!m.view.valid()) return hw1::stt::DecodeResult::Fallback;
  const lm::DecodeStatus status =
      lm::decode(logits, frames, exponent, m.view, nullptr, text, capacity, {control.context, control.cancelled});
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

size_t readModel(void* context, void* dest, size_t bytes) { return fread(dest, 1, bytes, static_cast<FILE*>(context)); }

bool transcribe(const int16_t* pcm, size_t samples, char* text, size_t capacity, STTLocalStats& stats, char* error,
                size_t errorCapacity) {
  FILE* f = fopen(kModelPath, "rb");
  if (!f) {
    snprintf(error, errorCapacity, "cannot open %s", kModelPath);
    return false;
  }
  struct stat st = {};
  fstat(fileno(f), &st);
  const hw1::stt::ModelReader reader{f, size_t(st.st_size), readModel};
  const STTLocalControl control{};  // never cancelled, no progress callback
  const bool ok = hw1::stt::transcribe(reader, pcm, samples, text, capacity, control, stats, error, errorCapacity,
                                       nullptr, &gWeights, &gDecoder, nullptr);
  fclose(f);
  return ok;
}

void halt(const char* why) {
  for (;;) {
    printf("%s\n", why);
    vTaskDelay(pdMS_TO_TICKS(5000));
  }
}
}  // namespace

extern "C" void app_main() {
  printf("\nP4X-EYE captions: %s\n", kModelPath);
  printf("PSRAM free: %u KB\n", unsigned(heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024));
  if (!mountCard()) halt("Insert a FAT microSD card with /STT Models/ and reset.");
  struct stat st = {};
  if (stat(kModelPath, &st) != 0) halt("Model file missing on the card (see kModelPath in main.cpp).");

  for (int i = 0; i < kSlots; ++i) {
    gSlots[i].pcm = static_cast<int16_t*>(heap_caps_malloc(kPhraseSamples * sizeof(int16_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!gSlots[i].pcm) halt("No PSRAM for phrase buffers.");
  }
  gReady = xQueueCreate(kSlots, sizeof(int));
  gFree = xQueueCreate(kSlots, sizeof(int));
  for (int i = 0; i < kSlots; ++i) xQueueSend(gFree, &i, 0);

  // Load and verify the model now (and the language model at its first decode), so the first
  // phrase is not delayed by the 20 MB read.
  static char text[kMaxText + 1];
  static char error[128];
  STTLocalStats stats;
  {
    constexpr size_t kWarmSamples = kSampleRate / 2;
    auto* silence = static_cast<int16_t*>(heap_caps_calloc(kWarmSamples, sizeof(int16_t), MALLOC_CAP_SPIRAM));
    const int64_t t0 = esp_timer_get_time();
    const bool ok = silence && transcribe(silence, kWarmSamples, text, sizeof(text), stats, error, sizeof(error));
    heap_caps_free(silence);
    if (!ok) {
      printf("Model load failed: %s\n", error);
      halt("Check that the card holds the exact model this build is pinned to.");
    }
    printf("Model ready in %lld ms (%u bytes). PSRAM free: %u KB\n", (esp_timer_get_time() - t0) / 1000,
           unsigned(stats.modelBytes), unsigned(heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024));
  }

  if (!startMic()) halt("Microphone start failed.");
  if (xTaskCreatePinnedToCore(captureTask, "capture", 8192, nullptr, 3, nullptr, 1) != pdPASS) halt("No capture task.");
  printf("Measuring room noise...\n");

  bool announced = false;
  uint32_t dropped = 0;
  for (;;) {
    int slot = -1;
    if (xQueueReceive(gReady, &slot, pdMS_TO_TICKS(1000)) != pdTRUE) {
      if (!announced && gCalibrated.load()) {
        announced = true;
        printf("Listening (noise floor %u, level %u). Speak; a caption follows each pause.\n", unsigned(gNoise.load()),
               unsigned(gLevel.load()));
      }
      continue;
    }
    Phrase& p = gSlots[slot];
    // Optional trim (CAPTIONS_TRIM_TAIL_MS above). Very short phrases are padded to the model's minimum.
    size_t samples = p.samples;
    if (kTrimTailSamples && !p.hardLimit && p.voicedEnd && p.voicedEnd + kTrimTailSamples < samples)
      samples = p.voicedEnd + kTrimTailSamples;
    if (samples < 320) {
      memset(p.pcm + samples, 0, (320 - samples) * sizeof(int16_t));
      samples = 320;
    }
    const int64_t t0 = esp_timer_get_time();
    const bool ok = transcribe(p.pcm, samples, text, sizeof(text), stats, error, sizeof(error));
    const int64_t ms = (esp_timer_get_time() - t0) / 1000;
    const double at = double(p.startSample) / kSampleRate;
    if (ok && text[0]) {
      printf("[%7.1f s] %s\n", at, text);
    } else if (ok) {
      printf("[%7.1f s] (no speech recognised)\n", at);
    } else {
      printf("[%7.1f s] transcription failed: %s\n", at, error);
    }
    printf("           %.1f s of audio in %lld ms: features %u, model %u, decode %u ms%s\n", double(samples) / kSampleRate,
           ms, unsigned(stats.frontendMs), unsigned(stats.inferenceMs), unsigned(stats.decodeMs),
           stats.lmUsed ? ", language model" : ", greedy");
    const uint32_t d = gDropped.load();
    if (d != dropped) {
      printf("           %u phrase(s) dropped while transcribing\n", unsigned(d - dropped));
      dropped = d;
    }
    xQueueSend(gFree, &slot, 0);
  }
}
