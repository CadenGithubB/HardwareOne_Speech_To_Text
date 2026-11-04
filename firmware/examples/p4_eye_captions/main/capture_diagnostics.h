#pragma once
#include "stt/stt_stream_metrics.h"
#if HW1_STT_STREAM_METRICS
#include "driver/i2s_pdm.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "stt/stt_stream.h"
namespace captions_perf {
void begin(SemaphoreHandle_t, hw1::stt::StreamPipeline*);
void lock(void*, hw1::stt::StreamOperation);
void unlock(void*, hw1::stt::StreamOperation);
bool attachMic(i2s_chan_handle_t, size_t read_bytes, size_t descriptors);
void warmBytes(size_t);
void modelIdentity(const char* name, const void* blob, size_t bytes);
void captureRead(uint64_t started_us, uint64_t read_us, uint64_t push_started_us,
                 uint64_t done_us, size_t bytes, esp_err_t error, bool accepted);
void level(uint32_t samples, uint32_t uptime_ms, uint16_t rms, uint16_t noise);
void request();
void poll();  // owner only, between inference calls; output is outside all locks
}
#endif
