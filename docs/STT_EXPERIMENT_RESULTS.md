# STT experiment results — provisional, 3 November 2026

This is a concise ledger for the 24 required experiments. It is **not a completion
report**: 23 of 24 initial screens are measured. The vocabulary comparison is
incomplete; watchdog repeats and broader candidate qualification remain. The earlier
approved cleanup freed 757,760 bytes, but later storage pressure invalidated the two
failed vocabulary conv3 attempts. A current audit found no filesystem-full messages
in the other 36 captures checked (13–18, 20 and 21–23 plus vocabulary controls/target).
Absence of that message does not resolve their other qualification limits.
See [STT_ACTIONABLE_FINDINGS.md](STT_ACTIONABLE_FINDINGS.md) for ordered next actions
and [STT_OVERNIGHT_EXPERIMENTS.md](STT_OVERNIGHT_EXPERIMENTS.md) for detailed results.

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
| 09 | Highest-energy contiguous speaker window | Float gain; P4 mixed. Conv4 improves, conv2 regresses. Corrected-reference analysis remains mixed; replication required. |
| 10 | Defer new drafts while speaker jobs are pending | Ten-run scheduling comparison: strong label-speed gain, but WER/draft freshness worse than both surrounding controls. Reject default change. |
| 11 | Limit draft deferral to 100ms | Mixed across two fixtures; no general label/quality benefit established. No default change. |
| 12 | Draft pacing multiplier x2 → x3 | Less logged draft compute, inconsistent label gain and quality/freshness costs. No default change. |
| 13 | 1.25x recognition-input gain | Conv2 WER beats both controls; conv3 WER exceeds both. No general quality-preserving win. |
| 14 | Adaptive speech floor 45 → 41 | WER falls within broad control drift; poor conv3 identity. No reliable general win. |
| 15 | Pre-roll 300 → 450ms | Poor conv3 identity and 19 raw unknowns versus controls 3/11. No promotion. |
| 16 | Retained tail 500 → 600ms | WER falls within control drift; conv3 identity/true lag remain unqualified after RMS gate failure. |
| 17 | LM strength ×0.9 | Successful 0.900 decodes; WER worse than both controls on both fixtures. No promotion. |
| 18 | Decoder beam width ×1.25 | No general quality win; one conv3 session watchdog and lower PSRAM headroom. No promotion. |
| 19 | Require confidence gap ≥0.08 for profile updates | Independent device-embedding replay regresses identity metrics. Reject. |
| 20 | Speaker-input RMS normalization | Float gain did not transfer to P4: conv2 unknowns 1/38 → 19/38, correct labels 28/38 → 18/38; conv4 also trails fresh control. No promotion. |

| 21 | Freeze noise-floor/history adaptation during speech | All captures/controls complete. WER 18.84/26.61% versus final controls 19.04/26.39%; initial apparent gain is not established beyond control drift. No promotion. |
| 22 | Maximum segment 10 → 8s | All natural/stress captures and controls complete. Stress WER 16.67% versus controls 12.00/13.33%; natural identity mixed. Cut mechanism exercised; no promotion. |
| 23 | Force completed-phrase re-decode | All captures/controls complete. Label medians 7.363/14.744s versus initial 2.690/3.199s; five audio-pressure rejections and one session watchdog. Conv3 reference alignment rejected. No promotion. |

## Incomplete physical comparison

| ID | Single change | Current scope |
|---|---|---|
| 24 | Four-term bounded vocabulary bias | Baseline target/natural captures and candidate target captured. Candidate natural capture failed with filesystem-full errors. Same-image repeat interrupted under the same storage pressure, with zero captions. Final controls and clean repeat missing; no vocabulary quality/failure claim. |

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
- Float gains do not establish P4 gains. Energy selection remains mixed; normalization
  increased unknowns sharply on conv2 and also trailed its conv4 control. Neither is
  ready for adoption.
- Recognition controls drifted: identical-image WER changed 15.83 → 22.85% on conv2
  and 24.89 → 30.47% on conv3. Estimated noise floors rose too. Candidate results
  inside that range are not causal regressions or demonstrated wins. One wider-beam
  capture had a session watchdog; one tail capture lacks qualified alignment.
- Earlier conv1-only hold/merge gains do not generalize cleanly. Always report unknowns,
  one-to-one identity accuracy, splits and merges together.

## Interpretation and remaining work

Live true-lag numbers before the measurement-correction entry are superseded: the
early harness failed to shift `speech_end_s`. The corrected scorer rebuilds all clocks
from original references; a separate RMS/clock estimate repairs stale status onset.
Original artifacts remain intact, and sparse RMS agreement is not absolute precision.
The live references still use estimated playback onset. The scorer retains alignment
sensitivity, mixed/no-reference exclusions and missing labels; absolute manifest-end
latencies and per-phrase attribution remain provisional. No held-out-speaker success,
raw sample-clock microphone correlation, SD power-loss behavior or battery-life gain is claimed.

Remaining: resolve storage headroom, finish vocabulary and mandatory watchdog repeats, verify each mechanism was exercised,
score target corrections versus control insertions, inspect faults and memory, compare
both bracketing baselines, and produce the final 24-item report. Promising candidates
need repeat/held-out qualification before production promotion. Verify final production
restoration, ring reconnect disabled, board lock released, and repository status.

Raw audio, captions, device logs, model artifacts and flash backups stay ignored/private.

## Vocabulary partial screen — not complete

The three finalized captures were scored with rebuilt reference timing and independently
accepted RMS/clock fits. On the 16-phrase synthetic target/control fixture (133 words),
baseline WER was 17.29% (23 edits), candidate WER 20.30% (27 edits). Each recognized
1/8 expected target terms; each had zero vocabulary-term insertions on the eight control
phrases. Vocabulary activation was observed only in the candidate. This partial screen
shows no target-term improvement; one run and a missing trailing control do not establish
a causal WER regression. The simple single-voice fixture scored 16/16 speaker identities
in both runs and is not a similar-speaker qualification. The finalized natural baseline
WER was 28.97%; the failed natural candidate is excluded from full-reference WER.

The comparison remains incomplete: finish the unchanged natural candidate under usable
storage conditions, mandatory watchdog reproduction, and trailing controls. Private numeric
provenance is in `private/resume-20261102/overnight/24-partial-rms-metrics.json` and the
matching alignment report. Audio, terms and captions remain private.
