#pragma once
#include <cstddef>
#include <cstdint>
#include "stt_internal_memory.h"
namespace hw1::stt {
// Bounded, allocation-free ledger. Only its owning task accesses it. A free
// from another task can overestimate lifetime; it can never reduce the budget.
struct InternalMemoryLedger {
    struct Block { void* pointer; size_t bytes; };
    Block blocks[128]{};
    size_t live=0, peak=0, largest=0;
    bool overflow=false;
    __attribute__((always_inline)) inline void allocated(void* p,size_t n) {
        if(!p)return;
        if(n>largest)largest=n;
        // ESP-IDF emits an alloc hook (no free hook) for in-place realloc.
        for(auto& b:blocks)if(b.pointer==p){live-=b.bytes;b.bytes=n;live+=n;if(live>peak)peak=live;return;}
        for(auto& b:blocks)if(!b.pointer){b={p,n};live+=n;if(live>peak)peak=live;return;}
        overflow=true;
    }
    __attribute__((always_inline)) inline void freed(void* p) {
        for(auto& b:blocks)if(b.pointer==p && p){live-=b.bytes;b={};return;}
    }
    InternalMemorySample sample() const {return {peak,largest,!overflow};}
};
struct InternalMemoryPolicy {
    InternalMemorySample measured[2]{};
    void observe(bool resident,InternalMemorySample s) {
        if(!s.complete)return;
        auto& m=measured[resident?1:0];m.complete=true;
        if(s.peak>m.peak)m.peak=s.peak;
        if(s.largest>m.largest)m.largest=s.largest;
    }
    InternalMemoryBudget budget(bool resident) const {
        const auto& m=measured[resident?1:0];
        // Retain conservative cold/resident floors until full hardware peak
        // qualification; measured owned allocations may raise, never lower them.
        // Margin covers allocator headers, child-worker/driver work and races.
        constexpr size_t margin=32*1024, blockMargin=1024;
        const size_t floor=(resident?128:150)*1024;
        const size_t total=m.complete && m.peak+margin>floor?m.peak+margin:floor;
        const size_t block=m.complete && m.largest+blockMargin>margin?m.largest+blockMargin:margin;
        return {total,block};
    }
};
}
