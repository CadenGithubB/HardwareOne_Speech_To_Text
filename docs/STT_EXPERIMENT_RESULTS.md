# STT experiment screening results — completed, 3 November 2026

All 24 agreed changes have implemented, measured screens, and the broader pacing
comparison plus mandatory watchdog reruns are complete. This is a completed experimental
report, not production qualification. X2f is the preferred pacing candidate; no new
general recognition/speaker-accuracy gain is established. Defaults remain unchanged.
The final closure section records repeats, variability, exclusions and unchecked scope.

The approved 889-directory cleanup is independently verified: all target directories
are absent and 7,618,560 bytes were free versus 331,776 before cleanup. All archived
files were header-only. Eight subsequent captures completed with no filesystem-full
errors; forced re-decode still had one watchdog at a different sampled location.

Original-six offline reference numbers were corrected during the final audit; the
latest correction section below supersedes the older 194-phrase figures. Dispositions
are unchanged. See [STT_ACTIONABLE_FINDINGS.md](STT_ACTIONABLE_FINDINGS.md) for ordered next actions
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
| 07 | Increase profile capacity 8 → 10 | No recorded gain; corrected shuffled accuracy unchanged at reported precision, with a small split increase. Reject. |
| 08 | Speaker window 300 → 400 frames | Fixed-weight float accuracy improves, but merges increase. No promotion; quantized/P4 effects unchecked. |
| 09 | Highest-energy contiguous speaker window | Float gain; P4 mixed. Conv4 improves, conv2 regresses. Corrected-reference analysis remains mixed; further replication would be needed for adoption. |
| 10 | Defer new drafts while speaker jobs are pending | Ten-run scheduling comparison: strong label-speed gain, but WER/draft freshness worse than both surrounding controls. Reject default change. |
| 11 | Limit draft deferral to 100ms | Mixed across two fixtures; no general label/quality benefit established. No default change. |
| 12 | Draft pacing multiplier x2 → x3 | Less logged draft compute, inconsistent label gain and quality/freshness costs. No default change. |
| 13 | 1.25x recognition-input gain | Initial conv2 WER beats both controls and conv3 exceeds both; clean conv3 WER is 29.40% under changed, unbracketed conditions. No general win. |
| 14 | Adaptive speech floor 45 → 41 | WER falls within broad control drift; poor conv3 identity. No reliable general win. |
| 15 | Pre-roll 300 → 450ms | Initial conv3 has 19 unknowns versus controls 3/11; clean repeat has two. Changed, unbracketed conditions do not establish a causal benefit or harm. No promotion. |
| 16 | Retained tail 500 → 600ms | Initial WER falls within control drift and its conv3 fit is rejected; the clean repeat is qualified but unbracketed. No established benefit. |
| 17 | LM strength ×0.9 | Successful 0.900 decodes; initial WER worse than both controls on both fixtures. Later unbracketed variability does not establish benefit. No promotion. |
| 18 | Decoder beam width ×1.25 | No general quality win; original conv3 watchdog did not recur in clean repeats. Lower PSRAM headroom; no promotion. |
| 19 | Require confidence gap ≥0.08 for profile updates | Independent device-embedding replay regresses identity metrics. Reject. |
| 20 | Speaker-input RMS normalization | Initial P4 conv2 harm did not recur in a clean repeat (28/38 correct, one unknown); conv4 repeat is 25/34 with eight unknowns. No consistent benefit; no promotion. |
| 21 | Freeze noise-floor/history adaptation during speech | All captures/controls complete. WER 18.84/26.61% versus final controls 19.04/26.39%; initial apparent gain is not established beyond control drift. No promotion. |
| 22 | Maximum segment 10 → 8s | All natural/stress captures and controls complete. Stress WER 16.67% versus controls 12.00/13.33%; natural identity mixed. Cut mechanism exercised; no promotion. |
| 23 | Force completed-phrase re-decode | Initial labels 7.363/14.744s versus controls 2.690/3.199s; clean tests retain extra label delay and warnings. Conv3 reference fits rejected. Keep reuse; no promotion. |
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
  initially increased conv2 unknowns, but that harm did not recur in its clean repeat.
  Conv4 remains inconsistent; neither setting has a robust adoption result.
- Recognition controls drifted: identical-image WER changed 15.83 → 22.85% on conv2
  and 24.89 → 30.47% on conv3. Estimated noise floors rose too. Candidate results
  inside that range are not causal regressions or demonstrated wins. One wider-beam
  capture had a session watchdog; one tail capture lacks qualified alignment.
