# Overnight STT experiments — 2 November 2026

Scope: 24 required experiments. The user explicitly approved adding 19–24.
Each requires an implemented change and measured outcome, including rejected outcomes.

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
| 04 | Cap contribution of repeatedly observed speakers to centroid history | Replay shuffled and recorded orders, returning voices | Tested offline; reject promotion |
| 05 | Hold uncertain new profiles only during their first four observations | Replay on broader voices; compare earlier hold failure | Tested offline; reject promotion |
| 06 | Resolve a held phrase after subsequent agreeing evidence, with bounded delay | Sequential replay, revisions and delay | Tested offline; reject promotion |
| 07 | Raise speaker capacity from 8 to 10 | Capacity-triggered unknowns, false-profile count and memory | Tested offline; reject |
| 08 | Extend speaker input window from 3 s to 4 s | Re-export fixed weights/shape if supported; embedding and device cost | Float screen tested; no promotion |
| 09 | Select the highest-energy contiguous speaker window instead of the center | Offline acoustic embeddings, identity errors | P4 initial comparison complete; mixed |
| 10 | Defer draft admission while a speaker job is executing | P4 paired runs, labels versus draft freshness and WER | P4 initial comparison complete; no promotion |
| 11 | Bound draft deferral to 100 ms | Independent P4 scheduling arm, same endpoints | P4 initial comparison complete; no promotion |
| 12 | Increase draft pacing multiplier from 2 to 3 | P4 paired runs, contention versus shown-text lag | P4 initial comparison complete; no promotion |
| 13 | Apply 1.25x saturating PCM gain only to recognition input | Offline error screen then P4, clipping and WER | Build pipeline active; P4 queued |
| 14 | Reduce the segmenter's minimum energy threshold by 10% | Quiet-word recall versus false speech and WER | Build pipeline active; P4 queued |
| 15 | Increase recognition pre-roll by 150 ms | Initial-phoneme errors versus extra noise and latency | Build pipeline active; P4 queued |
| 16 | Increase recognition trailing audio retention by 100 ms | Final-word deletions versus latency | Build pipeline active; P4 queued |
| 17 | Lower language-model influence by 10% | Fixed-audio decoder replay, substitutions and WER | Build pipeline active; P4 queued |
| 18 | Increase decoder beam width by 25% | Fixed-audio decoder replay, WER, runtime and memory | Build pipeline active; P4 queued |
| 19 | Require a clear best-versus-runner-up similarity margin before adapting a centroid | Replay, identity contamination versus adaptation; creation unchanged | Tested offline; reject |
| 20 | Normalize loudness only for speaker embedding input | Quiet-voice accuracy, clipping and speaker cost | Positive float screen; P4 queued |
| 21 | Freeze background-noise adaptation during active speech | Quiet-word recall, false segments, WER and threshold traces | Built; P4 queued |
| 22 | Shorten maximum recognition segment duration for very long utterances | Long-form WER, boundary errors, latency and memory | Built; P4 queued |
| 23 | Force completed-phrase decode instead of reusing exact-coverage speculative text | Baseline already checks exact coverage; counterfactual accuracy/latency test | Built; P4 queued |
| 24 | Apply bounded vocabulary bias for names and technical terms | Target-word corrections versus false insertions on control phrases | Built; target/control P4 queued |

Implementation feasibility and exact existing defaults must be inspected before each
change. If an implementation is unsupported, record the concrete obstacle and choose
an equivalent experiment addressing the same hypothesis; do not silently count it as
tested. No network audio uploads. Keep logs and transcripts in ignored private folders.

## Results

See [the concise current ledger](STT_EXPERIMENT_RESULTS.md) for measured versus pending work.

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


### 04 — Cap profile history at eight observations

Implemented exponential forgetting after eight centroid updates: retain 7/8 of the
old accumulated vector before adding the next unit vector. Keep the actual observation
count for age-based rules. Zero is neutral. Combining this experimental cap with merging
is explicitly unsupported rather than incorrectly combining differently weighted sums.
A synthetic drifting-direction case verifies adaptation and a different assignment from
unbounded history; production-equivalence checks pass.

On the six device sets, reported coverage/accuracy/split/merge scores remained unchanged
at the reported precision, both recorded and shuffled. This is a null short-session
screen, not proof that forgetting cannot help long conversations. A longer-history
returning-speaker check remains required for this item. Evidence:
`private/resume-20261102/overnight/04-history-cap.json`.

### 05 — Young-profile hold

Used the existing C++ candidate implementation with `new_below=0.5,young=4`, independently
of all previous overnight changes. While the closest profile has fewer than four
observations, a non-matching phrase with similarity >=0.5 is held unknown instead of
creating a new profile. Same six device sets, 200 shuffles plus recorded order each.
Recorded coverage/accuracy improved 85.6%/77.8% -> 87.6%/82.5%; splits/100 fell
3.61 -> 1.03 and merges stayed 4.12. Across all orders, coverage/accuracy improved
86.5%/80.3% -> 89.8%/83.9%, but merges increased 3.87 -> 5.22 per 100.
Reject promotion: the recorded-order gain is not robust to phrase order. Evidence:
`private/resume-20261102/overnight/05-young-hold.json`. No firmware defaults changed.

Current checkpoint: 01–03 and 05 screened and rejected; 04 implemented/screened with
long-history validation outstanding. 06–24 remain to implement/test. The goal remains
active. Next: complete 04's longer-history check, then deferred resolution (06).


### 04 follow-up — Repeated-voice long-history stress

Completed 12 consecutive passes through each of the six captured phrase sequences,
preserving reference identity across returns. This is repeated-embedding stress, not
new long-form acoustic evidence. It exposes profiles to many updates, but cannot
model natural voice drift. Additional 50 shuffles per extended sequence: 306 replays,
118,728 scored phrase instances including repeats; not independent observations.

