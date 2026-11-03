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

The exact same vocabulary image and conv3 fixture are now being rerun, using unchanged
model/pacing/vocabulary parameters and session commands. The reproduction preserves
ring reconnect off, the approved app-only helper, lock ownership and speakers at 50%.
Afterward compare failure stage, input progress, CPU/task, and matching ELF PC symbols.
Inspect decoder versus neural/command/IPC timings to select a focused fix if reproducible;
do not add more tuning arms. Finish missing controls and the watchdog reproduction
matrix before declaring qualification complete.

See [STT_WATCHDOG_RETESTS.md](STT_WATCHDOG_RETESTS.md) for the user's mandatory rerun
rule and [STT_OVERNIGHT_EXPERIMENTS.md](STT_OVERNIGHT_EXPERIMENTS.md) for numeric records.
No production-default change, branch push, main merge or outward-facing filing is authorized.
