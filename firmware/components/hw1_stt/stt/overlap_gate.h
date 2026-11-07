#pragma once
// Overlap gate: a small ESP-DL int8 classifier on the recognizer's raw 64-bin log-mel rows,
// run once per final caption segment in fixed 200-frame chunks. It emits a flag beside the
// speaker label; it never touches the caption. Model file: a bare ESP-DL .espdl (W8A8, esp32p4)
// with input [1, 200, 1, 64] and output [1, 100, 1, 3], exported by tools/overlap_gate/g2_export.py.
// Decision rule: overlap_rule.h. docs/STT_OVERLAP_GATE_PHASE4_PLAN.md.
#include "overlap_rule.h"
#include <cstddef>
#include <cstdint>

namespace dl { class Model; class TensorBase; }

namespace hw1::stt::overlap {

inline constexpr size_t kMelBins = 64, kChunkFrames = 200, kChunkOutputs = 100;

enum class LoadStatus : uint8_t { Ok, BadModel, BadShape, NoMemory };
const char* describe(LoadStatus status);

struct LoadReport {
    uint32_t buildUs = 0, testUs = 0;
    int testResult = -1;          // dl::Model::test() on the file's embedded values: 0 ok, -1 not run
    size_t arenaPsram = 0, arenaInternal = 0;
    uint16_t modules = 0;
    int inputExponent = 0, outputExponent = 0;
};

class Gate {
 public:
    Gate() = default;
    ~Gate();
    Gate(const Gate&) = delete;
    Gate& operator=(const Gate&) = delete;
    // blob: the whole .espdl, 16-byte aligned, kept alive by the caller until reset().
    LoadStatus load(const uint8_t* blob, size_t bytes, bool selfTest);
    void reset();
    bool ready() const { return model_ != nullptr; }
    const LoadReport& loadReport() const { return report_; }
    int inputExponent() const { return report_.inputExponent; }
    int outputExponent() const { return report_.outputExponent; }
    // The int8 input buffer ([200][64], channel-last) the caller fills before run().
    int8_t* input();
    // Runs one chunk; returns the int8 logits ([100][3]) or nullptr.
    const int8_t* run();

 private:
    dl::Model* model_ = nullptr;
    dl::TensorBase* input_ = nullptr;
    dl::TensorBase* output_ = nullptr;
    LoadReport report_;
};

}  // namespace hw1::stt::overlap