Recorded-sequence coverage/accuracy: production 82.8%/77.5%, history cap 82.1%/77.3%.
Merges/100 improve 4.12 -> 3.65; splits remain 1.16. Over all orders, coverage/accuracy
84.6%/79.8% -> 84.8%/80.2%, splits 1.44 -> 1.49, merges 3.50 -> 3.20. Reject promotion:
benefits are order-dependent and the sequential returning-voice case loses coverage
and accuracy. Natural long-conversation qualification remains unperformed; no claim
that forgetting is universally ineffective. Evidence: ignored
`04-long-repeated-sets.json` / `04-long-repeated-result.json` in the overnight folder.

### 06 — Deferred unique-match resolution within three later phrases

Implemented an offline sequential revision window. After assigning each new phrase,
reconsider unresolved phrases from the preceding three positions against current
profiles. Revise only when exactly one profile matches at the production threshold;
never create/adapt a profile from a revision. No future evidence beyond that window.
Unresolved phrases stay unknown at session end. The emitted reason records the number
of later phrases waited (`resolved_after_1`, `_2`, `_3`). This bounds evidence distance
in phrases, not wall-clock seconds; no maximum idle-time delay is claimed.

Tests verify resolution after one/three phrases, expiration at four, no evidence at
session end, neutral equivalence, unchanged profile decisions and ambiguous matches
remaining unresolved. All prior speaker candidate regression tests pass.

Recorded-order coverage rises 85.6% -> 86.6%, accuracy 77.8% -> 78.4%, splits remain
3.61/100, merges rise 4.12 -> 4.64/100. Two unknown labels are revised (one after one
later phrase, one after three); the net gain includes one additional identity error.
Across 200 shuffles plus original order each: coverage 86.5% -> 87.3%, accuracy
80.3% -> 81.0%, splits 2.62 -> 2.66/100, merges 3.87 -> 3.91/100. Revisions: 141/105/94
at delays of one/two/three phrases. Reject promotion under the identity-error gate.
No UI revision protocol or P4 timing claim: the standalone replay experiment is sufficient
to reject this rule, and firmware is unchanged. Evidence:
`private/resume-20261102/overnight/06-deferred-three.json`.

Current checkpoint supersedes earlier progress notes: experiments 01–06 have offline
implementations and measured rejection outcomes (04 includes repeated-history stress).
Experiments 07–24 remain outstanding. Next: capacity change (07), then acoustic-window
and scheduling experiments. Full goal remains active.


### 07 — Ten-speaker capacity

Implemented a per-rule replay capacity setting, preserving the eight-profile default.
A deterministic 11-orthogonal-voice test exercises admission of speakers nine and ten,
refusal of eleven, and default equivalence. Production equivalence tests pass.
The six device recordings show identical recorded-order scores. Across 200 shuffles
plus original order per set, coverage stays 86.5%, accuracy falls 80.3% -> 80.2%,
splits rise 2.62 -> 2.63/100 and merges stay 3.87/100. The five capacity refusals are
replaced by extra profiles and ambiguity rather than improved identity accuracy.
Reject promotion. No extra P4 memory allocation was deployed. Evidence:
`private/resume-20261102/overnight/07-capacity-ten.json`.

### 08 — Four-second window, fixed-weight float screening

Made `export_speaker.feats_for` accept an explicit frame count; its default stays
300. Tests check unchanged deployed default, exact center crop, short-input repetition,
finite features and invalid frame counts. Compared 300 vs 400 frames (actual spans
2.99 vs 3.99 seconds) with the same pretrained weights and production clustering.
Re-exporting the quantized ESP-DL trunk and P4 timing are not performed at this stage.

Fresh embeddings were computed from all six prepared source playlists using per-clip
reference boundaries with 300 ms pre-roll / 500 ms tail. These are clean source audio
and idealized segment boundaries, not the live microphone captures used in 01–07.
175 scored source phrases per order. Each arm uses the identical 200 shuffled orders
plus recorded order per fixture, 1,206 replays / 35,175 scored instances. No new held-out
speaker audio was accessed. Model weights hash is preserved in the private result.

| Window | Recorded coverage / accuracy | Recorded splits / merges per 100 | All-orders coverage / accuracy | All-orders splits / merges per 100 |
|---|---:|---:|---:|---:|
| 300 frames | 89.1% / 82.9% | 6.29 / 0.00 | 89.8% / 83.2% | 6.50 / 0.16 |
| 400 frames | 89.1% / 83.4% | 5.71 / 0.00 | 91.7% / 86.8% | 4.46 / 0.69 |

Decision: promising accuracy/split improvement but fails the no-increased-merges gate;
no production promotion. Retain as a research lead if later identity safeguards improve.
Host embedding times are not P4 inference estimates. Unchecked: quantization effects,
P4 RAM/CPU cost, real segmentation, acoustic robustness and long-session stability.

The existing Torch environment lacked scipy; the initial attempt terminated before
completing embeddings. The retry uses macOS `afconvert` once per fixture to produce
identical 16 kHz mono PCM inputs for both arms; source and converted hashes/manifests
are private. An initial combined-group score used different shuffle seeds between
windows and is superseded by `08-window400-paired.json`, which compares the same
fixture index and seed separately per arm. Evidence under ignored overnight folder:
`08-input/`, `08-embeddings.json`, `08-window400-paired.json`, `08-controller*.log`,
`run08.py`. All values above come from the paired result.

Current checkpoint: 01–08 have measured screens, with explicitly limited scope for 08.
09–24 remain outstanding. Next: energy-selected speaker windows (09), then P4 draft /
speaker scheduling (10–12). No production defaults or fixed model weights changed.


