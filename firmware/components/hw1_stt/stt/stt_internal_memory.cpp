#include "stt_internal_memory_core.h"
#include "sdkconfig.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_memory_utils.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <atomic>
namespace {
hw1::stt::InternalMemoryPolicy policy;
#if CONFIG_HEAP_USE_HOOKS
// 1 KiB on a 32-bit target; no per-allocation header, heap tracing buffer or
// task-tracking mode. The fast inactive path does not lock or allocate.
hw1::stt::InternalMemoryLedger ledger;
std::atomic<TaskHandle_t> owner{nullptr};
#endif
}
#if CONFIG_HEAP_USE_HOOKS
extern "C" void esp_heap_trace_alloc_hook(void* p,size_t bytes,uint32_t) {
    const auto task=owner.load(std::memory_order_acquire);
    if(!task || xPortInIsrContext() || xTaskGetCurrentTaskHandle()!=task || !esp_ptr_internal(p))return;
    ledger.allocated(p,bytes);
}
extern "C" void esp_heap_trace_free_hook(void* p) {
    const auto task=owner.load(std::memory_order_acquire);
    if(!task || xPortInIsrContext() || xTaskGetCurrentTaskHandle()!=task || !esp_ptr_internal(p))return;
    ledger.freed(p);
}
#endif
namespace hw1::stt {
InternalMemoryBudget internalMemoryBudget(bool resident) {return policy.budget(resident);}
InternalMemoryScope::InternalMemoryScope() {
#if CONFIG_HEAP_USE_HOOKS
    // STT serializes transcribe calls; never clear a nested active ledger.
    TaskHandle_t expected=nullptr;
    if(owner.compare_exchange_strong(expected,xTaskGetCurrentTaskHandle(),std::memory_order_acq_rel)) {
        // Only this task's non-ISR hooks can now enter; clearing does not allocate.
        ledger={};active_=true;
    }
#endif
}
InternalMemoryScope::~InternalMemoryScope() {
#if CONFIG_HEAP_USE_HOOKS
    if(active_)owner.store(nullptr,std::memory_order_release);
#endif
}
void InternalMemoryScope::success(bool resident) {
#if CONFIG_HEAP_USE_HOOKS
    if(!active_)return;
    const auto sample=ledger.sample();policy.observe(resident,sample);
    const auto need=policy.budget(resident);
    owner.store(nullptr,std::memory_order_release);active_=false;
    ESP_LOGI("STT","internal owned: resident=%u peak=%u largest=%u complete=%u need=%u block=%u",
             unsigned(resident),unsigned(sample.peak),unsigned(sample.largest),unsigned(sample.complete),
             unsigned(need.total),unsigned(need.contiguous));
#else
    (void)resident;
#endif
}
}