- Earlier conv1-only hold/merge gains do not generalize cleanly. Always report unknowns,
  one-to-one identity accuracy, splits and merges together.

## Interpretation and qualification limits

Live true-lag numbers before the measurement-correction entry are superseded: the
early harness failed to shift `speech_end_s`. The corrected scorer rebuilds all clocks
from original references; a separate RMS/clock estimate repairs stale status onset.
Original artifacts remain intact, and sparse RMS agreement is not absolute precision.
The live references still use estimated playback onset. The scorer retains alignment
sensitivity, mixed/no-reference exclusions and missing labels; absolute manifest-end
latencies and per-phrase attribution remain provisional. No held-out-speaker success,
raw sample-clock microphone correlation, SD power-loss behavior or battery-life gain is claimed.

The requested screens, broader pacing comparison, target/control scoring and warning
reruns are complete. Future production adoption still needs approval and separate
held-out/long-soak qualification. Final restoration and repository/process checks are
recorded in the closure below.

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

## Completed broader production/x2f pacing comparison — 3 November

All twelve ABBA captures completed: production before, x2f A, x2f B, production after,
two of each per conv2–4. Fixture order reversed in the second half. Both images use
the same fixed models, speaker diagnostics, 64-byte L2, 250 MHz PSRAM and 600/1000ms
pauses; SDK configs are byte-identical. Production is pacing multiplier 1 / first-fast 0;
x2f is multiplier 2 / first-fast 1. This compares the existing pacing package, not the
isolated causal effect of either field. Microphone input used the same hashed private
WAVs through Mac mini speakers at 50%, with ring reconnect off and runtime peers closed.

All twelve RMS/clock fits passed the unchanged gate. No identity or reference-lag rows
were dropped. No panic, audio overrun or filesystem-full message occurred. Minimum
observed internal/PSRAM free values were 183,748 / 1,789,896 bytes. Fixed production
was restored and verified before the mandatory watchdog backfill acquired the board.

| Fixture / arm | WER | Unknowns / captions | Correct / eligible | Split / merge | True final median / p90 ms | Shown-text ms | Label after text ms | Session / all WD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| conv2 / prod-before | 19.24% | 1/38 | 29/38 | 0 / 8 | 1854 / 2656 | 1258 | 5435.5 | 1 / 1 |
| conv2 / x2f-a | 18.44% | 2/38 | 28/38 | 0 / 8 | 1978 / 2968 | 1260 | 1942 | 0 / 0 |
| conv2 / x2f-b | 22.24% | 1/36 | 27/36 | 0 / 8 | 1988 / 2909 | 1279 | 1650 | 0 / 0 |
| conv2 / prod-after | 23.05% | 2/35 | 23/34 | 0 / 9 | 2064 / 3268 | 1345 | 12510 | 2 / 2 |
| conv3 / prod-before | 28.76% | 4/44 | 36/43 | 3 / 1 | 1717 / 2559 | 1096 | 12720 | 1 / 1 |
| conv3 / x2f-a | 28.11% | 4/48 | 43/48 | 1 / 1 | 1470 / 2127 | 1201 | 1963.5 | 0 / 0 |
| conv3 / x2f-b | 28.76% | 5/47 | 38/46 | 3 / 1 | 1504 / 2632 | 1232 | 2458 | 0 / 0 |
| conv3 / prod-after | 29.61% | 5/47 | 36/46 | 5 / 1 | 1526 / 2621 | 1150 | 10061 | 1 / 1 |
| conv4 / prod-before | 19.57% | 4/35 | 31/35 | 0 / 0 | 2215 / 3233 | 1452 | 22769 | 3 / 3 |
| conv4 / x2f-a | 18.09% | 4/34 | 30/34 | 0 / 0 | 2561 / 3459 | 1525 | 2754 | 0 / 0 |
| conv4 / x2f-b | 23.40% | 2/33 | 30/32 | 0 / 0 | 2331 / 3342 | 1622 | 2406 | 0 / 0 |
| conv4 / prod-after | 25.11% | 3/35 | 32/35 | 0 / 0 | 2244 / 3434 | 1452 | 23503 | 3 / 3 |

WER is global; unknowns count every published caption. One-to-one identity includes
unknowns among eligible captions. Mixed-reference exclusions are production/x2f:
conv2 1/0, conv3 2/1, conv4 0/1; no-reference exclusions are zero. Reference final-lag
coverage varies: conv2 misses 0/0/1/1 clips in table order, conv3 5/2/2/1, conv4 0/1/1/1.
Shown text uses the device voiced-end anchor. Speaker-label delay is additional time
**after final-caption publication**, not after speech end. Do not add separate medians.