### 09 — Highest-energy contiguous speaker window

Added opt-in policy 3 to the actual portable C++ selector: maximize raw PCM sum of
squares over a fixed 2.99-second contiguous window, testing 10 ms start positions,
the exact final endpoint and the center; equal-energy ties favor the center. The
allocation-free `highest_energy_start` helper can be used by the P4 copy adapter.
Unlike policy 1, this measures energy magnitude rather than active-frame density.
Default selection and window/model size remain unchanged. Sanitizer-backed selector
checks include constant-energy center ties, stronger beginning audio, exact non-grid
endpoint inclusion, randomized bounds and all older policy tests.

Fresh float embeddings use the same fixed weights, 300 frames, per-clip boundaries,
converted 16 kHz source audio, references, threshold, and matched shuffle orders as 08.
Only the window selector changes. Six fixtures, 175 scored phrases per order:

| Selector | Recorded coverage / accuracy | Recorded splits / merges per 100 | All-orders coverage / accuracy | All-orders splits / merges per 100 |
|---|---:|---:|---:|---:|
| Center | 89.1% / 82.9% | 6.29 / 0.00 | 89.8% / 83.2% | 6.50 / 0.16 |
| Energy | 90.9% / 85.7% | 5.14 / 0.00 | 90.6% / 84.5% | 5.99 / 0.16 |

This passes the aggregate float-screen identity-error criterion, but is not production
qualification. Result/embeddings/selections: ignored `overnight/09-result.json`,
`09-embeddings.json`, `09-selections.json`. New window contents may alter quantized
embeddings, runtime, noisy-audio behavior and mixed-speaker sensitivity.

A P4 arm was built with `build_arms.sh`, x2f pacing, unchanged production rules/pauses,
64-byte cache lines and 250 MHz PSRAM. Only long-phrase speaker-window start selection
changes; recognition PCM and phrase sample counts stay intact. The adapter selects
before copying the fixed speaker job buffer, without extra runtime allocations.
`bench-codex-energy-window.bin` SHA256:
`474a9c29f0030baeec00bd792bb5fa3d099179310485c3c251326eeae265dd20`.
HardwareOne source files were restored after the build and tracked checkout is clean.

The P4 controller is running a new paired acoustic screen: center conv2, energy conv2,
energy conv4, center conv4, using Mac mini speakers at 50%. It owns busy.lock, uses the
approved app-only flash helper, and restores verified `soak-app.bin` in its finalizer.
Counterbalancing addresses order in part; these are still single runs per fixture/arm.
Evidence: `private/resume-20261102/09-p4-status.json` and
`overnight/09-p4-controller.log`, controller `overnight/run09_p4.py`.
P4 results are pending: do not count the positive float screen as a device improvement.
10–24 remain outstanding; scheduling is next after this promising-candidate check.


### 10–12 — Independent scheduling arms built, P4 measurements queued

Added opt-in benchmark draft gate (`speaker_draft_gate.h`), tested as actual C++ under
ASan/UBSan for unbounded deferral, exact 100 ms deadline, clearing/rearming and uint32
clock rollover. This header is not wired into production defaults.

The HardwareOne benchmark adapter samples whether any speaker job slot is occupied
before draft admission. This includes queued and executing work, deliberately avoiding
an active-only race where the speaker worker starts immediately after a snapshot. The
same STT worker submits jobs, so no new speaker job is submitted concurrently by a
separate capture owner. A successful label may be posted before its slot is returned;
the gate conservatively includes the remaining diagnostic/yield tail. It gates only
new drafts in the no-final-slot branch; capture and final recognition remain eligible.
The no-draft loop retains its existing 10 ms tick; no spin-wait was introduced.

- 10: unbounded draft deferral until no speaker job is pending.
- 11: same admission policy, but release a ready draft after at most 100 ms waiting;
  start a new interval for each subsequent admission. Cap is tick-granularity, not a
  hard realtime guarantee; task scheduling can add delay.
- 12: independent x3 draft pacing arm; scheduling source/API restored before building.

All retain fixed weights, production speaker rules, centered windows, 600/1000 ms
closing pauses, diagnostics on, 64-byte cache lines and 250 MHz PSRAM. Energy-window
selection is not stacked. Built through `build_arms.sh`; HardwareOne tracked sources
were restored in a finalizer. Artifacts and exact source diffs are in ignored arms:
- `codex-spk-gate`: SHA256 `a2ab1fa495569014ffc8c23089fd23be874d89ff4aba08c4c4605a0ae4cf88dc`.
- `codex-spk-gate100`: SHA256 `aa84a4d48f203f710460a5d95f6906b07129ee5c9f6b535b6e18c5278528fa38`.
- `codex-pace3`: SHA256 `a26ba5c11b389b61ddb58735752ff9a45f0cd0673b58e851f390b348fda3f605`.

The queued P4 controller requires experiment 09 to finish successfully and restore
production before taking the lock. It then runs conv2/conv4 on a fresh x2 baseline,
each independent arm, and an x2 baseline afterward, using Mac mini Speakers at 50%.
It writes `10-12-p4-status.json` and restores fixed production in its finalizer. A
preceding failure stops admission of new tests for inspection. Build success and
policy unit checks are not performance/accuracy results; 10–12 remain unmeasured.
Controller: `private/resume-20261102/overnight/run10_12_p4.py`;
log: `overnight/10-12-p4-controller.log`. The active energy comparison retains the port.


### 13–18 — Recognition arm preparation (not measured yet)

Recognition experiment arms are built serially from restored baseline source, never
stacked. Fixed recognition/speaker weights, centered speaker windows, speaker rules,
x2f pacing, diagnostics and 600/1000 ms closing pauses stay common.

