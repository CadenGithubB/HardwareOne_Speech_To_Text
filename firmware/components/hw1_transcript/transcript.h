#pragma once
#include <cstddef>
#include <cstdint>

namespace hw1::transcript {
constexpr size_t kMaxWords = 256, kSpokenBytes = 31, kDisplayBytes = 63;
struct Word { char spoken[kSpokenBytes + 1]{}; char display[kDisplayBytes + 1]{}; };
// Owned by the application/inference task. Edits are applied between decodes.
// TSV on disk: DISPLAY<TAB>spoken, or DISPLAY alone for ASCII case-only entries.
class Vocabulary {
 public:
  bool put(const char* display, const char* spoken, char* error, size_t capacity);
  bool remove(const char* spoken);
  const char* display(const char* word, size_t bytes) const;
  size_t count() const { return count_; }
  const Word& at(size_t i) const { return words_[i]; }
  void clear() { count_ = 0; }
 private:
  Word words_[kMaxWords]{};
  size_t count_ = 0;
};
// No heap, filesystem, guessed punctuation or change to raw recognition input.
// Returns false on insufficient space; output is an empty string, never a
// plausible-looking truncated transcript. Callers should retain/show raw text.
bool format(const char* raw, const Vocabulary& vocabulary, bool paragraphStart,
            char* output, size_t capacity);
// Status-only identity. durable=false means counters must not be used as a
// persistent ordering key. The application supplies its platform persistence.
struct BootIdentity {
  uint64_t boot = 0, powerOn = 0;
  bool durable = false;
};
bool nextBoot(BootIdentity previous, bool powerOnReset, BootIdentity& next);
}
