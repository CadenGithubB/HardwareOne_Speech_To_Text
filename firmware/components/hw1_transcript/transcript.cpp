#include "transcript.h"
#include <cstring>
#include <cstdio>
#include <limits>

namespace hw1::transcript {
namespace {
bool letter(char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); }
char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + 'a' - 'A') : c; }
char upper(char c) { return c >= 'a' && c <= 'z' ? char(c - 'a' + 'A') : c; }
bool space(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n' || c == '\f' || c == '\v'; }
bool fail(char* out, size_t cap, const char* why) { if (out && cap) std::snprintf(out, cap, "%s", why); return false; }
bool spokenValid(const char* word) {
  if (!word) return false;
  const size_t n = std::strlen(word);
  if (!n || n > kSpokenBytes || !letter(word[0]) || !letter(word[n-1])) return false;
  for (size_t i = 0; i < n; ++i) if (!(word[i] >= 'a' && word[i] <= 'z') && word[i] != '\'') return false;
  return std::strstr(word, "''") == nullptr;
}
}
bool Vocabulary::put(const char* shown, const char* spoken, char* error, size_t cap) {
  if (error && cap) error[0] = 0;
  if (!shown || !*shown || std::strlen(shown) > kDisplayBytes) return fail(error, cap, "Display must contain 1-63 printable ASCII characters");
  // Printable ASCII keeps aliases compatible with the current caption alphabet/renderers.
  // No whitespace means a single recognized word cannot silently become a phrase.
  for (const char* p = shown; *p; ++p)
    if (*p < 33 || *p > 126 || *p == '|') return fail(error, cap, "Display must be one printable ASCII term without | or spaces");
  char derived[kSpokenBytes + 1]{};
  if (!spoken || !*spoken) {
    if (std::strlen(shown) > kSpokenBytes) return fail(error, cap, "Spoken form exceeds 31 characters");
    for (size_t i = 0; shown[i]; ++i) derived[i] = lower(shown[i]);
    spoken = derived;
  }
  if (!spokenValid(spoken)) return fail(error, cap, "Spoken form needs 1-31 lowercase letters with internal apostrophes; use DISPLAY|spoken");
  size_t index = count_;
  for (size_t i = 0; i < count_; ++i) if (!std::strcmp(words_[i].spoken, spoken)) { index = i; break; }
  if (index == count_ && count_ == kMaxWords) return fail(error, cap, "Vocabulary full (256 terms)");
  std::snprintf(words_[index].spoken, sizeof(words_[index].spoken), "%s", spoken);
  std::snprintf(words_[index].display, sizeof(words_[index].display), "%s", shown);
  if (index == count_) ++count_;
  return true;
}
bool Vocabulary::remove(const char* spoken) {
  if (!spoken) return false;
  for (size_t i = 0; i < count_; ++i) if (!std::strcmp(words_[i].spoken, spoken)) {
    for (size_t j = i + 1; j < count_; ++j) words_[j - 1] = words_[j];
    words_[--count_] = {};
    return true;
  }
  return false;
}
const char* Vocabulary::display(const char* raw, size_t bytes) const {
  for (size_t i = 0; i < count_; ++i) {
    const Word& w = words_[i];
    if (std::strlen(w.spoken) != bytes) continue;
    size_t j = 0;
    for (; j < bytes && w.spoken[j] == lower(raw[j]); ++j) {}
    if (j == bytes) return w.display;
  }
  return nullptr;
}
bool format(const char* raw, const Vocabulary& vocabulary, bool paragraphStart, char* output, size_t capacity) {
  if (!output || !capacity || !raw || raw == output) return false;
  output[0] = 0;
  size_t used = 0;
  const char* p = raw;
  while (*p) {
    while (space(*p)) ++p;
    if (!*p) break;
    const char* start = p;
    while (*p && !space(*p)) ++p;
    const size_t bytes = size_t(p - start);
    const char* alias = vocabulary.display(start, bytes);
    const char* value = alias ? alias : start;
    const size_t n = alias ? std::strlen(alias) : bytes;
    const size_t needed = n + (used ? 1 : 0);
    if (needed >= capacity - used) { output[0] = 0; return false; }
    if (used) output[used++] = ' ';
    const size_t begin = used;
    std::memcpy(output + used, value, n); used += n;
    if (!alias) {
      const bool pronoun = bytes == 1 && lower(start[0]) == 'i';
      const bool contraction = bytes >= 3 && lower(start[0]) == 'i' && start[1] == '\'' &&
          ((bytes == 3 && lower(start[2]) == 'm') ||
           (bytes == 4 && ((lower(start[2]) == 'v' && lower(start[3]) == 'e') ||
                           (lower(start[2]) == 'l' && lower(start[3]) == 'l') ||
                           (lower(start[2]) == 'r' && lower(start[3]) == 'e'))) ||
           (bytes == 3 && lower(start[2]) == 'd'));
      if (paragraphStart || pronoun || contraction) output[begin] = upper(output[begin]);
    }
    paragraphStart = false;
  }
  output[used] = 0;
  return true;
}
bool nextBoot(BootIdentity previous, bool powerOnReset, BootIdentity& next) {
  next = {};
  if (previous.boot == std::numeric_limits<uint64_t>::max() ||
      (powerOnReset && previous.powerOn == std::numeric_limits<uint64_t>::max())) return false;
  next.boot = previous.boot + 1;
  next.powerOn = previous.powerOn + (powerOnReset ? 1 : 0);
  // Durable only after the platform successfully commits it.
  return true;
}
}