- 13: exact saturating 1.25x int16 gain in recognition frontend sample conversion,
  including full, incremental and ring feature paths. Segmentation and speaker PCM
  stay original. Integer implementation rounds halves away from zero; an exhaustive
  65,536-value sanitizer check verifies rounding, saturation and monotonicity. This
  does not by itself establish recognition improvement; normalization may remove much
  of the gain effect. Gain is applied before existing dither/pre-emphasis.
- 14: adaptive speech floor 45 -> 41 (nearest integer to a 10% reduction; actual 8.9%).
- 15: recognition pre-roll 4,800 -> 7,200 samples (300 -> 450 ms).
- 16: common retained-tail constant 8,000 -> 9,600 samples (500 -> 600 ms), including
  the matching speculative coverage requirements; phrase closing pauses unchanged.
- 17: scale the existing LM strength by 0.9, preserving the alpha/beta/custom-word
  balance rather than changing only one bonus. Must verify LM actually loaded and
  decoded successfully; fallback runs cannot demonstrate this experiment.
- 18: request ceil(1.25 * file beam), capped at decoder `kMaxBeam` (64). Must inspect
  the loaded file beam and ensure this actually increases it; a cap-induced no-op is
  not a tested change. Decoder workspace may rise; memory errors/fallbacks are outcomes
  to record, not discard. Existing fixed LM blob is not overwritten.

Build controller: ignored `private/resume-20261102/overnight/build13_18.py`; arm map
`13-18-arms.json`, full source diffs and build manifests in the arms folders. Source
restoration is in a finalizer. All six builds completed, their image hashes were checked, and HardwareOne tracked
sources are clean after restoration. This is build verification, not a device result.

The recognition P4 controller waits for the scheduling chain to complete ten successful
captures and restore fixed production, then requires all six SHA-verified images. It
runs conv2/conv3 on baseline-before, each independent arm, and baseline-after. The
serialized controllers own busy.lock only during board use. They stop and restore on
failed captures. The still-idle scheduling queue was intentionally restarted once to
strengthen its predecessor gate to require four successful energy captures; recognition
queue likewise requires ten successful scheduling captures. No observation timeout was
treated as a stopped board task or used to restart an active test.

Recognition controller: `overnight/run13_18_p4.py`, state `13-18-p4-status.json`, log
`overnight/13-18-p4-controller-queued.log`. A three-hour predecessor wait is bounded;
expiry leaves the board untouched. These are queued tests, not measured improvements.
The energy comparison and scheduling work retain priority. Full goal remains active.


### 19 — Confidence margin for profile adaptation

Implemented an independent `update_margin=0.08` C++ candidate. A uniquely matched
phrase retains its label but does not adapt the profile if its best-versus-runner-up
gap is <0.08. New-profile admission, unknown handling and thresholds stay production.
A deterministic neighbouring-speaker test verifies retained labels, protected future
centroids, default equivalence and normal learning when there is no competitor.
Production-rule equivalence checks pass. This is independent of ambiguity labeling (01).

On six device sets, recorded coverage/accuracy 85.6%/77.8% -> 87.6%/78.4%, but splits
3.61 -> 4.64/100 and merges 4.12 -> 5.15/100. Nine updates were withheld. Across matched
200 shuffles plus original order per set, coverage 86.5% -> 86.6%, accuracy 80.3% ->
80.2%, splits 2.62 -> 2.85/100, merges 3.87 -> 3.91/100. Reject promotion under the
identity-error gate. Evidence: `overnight/19-update-margin.json` (ignored).


### 20 — Speaker-window loudness normalization

Implemented opt-in native C++ RMS normalization to target 1,000 PCM units, clamping
gain to [0.25,4] and rounding/saturating each sample. Silence stays unchanged; invalid
targets are rejected as a no-op. Acts on the selected center speaker window, not the
recognition or segmentation input. ASan/UBSan tests cover gain limits, silence, sparse
clipping and invalid inputs. The host bridge returns an owned copy so source PCM is
preserved. Older selector/frontend sanitizer checks still pass.

Fresh float embeddings: fixed weights, same 300-frame center windows, same converted
source audio and per-clip spans as 08/09, same production clustering, paired shuffle
seeds. No energy selection or confidence changes are stacked. Six fixtures / 175
scored source phrases per order, 200 shuffles plus recorded order per fixture:

| Input | Recorded coverage / accuracy | Recorded splits / merges per 100 | All-orders coverage / accuracy | All-orders splits / merges per 100 |
|---|---:|---:|---:|---:|
| Original | 89.1% / 82.9% | 6.29 / 0.00 | 89.8% / 83.2% | 6.50 / 0.16 |
| RMS normalized | 91.4% / 85.7% | 5.71 / 0.00 | 90.1% / 83.6% | 6.42 / 0.14 |

Positive initial screen; small shuffled-order gain requires device confirmation and
repetition. Not production qualification or evidence on unseen speakers. Private:
`overnight/20-result.json`, `20-embeddings.json`, `20-selections.json`, `run20.py`.

Built P4 image `bench-codex-speaker-level.bin`, SHA256
`c094c1cf8ef18b955bc18abca54e3e53b124609d3195b9f31ca38bba793c01e1`.
Only the already-owned center-cropped speaker job buffer is normalized immediately
before embedding; no new runtime allocation. Fixed model, rules, pacing, pauses and
cache configuration remain common. HardwareOne tracked source was restored and clean.
The queued controller waits for successful 13–18 completion/restoration, then runs
center conv2, normalized conv2/conv4, center conv4 with speakers at 50%, exclusive
busy.lock and approved app-only flashes, restoring fixed production afterward.
Private state: `20-p4-status.json`; controller `overnight/run20_p4.py`.
P4 timings/quantized accuracy are pending; no defaults changed.

