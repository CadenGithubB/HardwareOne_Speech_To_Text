#include "transcript.h"
#include <cassert>
#include <cstring>
#include <cstdio>
#include <string>
using namespace hw1::transcript;
int main() {
  Vocabulary v; char error[160], out[4096];
  assert(v.put("HardwareOne", nullptr, error, sizeof(error)));
  assert(v.put("OpenAI", nullptr, error, sizeof(error)));
  assert(v.put("ESP32", "esp", error, sizeof(error)));
  assert(!v.put("ESP32", nullptr, error, sizeof(error)));
  assert(!v.put("bad word", "bad", error, sizeof(error)));
  assert(!v.put("Bad", "Bad", error, sizeof(error)));
  assert(!v.put("Bad", "bad word", error, sizeof(error)));
  assert(!v.put("Bad", "'bad", error, sizeof(error)));
  assert(v.count() == 3);
  assert(format("  i think\t hardwareone\n and openai  ", v, true, out, sizeof(out)));
  assert(!std::strcmp(out, "I think HardwareOne and OpenAI"));
  assert(format("i'm going and i've said i'll do it i'd like", v, false, out, sizeof(out)));
  assert(!std::strcmp(out, "I'm going and I've said I'll do it I'd like"));
  assert(format("hardwareoneish esp", v, false, out, sizeof(out)));
  assert(!std::strcmp(out, "hardwareoneish ESP32"));
  assert(format("this is", v, true, out, sizeof(out)));
  assert(!std::strcmp(out, "This is"));
  assert(format("still the same paragraph", v, false, out, sizeof(out)));
  assert(!std::strcmp(out, "still the same paragraph"));
  assert(format("  \n\t ", v, true, out, sizeof(out)) && !out[0]);
  assert(!format("hardwareone", v, true, out, 5) && !out[0]);
  assert(format("a", v, false, out, 2) && !std::strcmp(out, "a"));
  assert(!format("a", v, false, out, 1) && !out[0]);
  assert(v.put("OPENAI", "openai", error, sizeof(error)) && v.count() == 3);
  assert(v.remove("openai") && v.count() == 2 && !v.remove("openai"));
  assert(!v.display("openai", 6));
  Vocabulary full;
  for (size_t i = 0; i < kMaxWords; ++i) {
    std::string word = "word"; size_t n = i;
    for (int j = 0; j < 3; ++j) { word += char('a' + n % 26); n /= 26; }
    assert(full.put(word.c_str(), nullptr, error, sizeof(error)));
  }
  assert(!full.put("extra", nullptr, error, sizeof(error)));
  assert(full.put("WORDaaa", "wordaaa", error, sizeof(error)));
  BootIdentity next;
  assert(nextBoot({}, true, next) && next.boot == 1 && next.powerOn == 1 && !next.durable);
  BootIdentity previous = next;
  assert(nextBoot(previous, false, next) && next.boot == 2 && next.powerOn == 1);
  previous.boot = UINT64_MAX;
  assert(!nextBoot(previous, false, next) && !next.durable);
  previous = {}; previous.powerOn = UINT64_MAX;
  assert(!nextBoot(previous, true, next));
  // Raw is immutable and output growth cannot corrupt caller sentinels.
  const std::string raw = "i hardwareone ";
  for (size_t cap = 1; cap < 40; ++cap) {
    char guarded[48]; std::memset(guarded, '#', sizeof(guarded));
    const bool ok = format(raw.c_str(), v, true, guarded + 1, cap);
    assert(guarded[0] == '#' && guarded[cap + 1] == '#');
    if (ok) assert(!std::strcmp(guarded + 1, "I HardwareOne")); else assert(!guarded[1]);
    assert(raw == "i hardwareone ");
  }
  std::puts("transcript formatting, vocabulary bounds and startup ordering passed");
}
