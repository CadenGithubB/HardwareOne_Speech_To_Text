// Host check of the portable overlap decision rule (firmware/components/hw1_stt/stt/overlap_rule.h).
// With no arguments: constructed cases. With a file argument: reads int8 logits ([frame][3]) split
// into chunks of 100 frames, prints "frames marked fraction flag" for tests/test_overlap_rule.py to
// compare against the Python reference used for the host scores.
#include "stt/overlap_rule.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>

using namespace hw1::stt::overlap;

static void constructed() {
    Rule rule;
    uint8_t marks[64];
    const int exponent = -3;
    // Strongly "two" logits: class 2 = 10.0 (80/8), others 0 -> posterior ~1.
    int8_t two[3] = {0, 0, 80}, one[3] = {80, 0, 0};
    std::vector<int8_t> seq;
    auto push = [&](const int8_t* v, int n) { for (int i = 0; i < n; ++i) seq.insert(seq.end(), v, v + 3); };
    // 9 marked frames (below min_run 10) then 11 unmarked: run dropped -> fraction 0.
    push(two, 9); push(one, 11);
    Accumulator a(marks, sizeof marks);
    a.add(seq.data(), 20, exponent, rule);
    Decision d = a.decide(rule);
    assert(d.frames == 20 && d.marked == 0 && d.fraction == 0.0f && !d.flag);
    // 10 marked frames split across two chunks (6 + 4) survive the filter: fraction 10/20 >= 0.36.
    seq.clear(); push(two, 6);
    Accumulator b(marks, sizeof marks);
    b.add(seq.data(), 6, exponent, rule);
    seq.clear(); push(two, 4); push(one, 10);
    b.add(seq.data(), 14, exponent, rule);
    d = b.decide(rule);
    assert(d.frames == 20 && d.marked == 10 && std::fabs(d.fraction - 0.5f) < 1e-6f && d.flag);
    // Threshold edge: 7 marked of 20 = 0.35 < 0.36 -> no flag; needs a run >= 10 to count, so use 10 of 28.
    seq.clear(); push(two, 10); push(one, 18);
    Accumulator c(marks, sizeof marks);
    c.add(seq.data(), 28, exponent, rule);
    d = c.decide(rule);
    assert(d.marked == 10 && !d.flag);           // 10/28 = 0.357 < 0.360
    // Capacity overflow counts frames but cannot mark them.
    uint8_t small[4];
    Accumulator e(small, sizeof small);
    seq.clear(); push(two, 12);
    e.add(seq.data(), 12, exponent, rule);
    assert(e.overflow() && e.decide(rule).frames == 12 && e.decide(rule).marked == 0);
    // Quantization of the silence constant saturates to -128 at exponent -3.
    assert(quantize_bin(std::log(std::ldexp(1.0f, -24)), -3) == -128);
    assert(quantize_bin(0.0f, -3) == 0 && quantize_bin(-1.0f, -3) == -8 && quantize_bin(20.0f, -3) == 127);
    std::puts("constructed cases ok");
}

int main(int argc, char** argv) {
    if (argc < 2) { constructed(); return 0; }
    FILE* f = std::fopen(argv[1], "rb");
    if (!f) return 2;
    std::vector<int8_t> logits(1 << 20);
    const size_t n = std::fread(logits.data(), 1, logits.size(), f);
    std::fclose(f);
    const size_t frames = n / 3;
    std::vector<uint8_t> marks(frames + 1);
    Rule rule;
    Accumulator acc(marks.data(), marks.size());
    for (size_t start = 0; start < frames; start += 100)
        acc.add(logits.data() + start * 3, std::min<size_t>(100, frames - start), -3, rule);
    const Decision d = acc.decide(rule);
    std::printf("%u %u %.9f %d\n", d.frames, d.marked, double(d.fraction), d.flag ? 1 : 0);
    return 0;
}