| Fixture | Mean WER production → x2f | Pooled correct / eligible production → x2f | Raw unknowns / captions production → x2f | Range of per-run median label delay, production → x2f |
|---|---:|---:|---:|---:|
| conv2 | 21.145% → 20.340% | 52/72 → 55/74 | 3/73 → 3/74 | 5.436–12.510s → 1.650–1.942s |
| conv3 | 29.185% → 28.435% | 72/89 → 81/94 | 9/91 → 9/95 | 10.061–12.720s → 1.964–2.458s |
| conv4 | 22.340% → 20.745% | 63/70 → 60/66 | 7/70 → 6/67 | 22.769–23.503s → 2.406–2.754s |

Means/pools describe two runs per configuration, not new independent speakers or a
statistical noninferiority result. WER and pooled speaker correctness hold in this
screen, with no raw-unknown increase; individual repeated WER values still vary.
X2f is the preferred pacing candidate for subsequent qualification. Its label-speed
benefit now extends beyond conv1. No default change or general accuracy gain is claimed.

Tradeoffs remain visible: x2f shown-text medians are slightly later on all fixtures;
conv4 reference-final medians are 2.331/2.561s versus production 2.215/2.244s. It does
not make every latency metric better. Keep production 600/1000ms closing pauses.

Production logged 11 session/whole-log watchdog warnings in all six captures, versus
zero in all six x2f captures. Production warnings recur in its later same-image/input
controls. Most sample ESP-DL workers; conv4 also samples decoder and math code. For
example, conv2 depthwise-worker warnings occur at capture +124.057 and +121.585s;
conv4 warnings near +181.442/+181.739s sample different code. These are recurrent
warning-bearing cases, not identical-PC deterministic reproductions or proof of an
ESP-DL defect. The broader mandatory matrix and extra clean forced-redecode repeat
remain active. Do not promote production defaults while qualification is unresolved.

Private numeric provenance: `pacing-final-analysis-status.json` in the ignored run
root; `pacing-final-alignment.json`, `pacing-final-rms-metrics.json`,
`pacing-final-status-estimate-metrics.json`, `pacing-qualified-summary.json` and
`watchdog-repeat-matrix.json` in its overnight folder. The unqualified status-estimate
report was used only for alignment-independent fields; all published identity/final-lag
values come from the strict qualified report. Two legacy SD-input repeats are serialized
behind the live backfill, reuse existing audio, and end with fixed-production restoration
and a fresh persisted ring-off/capacity readback. These final checks are not complete yet.

## Corrected original-six speaker-rule references — 3 November

This section supersedes the earlier 01–07 and 19 device-replay numbers and their
repeated-history follow-up. The six original completed captures all pass the existing
RMS/clock alignment gate. Their accepted onsets are 0.301–0.386s later than the old
status-snapshot estimate. Rebuilding references from canonical manifests changes only
two phrases' mixed flags from true to false, one in conv2 and one in conv3. Their
reference speaker IDs remain unchanged. Derived sets preserve all embedding values, phrase lengths, order and device
labels/reasons; original artifacts are untouched.

All 196 phrases are now eligible, versus 194 previously. The original production replay
matches all 196 device label/reason decisions. Each independent candidate uses its exact
previous settings, seed 1, and the same 200 shuffled orders plus recorded order per
fixture: 1,206 replays / 39,396 scored instances, not independent new audio/speakers.
No caption or candidate result was used to fit onset, and no alignment gate was relaxed.

| Rule | Recorded coverage / accuracy | All-order coverage / accuracy | All-order splits / merges per 100 |
|---|---:|---:|---:|
| Production | 85.7% / 78.1% | 86.4% / 80.2% | 2.59 / 3.84 |
| #01 | 91.3% / 83.2% | 93.3% / 86.5% | 2.88 / 4.23 |
| #02 | 87.2% / 78.6% | 86.0% / 78.6% | 4.06 / 3.56 |
| #03 | 84.2% / 76.0% | 85.4% / 79.1% | 3.16 / 3.43 |
| #04 | 85.7% / 78.1% | 86.4% / 80.2% | 2.60 / 3.84 |
| #05 | 87.2% / 82.1% | 89.7% / 83.8% | 1.09 / 5.20 |
| #06 | 86.7% / 78.6% | 87.2% / 81.0% | 2.63 / 3.88 |
| #07 | 85.7% / 78.1% | 86.4% / 80.2% | 2.60 / 3.84 |
| #19 | 87.8% / 78.6% | 86.5% / 80.1% | 2.83 / 3.88 |

