// ESP-DL's metadata allocator and the runtime's PSRAM blocks (see stt_dl_metadata.h).
// HW1-HOSTTEST: test/host/test_stt_dl_metadata.py compiles this file on the host with
// fakes of System_MemUtil.h and the ESP-IDF heap headers.
#include "stt_dl_metadata.h"

#include <atomic>
#include <cstdlib>

#include "System_MemUtil.h"
#include "dl_tool_metadata.hpp"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_memory_utils.h"

namespace hw1::stt {
namespace {

static_assert(kDlMetadataKinds == dl::tool::kMetadataKinds, "one counter set per ESP-DL metadata kind");

constexpr uint32_t kPsram8Bit = MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT;
constexpr uint32_t kInternal8Bit = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
// The heap's own alignment for ps_alloc blocks (TLSF: 4 bytes on the P4).
constexpr size_t kHeapAlign = 4;

// ps_alloc tags, one per dl::tool::MetadataKind (order of the enum).
constexpr const char* kTags[kDlMetadataKinds] = {
    "stt.dl.model", "stt.dl.ctx",   "stt.dl.loader", "stt.dl.fbs",   "stt.dl.module", "stt.dl.tensor",
    "stt.dl.exp",   "stt.dl.shape", "stt.dl.index",  "stt.dl.list",  "stt.dl.names"};

struct Counters {
  std::atomic<uint32_t> allocs{0}, bytes{0}, internal{0}, internalBytes{0}, failed{0};
};
Counters gKinds[kDlMetadataKinds];
std::atomic<uint32_t> gFrees{0};
std::atomic<bool> gInstalled{false};

size_t kindIndex(dl::tool::MetadataKind kind) {
  const size_t k = static_cast<size_t>(kind);
  return k < kDlMetadataKinds ? k : 0;
}

// Aligned blocks (8 or 16 bytes): an explicit PSRAM request with the same
// policy as ps_alloc(PreferPSRAM): PSRAM, then internal RAM; internal only
// while the PSRAM bypass is on. Reported to the same fallback counter and
// allocation tracker as ps_alloc.
void* alignedPreferPsram(size_t align, size_t size, const char* tag) {
  const bool tryPsram = !psramBypassEnabled() && psramAvailableRuntime();
  void* p = tryPsram ? heap_caps_aligned_alloc(align, size, kPsram8Bit) : nullptr;
  if (!p) p = heap_caps_aligned_alloc(align, size, kInternal8Bit);
  const bool usedPsram = p && esp_ptr_external_ram(p);
  const bool fellBack = tryPsram && p && !usedPsram;
  if (fellBack) gPsAllocFallbacks.fetch_add(1, std::memory_order_relaxed);
  memAllocDebug("aligned", p, size, true, usedPsram, fellBack, tag);
  return p;
}

void* allocate(size_t size, size_t align, dl::tool::MetadataKind kind) {
  const size_t k = kindIndex(kind);
  void* p = align <= kHeapAlign ? ps_alloc(size, AllocPolicy::PreferPSRAM, kTags[k])
                                : alignedPreferPsram(align, size, kTags[k]);
  Counters& c = gKinds[k];
  if (!p) {
    c.failed.fetch_add(1, std::memory_order_relaxed);
    return nullptr;
  }
  c.allocs.fetch_add(1, std::memory_order_relaxed);
  c.bytes.fetch_add(uint32_t(size), std::memory_order_relaxed);
  if (!esp_ptr_external_ram(p)) {
    c.internal.fetch_add(1, std::memory_order_relaxed);
    c.internalBytes.fetch_add(uint32_t(size), std::memory_order_relaxed);
  }
  return p;
}

// Any heap block: ESP-DL also returns objects prebuilt code allocated with
// malloc_aligned or global new (ps_free is free(), which takes every block).
void release(void* p) {
  if (!p) return;
  gFrees.fetch_add(1, std::memory_order_relaxed);
  ps_free(p);
}

const dl::tool::MetadataAllocator kAllocator{allocate, release};

DlMetadataStats load(const Counters& c) {
  DlMetadataStats s;
  s.allocs = c.allocs.load(std::memory_order_relaxed);
  s.bytes = c.bytes.load(std::memory_order_relaxed);
  s.internal = c.internal.load(std::memory_order_relaxed);
  s.internalBytes = c.internalBytes.load(std::memory_order_relaxed);
  s.failed = c.failed.load(std::memory_order_relaxed);
  return s;
}

}  // namespace

bool installDlMetadataAllocator() {
  if (!gInstalled.load(std::memory_order_acquire)) {
    dl::tool::set_metadata_allocator(&kAllocator);
    gInstalled.store(true, std::memory_order_release);
  }
  return dl::tool::get_metadata_allocator() == &kAllocator;
}

bool dlMetadataAllocatorInstalled() { return dl::tool::get_metadata_allocator() == &kAllocator; }

DlMetadataStats dlMetadataStats(size_t kind) {
  return kind < kDlMetadataKinds ? load(gKinds[kind]) : DlMetadataStats{};
}

DlMetadataStats dlMetadataStats() {
  DlMetadataStats total;
  for (const Counters& c : gKinds) {
    const DlMetadataStats s = load(c);
    total.allocs += s.allocs;
    total.bytes += s.bytes;
    total.internal += s.internal;
    total.internalBytes += s.internalBytes;
    total.failed += s.failed;
  }
  total.frees = gFrees.load(std::memory_order_relaxed);
  return total;
}

DlMetadataStats dlMetadataDelta(const DlMetadataStats& before, const DlMetadataStats& after) {
  DlMetadataStats d;
  d.allocs = after.allocs - before.allocs;
  d.bytes = after.bytes - before.bytes;
  d.internal = after.internal - before.internal;
  d.internalBytes = after.internalBytes - before.internalBytes;
  d.failed = after.failed - before.failed;
  d.frees = after.frees - before.frees;
  return d;
}

void* sttPsramAlloc(size_t size, const char* tag) { return ps_alloc(size, AllocPolicy::PreferPSRAM, tag); }

void sttPsramFree(void* ptr) { ps_free(ptr); }

void sttPsramBadAlloc(size_t size) {
  ESP_LOGE("STT", "Out of memory for a %u-byte resident-model block", unsigned(size));
  std::abort();
}

}  // namespace hw1::stt
