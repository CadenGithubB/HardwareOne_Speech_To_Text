#pragma once
#include "stt_model_identity.h"
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
namespace hw1::stt::container {
inline constexpr size_t kHeaderBytes=96;
static_assert(identity::kCompressedBytes<=std::numeric_limits<size_t>::max()-kHeaderBytes);
inline uint32_t word(const uint8_t* p) {
    return uint32_t(p[0]) | uint32_t(p[1])<<8 | uint32_t(p[2])<<16 | uint32_t(p[3])<<24;
}
inline bool valid_size(size_t bytes) { return bytes==kHeaderBytes+identity::kCompressedBytes; }
// Only a complete, exactly identified envelope may reach decompression. The
// codec is pinned too: 1 = zlib payload, 0 = stored (payload is the raw graph). The
// runtime separately verifies the decompressed SHA before invoking ESP-DL.
inline bool valid_header(const uint8_t* header,size_t available,size_t bytes) {
    return header && available==kHeaderBytes && valid_size(bytes)
        && std::memcmp(header,"HW1STT1\0",8)==0
        && word(header+8)==1 && word(header+12)==identity::kCodec
        && word(header+16)==identity::kRawBytes && word(header+20)==identity::kCompressedBytes
        && word(header+24)==identity::kSampleRate && word(header+28)==identity::kMaxSamples
        && std::memcmp(header+32,identity::kRawSha,32)==0
        && std::memcmp(header+64,identity::kFrontendSha,32)==0;
}
inline bool read_header(void* context,size_t bytes,size_t (*read)(void*,void*,size_t)) {
    if(!read || !valid_size(bytes))return false;
    uint8_t header[kHeaderBytes];size_t have=0;
    while(have<sizeof(header)) {
        const size_t amount=read(context,header+have,sizeof(header)-have);
        if(!amount || amount>sizeof(header)-have)return false;
        have+=amount;
    }
    return valid_header(header,have,bytes);
}
} // namespace hw1::stt::container