No promotion decision changes. #01/#05/#06 increase merges; #02/#03 reduce reordered
accuracy; #07 has no reported-precision accuracy gain and slightly more splits;
#19 regresses identity metrics. #04's short screen keeps accuracy unchanged, with a
small split increase. Its corrected twelve-copy stress has recorded coverage/accuracy
83.0%/77.8% → 82.3%/77.5%; all-order accuracy 79.6% → 80.1%, splits 1.43 → 1.47,
merges 3.49 → 3.17. The sequential returning-voice result still loses coverage/accuracy.
That stress is 119,952 scored repeated instances, not natural long-session evidence.

The original hold/merge default suite was rerun on the same repaired references:

| Rule | All-order coverage | All-order accuracy | Splits / merges per 100 |
|---|---:|---:|---:|
| Production | 86.4% | 80.2% | 2.59 / 3.84 |
| Hold 0.50 | 89.0% | 82.9% | 0.52 / 5.83 |
| Hold 0.45 | 86.3% | 79.5% | 0.40 / 6.74 |
| Hold 0.50, young four | 89.7% | 83.8% | 1.09 / 5.20 |
| Merge young three | 94.9% | 83.3% | 4.37 / 8.47 |
| Merge young three, similarity 0.45 | 94.8% | 83.5% | 4.31 / 8.25 |
| Hold 0.50 plus merge young three | 90.2% | 80.9% | 1.55 / 8.83 |

More labelled phrases do not meet the no-extra-identity-errors gate. In particular,
the earlier conv1 hold benefit does not justify promotion to these broader voices.
These remain development recordings and estimated-reference replays, not unseen-speaker
qualification or P4 latency measurements. Clean-source float screens #08/#09/#20 and
the independently RMS-qualified later P4 comparisons are unaffected by this repair.

Private provenance: `original-six-rms-alignment.json`, `offline-rms-reference-audit.json`,
`offline-rms-voiceprints.json`, `offline-rms-corrected-rule-comparison.json`,
`04-long-rms-corrected-result.json` and `offline-rms-default-hold-merge.json` under the
ignored overnight folder. All 21 locally built archived apps were also checked against
recorded SHA256, 64-byte L2, 250 MHz PSRAM and ESP-IDF 5.5.5 SDK settings; their numeric
proof is `archived-build-config-audit.json`. Legacy Claude SD pause apps have separate
historical image/ELF evidence; no absent local SDK archive is implied.

## Requested sweep and watchdog reruns completed — 3 November, 15:38

All 24 agreed changes have implemented, measured screens: eight device-embedding
replay experiments, one fixed-weight float-window experiment, and fifteen P4 experiments.
The broader twelve-capture production/x2f comparison and the user's mandatory warning
reruns are complete. This completes the requested experimental sweep/report, not
held-out-speaker, long-soak or production-default qualification. No default is changed.

**Recommendation:** prefer x2f pacing with the existing 600/1000ms pauses for a subsequent
approved adoption step. Its twelve-capture screen holds measured WER/speaker outcomes
while substantially shortening additional speaker-label delay; final/shown-text tradeoffs
remain visible in the pacing table. Keep production speaker identity rules, centered
speaker input and exact-coverage speculative reuse. No new general accuracy gain is
established; do not promote the other tested changes from single or unbracketed runs.

### Final mandatory live reruns

Nineteen queued live reruns completed, followed by one additional same-image/conv2
match for its newly encountered in-session warnings. All 20 completed without panic,
audio overrun or filesystem-full errors. The only warnings were two in forced-redecode
conv3 and two in forced-redecode conv2; the additional conv2 match had zero. Minimum
observed internal/PSRAM free values were 178,096 / 1,548,616 bytes.

