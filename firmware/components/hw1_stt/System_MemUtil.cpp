// See System_MemUtil.h.
#include "System_MemUtil.h"

#include <cstdlib>
#include <cstring>

#include "esp_heap_caps.h"
#include "esp_memory_utils.h"

std::atomic<uint32_t> gPsAllocFallbacks{0};

extern "C" __attribute__((weak)) void memAllocDebug(const char*, void*, size_t, bool, bool, bool, const char*) {}

bool psramAvailableRuntime() { return heap_caps_get_total_size(MALLOC_CAP_SPIRAM) > 0; }

namespace {
constexpr uint32_t kPsram = MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT;
constexpr uint32_t kInternal = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
}  // namespace

void* ps_alloc(size_t size, AllocPolicy policy, const char* tag) {
  if (!size) return nullptr;
  void* p = nullptr;
  bool requestedPs = false;
  switch (policy) {
    case AllocPolicy::PreferPSRAM:
      requestedPs = true;
      if (psramAvailableRuntime()) p = heap_caps_malloc(size, kPsram);
      if (!p) p = heap_caps_malloc(size, kInternal);
      break;
    case AllocPolicy::PreferInternal:
      p = heap_caps_malloc(size, kInternal);
      if (!p && psramAvailableRuntime()) p = heap_caps_malloc(size, kPsram);
      break;
    case AllocPolicy::RequirePSRAM:
      requestedPs = true;
      if (psramAvailableRuntime()) p = heap_caps_malloc(size, kPsram);
      break;
    case AllocPolicy::RequireInternal:
      p = heap_caps_malloc(size, kInternal);
      break;
    case AllocPolicy::DefaultHeap:
      p = std::malloc(size);
      break;
  }
  const bool usedPs = p && esp_ptr_external_ram(p);
  const bool fellBack = requestedPs && p && !usedPs;
  if (fellBack) gPsAllocFallbacks.fetch_add(1, std::memory_order_relaxed);
  memAllocDebug("alloc", p, size, requestedPs, usedPs, fellBack, tag);
  return p;
}

void* ps_calloc(size_t n, size_t size, AllocPolicy policy, const char* tag) {
  if (n && size > SIZE_MAX / n) return nullptr;
  void* p = ps_alloc(n * size, policy, tag);
  if (p) std::memset(p, 0, n * size);
  return p;
}

// Every heap_caps block and every malloc block is accepted (one heap).
void ps_free(void* ptr) { heap_caps_free(ptr); }
