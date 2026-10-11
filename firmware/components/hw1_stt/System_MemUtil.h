#pragma once
// The small part of HardwareOne's System_MemUtil.h that the STT engine uses
// (stt_dl_metadata.cpp), implemented in System_MemUtil.cpp on the ESP-IDF heap
// without Arduino. Blocks are requested explicitly from PSRAM and fall back to
// internal RAM; nothing global (no malloc interception) changes.
#include <atomic>
#include <cstddef>
#include <cstdint>

enum class AllocPref : uint8_t {
  PreferPSRAM = 0,      // SPIRAM|8BIT, then INTERNAL|8BIT
  PreferInternal = 1,   // INTERNAL|8BIT, then SPIRAM|8BIT
  RequirePSRAM = 2,     // SPIRAM|8BIT only
  RequireInternal = 3,  // INTERNAL|8BIT only
  DefaultHeap = 4       // plain malloc
};
using AllocPolicy = AllocPref;

// True when a byte-addressable external heap is registered (total size, not free size).
bool psramAvailableRuntime();
// A global "never use PSRAM" switch; always off in this component.
inline bool psramBypassEnabled() { return false; }
// Counts successful PreferPSRAM allocations that had to use internal RAM.
extern std::atomic<uint32_t> gPsAllocFallbacks;
// Allocation debug hook; a no-op here (weak, so an app may define its own).
extern "C" void memAllocDebug(const char* op, void* ptr, size_t size, bool requestedPS, bool usedPS,
                              bool fellBack, const char* tag);

void* ps_alloc(size_t size, AllocPolicy policy, const char* tag);
void* ps_calloc(size_t n, size_t size, AllocPolicy policy, const char* tag);
void ps_free(void* ptr);
