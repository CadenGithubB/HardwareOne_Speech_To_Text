#pragma once
#include <cstdint>
namespace hw1::stt {
// Experimental 1.25x recognition-only PCM gain. Exact integer arithmetic;
// nearest integer with halves away from zero, followed by int16 saturation.
inline int16_t recognition_gain_125(int16_t sample) {
    const int32_t scaled=int32_t(sample)*5;
    const int32_t rounded=(scaled+(scaled>=0 ? 2 : -2))/4;
    return int16_t(rounded>32767 ? 32767 : rounded<-32768 ? -32768 : rounded);
}
}