Experiment 09's first P4 conv2 pair is mixed: center/energy majority speaker accuracy
76.32%/73.68%, unknowns 1/1, label lag 1296.5/1401 ms; both 38 captions, no overruns
or watchdogs. WER 15.63%/14.83% differs despite unchanged recognition code, illustrating
acoustic run variation. This single pair does not validate the earlier float gain.
Conv4 and final baseline are still running; wait for the complete paired report.

Current work: 09 P4 running; 10–12 and 13–18 independently built/queued; 19 rejected
in offline replay; 20 positive float screen with independent P4 arm built/queued.
21–24 remain to implement/test. Full 24-experiment goal remains active.


### 09 — Completed first P4 comparison (provisional)

Four captures completed and the controller verified restoring fixed production before
releasing the lock. Scheduling tests subsequently took ownership. All four completed
captures have zero overruns, watchdog warnings or panics; production replay agrees
with every recorded label/reason (38/38, 38/38, 36/36, 37/37).

| Arm / fixture | Captions | Scored speaker phrases | WER | Actual one-to-one speaker accuracy | Unknown scored phrases | Split / merge phrases |
|---|---:|---:|---:|---:|---:|---:|
| Center conv2 | 38 | 37 | 15.63% | 28/37 = 75.68% | 1 | 0 / 8 |
| Energy conv2 | 38 | 38 | 14.83% | 28/38 = 73.68% | 1 | 0 / 9 |
| Energy conv4 | 36 | 36 | 17.66% | 33/36 = 91.67% | 3 | 0 / 0 |
| Center conv4 | 37 | 37 | 18.09% | 28/37 = 75.68% | 7 | 2 / 0 |

The conv4 majority-mapped baseline score was 81.08%; use the stricter 75.68% above
because majority mapping conceals the duplicate cluster. Labels were scored directly
from device assignments with `spkrules.run_metrics`, not replaced by offline predictions.
Different segmentation/mixed-phrase exclusions produce different denominators. Alignment
still uses estimated playback onset; independent acoustic runs and one run per arm/fixture
are insufficient for a universal gain claim. No held-out speaker qualification yet.
Decision: retain as promising on conv4, but do not promote automatically: conv2 identity
errors regress. Repeat validation is needed. Full result:
`overnight/09-p4-results.json`; scorer `overnight/score09.py`; logs remain private.

### 21–23 — Independent segmentation/redecode arms built

21 adds an opt-in freeze of both noise-floor estimate and ambient-history updates
while an utterance is active. Baseline already freezes upward movement but permits
quieter evidence to lower the floor. The new option freezes that downward movement
as well. Existing speech-peak logic remains unchanged. Synthetic calibrated noise at
RMS 60, speech at 1000, and a 50 ms quiet gap at RMS 5 demonstrates the difference:
baseline floor falls to 5, frozen floor stays 60. The default flag is false.

22 reduces only the max segment setting from 10s to 8s, preserving the 2s quiet-cut
search. Sanitizer-backed tests force 25s of continuous voiced PCM through actual 8s
and 10s configs, verify earlier cuts and exact sample conservation. Existing 720
chunk comparisons / 1,076 reference segments continue to pass.

23 inspection found baseline already requires matching request ID, phrase start,
voiced end, and exact completed inference sample count. The original plan's proposed
coverage guard would be a no-op. Refined the experiment to force fresh completed-phrase
decoding instead of accepting otherwise valid speculation. Speculative work still runs;
its completed result is discarded. This tests whether reuse has an accuracy/latency
trade-off without claiming a missing guard was fixed. Actual C++ predicate checks
cover missing/stale IDs, mismatched lengths, exact matches, and forced re-decode.

All three builds retain the same fixed models, x2f pacing, production speaker rules,
center windows, closing pauses, cache settings and diagnostics. HardwareOne tracked
sources were restored. Queued P4 tests use conv2/conv3 on baseline-before, each independent
arm, baseline-after, after 20 completes successfully/restores production. Their controller
requires completed predecessor captures, exclusive busy.lock, Mac mini Speakers at 50%,
approved app-only flashes and restoration afterward. No P4 measurement yet.
- 21: `codex-21-freeze-noise` SHA256 `8e9ffad65a142af0c7168faebe2c02681fa1e998f4eef82b02dfe5225f0adab7`.
- 22: `codex-22-max8` SHA256 `08af797aa3c0546743a090f99c04c89b03de94b4ff5005cd0710cd12246e8cfe`.
- 23: `codex-23-redecode` SHA256 `76684ef2282dc86ed3e0470e8417c7fa88d002937637e5e7e77c388bdf33f5ac`.

State: `21-23-p4-status.json`; build/controller scripts and source diffs are private.

### 24 — Bounded vocabulary mechanism check (in progress)

Added an opt-in compile-time decoder bonus cap; default is positive infinity, preserving
existing behavior. The cap is applied consistently to the search score and its pruning
upper bound. With cap 1.5 nats, actual C++ decoder tests show that a custom-word bonus
can overturn a 0.25-nat acoustic preference but cannot overturn a 5-nat control preference.
Strong target acoustics stay correct. Tests use synthetic logits/LM to isolate behavior;
they are not real-audio WER or proper-name qualification. The unchanged-default LM
oracle/strength/context suite passes. No production vocabulary, files or settings changed.
Still required: implement fixed experiment vocabulary in a private arm, target/control
audio, and end-to-end scoring. Do not count 24 as completed from these unit checks.


### 24 — Fixed vocabulary and end-to-end trial prepared