| Arm / fixture | WER | Unknowns / captions | Correct / eligible | Final median / p90 ms | Shown ms | Label after text ms | Session / all WD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 23-clean-repeat / conv3 | 29.40% | 11/47 | withheld | withheld | 1439 | 9721 | 2 / 2 |
| 13 / conv3 | 29.40% | 5/44 | 36/44 | 1529 / 2348 | 1250 | 2118 | 0 / 0 |
| 14 / conv2 | 22.24% | 2/38 | 28/38 | 1975 / 2663 | 1337 | 2036.5 | 0 / 0 |
| 14 / conv3 | 29.18% | 8/46 | 34/45 | 1523 / 2394 | 1243 | 2163.5 | 0 / 0 |
| 15 / conv2 | 19.84% | 3/38 | 28/38 | 1858 / 2890 | 1295 | 2033.5 | 0 / 0 |
| 15 / conv3 | 30.04% | 2/46 | 43/46 | 1542 / 2475 | 1235 | 2260.5 | 0 / 0 |
| 16 / conv2 | 23.25% | 3/38 | 28/38 | 1961 / 3106 | 1302 | 2033 | 0 / 0 |
| 16 / conv3 | 31.33% | 4/46 | 41/45 | 1550 / 2093 | 1246 | 2048.5 | 0 / 0 |
| 17 / conv2 | 24.45% | 3/38 | 27/38 | 1933 / 2837 | 1284 | 1747.5 | 0 / 0 |
| 17 / conv3 | 28.11% | 2/46 | 43/46 | 1563 / 2034 | 1215 | 2164.5 | 0 / 0 |
| 18 / conv2 | 23.05% | 2/38 | 28/38 | 1952 / 2632 | 1313 | 1555.5 | 0 / 0 |
| 20 / conv2 | 20.24% | 1/38 | 28/38 | 1982 / 2817 | 1293 | 2037.5 | 0 / 0 |
| 20 / conv4 | 19.36% | 8/34 | 25/34 | 2228 / 3362 | 1558 | 2539 | 0 / 0 |
| 21 / conv2 | 21.64% | 3/38 | 27/38 | 1973 / 3015 | 1284 | 2006.5 | 0 / 0 |
| 21 / conv3 | 30.04% | 4/43 | 35/41 | 1552 / 2667 | 1241 | 2279 | 0 / 0 |
| 22 / conv2 | 22.65% | 3/42 | 29/42 | 1919 / 2476 | 1294 | 1988.5 | 0 / 0 |
| 22 / conv3 | 29.18% | 8/47 | 36/47 | 1517 / 2260 | 1252 | 2170 | 0 / 0 |
| 22 / long22 | 14.67% | 0/7 | 7/7 | unavailable | unavailable | 3080 | 0 / 0 |
| 23 / conv2 | 21.44% | 1/37 | 27/37 | 2715 / 4571 | 1589 | 4156 | 2 / 2 |
| 23-conv2-clean-match / conv2 | 20.24% | 2/38 | 28/38 | 2529 / 4170 | 1543 | 4011.5 | 0 / 0 |


Nineteen of the 20 reference fits passed. The fresh forced-redecode conv3 fit failed
the unchanged RMS gate; its identity and true-end lag are withheld, while global WER,
raw unknown coverage and device-internal label delay remain reportable. Long22 lacks
`speech_end_s` annotations and the draft tool has no usable timing summary: its true-end
and shown-text lags are unavailable, with no substituted clip endpoint. Qualified
identity includes unknowns and retains mixed/no-reference exclusions in the private
report. Speaker-label delay starts at final-text publication, not true speech end.

These are reproduction runs under recovered storage, not fresh bracketing quality
comparisons. They reveal variability: normalized conv2's initial 18/38 correct and
19 unknowns became 28/38 and one unknown; normalized conv4's repeat is 25/34 with
eight unknowns. The large initial conv2 harm did not recur, but a consistent normalization
benefit is not established. Likewise pre-roll conv3's original 19 unknowns became two;
this unbracketed repeat cannot isolate the setting from the changed conditions.
Do not cherry-pick either the initial harm or the best later outcome as a general effect.

### Warning locations and coverage

The complete matrix contains 37 warning-bearing firmware/input/mode groups and zero
missing later completed observations, including whole-log and original session-counter/
after-capture-start scopes. Existing verified later observations count; setup and
in-session warnings stay distinct. Earlier no-warning and interrupted/storage-confounded
attempts remain covered by their separate audits. This is not a claim that every later
warning reproduces the same instruction or that a warning-free repeat fixes a defect.

- Forced-redecode conv3: original flash/cache IPC at capture +50.612s; first clean repeat
  ESP-DL workers at +118.817s; next clean match ESP-DL workers at +42.280/+107.788s.
  The worker/kernel family recurs, but the input positions and sampled PCs differ.
- Forced-redecode conv2: new clean warnings at +202.061s (speaker frontend return address;
  ROM PC unresolved) and +227.885s (ESP-DL convolution-argument work). Its next unchanged
  image/WAV match completed without a warning. Capture-relative times are not exact
  acoustic positions; the second event is near the playback tail.
