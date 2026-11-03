# STT experiment results — provisional, 3 November 2026

This is a concise ledger for the 24 required experiments. It is **not a completion
report**: all 24 initial screens now have measured outcomes. This does not finish
qualification: the broader production/x2f comparison and mandatory watchdog matrix
are still running/pending. No new general recognition/speaker-accuracy improvement
has been qualified for production. The completed clean-storage vocabulary comparison
shows no target-term gain and is not promoted.

The approved 889-directory cleanup is independently verified: all target directories
are absent and 7,618,560 bytes were free versus 331,776 before cleanup. All archived
files were header-only. Eight subsequent captures completed with no filesystem-full
errors; forced re-decode still had one watchdog at a different sampled location.

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
| 24 | Four-term bounded vocabulary bias | Six clean-storage captures complete. No target-term gain; synthetic WER worse than both controls, natural unknowns higher than both. One late-control alignment rejected. No promotion. |

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

Remaining: finish the broader pacing comparison and mandatory watchdog repeats, verify each mechanism was exercised,
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

## Clean-storage qualification: first finalized control

The new baseline-before synthetic vocabulary fixture completed 16 captions. WER is
15.04% (20 edits / 133 words), 1/8 target terms recognized, zero vocabulary-term
insertions on controls, zero raw unknown labels, zero watchdogs including setup,
zero overruns and no panic. The RMS/clock fit passed. Filesystem free space was
7,606,272 bytes before and 7,593,984 after this capture. This is one simple single-voice
control, not a demonstrated accuracy gain or general stability qualification. Candidate
and trailing controls remain pending; do not combine this with the old storage-confounded
attempts as a matched comparison. Natural conv3 baseline capture is running.

Private numeric provenance is `overnight/clean-qualification-partial-metrics.json` and
its alignment report under the existing ignored run root. Only finalized captures are
scored; later snapshots may extend this checkpoint.

## Completed clean-storage vocabulary comparison and priority watchdog repeats

All six vocabulary captures completed, followed by the two archived-image conv3
watchdog reruns. Models, pauses, speaker rules and recorded image hashes were preserved.
The explicitly approved storage cleanup changed the runtime environment; these are
not claims of an identical filesystem state or proof of a sole historical cause.

| Synthetic target/control fixture | WER | Target hits / 8 | Control-term insertions | Unknowns / captions |
|---|---:|---:|---:|---:|
| baseline before | 15.04% | 1/8 | 0 | 0/16 |
| vocabulary | 21.05% | 0/8 | 0 | 0/16 |
| baseline after | 18.05% | 0/8 | 0 | 0/16 |

No target-term gain was established. Candidate WER exceeds both controls on this
fixture; it is a single synthetic voice and all three runs scored 16/16 eligible
speaker identities. The 1.5-nat ceiling was nonbinding: the tested existing bonus is
1.0 nat. Do not promote this four-term configuration or infer that every vocabulary
setting/domain is ineffective.

| Natural conv3 | WER | Raw unknowns / captions | Correct / eligible | Final median / p90 ms | Shown-text lag ms | Label after text ms | Session / all watchdogs |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline before | 28.76% | 9/47 | 35/46 | 1475 / 2275 | 1153 | 2037 | 0 / 0 |
| vocabulary | 26.82% | 10/47 | 31/45 | 1516 / 2582 | 1227 | 2279 | 0 / 0 |
| baseline after | 27.04% | 3/46 | withheld | withheld | 1233 | 2111 | 0 / 0 |
| forced re-decode repeat | 27.04% | 10/47 | withheld | withheld | 1495 | 11461 | 1 / 1 |
| wider-beam repeat | 28.33% | 9/44 | 23/41 | 1605 / 3227 | 1264 | 2049 | 0 / 0 |

Speaker lag is **label availability minus final-caption publication**, as defined by
`benchscore.py`; it is additional delay after text, not speech-end-to-label latency.
Shown-text lag uses the device's voiced-end anchor. Final median/p90 uses accepted
reference alignment and covered clip ends. Do not add medians to invent an end-to-end
speaker metric. Mixed-reference exclusions for the qualified natural captures are
1 (baseline before), 2 (vocabulary), and 3 (wider beam); no-reference exclusions are zero.

The late baseline and forced-redecode repeat failed the unchanged RMS quality gate,
so their reference identity and true-end lag are withheld. The late control's odd-split
correlation was 0.6416, below 0.65. Global WER, raw coverage, device-internal delays and
watchdog counts do not require that alignment. Synthetic clips lack `speech_end_s`;
true-end lag is explicitly unavailable, with no clip-end substitution. The scorer now
reports that missing annotation instead of a traceback. Its existing scoring checks
and a functional check on the real synthetic/natural captures passed; the rejected
alignments remain rejected.

Vocabulary conv3 WER beats the late control by only one word, while unknowns are 10
versus controls 9/3, and qualified identity is 31/45 versus the early control's 35/46.
That does not establish a quality-preserving gain. Wider-beam WER falls within control
drift; its 23/41 eligible identities include ten merge errors. No promotion.

The old vocabulary failure stopped capture at 100.15s with 21 session / 24 whole-log
watchdogs and 22 filesystem-full errors. Its unchanged-image clean-storage rerun
completed 234.368s of capture over the whole 220.04s fixture, with zero watchdogs or
filesystem-full errors. The wider-beam warning did not recur in its clean repeat.

Forced re-decode still produced one warning: the old event sampled flash/cache IPC
at capture +50.612s; the clean repeat sampled ESP-DL convolution workers on both cores
at +118.817s. This is a different location/position, not a reproduced old signature or
a demonstrated kernel defect. One more clean same-image/fixture repeat is queued.
Its 11.461s additional label delay, unchanged WER versus the late control, and warning
support retaining exact-coverage speculative reuse.

All eight captures completed without panic, audio overruns or filesystem-full messages.
The only watchdog was the forced-redecode event. Minimum observed internal/PSRAM free
values were 183,488 / 1,599,692 bytes. These are screens, not long-soak, held-out-speaker
or production qualification. Private provenance: `clean-vocabulary-qualified-summary.json`,
`clean-eight-final-rms-metrics.json`, `clean-eight-final-status-estimate-metrics.json`,
`vocabulary-failure-reproduction-comparison.json` and
`forced-redecode-clean-watchdog-comparison.json`, all under the ignored overnight folder.
