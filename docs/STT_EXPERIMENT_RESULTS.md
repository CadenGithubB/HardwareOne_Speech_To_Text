# STT experiment results — provisional, 3 November 2026

This is a concise ledger for the 24 required experiments. It is **not a completion
report**: physical measurements are incomplete. Approved, verified diagnostic-log cleanup recovered
757,760 bytes of internal flash space, and the physical queue has resumed. Ring reconnect
was confirmed off after reboot; setup watchdog warnings remain in the stability record. The detailed protocol, exact
numbers, raw-artifact locations and limitations are in
[STT_OVERNIGHT_EXPERIMENTS.md](STT_OVERNIGHT_EXPERIMENTS.md).

No experimental production defaults have been adopted. No branches were pushed.
Hardware tests use the verified P4, fixed models, 64-byte cache lines and 250 MHz
PSRAM, with app-only flashing and production restoration between serialized groups.

## Completed screens and comparisons

| ID | Single change | Evidence and disposition |
|---|---|---|
| 01 | Label an ambiguous match when cosine gap ≥0.08 | Device-embedding replay: coverage improves, but extra identity errors. Reject promotion. |
| 02 | Create profiles from 1.5s rather than 2s phrases | Independent replay: more splits; reordered accuracy regresses. Reject. |
| 03 | Require 3s phrases to update profiles | Independent replay: coverage and accuracy regress. Reject. |
| 04 | Cap centroid history at eight observations | Short screen null; repeated-history stress has order-dependent gains and sequential losses. No promotion; not a natural long-session qualification. |
| 05 | Hold uncertain creation only for young profiles | Recorded-order accuracy improves, but shuffled merge errors increase. Reject promotion. |
| 06 | Resolve unknowns using up to three later phrases | Two recorded unknowns resolved, including one extra identity error. Reject promotion. |
| 07 | Increase profile capacity 8 → 10 | No recorded gain; slightly worse shuffled accuracy. Reject. |
| 08 | Speaker window 300 → 400 frames | Fixed-weight float accuracy improves, but merges increase. No promotion; quantized/P4 effects unchecked. |
| 09 | Highest-energy contiguous speaker window | Float gain; P4 mixed. Conv4 improves, conv2 regresses. Repeat/alignment validation required before promotion. |
| 10 | Defer new drafts while speaker jobs are pending | Ten-run scheduling comparison: strong label-speed gain, but WER/draft freshness worse than both surrounding controls. Reject default change. |
| 11 | Limit draft deferral to 100ms | Mixed across two fixtures; no general label/quality benefit established. No default change. |
| 12 | Draft pacing multiplier x2 → x3 | Less logged draft compute, inconsistent label gain and quality/freshness costs. No default change. |
| 19 | Require confidence gap ≥0.08 for profile updates | Independent device-embedding replay regresses identity metrics. Reject. |

## Implemented; physical results pending

| ID | Single change | Current scope |
|---|---|---|
| 13 | 1.25x recognition-input gain | Exact PCM arithmetic tested; both P4 fixtures measured. Conv2 WER improves, conv3 WER/identity/latency worsen; trailing baseline pending. |
| 14 | Adaptive speech floor 45 → 41 | Independent image built; physical recognition batch pending behind arm13. |
| 15 | Pre-roll 300 → 450ms | Independent image built; physical recognition batch pending behind arm13. |
| 16 | Retained tail 500 → 600ms | Independent image built; physical recognition batch pending behind arm13. |
| 17 | LM strength ×0.9 | Image built; require successful LM decoding at changed strength. |
| 18 | Decoder beam width ×1.25 | Image built; observed file beam 32 implies requested beam 40. Require successful decode; check memory/fallback. |
| 20 | Speaker-input RMS normalization | Small positive float screen; independent P4 image built and queued. |
| 21 | Freeze noise-floor/history adaptation during speech | Opt-in C++ policy and mechanism test pass; independent P4 image queued. |
| 22 | Maximum segment 10 → 8s | Sample conservation checked; independent image queued, with separate long-speech stress controls. |
| 23 | Force completed-phrase re-decode | Baseline already guards exact speculative coverage. Counterfactual policy tested and built; P4 queued. |
| 24 | Four-term bounded vocabulary bias | Decoder mechanism tested; frozen target/control fixture and independent image queued. Actual effective bonus is existing 1.0 nat under a 1.5 ceiling. |

Rows marked queued/built are not counted as measured device results. Offline identity
replays cannot establish firmware speed or stability. Host float windows do not prove
quantized-device accuracy. Rejected configurations do not prove their entire hypothesis
can never help under another setting or domain.

## Strongest observations so far

- Draft contention is real. Full deferral reduced median speaker-network time to about
  767ms and label delay to about 883–886ms across conv2/conv4, while worsening WER and
  draft freshness in this comparison.
- Speaker labels remain sensitive to capture/segmentation and phrase order. Identical
  baseline images gave conv4 one-to-one accuracy 32/34 and 26/34. That variability must
  not be mistaken for a candidate's causal effect.
- Energy-selected windows and loudness normalization are research leads, with positive
  float results. Energy selection's first P4 result is mixed; normalization is unmeasured
  on P4. Neither is ready for automatic adoption.
- Earlier conv1-only hold/merge gains do not generalize cleanly. Always report unknowns,
  one-to-one identity accuracy, splits and merges together.

## Interpretation and remaining work

The live references use estimated playback onset. The scorer retains alignment
sensitivity, mixed/no-reference exclusions and missing labels; absolute manifest-end
latencies and per-phrase attribution remain provisional. No held-out-speaker success,
acoustic correlation, SD power-loss behavior or battery-life gain is claimed.

Remaining: complete queued physical batches, verify each mechanism was exercised,
score target corrections versus control insertions, inspect faults and memory, compare
both bracketing baselines, and produce the final 24-item report. Promising candidates
need repeat/held-out qualification before production promotion. Verify final production
restoration, ring reconnect disabled, board lock released, and repository status.

Raw audio, captions, device logs, model artifacts and flash backups stay ignored/private.
