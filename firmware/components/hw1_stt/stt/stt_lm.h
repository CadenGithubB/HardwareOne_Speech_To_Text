#pragma once
#include <cstddef>
#include <cstdint>
// HW1LM1 word n-gram language model and CTC prefix beam search. The binding
// contract is experiments/stt_train/lm/FORMAT.md; the host builder/reference
// decoder and this implementation must agree on its parity fixtures.
// No filesystem, logging or task API here. ESP-IDF builds hash with mbedTLS,
// allocate the decode workspace in PSRAM and yield; host builds are portable.
namespace hw1::stt::lm {
inline constexpr size_t kClasses=29, kBlank=28, kSpace=0, kMaxBeam=64, kMaxFrames=4096;
inline constexpr size_t kMaxCustomWords=256, kMaxCustomWordBytes=31;
inline constexpr uint16_t kNoWord=0xffff;              // V <= 65535, so never a word id
inline constexpr int32_t kInvalidScore=INT32_MIN;
enum class LoadStatus : uint8_t {
    Ok, InvalidArgument, BadSize, BadMagic, BadVersion, BadHeader, BadLayout, BadPadding,
    BadChecksum, BadStrings, Unsorted, BadWordId, MissingSpecial
};
const char* describe(LoadStatus status);
bool sha256(const void* data, size_t bytes, uint8_t hash[32]);

// Zero-copy view over a complete .lm blob. The blob must stay alive and
// unmodified while the view, or a decode using it, exists. Open validates the
// header, section bounds/padding, SHA-256 trailer, string and n-gram order
// and word ids (linear, once); failure leaves the view empty.
class Lm {
 public:
    LoadStatus open(const uint8_t* data, size_t bytes);
    bool valid() const { return data_!=nullptr; }
    uint32_t vocab() const { return vocab_; }
    uint32_t bigrams() const { return bigrams_; }
    uint32_t trigrams() const { return trigrams_; }
    float alpha() const { return alpha_; }
    float beta() const { return beta_; }
    float unkLog10() const { return unk_; }
    uint32_t beamWidth() const { return beam_; }
    float charPrune() const { return prune_; }
    float hotwordBonus() const { return bonus_; }
    uint16_t bos() const { return bos_; }
    uint16_t eos() const { return eos_; }
    uint16_t unk() const { return unkId_; }
    const char* word(uint16_t id) const;              // nullptr when out of range
    int find(const char* word, size_t length) const;  // -1 when absent
    // ARPA backoff log10 x1000 of `word` after (w2, w1): p3(w2,w1,word), or
    // p2(w1,word) when w2==kNoWord. Integer sum of the quantised terms.
    int32_t score(uint16_t w2, uint16_t w1, uint16_t word) const;
    // The same value as the decoder uses it: a double sum of q/1000.0 terms
    // in the host reference's order (NaN for invalid ids).
    double log10(uint16_t w2, uint16_t w1, uint16_t word) const;
    // Bounds of log10() over all valid ids (every n-gram/backoff path, as
    // computed doubles; unkLog10 is separate), found by open(). The decoder
    // uses them only to skip work that provably cannot change its result.
    double log10Max() const { return log10Max_; }
    double log10Min() const { return log10Min_; }
 private:
    long findBigram(uint16_t a, uint16_t b) const;
    long findTrigram(uint16_t a, uint16_t b, uint16_t c) const;
    int32_t p2(uint16_t b, uint16_t c) const;
    double p2d(uint16_t b, uint16_t c) const;
    const uint8_t* data_=nullptr;
    const uint8_t *unigram_=nullptr, *offsets_=nullptr, *strings_=nullptr, *bigram_=nullptr, *trigram_=nullptr;
    uint32_t vocab_=0, bigrams_=0, trigrams_=0, strings_bytes_=0, beam_=0;
    float alpha_=0, beta_=0, unk_=0, prune_=0, bonus_=0;
    double log10Max_=0, log10Min_=0;
    uint16_t bos_=kNoWord, eos_=kNoWord, unkId_=kNoWord;
};

// Optional hotword list (UTF-8): lines split like Python str.splitlines(),
// each normalised like common.py::normalize_text; lines that are not then a
// single word of 1..31 bytes are ignored. Keeps the first 256 distinct words
// (hw1lm.py parse_custom_words). ~8 KiB, no heap.
class CustomWords {
 public:
    size_t parse(const char* data, size_t bytes);   // replaces contents; returns count
    bool contains(const char* word, size_t length) const;
    size_t size() const { return count_; }
    const char* word(size_t index) const { return index<count_ ? words_[index] : nullptr; }
 private:
    char words_[kMaxCustomWords][kMaxCustomWordBytes+1]{};
    uint16_t count_=0;
};

enum class DecodeStatus : uint8_t { Ok, InvalidArgument, OutOfMemory, Cancelled, OutputTooSmall };
struct DecodeControl {
    void* context=nullptr;
    bool (*cancelled)(void*)=nullptr;   // polled every 32 frames
};
struct DecodeStats {
    uint32_t frames=0, beam=0;
    uint32_t nodes=0;        // prefix nodes created (<= frames*beam+1)
    uint32_t candidates=0;   // scored candidates, all frames
    uint32_t completions=0;  // word LM evaluations (per prefix, only where the result can matter)
    size_t workspaceBytes=0;
    // Completed words in the actual initial/final context, excluding BOS/EOS.
    // 0..2 words; UINT8_MAX means that stage was not reached. The end context
    // includes a final partial word, before EOS and output-buffer truncation.
    // Each decode currently starts at BOS; no context is retained in Lm.
    uint8_t startHistoryWords=UINT8_MAX, endHistoryWords=UINT8_MAX;
};
// Bytes of the single workspace allocation decode() makes for this shape:
// 40*(frames*beam+1) nodes + 4*pow2(2*(frames*beam+1)) prefix index
// + 44*beam beams/heap + 48*29*beam candidates + 34*min(pow2(max(256,
// 2*frames)),8192) word/n-gram memo + ~4.7 KiB tables. 0 if out of range.
size_t workspace_bytes(size_t frames, size_t beam);
// logits: int8 model output [frames x 29], value = q * 2^exponent (ESP-DL
// sign: the P4 model's -2; hw1lm.py writes the same scale as +2); per-frame
// log_softmax is applied here. beam 0 uses the file's beam_width. char_prune
// skips non-blank tokens below it except the repeat of the prefix's last
// symbol, matching hw1lm.py (FORMAT.md leaves that case implicit). Text is the
// best prefix without a trailing space, NUL-terminated even on failure
// (OutputTooSmall keeps the leading capacity-1 bytes). strength must be finite
// in [0,1]: scale alpha, beta and the custom-word bonus together, preserving
// their balance. 1 preserves file/reference behavior; 0 is acoustic-only CTC
// beam search (not greedy). The checked blob and Lm view are never modified.
DecodeStatus decode(const int8_t* logits, size_t frames, int exponent, const Lm& lm,
                    const CustomWords* words, char* text, size_t capacity,
                    const DecodeControl& control={}, size_t beam=0, DecodeStats* stats=nullptr,
                    float strength=1.0f);
}
