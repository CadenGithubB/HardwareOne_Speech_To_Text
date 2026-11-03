#pragma once
#include <cstdint>
#include <cstddef>
namespace hw1::stt {
// Benchmark policy: retain exact-input promotion or force completed-phrase decode.
inline bool promote_speculative(uint32_t requested,uint32_t completed,size_t cached_samples,
                                size_t final_samples,bool force_redecode=false) {
    return !force_redecode && requested && requested==completed && cached_samples==final_samples;
}
}