Prepared and froze an independent four-term experiment vocabulary before any acoustic
results, using task-related proper names/technical terms. Terms, spellings and all
reference phrases are private in `vocab24/experiment.json`. They are appended only to
the model's in-RAM vocabulary snapshot when capacity permits; existing stored vocabulary
is not edited. A runtime diagnostic checks presence of all four terms without printing
user vocabulary. The experimental decoder caps total custom-word bonus at 1.5 nats;
LM alpha/beta, fixed weights and all other baseline policies remain unchanged. This is
one fixed bounded-vocabulary feature trial, not a sweep or a claim that higher caps
cannot help. Verify `TL vocab_test active=1`, successful LM decoding and positive
configured bonus before interpreting target-word results; inactive trials are not gains.

Private Mac-native Samantha fixture: 16 interleaved phrases (eight targets and eight
controls, including confusable ordinary-word contexts), 72.736 seconds at 16 kHz mono
int16 with 1.4s inter-phrase gaps and an initial two-second silence. Speech was rendered
locally to files, not played during generation or sent to a service. Immutable config,
audio and source hashes are in the manifest. This synthetic single-voice fixture tests
bias mechanics; it cannot establish natural-speech or speaker-ID qualification. Score
exact canonical spelling and control insertions transparently, preserving raw captions;
do not hide tokenization differences by silently formatting captions.

Built `bench-codex-24-vocabcap.bin`, SHA256
`b37e00c0dcfda653c6f305e0d6408ecbb5c03f0c24381054a62da6f23f584bb1`.
HardwareOne sources restored and clean after build. Private artifacts/scripts:
`overnight/build24.py`, `prepare24.py`, `24-arm-ready.json`, and the standard arm
source diff/build manifest. The first controller launch had an indentation syntax error
before execution; no board operation occurred. The corrected script was parsed before
launch, and the original error log is retained.

Queued P4 sequence after successful 21–23 completion/restoration: baseline-before,
vocabulary arm, baseline-after; each reads `vocab24` and natural conv3 via the Mac's
speakers at 50%. No audio upload. Requires ten completed predecessor captures, checked
image hash, exclusive lock and approved app-only flash; restores fixed production in
its finalizer. Controller `overnight/run24_p4.py`, state `24-p4-status.json`, corrected
log `overnight/24-p4-controller-retry.log`. Six new captures are planned, not complete.
Runtime LM activation, target/control WER, false insertions, natural-conv3 regression,
performance and memory effects are still unmeasured. Final all-arm report remains pending.

Latest controller verification: the scheduling process and four successor queues all
returned live session handles. The active chain has not been restarted due to stale
state or an observation timeout. Scheduling is on its baseline conv4; later queues
are waiting and do not own the board. Goal remains active until measurements and
requirement-by-requirement report are complete.


### Scoring and first scheduling evidence — 3 November 2026

Added `score_experiments.py` to score finalized captures while later tests run. It
preserves incomplete/error entries and derives provenance hashes, actual one-to-one
speaker counts across all captions (including absent labels/embeddings as unknown),
diagnostic-only counts, memory observations, alignment sensitivity, draft/network
wall cost, and runtime activation evidence. Tests cover cancellation versus successful
decode counts, true/false vocabulary flags, timing-clock overlap and missing-label
coverage. It invokes the existing three timing tools; all acoustic onset/manifest-end
reference limitations remain. Private snapshot: `overnight/live-chain-metrics.json`.

Runtime baseline confirms file LM beam 32, strength 1.0, configured hotword bonus 1.0,
and active speculation. Thus 18 requests 40, not a cap-induced no-op; the decoder log
prints file beam, not the requested override, so inspect compiled source plus successful
decoding. For 24, the 1.5 ceiling is non-binding on the existing 1.0 bonus: this is four
extra terms at effective 1.0, not an increase to 1.5. Activation and control errors still
need to be checked on the actual vocabulary arm. Baseline has zero custom words.

First completed 10 conv2 capture versus its fresh baseline-before (single runs):

| Metric | Baseline | Defer drafts while speaker pending |
|---|---:|---:|
| Median speaker-network ms | 1165.735 | 767.080 |
| Median speaker-job wall ms | 1269.555 | 868.794 |
| Median label delay ms | 1286.5 | 883.0 |
| Speaker jobs with draft overlap | 24/38 | 0/38 |
| WER | 16.43% | 19.04% |
| One-to-one correct speaker phrases | 29/38 | 29/38 |
| Merge phrases / unknowns | 8 / 1 | 8 / 1 |
| Median shown-text lag ms | 1256 | 1365 |
| Phrases without drafts | 0 | 3 |
| Manifest-end final median / p90 ms | 3159 / 3944 | 3137 / 3950 |

This is direct evidence that draft contention costs speaker time, but not a safe
production change: shown-text freshness and single-run WER regress. Capture offsets,
acoustic variation and final baseline-after remain important. Do not attribute the WER
change solely to scheduling from one pair. The remaining scheduling captures and final
baseline are still pending. Counterbalancing/single-pair screens are not replication.
The scorer distinguishes in-session watchdogs from total setup warnings and keeps raw
counts rather than silently excluding skipped speaker jobs. No defaults changed.


### Coverage strengthening and vocabulary attribution — 3 November 2026

The first natural conv2 baseline has zero forced boundaries. Added a separately frozen
45.00s same-speaker stress source to ensure experiment 22 can exercise hard cuts:
concatenate nine source clips from the existing conv2 speaker with the most audio,
compress low-energy runs >=260 ms to 100 ms (threshold max(32 PCM RMS, 10% of source
p90 frame RMS)), retain the rest, and bracket with silence. Stored under ignored
`long22/`, with source manifest/audio hashes and transformation metadata. This is a
synthetic stress case; compressed low-level frames can contain soft speech, so it is
not natural-conversation accuracy qualification. No board upload or new identity data.

