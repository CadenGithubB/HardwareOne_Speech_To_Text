#pragma once
// Private diagnostic model reconstruction. No allocator or production loader changes.
// Callers verify the base envelope/raw SHA and reconstructed target SHA separately.
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace hw1::diagnostic {
struct ModelDelta {
    const uint8_t* bytes = nullptr;
    size_t length = 0, base_bytes = 0, target_bytes = 0;
    size_t segments = 0, literal_offset = 0, literal_bytes = 0;
};
inline uint32_t deltaWord(const uint8_t* p) {
    return uint32_t(p[0]) | uint32_t(p[1]) << 8 |
           uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
// Validate the complete plan before writing any destination bytes. Subtractions
// keep all bounds checks safe on the P4's 32-bit size_t.
inline bool parseModelDelta(const void* data, size_t length, size_t baseBytes,
                            const uint8_t* baseSha, const uint8_t* targetSha,
                            size_t targetBytes, ModelDelta& result) {
    result = {};
    if (!data || !baseSha || !targetSha || length < 88 || !baseBytes || !targetBytes) return false;
    const auto* p = static_cast<const uint8_t*>(data);
    if (std::memcmp(p, "HW1DLT1\0", 8) || deltaWord(p+8) != baseBytes ||
        deltaWord(p+12) != targetBytes || std::memcmp(p+24, baseSha, 32) ||
        std::memcmp(p+56, targetSha, 32)) return false;
    const size_t count = deltaWord(p+16), literals = deltaWord(p+20);
    if (!count || count > (length-88)/16) return false;
    const size_t start = 88+count*16;
    if (literals != length-start) return false;
    size_t written = 0;
    for (size_t i=0; i<count; ++i) {
        const auto* segment = p+88+i*16;
        const size_t dest=deltaWord(segment), source=deltaWord(segment+4);
        const size_t size=deltaWord(segment+8), literal=deltaWord(segment+12);
        if (dest != written || !size || size > targetBytes-written) return false;
        if (source == UINT32_MAX) {
            if (literal > literals || size > literals-literal) return false;
        } else if (literal != UINT32_MAX || source > baseBytes || size > baseBytes-source) return false;
        written += size;
    }
    if (written != targetBytes) return false;
    result = {p,length,baseBytes,targetBytes,count,start,literals};
    return true;
}
using DeltaReadAt = size_t (*)(void*, size_t, void*, size_t);
using DeltaYield = void (*)();
// The source is immutable and separate from destination; this is not an
// in-place patcher. A failed read leaves a partial, unverified destination that
// must never reach the model parser. Callers free it and retain the original.
inline bool applyModelDelta(const ModelDelta& delta, DeltaReadAt read,
                            void* context, void* destination, size_t capacity,
                            DeltaYield yield = nullptr) {
    if (!delta.bytes || !read || !destination || capacity < delta.target_bytes) return false;
    auto* output = static_cast<uint8_t*>(destination);
    for (size_t i=0; i<delta.segments; ++i) {
        const auto* segment = delta.bytes+88+i*16;
        const size_t dest=deltaWord(segment), source=deltaWord(segment+4);
        const size_t size=deltaWord(segment+8), literal=deltaWord(segment+12);
        for (size_t done=0; done<size;) {
            const size_t n = size-done > 65536 ? 65536 : size-done;
            if (source == UINT32_MAX) {
                std::memcpy(output+dest+done, delta.bytes+delta.literal_offset+literal+done, n);
            } else if (read(context,source+done,output+dest+done,n) != n) return false;
            done += n;
            if (yield) yield();
        }
    }
    return true;
}
} // namespace hw1::diagnostic
