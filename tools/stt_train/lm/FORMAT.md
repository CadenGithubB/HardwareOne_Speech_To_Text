# HW1LM1: word n-gram LM + CTC beam decoder contract

Shared contract between the host tools (`experiments/stt_train/lm/`) and the
firmware decoder (`components/hardwareone/stt/`). Both sides implement the
decoder below; outputs must agree on the parity fixtures.

## Text normalisation
Same as `experiments/stt_train/common.py::normalize_text`: lowercase `a-z`,
apostrophe, single spaces. Model vocab (29 classes): index 0 = space,
1..26 = `a`..`z`, 27 = `'`, 28 = CTC blank.

## File layout (little-endian, `.lm`)
Header, 64 bytes:

| off | type | field |
|---:|---|---|
| 0 | char[8] | magic `HW1LM1\0\0` |
| 8 | u32 | version = 1 |
| 12 | u32 | V vocab size (<= 65535, includes `<s>`, `</s>`, `<unk>`) |
| 16 | u32 | n_bigrams |
| 20 | u32 | n_trigrams |
| 24 | u32 | strings_bytes |
| 28 | f32 | alpha: LM weight (multiplies natural-log LM probability) |
| 32 | f32 | beta: word insertion bonus, nats per completed word |
| 36 | f32 | unk_log10: flat log10 probability for any out-of-vocabulary word (no context, no backoff) |
| 40 | u32 | beam_width (1..64) |
| 44 | f32 | char_prune: skip non-blank tokens whose frame log-prob (nats) is below this |
| 48 | u32 | total_bytes: whole file size including the SHA-256 trailer |
| 52 | f32 | hotword_bonus: nats added when a completed word is in the custom word list |
| 56 | u8[8] | reserved, zero |

Sections follow, in order; each starts at a 4-byte-aligned offset (zero padding):

1. `unigram[V]`: `{i16 log10_q, i16 backoff10_q}`
2. `string_offset[V]`: `u32`, offset of word i in the strings blob
3. strings blob (`strings_bytes`): NUL-terminated words, **byte-order sorted,
   strictly increasing; word id = index**. `<s>`, `</s>`, `<unk>` appear by
   their literal strings (find them by binary search).
4. `bigram[n_bigrams]`: `{u16 w1, u16 w2, i16 log10_q, i16 backoff10_q}`, sorted by (w1, w2)
5. `trigram[n_trigrams]`: `{u16 w1, u16 w2, u16 w3, i16 log10_q}`, sorted by (w1, w2, w3)
6. padding to 4 bytes, then a 32-byte SHA-256 of every preceding byte.

Quantisation: `log10 value = q / 1000.0`. Missing backoff = 0.

## LM scoring (standard ARPA backoff, log10)
```
p3(a,b,c) = trigram(a,b,c) if present else backoff2(a,b) + p2(b,c)
p2(b,c)   = bigram(b,c)    if present else backoff1(b) + p1(c)
p1(c)     = unigram(c)
```
`backoff2(a,b)` is the bigram entry's backoff (0 if the bigram is absent).
Context starts as `(<s>)`: the first word uses `p2(<s>, w)`, later words use
`p3(w_{-2}, w_{-1}, w)`. An OOV word scores `unk_log10` flat and **is still
pushed into the context as `<unk>`**. Natural log = log10 * ln(10).

## Decoder (CTC prefix beam search with word LM)
Input: T x 29 natural-log probabilities (log_softmax of the dequantised
model output per frame).

Each beam = character prefix (no leading space, no double spaces) with
`p_b`, `p_nb` (CTC, nats), `lm` (accumulated alpha*ln P + beta + hotword
bonuses, nats), LM context (last two word ids) and the current partial word.

Per frame, for every beam:
- blank: `p_b'[prefix] += total(prefix) + lp[blank]`
- repeat of the last char c: `p_nb'[prefix] += p_nb + lp[c]`, and
  `p_nb'[prefix+c] += p_b + lp[c]`
- any other non-blank char c with `lp[c] >= char_prune`:
  `p_nb'[prefix+c] += total(prefix) + lp[c]`
- space when the prefix is empty or already ends in space: treated like
  blank (added to `p_b'[prefix]`), never creates a new prefix.
- space after a letter completes the partial word: the new beam's `lm` gains
  `alpha * ln10 * log10P(word | context) + beta (+ hotword_bonus if listed)`.

`total = logsumexp(p_b, p_nb)`. Beams with the same prefix merge by
logsumexp of `p_b` and `p_nb` (the LM part is identical by construction).
Keep the top `beam_width` by `total + lm`; ties break by prefix bytes,
ascending.

Finish: for each beam, if a partial word remains, score it like a space
completion (but emit no trailing space), then add
`alpha * ln10 * log10P(</s> | context)`. Return the best prefix.

## Custom words
Optional plain text file, one word per line, normalised as above; at most
256 words of at most 31 bytes; other lines are ignored. On the device it
lives at `/STT Models/custom_words.txt`, next to the model and
`/STT Models/meeting.lm`.
