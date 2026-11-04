// Separate diagnostic image. Model bytes live in the app, never on the card.
#include "dl_model_base.hpp"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include "stt/speaker_model.h"
#include "stt_dl_metadata.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <new>
#include <vector>

#ifdef NDEBUG
#error "Speaker contract verification requires enabled assertions"
#endif

extern const uint8_t candidate[] asm("_binary_speaker_candidate_start");
extern const uint8_t candidateEnd[] asm("_binary_speaker_candidate_end");
extern const uint8_t independent[] asm("_binary_speaker_reference_start");
extern const uint8_t independentEnd[] asm("_binary_speaker_reference_end");

extern "C" void app_main() {
  printf("STT_SPEAKER_BEGIN\n");
  assert(hw1::stt::installDlMetadataAllocator());
  size_t bytes = reinterpret_cast<uintptr_t>(candidateEnd) -
                 reinterpret_cast<uintptr_t>(candidate);
  assert(bytes > 160 && !memcmp(candidate, "HW1SPK1", 8));
  uint8_t sha[32];
  assert(mbedtls_sha256(candidate, bytes - 32, sha, 0) == 0 &&
         !memcmp(sha, candidate + bytes - 32, 32));
  uint32_t offset, size;
  memcpy(&offset, candidate + 60, 4);
  memcpy(&size, candidate + 64, 4);
  assert(offset % 16 == 0 && size <= bytes - 32 && offset == bytes - 32 - size);
  for (bool prepare : {false, true})
    for (auto mode :
         {dl::RUNTIME_MODE_SINGLE_CORE, dl::RUNTIME_MODE_MULTI_CORE}) {
      auto *raw = static_cast<uint8_t *>(heap_caps_aligned_alloc(
          16, size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
      assert(raw);
      memcpy(raw, candidate + offset, size);
      auto *model = new (std::nothrow)
          dl::Model(reinterpret_cast<const char *>(raw),
                    fbs::MODEL_LOCATION_IN_FLASH_RODATA, 0,
                    dl::MEMORY_MANAGER_GREEDY, nullptr, false);
      assert(model);
      auto *graph = model->get_fbs_model();
      graph->load_map();
      assert(model->get_inputs().size() == 1 &&
             model->get_outputs().size() == 1);
      const auto &in = *model->get_inputs().begin();
      const auto &out = *model->get_outputs().begin();
      auto *input = graph->get_test_input_tensor(in.first);
      auto *expected = graph->get_test_output_tensor(out.first);
      assert(input && expected && in.second->dtype == dl::DATA_TYPE_INT16 &&
             out.second->dtype == dl::DATA_TYPE_INT16);
      assert(in.second->get_bytes() == 24000 &&
             out.second->get_bytes() == 19200 &&
             expected->get_bytes() == 19200);
      assert(reinterpret_cast<uintptr_t>(independentEnd) -
                 reinterpret_cast<uintptr_t>(independent) ==
             19200);
      for (unsigned run = 0; run < 4; ++run) {
        bool synthetic = run == 2;
        if (synthetic) {
          uint32_t state = 1;
          auto *dst = static_cast<int16_t *>(in.second->data);
          for (unsigned i = 0; i < 12000; ++i) {
            state = 1664525 * state + 1013904223;
            dst[i] = int(state >> 19) - 4096;
          }
        } else {
          assert(in.second->assign(input));
        }
        if (prepare)
          model->prepare_args(mode);
        for (int i = 0; i < model->module_count(); ++i) {
          model->run(model->module_count(), i, mode);
          vTaskDelay(1);
        }
        const bool equal =
            memcmp(out.second->data,
                   synthetic ? static_cast<const void *>(independent)
                             : expected->data,
                   19200) == 0;
        printf("STT_SPEAKER_RESULT prepare=%d mode=%d run=%u exact=%d\n",
               int(prepare), int(mode), run, int(equal));
      }
      delete input;
      delete expected;
      graph->clear_map();
      delete model;
      heap_caps_free(raw);
    }
  // Exercise the product's package validation, optional SDK self-test, feature
  // extraction and pooling on a fresh writable copy, as in the SD adapter.
  auto *package = static_cast<uint8_t *>(
      heap_caps_aligned_alloc(16, bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  assert(package);
  memcpy(package, candidate, bytes);
  using namespace hw1::stt::speaker;
  auto *speaker = new (std::nothrow) Model;
  assert(speaker);
  Model::setLoadSelfTest(true);
  assert(speaker->load(package, bytes, 160000, hw1::stt::sttPsramAlloc,
                       hw1::stt::sttPsramFree) == LoadStatus::Ok);
  Model::setLoadSelfTest(false);
  const int selfTest = speaker->loadReport().testResult;
  assert(speaker->info().dim == 512);
  std::vector<float> first(512), repeat(512);
  std::vector<int16_t> pcm(16000);
  uint32_t seed = 42;
  for (auto &sample : pcm) {
    seed = 1664525 * seed + 1013904223;
    sample = int(seed >> 20) - 2048;
  }
  assert(speaker->embed(pcm.data(), pcm.size(), first.data()));
  assert(speaker->embed(pcm.data(), pcm.size(), repeat.data()));
  double norm = 0;
  for (float v : first) {
    assert(std::isfinite(v));
    norm += double(v) * v;
  }
  const bool same =
      memcmp(first.data(), repeat.data(), 512 * sizeof(float)) == 0;
  printf("STT_SPEAKER_PRODUCT self_test=%d repeat=%d nonzero=%d\n", selfTest,
         int(same), int(norm > 0));
  delete speaker;
  heap_caps_free(package);
  printf("STT_SPEAKER_COMPLETE\n");
  for (;;)
    vTaskDelay(pdMS_TO_TICKS(1000));
}
