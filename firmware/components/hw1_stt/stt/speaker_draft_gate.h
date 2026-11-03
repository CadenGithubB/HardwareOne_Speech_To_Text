#pragma once
// Experimental draft admission policy, opt-in in benchmark adapters only.
#include <cstdint>
namespace hw1::stt::speaker {
struct DraftGate {
    bool waiting=false;
    uint32_t since=0;
    // Called only for an eligible draft. Zero cap defers until no pending job.
    bool defer(bool pending,uint32_t now,uint32_t cap_ms) {
        if(!pending) { waiting=false; return false; }
        if(!waiting) { waiting=true; since=now; }
        if(!cap_ms || uint32_t(now-since)<cap_ms)return true;
        waiting=false;
        return false;
    }
    void reset() { waiting=false; }
};
}