The still-idle 21–23 queue was intentionally restarted to add `long22` to its baseline
before/after and only arm 22. It now expects 13 total captures. The idle 24 queue was
updated to require those 13 successes/restoration. Neither owned the board during this
change; the active scheduling run was not interrupted. Corrected queue logs:
`21-23-p4-controller-stress.log`, `24-p4-controller-stress-gate.log`. A detected queue
wait or an observation timeout was not treated as process termination.

Vocabulary scoring now accepts the frozen experiment config. It separately reports
exact target-token hits, ordinary-control insertions, globally excess terms, and terms
in mixed-reference or unassigned captions. No mixed caption gets clip-level credit;
missing target captions remain in the denominator. Synthetic checks demonstrate that
control false insertions cannot be presented as target corrections, and out-of-reference
terms remain visible. Raw pooled WER is not formatted or rewritten. This scoring is
prepared for 24; no vocabulary-arm acoustic result is available yet.

Further provisional scheduling captures (single runs, baseline-after still pending):
- 10 conv4: median trunk 1371.842 -> 767.097 ms; label delay 1910.5 -> 886 ms;
  draft-overlap jobs 28/34 -> 0/35. But actual correct speaker phrases 32/34 -> 27/35,
  unknowns 2 -> 7, splits 0 -> 1, and WER 17.66% -> 18.30%. Shown lag 1554 -> 1651 ms,
  no-draft phrases 3 -> 5. Strong compute benefit, unacceptable quality evidence so far.
- 11 conv2: trunk 977.212 ms, labels 1278 ms versus baseline 1165.735 / 1286.5 ms;
  shown lag 1260 versus 1256 ms. WER 15.23% versus 16.43%, correct speaker phrases
  remain 29/38, but unknown 1 -> 0 comes with merge phrases 8 -> 9. A faster kernel
  wall time is not automatically a faster useful label. Full arm/baseline-after pending.

The natural clip references and estimated playback onset still limit absolute live
latency and per-phrase identity attribution. The scorer records ±0.5s sensitivity;
repeat validation with measured playback onset is required before promoting a promising
candidate. No default changed, no failed/ambiguous reference was silently hidden.


### Playback alignment preparation and first x3 result — 3 November 2026

Read-only CoreAudio inspection confirmed Mac mini output volume 50%, 48 kHz output,
and reported pipeline components totaling 1,100 frames (22.917 ms). Output was already
running because an authorized live test was playing. No audio or board operation was
started by this query.

Added a pure playback alignment estimator, with tests for known timing, round-trip
uncertainty, missing/ambiguous IO transitions, invalid clocks and unavailable latency.
It retains `snapshot_age_unmeasured` / `acoustic_onset_measured=false`; CoreAudio IO
start plus nominal pipeline is not acoustic correlation. This helper is prepared for
future measured repeats, not integrated into the already-running/queued trials, and
not used to revise past alignments. Do not call existing absolute latency exact.

First x3 pacing conv2 capture: WER 16.43%, actual correct speaker phrases 29/38,
unknown 1, merges 8, matching the baseline-before point estimates. Median label delay
1283.0 versus baseline 1286.5 ms; trunk 1158.699 versus 1165.735 ms. Shown-text lag
worsened 1256 -> 1356 ms. No convincing label advantage from this point; conv4 and
baseline-after remain pending. Full scheduling report must use both final baselines,
not pick the favorable individual comparisons. Source: live scheduling metrics JSON.


### Setup retry correction — 3 November 2026

Found avoidable pre-test waiting in the old harness: `closering` immediately returned
an explicit `Error: ... close deferred ... retry closering`, but its success-only regex
waited the entire 90-second timeout before the next attempt. This was not 90 seconds
of board computation. `close_test_peers.py` now matches success or error acknowledgements,
retries recognized transient close replies after 5s (at most 12 acknowledgements), and
propagates real serial timeouts or authorization/unexpected errors. It opens no port
and changes no device settings by itself. Synthetic observed-response checks pass.

Only the four then-idle successor controllers (13–18, 20, 21–23, 24) were stopped,
verified terminal with exit 143, patched/parsed and restarted. Snapshots and old logs
are preserved privately. The active scheduling owner was not touched. Their new logs
are `<group>-p4-fast-close.log`; state paths/predecessor gates remain unchanged.
This is a harness response-handling correction before recording, not a new algorithm
arm or extra measured success. Comparisons within each later batch use the same setup
path for its controls and candidates. Earlier measurements retain their original setup.


### 10–12 — Completed scheduling comparison

All ten captures completed, with zero panics, audio overruns or watchdogs (including
setup). Fixed production restoration was verified, the lock released, and the next
recognition controller took ownership. Final metrics and input hashes are in ignored
`overnight/10-12-final-metrics.json`, generated by `score_experiments.py`.

| Arm | Fixture | WER | One-to-one correct / scored | Unknown | Split / merge | Label median ms | Shown lag median ms |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline-before | conv2 | 16.43% | 29/38 | 1 | 0/8 | 1286.5 | 1256 |
| baseline-before | conv4 | 17.66% | 32/34 | 2 | 0/0 | 1910.5 | 1554 |
| codex-spk-gate | conv2 | 19.04% | 29/38 | 1 | 0/8 | 883.0 | 1365 |
| codex-spk-gate | conv4 | 18.30% | 27/35 | 7 | 1/0 | 886 | 1651 |
| codex-spk-gate100 | conv2 | 15.23% | 29/38 | 0 | 0/9 | 1278.0 | 1260 |
| codex-spk-gate100 | conv4 | 17.87% | 31/34 | 3 | 0/0 | 1896.5 | 1536 |
| codex-pace3 | conv2 | 16.43% | 29/38 | 1 | 0/8 | 1283.0 | 1356 |
| codex-pace3 | conv4 | 18.09% | 27/36 | 6 | 3/0 | 1420.5 | 1520 |
| baseline-after | conv2 | 17.23% | 28/38 | 2 | 0/8 | 1286.0 | 1247 |
| baseline-after | conv4 | 17.23% | 26/34 | 7 | 1/0 | 1943.0 | 1461 |