- Production pacing: warnings recur in its later conv2–4 controls, totaling 11 across
  six captures. X2f has zero in its six balanced captures. The earlier table retains
  the sampled worker/decoder/math differences; no deterministic same-PC fault is claimed.
- The other 17 original cases in the final live batch and the additional conv2 match
  have zero warnings. Earlier clean vocabulary and wider-beam conv3 warnings also did
  not recur. Approved storage recovery changed conditions; no sole-cause inference.

All sampled addresses use the matching archived ELF when available. The unresolved
ROM PC and unavailable legacy SD ELF mappings are not guessed from another image.
No PSRAM software-writer hunt is reopened and no Espressif issue is filed.

### Two legacy SD-input matches

Both reuse `/sd/recordings/bench_conv1.pcm`; no audio upload occurred. The first queue
launch stopped before board ownership because the host manifest path was wrong; it
was corrected to the existing `~/claude-heaptw/conv1/manifest.json` before these runs.

| Repeat | WER | Correct / eligible | Unknowns / captions | Final median / p90 ms | Shown ms | Label after text ms | Session / all WD |
|---|---:|---:|---:|---:|---:|---:|---:|
| diagnostic conv1 | 3.80% | 25/40 | 14/40 | 1805 / 2571 | 1229 | 2202.5 | 0 / 0 |
| short-pause700 conv1 | 4.22% | 26/41 | 14/41 | 1671 / 2855 | 1190 | 2491 | 0 / 0 |

Both have one split, zero merges, zero excluded reference captions, no panic/full error,
and zero overruns recovered from actual terminal `stt status` replies in their raw logs
(the legacy helper omits that field from `bench.json`). True lag covers 31/32 clip ends.
Majority-mapped speaker scores differ from these one-to-one scores; do not conceal the
split. Short-pause700's last historical in-session warning did not recur; diagnostic
conv1's setup warnings did not recur. Remote PCM hashes and historical peer-policy
readbacks are unavailable. The same recorded path/source=0 and exact image are verified;
old peer behavior/full-storage state was not recreated. Keep existing closing pauses.

### Final state, validation and unchecked scope

Fixed production `soak-app.bin` was app-only flashed and readback-verified, SHA256
`172f4377e59c544a9ce39a492708adf5c7f208f98d1f2bdbed6520ad21f1eb7e`.
The helper verified P4 MAC `e8:f6:0a:e3:a7:68` and the recorded partition-table checksum.
A fresh console read back persisted ring reconnect **disabled** and 7,196,672 bytes free.
No full erase/filesystem-partition flash, model/vocabulary persistence change, production-
default change, branch push, main merge or outward filing was performed. Private rollback
and filesystem backups are retained. Normal device audit logging continued.

Required host checks passed on the current code: `tests/test_transcript.py`,
`tests/test_product_storage.py` with ESP-IDF cJSON, `tests/test_viewer.mjs` and
`tests/test_bridge.py`. Numeric logs/hashes are in `overnight/final-host-checks/report.json`.
Scoring/alignment checks passed earlier; only documentation changed after the final host run.
The requirement-by-requirement private audit is `overnight/completion-audit.json`.

Not checked/claimed: unseen-speaker qualification; natural long-history drift; quantized/P4
four-second speaker-window accuracy/cost; raw sample-clock microphone alignment; SD/FAT
power-loss behavior; battery/energy gain; isolated gain/DC/clipping effects or quiet-word
acoustic recall; direct runtime effective-beam telemetry (the source requests 40 from the
loaded file's 32); a deterministic causal watchdog defect; or safe production retention.
The vocabulary cap was nonbinding at the existing 1.0-nat bonus, and the synthetic fixture
is a single voice. Offline shuffled/repeated embeddings are not new independent recordings.
These limits are explicit outcomes of the requested screens, not deferred claims of success.

Private final evidence: `final-qualification-analysis-status.json`,
`final-board-readback.json`, and `overnight/watchdog-final-rms-alignment.json`,
`watchdog-final-rms-metrics.json`, `watchdog-final-status-estimate-metrics.json`,
`watchdog-final-sd-metrics.json`, `watchdog-repeat-matrix.json` and
`forced-redecode-final-warning-comparison.json`. Raw captures and before-cleanup backups
remain ignored/private. Full per-event clocks, tasks, PCs/RA, hashes and exclusions remain
reviewable there; public material contains numeric summaries only.
