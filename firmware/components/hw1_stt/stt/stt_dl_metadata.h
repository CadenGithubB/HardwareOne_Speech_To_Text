#pragma once
// Where ESP-DL keeps a model's long-lived metadata, and the runtime's own
// long-lived blocks (quartznet_runtime.cpp, HW1_STT_RESIDENT_MODEL=1).
//
// ESP-DL (the tree-local esp-dl staged by tools/p4/prepare_esp_dl.py,
// dl_tool_metadata.hpp) asks one allocator for every
// block a dl::Model keeps for its lifetime: the Model, context, loader and
// flatbuffer objects, module and tensor objects, per-channel exponent arrays,
// tensor shapes, module index vectors and Conv attributes, the tensor lists and
// execution plan, and the tensor-name map with its keys. installDlMetadataAllocator()
// makes that allocator an explicit PSRAM request:
//  - ps_alloc(size, AllocPolicy::PreferPSRAM, "stt.dl.<kind>") for blocks that
//    need no more than the heap's own 4-byte alignment (System_MemUtil: falls
//    back to internal RAM, counted in gPsAllocFallbacks and logged);
//  - for the few kinds ESP-DL aligns to 8 or 16 bytes (Model; module, tensor and
//    exponent blocks, as upstream's malloc_aligned did), heap_caps_aligned_alloc
//    with MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT, then internal RAM, counted the same
//    way. Never MALLOC_CAP_SIMD: that pads every block to the L2 cache line.
// Every block is returned through ps_free (any heap block is accepted, so
// objects prebuilt code allocated are freed correctly too). Nothing global
// changes: no malloc interception, no CONFIG_SPIRAM_MALLOC_ALWAYSINTERNAL
// threshold change. No metadata block is read by DMA or with the cache
// disabled: ESP-DL runs in tasks only, from flash, with the cache on.
//
// The hook is process-wide once installed (it stays until reboot): it also
// places the metadata of per-call STT models and of any ESP-DL model ESP-SR
// builds after it (WakeNet constructs this tree's dl::Model).
#include <cstddef>
#include <cstdint>
#include <limits>
#include <new>

namespace hw1::stt {

struct DlMetadataStats {
  uint32_t allocs = 0;         // blocks the hook served
  uint32_t bytes = 0;          // bytes requested for them
  uint32_t internal = 0;       // of those, blocks that landed in internal RAM (PSRAM refused or bypassed)
  uint32_t internalBytes = 0;  // bytes requested for those
  uint32_t failed = 0;         // requests neither heap could serve
  uint32_t frees = 0;          // non-null blocks returned through the hook
};
inline constexpr size_t kDlMetadataKinds = 11;  // dl::tool::kMetadataKinds (static_assert in the .cpp)

// Idempotent; call before building any model. Returns true once installed.
bool installDlMetadataAllocator();
bool dlMetadataAllocatorInstalled();
// Cumulative since boot, over all kinds or one kind (dl::tool::MetadataKind
// value). Updated atomically; a snapshot pair brackets one build, but another
// task building an ESP-DL model at the same time is counted too.
DlMetadataStats dlMetadataStats();
DlMetadataStats dlMetadataStats(size_t kind);
// The difference of two snapshots (after - before), field by field.
DlMetadataStats dlMetadataDelta(const DlMetadataStats& before, const DlMetadataStats& after);

// The runtime's own long-lived blocks (the resident model's bookkeeping):
// ps_alloc(size, AllocPolicy::PreferPSRAM, tag) / ps_free, counted in the
// same System_MemUtil fallback counter. Heap alignment (4 bytes on the P4).
void* sttPsramAlloc(size_t size, const char* tag);
void sttPsramFree(void* ptr);

// Out of memory where nullptr cannot be returned (a container): aborts, as ::operator new does.
[[noreturn]] void sttPsramBadAlloc(size_t size);

// std allocator over sttPsramAlloc (tag "stt.resident"); stateless.
template <class T>
struct PsramStlAllocator {
  using value_type = T;
  PsramStlAllocator() noexcept = default;
  template <class U>
  constexpr PsramStlAllocator(const PsramStlAllocator<U>&) noexcept {}
  T* allocate(size_t n) {
    static_assert(alignof(T) <= sizeof(void*), "the heap aligns blocks to the pointer size");
    if (n > std::numeric_limits<size_t>::max() / sizeof(T)) sttPsramBadAlloc(std::numeric_limits<size_t>::max());
    void* p = sttPsramAlloc(n * sizeof(T), "stt.resident");
    if (!p) sttPsramBadAlloc(n * sizeof(T));
    return static_cast<T*>(p);
  }
  void deallocate(T* p, size_t) noexcept { sttPsramFree(p); }
  friend bool operator==(const PsramStlAllocator&, const PsramStlAllocator&) noexcept { return true; }
  friend bool operator!=(const PsramStlAllocator&, const PsramStlAllocator&) noexcept { return false; }
};

}  // namespace hw1::stt