Interpretation against both baseline-before and baseline-after:
- 10: strong and repeatable compute/label benefit across these two fixtures. Median
  trunk time falls to ~767 ms, with zero observed draft overlap. Labels fall from
  1286–1286.5 -> 883 ms on conv2 and 1910.5–1943 -> 886 ms on conv4. But WER and shown
  lag are worse than both surrounding controls on both fixtures. Reject default change.
- 11: conv2 WER improves versus both controls, but one additional merge replaces an
  unknown, and label delay stays essentially unchanged. Conv4 WER is worse than both
  controls, with label delay essentially unchanged. No general benefit established.
- 12: conv2 WER matches the better control and label delay is unchanged, with worse
  shown lag. Conv4 labels improve but WER exceeds both controls and there are three
  splits versus control zero/one. No general benefit established. Conv2 logged draft
  busy time falls from 75,020–75,678 to 57,930 ms (~23% fewer logged draft milliseconds),
  but that is not a power measurement or a demonstrated battery-life gain.

Conv4 speaker accuracy varies widely even between identical baseline images (32/34
versus 26/34), so earlier single-control claims of a causal speaker regression were
premature. Full deferral's 27/35 is within that broad control range. Its WER/draft-lag
trade-off remains unfavorable in this screen. Compare raw counts/denominators and
alignment sensitivity; do not cherry-pick whichever baseline makes an arm look good.
This is one capture per arm/fixture bracketed by two controls, not replication or
unseen-speaker qualification. Recognition experiments are now running; their results
and all later queued work are still pending. No production defaults changed.

### Resume interruption: internal filesystem full

On model-switch resume, three recognition captures were finalized: baseline-before
conv2/conv3 and arm13 conv2. Arm13 conv3 failed during setup, before `stt start`:
`savesettings` returned a storage-full error rather than success. Its serial log has
an IDLE0 watchdog warning with `cmd_exec_task` running, and LittleFS reported
`No more free space`. This is a separate filesystem/setup failure; it is not evidence
of an STT inference crash or recurrence of the closed cache-line fault.

The controller restored and verified `soak-app.bin` (SHA256
`172f4377e59c544a9ce39a492708adf5c7f208f98d1f2bdbed6520ad21f1eb7e`).
Successor controllers stopped or were terminated while waiting, without running their
physical comparisons. Existing completed captures remain preserved; no restart from
scratch is warranted. The numeric scorer processed 17 finalized captures across
09, 10–12 and partial 13–18 with zero scoring errors.

A read-only capacity query measured LittleFS total 9,285,632 bytes, used 9,281,536,
free 4,096; SD free space was 31,015,829,504 bytes. Runtime system/sensor logging was
not running on inspection. Listing the broad capture directory itself stalled and
produced filesystem watchdog warnings, so further broad traversal was stopped.
Ring reconnection was seen on production boot despite earlier off/save acknowledgements;
runtime reconnect was disabled again. Persistence remains to be reverified after
space recovery and a successful save/reboot.

Proposed recovery is private verified backups of only `errors.log`, `events.log`,
and `system-events.log` under `/system/sys_logs`, followed by removal of those board
copies (about 771 KB total). Automatic approval review rejected removal because explicit
authorization for destructive changes is required by project instructions. User approval
is pending; no board log deletion or flash erase has occurred. Backup preparation uses
the approved helper and owns the board lock. Resume must preserve the three completed
recognition captures, rerun the failed setup/capture, and retain both bracketing controls.
No recognition candidate is qualified from this partial comparison.

Backup preparation completed: all three logs total 771,291 bytes. Each was saved in
ignored private storage, fsynced, reread from disk, then independently read again from
the board and compared byte for byte. SHA256 values and file paths are in the private
backup report. All original board files remain intact; lock released. No queued
controller remains live. Cleanup approval is still required.

### Offline recovery preparation while cleanup approval is pending

The private recognition controller now requires `--resume` when a checkpoint exists.
It validates the previous failed/restored state, keeps completed captures and interruption
history, rejects duplicate capture keys, skips completed arm/fixture pairs before flashing,
and requires all 16 unique captures before completion. An isolated checkpoint check
executed only initialization/selection logic (no serial-helper import or board access):
three captures retained, 13 remaining, first pending arm13/conv3. The unchanged queued
13–18, 20, 21–23 and 24 firmware manifests were rehashed successfully. This prepares a
resume; it does not authorize cleanup or restart any hardware controller.

Partial recognition results (estimated acoustic alignment, no post-control yet):

| Arm | Fixture | WER | One-to-one correct/scored | Unknown | Session watchdog/panic |
|---|---|---:|---:|---:|---:|
| baseline-before | conv2 | 15.83% | 29/38 | 0 | 0/0 |
| baseline-before | conv3 | 24.89% | 42/47 | 3 | 0/0 |
| 13: recognition gain 1.25x | conv2 | 14.03% | 28/38 | 1 | 0/0 |

The apparent conv2 WER improvement comes with one fewer correctly attributed speaker;
without conv3 and the post-controls, neither improvement nor a causal regression is
qualified. The failed conv3 setup's filesystem watchdog is retained separately and
must not be hidden by the zero session-watchdog figures above. All broader physical
comparisons remain stopped, pending approved space recovery. No defaults changed.
