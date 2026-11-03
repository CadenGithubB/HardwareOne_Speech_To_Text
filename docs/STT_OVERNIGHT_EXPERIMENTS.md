# Overnight STT experiments — 2 November 2026

Goal: fewer unknown speakers without more mistaken identities, better recognition,
and faster speaker labels. Each experiment starts from the same baseline; no stacking
changes until independently evaluated. Production promotion requires user approval.
Audio stays private; live P4 tests use the Mac mini speakers at 50%, the approved
app-only flash helper, a verified rollback, and exclusive board ownership.

Baseline: x2f pacing, production speaker rules, 600/1000 ms closing pauses,
64-byte L2 lines, 250 MHz PSRAM. Existing six live recordings and their device
voiceprints are development material. Keep final held-out speaker partitions untouched
until a candidate is frozen. Repeated acoustic A/B runs are needed for promotion.

Acceptance: report WER, one-to-one speaker accuracy, unknowns, split/merge errors,
label lag, draft/final latency, overruns, watchdogs, memory headroom and crashes as
applicable. Reject improvements that merely turn unknowns into incorrect labels.
Offline replay does not establish firmware latency, acoustic equivalence or stability.
Record null results and failed runs. Each item below must be implemented and tested;
'planned' is not a completed experiment. Screening gates determine which warrant P4
confirmation, with rejected candidates retained as measured results.

| ID | Single change to investigate | First test / decision evidence | State |
|---|---|---|---|
| 01 | Resolve ambiguous matches only when best-minus-runner-up cosine >=0.08; do not update centroids | Device-voiceprint replay, identity errors vs unknowns | Tested offline; reject promotion |
| 02 | Allow new profiles from 1.5 s phrases rather than 2 s | Replay, short-phrase unknowns and false profiles | Tested offline; reject |
| 03 | Require 3 s for centroid updates, retaining current admission rules | Replay, centroid contamination vs adaptation | Tested offline; reject |
| 04 | Cap contribution of repeatedly observed speakers to centroid history | Replay shuffled and recorded orders, returning voices | Planned |
| 05 | Hold uncertain new profiles only during their first four observations | Replay on broader voices; compare earlier hold failure | Planned |
| 06 | Resolve a held phrase after subsequent agreeing evidence, with bounded delay | Sequential replay, revisions and delay | Planned |
| 07 | Raise speaker capacity from 8 to 10 | Capacity-triggered unknowns, false-profile count and memory | Planned |
| 08 | Extend speaker input window from 3 s to 4 s | Re-export fixed weights/shape if supported; embedding and device cost | Planned |
| 09 | Select the highest-energy contiguous speaker window instead of the center | Offline acoustic embeddings, identity errors | Planned |
| 10 | Defer draft admission while a speaker job is executing | P4 paired runs, labels versus draft freshness and WER | Planned |
| 11 | Bound draft deferral to 100 ms | Independent P4 scheduling arm, same endpoints | Planned |
| 12 | Increase draft pacing multiplier from 2 to 3 | P4 paired runs, contention versus shown-text lag | Planned |
| 13 | Apply 1.25x saturating PCM gain only to recognition input | Offline error screen then P4, clipping and WER | Planned |
| 14 | Reduce the segmenter's minimum energy threshold by 10% | Quiet-word recall versus false speech and WER | Planned |
| 15 | Increase recognition pre-roll by 150 ms | Initial-phoneme errors versus extra noise and latency | Planned |
| 16 | Increase recognition trailing audio retention by 100 ms | Final-word deletions versus latency | Planned |
| 17 | Lower language-model influence by 10% | Fixed-audio decoder replay, substitutions and WER | Planned |
| 18 | Increase decoder beam width by 25% | Fixed-audio decoder replay, WER, runtime and memory | Planned |

Implementation feasibility and exact existing defaults must be inspected before each
change. If an implementation is unsupported, record the concrete obstacle and choose
an equivalent experiment addressing the same hypothesis; do not silently count it as
tested. No network audio uploads. Keep logs and transcripts in ignored private folders.

## Results

### 01 — Ambiguity margin 0.08

Implemented in the C++ candidate replay clusterer; production firmware is unchanged.
A winning label needs an absolute cosine gap >=0.08 over the runner-up. The ambiguous
phrase cannot adapt a centroid. Neutral-mode equivalence and a targeted no-adaptation
check pass (`tests/test_spkrules.py`, `tests/test_speaker_ambiguity_margin.py`).

Six complete device captures: 196 phrases, 194 scored (mixed/reference exclusions).
Recorded-order coverage increased 85.6% -> 91.2%, overall one-to-one accuracy
77.8% -> 83.0%, but merge errors increased 4.12 -> 4.64 per 100 scored phrases.
Across 200 shuffled orders plus the original per set (1,206 replays, not independent
recordings), coverage increased 86.5% -> 93.3%, accuracy 80.3% -> 86.5%, and merges
3.87 -> 4.26 per 100. Splits also increased 2.62 -> 2.90 per 100.

Decision: reject promotion under the no-extra-identity-errors gate. More labels alone
are insufficient. This rule is retained as an offline experimental option for further
analysis. No P4 performance or held-out accuracy claim. Evidence:
`private/resume-20261102/overnight/01-ambiguity-margin.json` (ignored). Excludes the
failed live run and later memory-arena trials. Next: experiment 02, separating new
profile admission length from the existing centroid-update length requirement.


### 02–03 — Independent admission and adaptation length gates

Implemented separate `create_ms` and `update_ms` settings in the offline C++
candidate. Zero inherits the production minimum. Experiment 02 changes only admission
to 1.5 s; experiment 03 changes only adaptation to 3 s. Neither includes experiment 01.
Threshold-edge tests verify 23,999/24,000 sample admission, 47,999/48,000 sample
adaptation, unchanged admission under the adaptation experiment, and no centroid
movement from a short matched phrase. Production equivalence and margin checks pass.

Same six device sets / 194 scored phrases as experiment 01:

| Rule | Recorded coverage | Recorded accuracy | Recorded splits/100 | Recorded merges/100 | All-orders coverage | All-orders accuracy | All-orders splits/100 | All-orders merges/100 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Production | 85.6% | 77.8% | 3.61 | 4.12 | 86.5% | 80.3% | 2.62 | 3.87 |
| 02: create at 1.5 s | 87.1% | 78.4% | 4.64 | 4.12 | 86.1% | 78.7% | 4.10 | 3.59 |
| 03: adapt at 3 s | 84.0% | 75.8% | 4.12 | 4.12 | 85.5% | 79.2% | 3.19 | 3.45 |

Decision: reject both for promotion. Experiment 02 creates extra duplicate identities
and loses accuracy under reordered input. Experiment 03 reduces coverage and accuracy
in both comparisons. Lower merge counts do not compensate for those regressions.
All-orders means 200 shuffles plus recorded order per set, not independent samples.
No new acoustic or device-performance claim. Evidence: ignored
`private/resume-20261102/overnight/02-short-admission.json` and
`03-long-update.json`. Next: experiment 04; experiments 04–18 remain outstanding.
