// Standalone synthetic kernel probe, not a speech recognizer. No storage or
// radio initialization. All test buffers are volatile PSRAM allocations.
#include "sdkconfig.h"
#include "dl_module_conv.hpp"
#include "esp_heap_caps.h"
#include "esp_psram.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <algorithm>
#include <array>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#if !CONFIG_IDF_TARGET_ESP32P4 || !CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
#error "This probe requires ESP32-P4 and the USB Serial/JTAG console"
#endif
#if CONFIG_FREERTOS_NUMBER_OF_CORES != 2
#error "This comparison requires both P4 CPU cores"
#endif

namespace {
constexpr int kTime = 800;
constexpr int kChannels = 512;
constexpr int kExponent = -4;
constexpr int kShift = kExponent - kExponent - kExponent;
constexpr size_t kElements = size_t(kTime) * kChannels;
constexpr size_t kWeights = size_t(kChannels) * kChannels;
constexpr uint64_t kMacs = uint64_t(kTime) * kChannels * kChannels;
constexpr uint32_t kInputSeed = 0x5137a951u;
constexpr uint32_t kWeightSeed = 0xb45cd217u;
constexpr uint32_t kCaps = MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT;

struct Buffer {
    int8_t* data = nullptr;
    explicit Buffer(size_t bytes) {
        data = static_cast<int8_t*>(heap_caps_aligned_alloc(16, bytes, kCaps));
    }
    ~Buffer() { heap_caps_free(data); }
    Buffer(const Buffer&) = delete;
    Buffer& operator=(const Buffer&) = delete;
};

uint32_t mix(uint32_t x) {
    x ^= x >> 16;
    x *= 0x7feb352du;
    x ^= x >> 15;
    x *= 0x846ca68bu;
    return x ^ (x >> 16);
}
int8_t value(uint32_t seed, size_t index) {
    return static_cast<int8_t>(int(mix(seed ^ uint32_t(index)) & 15u) - 8);
}
int8_t weight(int output, int input) {
    return value(kWeightSeed, size_t(output) * kChannels + input);
}

// Signed nearest-even division, without relying on signed shifts or the host
// floating-point rounding environment. This model's shift is exactly four.
int8_t requantize(int64_t accumulator) {
    const bool negative = accumulator < 0;
    const uint64_t magnitude = negative ? uint64_t(-accumulator) : uint64_t(accumulator);
    uint64_t rounded = magnitude >> kShift;
    const uint64_t remainder = magnitude & ((uint64_t(1) << kShift) - 1);
    const uint64_t half = uint64_t(1) << (kShift - 1);
    if (remainder > half || (remainder == half && (rounded & 1u))) ++rounded;
    const int64_t signed_value = negative ? -int64_t(rounded) : int64_t(rounded);
    return static_cast<int8_t>(std::max<int64_t>(-128, std::min<int64_t>(127, signed_value)));
}
uint32_t checksum(const int8_t* data) {
    uint32_t hash = 2166136261u;
    for (size_t i = 0; i < kElements; ++i) {
        hash ^= static_cast<uint8_t>(data[i]);
        hash *= 16777619u;
    }
    return hash;
}
void heap(const char* phase) {
    std::printf("HEAP phase=%s internal_free=%zu internal_min=%zu internal_largest=%zu "
                "psram_free=%zu psram_min=%zu psram_largest=%zu\n", phase,
        heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
        heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
        heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
        heap_caps_get_free_size(kCaps), heap_caps_get_minimum_free_size(kCaps),
        heap_caps_get_largest_free_block(kCaps));
}

struct Result {
    const char* name;
    std::array<int64_t, 3> elapsed{};
    uint32_t hash = 0;
    int reference_max_diff = 0;
    int path_max_diff = 0;
    bool repeats_equal = true;
    bool passed = false;
};

bool check_reference(const int8_t* output, int& max_diff) {
    constexpr int times[4] = {0, 399, 400, 799};
    constexpr int channels[4] = {0, 15, 16, 511};
    for (unsigned sample = 0; sample < 128; ++sample) {
        const int t = sample < 16 ? times[sample / 4] : int(mix(sample ^ 0x691d8bu) % kTime);
        const int c = sample < 16 ? channels[sample % 4] : int(mix(sample ^ 0xba478u) % kChannels);
        int64_t accumulator = 0;
        for (int in = 0; in < kChannels; ++in) {
            // Reference regenerates canonical weights; it does not reuse the
            // packed-layout indexing used by the tested kernels.
            accumulator += int(value(kInputSeed, size_t(t) * kChannels + in)) * int(weight(c, in));
        }
        const int expected = requantize(accumulator);
        const int actual = output[size_t(t) * kChannels + c];
        max_diff = std::max(max_diff, std::abs(actual - expected));
        if (actual != expected) {
            std::printf("REFERENCE_MISMATCH sample=%u time=%d channel=%d expected=%d actual=%d\n",
                        sample, t, c, expected, actual);
            return false;
        }
    }
    return true;
}

void run_path(bool two_dimensional, dl::runtime_mode_t mode, int8_t* input_data,
              int8_t* weight_data, int8_t* output_data, const int8_t* reference, Result& result) {
    const std::vector<int> input_shape = two_dimensional
        ? std::vector<int>{1, kTime, 1, kChannels} : std::vector<int>{1, kTime, kChannels};
    const std::vector<int> weight_shape = two_dimensional
        ? std::vector<int>{1, 1, kChannels, kChannels} : std::vector<int>{1, kChannels, kChannels};
    // deep=false borrows the checked, aligned buffers. No hidden full copies.
    dl::TensorBase input(input_shape, input_data, kExponent, dl::DATA_TYPE_INT8, false, kCaps);
    dl::TensorBase filter(weight_shape, weight_data, kExponent, dl::DATA_TYPE_INT8, false, kCaps);
    dl::TensorBase output(input_shape, output_data, kExponent, dl::DATA_TYPE_INT8, false, kCaps);
    dl::module::Conv op(dl::Linear,
        two_dimensional ? std::vector<int>{0, 0, 0, 0} : std::vector<int>{0, 0},
        two_dimensional ? std::vector<int>{1, 1} : std::vector<int>{1},
        two_dimensional ? std::vector<int>{1, 1} : std::vector<int>{1},
        result.name, 1, dl::QUANT_TYPE_SYMM_8BIT);
    std::printf("BEGIN path=%s\n", result.name);
    std::fflush(stdout);
    uint32_t expected_hash = 0;
    for (int iteration = 0; iteration < 4; ++iteration) {
        // Distinct sentinels catch a missing or incomplete kernel execution.
        std::memset(output_data, iteration & 1 ? 0x5a : 0xa5, kElements);
        vTaskDelay(pdMS_TO_TICKS(20));
        const int64_t begin = esp_timer_get_time();
        op.run(std::vector<dl::TensorBase*>{&input, &filter},
               std::vector<dl::TensorBase*>{&output}, mode);
        const int64_t elapsed = esp_timer_get_time() - begin;
        if (iteration > 0) result.elapsed[size_t(iteration - 1)] = elapsed;
        result.hash = checksum(output_data);
        if (iteration == 0) expected_hash = result.hash;
        else if (result.hash != expected_hash) result.repeats_equal = false;
    }
    const bool scalar_ok = check_reference(output_data, result.reference_max_diff);
    if (reference) {
        for (size_t i = 0; i < kElements; ++i) {
            result.path_max_diff = std::max(result.path_max_diff,
                std::abs(int(output_data[i]) - int(reference[i])));
        }
    }
    result.passed = scalar_ok && result.repeats_equal && result.path_max_diff == 0;
    std::printf("CHECK path=%s passed=%d checksum=%08" PRIx32
                " reference_samples=128 reference_max_diff=%d path_max_diff=%d repeats_equal=%d\n",
                result.name, result.passed, result.hash, result.reference_max_diff,
                result.path_max_diff, result.repeats_equal);
    heap(result.name);
}

bool benchmark() {
    heap("before_buffers");
    Buffer input(kElements), filter(kWeights), out1d(kElements), out2d(kElements), out_multi(kElements);
    if (!input.data || !filter.data || !out1d.data || !out2d.data || !out_multi.data) {
        std::puts("FAIL reason=psram_allocation");
        return false;
    }
    for (size_t i = 0; i < kElements; ++i) input.data[i] = value(kInputSeed, i);
    // ESP-DL PIE int8 pack: (Co/16, K=1, Ci, Co%16), not plain Ci/Co.
    for (int block = 0; block < kChannels / 16; ++block) {
        for (int in = 0; in < kChannels; ++in) {
            for (int lane = 0; lane < 16; ++lane) {
                filter.data[(size_t(block) * kChannels + in) * 16 + lane] = weight(block * 16 + lane, in);
            }
        }
    }
    Result one{"conv1d_single"}, two{"conv2d_single"}, multi{"conv2d_multi"};
    run_path(false, dl::RUNTIME_MODE_SINGLE_CORE, input.data, filter.data, out1d.data, nullptr, one);
    run_path(true, dl::RUNTIME_MODE_SINGLE_CORE, input.data, filter.data, out2d.data, out1d.data, two);
    run_path(true, dl::RUNTIME_MODE_MULTI_CORE, input.data, filter.data, out_multi.data, out1d.data, multi);
    if (!one.passed || !two.passed || !multi.passed) {
        std::puts("FAIL reason=correctness_no_timing_claim");
        return false;
    }
    for (const Result* result : {&one, &two, &multi}) {
        auto sorted = result->elapsed;
        std::sort(sorted.begin(), sorted.end());
        std::printf("TIMING path=%s warmups=1 repetitions=3 us=%" PRId64 ",%" PRId64 ",%" PRId64
                    " median_us=%" PRId64 " macs=%" PRIu64 "\n", result->name,
                    result->elapsed[0], result->elapsed[1], result->elapsed[2], sorted[1], kMacs);
    }
    return true;
}
} // namespace

extern "C" void app_main() {
    // Give an attached USB console time to observe the beginning. No input,
    // filesystem, partition writes, NVS, microphone, or radio is initialized.
    vTaskDelay(pdMS_TO_TICKS(1500));
    std::printf("OPERATOR_PROBE version=1 target=esp32p4 idf=5.5.5 espdl=3.3.12 "
                "cpu_mhz=%d psram_bytes=%zu T=%d C=%d q_in=%d q_weight=%d q_out=%d "
                "input_seed=%08" PRIx32 " weight_seed=%08" PRIx32 "\n",
                CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ, esp_psram_get_size(), kTime, kChannels,
                kExponent, kExponent, kExponent, kInputSeed, kWeightSeed);
    bool ok = esp_psram_is_initialized();
    if (ok) ok = benchmark();
    else std::puts("FAIL reason=psram_unavailable");
    heap("after_buffers_freed");
    std::printf("OPERATOR_PROBE_DONE passed=%d\n", ok);
    std::fflush(stdout);
}
