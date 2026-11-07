#include "overlap_gate.h"
#include "dl_model_base.hpp"
#include "esp_timer.h"
#include <new>

namespace hw1::stt::overlap {

const char* describe(LoadStatus s) {
    switch (s) {
        case LoadStatus::Ok: return "ok";
        case LoadStatus::BadModel: return "ESP-DL model rejected";
        case LoadStatus::BadShape: return "unexpected input/output";
        case LoadStatus::NoMemory: return "no memory";
    }
    return "unknown";
}

Gate::~Gate() { reset(); }

void Gate::reset() {
    delete model_;
    model_ = nullptr;
    input_ = output_ = nullptr;
}

LoadStatus Gate::load(const uint8_t* blob, size_t bytes, bool selfTest) {
    reset();
    if (!blob || bytes < 64 || ((uintptr_t(blob)) & 15)) return LoadStatus::BadModel;
    LoadReport rep;
    // Same construction as the speaker trunk and the resident recognizer: in place on the caller's
    // PSRAM copy, internal RAM limit 0, metadata through the installed PSRAM allocator.
    const int64_t build0 = esp_timer_get_time();
    model_ = new (std::nothrow) dl::Model(reinterpret_cast<const char*>(blob), fbs::MODEL_LOCATION_IN_FLASH_RODATA, 0,
                                          dl::MEMORY_MANAGER_GREEDY, nullptr, false);
    if (!model_) return LoadStatus::NoMemory;
    rep.buildUs = uint32_t(esp_timer_get_time() - build0);
    const int modules = model_->module_count();
    if (modules <= 0 || modules > 256) { reset(); return LoadStatus::BadModel; }
    rep.modules = uint16_t(modules);
    model_->get_arena_size(&rep.arenaPsram, &rep.arenaInternal);
    auto& ins = model_->get_inputs();
    auto& outs = model_->get_outputs();
    if (ins.size() != 1 || outs.size() != 1) { reset(); return LoadStatus::BadShape; }
    input_ = ins.begin()->second;
    output_ = outs.begin()->second;
    const auto& is = input_->shape;
    const auto& os = output_->shape;
    const bool shapes = is.size() == 4 && is[0] == 1 && size_t(is[1]) == kChunkFrames && is[2] == 1 && size_t(is[3]) == kMelBins &&
                        os.size() == 4 && os[0] == 1 && size_t(os[1]) == kChunkOutputs && os[2] == 1 && size_t(os[3]) == kClasses;
    if (!shapes || input_->dtype != dl::DATA_TYPE_INT8 || output_->dtype != dl::DATA_TYPE_INT8 ||
        input_->exponent.is_per_channel() || output_->exponent.is_per_channel()) {
        reset();
        return LoadStatus::BadShape;
    }
    rep.inputExponent = int(input_->exponent);
    rep.outputExponent = int(output_->exponent);
    if (selfTest) {
        const int64_t t0 = esp_timer_get_time();
        rep.testResult = int(model_->test());
        rep.testUs = uint32_t(esp_timer_get_time() - t0);
    }
    report_ = rep;
    return LoadStatus::Ok;
}

int8_t* Gate::input() { return model_ ? static_cast<int8_t*>(input_->data) : nullptr; }

const int8_t* Gate::run() {
    if (!model_) return nullptr;
    model_->run(dl::RUNTIME_MODE_SINGLE_CORE);
    return static_cast<const int8_t*>(output_->data);
}

}  // namespace hw1::stt::overlap
