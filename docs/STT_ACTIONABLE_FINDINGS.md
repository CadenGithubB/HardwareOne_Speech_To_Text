# STT decisions and next actions — 3 November 2026

The initial sweep has not established a new general recognition/speaker-accuracy win.
It has identified configurations to avoid, a bounded pacing candidate, measurement
problems, and a concrete runtime failure to reproduce. Production defaults are unchanged.

| Decision | Evidence | Action |
|---|---|---|
| Qualify x2f pacing | Earlier matched conv1 SD screen: label median 19.486 → 4.063s; WER 3.80% both; reported speaker outcomes held. One local x2f session watchdog. | Check matching repeats and watchdog location; broader matched qualification before adoption. This is a conv1 result, not a general accuracy claim. |
| Keep exact-coverage speculative reuse | Forcing final re-decode raised label median 2.690 → 7.363s on conv2 and 3.199 → 14.744s on conv3; five speaker jobs rejected for audio pressure and one session watchdog. | Do not adopt forced re-decode. This does not compare disabling speculation entirely. |
| Reject the tested normalization setting | Conv2 correct labels 28/38 → 18/38; unknowns 1/38 → 19/38. Conv4 also trails its fresh control. | Do not promote this target/gain configuration; do not infer all normalization is ineffective. |
| Do not promote noise freezing yet | WER 18.84/26.61% versus final controls 19.04/26.39%; the initial apparent gain is not established beyond control drift. One extra initial-control conv2 merge. | Keep as a research lead only; no claimed general accuracy improvement. |
| Keep production closing pauses | Long-pause400 improves conv1 WER by one word but increases unknowns; short700 and combined pauses raise WER. | Retain 600/1000ms. |
| Fix evaluation before believing small changes | Identical-image controls changed WER 15.83 → 22.85% and 24.89 → 30.47%; noise estimates changed too. Stale onset and mixed-clock speech-end fields were corrected in analysis. | Retain both controls, raw unknown coverage, exclusions and rejected alignment fits. No cherry-picked baseline or causal claim. |

## Immediate debugging target

The four-term vocabulary image completed its target/control fixture, but its natural
conv3 test failed: `STT audio queue full; backend cannot keep up`, with 21 in-session
watchdog warnings and no panic. Fixed production was restored and verified. The planned
final two controls did not run. Do not interpret the failure as proof of a particular
code defect before the matched repeat and stage evidence.

The exact-image/conv3 repeat was stopped because LittleFS reported no free space
before test audio began; it produced no captions. The original failure also contains
22 filesystem-full errors. The repeat contains 26. These are storage-confounded
attempts, not evidence that vocabulary caused the watchdogs. The fixed-production
app was written and verified after the interruption (10:06 on 3 November).

A new read-only inspection measured 352,256 bytes free. The command audit file was
514,346 bytes, already above its 512,000-byte cap. Source inspection shows rotation
copies up to 85% of the cap (435,200 bytes) into a sibling temporary file while holding
the filesystem lock. The overflow check requests only the append-line size plus 512
bytes, subject to a 100 KiB floor; it does not reserve that rotation copy. This is a
concrete mismatch to investigate, not yet a demonstrated cause/fix for every watchdog.
The three previously authorized logs total only 46,104 bytes in that inspection;
clearing those alone cannot provide the audit rotation headroom.

The previous 128 KiB free-space gate was insufficient. Do not continue tuning or
claim a clean watchdog reproduction while storage errors persist.

## Ordered next actions and acceptance criteria

1. **Make storage safe for testing.** Inspect log growth/rotation and preserve private
   backups before the already-authorized three-log cleanup. Establish headroom from
   actual rotation/write requirements, rather than choosing another arbitrary byte
   threshold. Setup and a complete baseline must finish without filesystem-full
   errors; record free space before and after. Do not delete other files without
   authorization or change production logging defaults.
2. **Repeat the failed case under usable storage conditions.** Keep the vocabulary
   image, conv3 input and test settings identical. Record the changed storage condition.
   Compare watchdog task, input position and failure stage with the original; do not
   count the interrupted, zero-caption run as a clean reproduction. Finish controls.
3. **Qualify the strongest candidate: x2f pacing.** Run matched production/x2f comparisons
   on broader conversations. Report WER, speaker correctness/unknowns, final median/p90,
   shown-text and label lag. Require quality to hold and investigate/repeat watchdogs
   before recommending adoption. The earlier conv1 label-lag improvement is about 79%,
   but remains limited to that conversation and setup.
4. **Close the experiment report.** Keep rejected settings rejected, show control drift
   and excluded comparisons, and complete the watchdog repeat matrix. No more tuning
   arms until these reliability and qualification checks are resolved.

See [STT_WATCHDOG_RETESTS.md](STT_WATCHDOG_RETESTS.md) for the user's mandatory rerun
rule and [STT_OVERNIGHT_EXPERIMENTS.md](STT_OVERNIGHT_EXPERIMENTS.md) for numeric records.
No production-default change, branch push, main merge or outward-facing filing is authorized.

## Validation checkpoint — 3 November

Required host checks passed: `tests/test_transcript.py`, `tests/test_product_storage.py`
(with ESP-IDF cJSON), `tests/test_viewer.mjs` and `tests/test_bridge.py`. The scoring
and alignment checks also passed; alignment uses the existing NumPy environment.
These host checks do not qualify microphone accuracy, P4 runtime or SD power-loss behavior.
