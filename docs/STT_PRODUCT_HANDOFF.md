# Standalone STT readability and recording handoff

## PSRAM fault root cause and fix — 2 November 2026 (Claude)

This supersedes the "corrupting writer is unknown" status below and in
[P4_HEAP_WATCH_PLAN.md](P4_HEAP_WATCH_PLAN.md).

**There is no software writer.** The cause is the combination of HardwareOne 755edfa0 (10 Oct)
and 5143de9b (13 Oct):
- 755edfa0 set 128-byte L2 cache lines, which made each phrase 344 ms faster.
- 5143de9b raised PSRAM to 250 MHz. That commit contributes, but is not required for the fault.

Under heavy CPU and DMA load, PSRAM contents end up as if a cache line had been written 8 or 32
bytes off. That damages:
- **The heap header:** `heap_data` takes the `minimum_free_bytes` value. The invalid `0x002960c4`
  in the plan above is this signature.
- **SDIO receive buffers.**
- **Spinlocks and function pointers.**

There are two crash classes: at session start (during the 20 MB model read into PSRAM) and at
session end.

PCM-file bench (conv1 read from SD; deterministic):

| PSRAM / L2 line | Start crashes | End crashes | Close ms | Model ms per audio ms |
|---|---|---|---|---|
| 250 MHz / 128 B (production) | ~11% | up to 31% | 1250 | 0.272 |
| 200 MHz / 128 B | 17% (4 crashes + 1 hang of 30) | 0/14 | 1303 | 0.282 |
| 80 MHz / 128 B | 0/30 | not run | — | — |
| 250 MHz / 64 B | 0/30 | 0/10 | 1360 | 0.299 |
| 200 MHz / 64 B | 0/30 | 0/10 | 1424 | 0.310 |

**Software writers ruled out.** The loggers were layout-neutral (RTC-memory rings and flash code,
with the DRAM and PSRAM layout unchanged), because instrumentation that used extra RAM masked the
fault. Ruled out:
- Upward overlapping memmoves into PSRAM: none.
- SDMMC DMA misdirection: 0 anomalies in 76,902 transactions, logged with controller state.
- PSRAM stack overflow.
- Model inflate: the model is stored uncompressed.
- A warm-loader race.

**Fix:** HardwareOne `027eef22` "Use 64-byte L2 cache lines on the ESP32-P4", branch
`claude/p4-l2-64` on `aa6508fd`, keeping PSRAM at 250 MHz.
- **Cost:** about 110 ms of caption close latency. Model time rises from 0.272 to 0.299 ms per
  audio ms. WER (3.8%) and speaker accuracy are unchanged.
- **Build folders:** existing ones keep 128 B lines until their sdkconfig is recreated.

**Production soak** (aa6508fd plus only the fix, 2 Nov):
- 30 of 30 starts, and 39 of 40 live sessions with the conv1 clip played at 50%.
- The 40th was reset into download mode by an `esptool chip_id` from a Codex session on the mini
  (18:13:26–32). It was not a firmware fault: there was no panic.
- In total, 0 firmware faults in 70 starts and 39 complete sessions. With 128 B lines, about 8
  start failures and about 6 session faults would be expected.
- Since then, `heaptw_remote.py` sets `TIOCEXCL` on the port, so such a probe fails instead of
  resetting the board.

**HardwareOne branches.** All three are local to a MacBook clone (origin: the MacBook's
`~/esp/hardwareone-idf`). They are not pushed. They are copied to the mini as a git bundle; see
`~/claude-heaptw/pickup/README.txt`.

| Branch | Commit | Contents |
|---|---|---|
| `claude/p4-l2-64` | `027eef22` | The fix only. |
| `claude/stt-bench` | `9520a5b1` (on `027eef22`) | `sttperf pcmsrc`; pacing, pause and speaker-rule knobs; off-by-default diagnostics (`System_HeapTripwire`, `System_MemmoveLog`, `tools/p4/idf-sdmmc-bench-hooks.patch`). |
| `claude/heap-tripwire` | `2fc6b6f5` | The earlier v6 tripwire, superseded by the bench port. |

**Bench tools:** [tools/device_tests/bench/](../tools/device_tests/bench/README.md).

**Speed findings (64 B, x2f pacing).**
- **Final caption timing:** the final caption arrives a median 1.87 s after the true speech end
  (p90 2.85 s):
  - ~0.49 s waiting for the pause to close the phrase.
  - ~1.37 s of final decode over the whole phrase, at 0.30 ms per audio ms.
- **Speculative finals:** they almost never apply to phrases of 4 s or more. Closing uses the
  peak-relative stop-silence, while the trim and speculation use the trim-voiced test, whose
  voiced end lands ~125 ms after the true end.
- **The model already runs on both cores** (resident graph).
- **Draft pacing x2f** (2× pacing; a phrase's first draft paced only by the 600 ms minimum and
  1 s floor) cuts the median speaker-label lag from ~7.3 s to ~2.3 s, at no WER cost. With 128 B
  lines at 250 MHz it crashed in 23 of 54 runs; with 64 B lines it is stable.

**Running at handoff:** `~/claude-heaptw/arms1-chain.sh` holds `busy.lock` until about 21:35 on
2 Nov. It runs four arms × 3:
- `prodl64`: production pacing.
- `x2fes400`: 400 ms pause at 4 s or more.
- `x2fsc700`: 700 ms pause below 4 s.
- `x2fes4sc7`: both.

Results go to `~/claude-heaptw/arms1-summary.txt`. The board is left on the last arm image.
`original-slot.bin` there is the 128 B production rollback, and `soak-app.bin` is production with
64 B lines.

**Next:**
- Score arms1, then adopt x2f pacing and any pause change that keeps WER and speaker accuracy.
- Accuracy work needs conv2–4 and the corpus stores in the bench. conv1's speakers are far
  apart, so it cannot test the speaker hold/merge rules. Upload them to SD with
  `heaptw_remote.py upload`.
- Report the cache-line fault to Espressif. This needs the user's approval.

The full working notes are in `~/claude-heaptw/pickup/2026-11-01-combined-stt-handoff.md` on the
mini (private, not in git).

## Codex pickup in progress — 2 November 2026

The user authorized preserving the dirty standalone checkout before pickup. Local backup
branch `codex/backup-local-stt-20261102`, commit `7aad4c0`, retains its editable source,
tests and documentation. The untracked handoff package was moved intact to ignored
`private/pre-claude-resume-20261102/handoff/`. No private evidence was committed.
Speech then fetched/switched/fast-forwarded cleanly to `claude/spkeval-diagnostics`
`8bda527`. The existing HardwareOne checkout is the reboot-preserved
`~/stt-tmp-backup-20261101/hardwareone-ab`; its current branch
`codex/stt-live-fault-capture` at `94183e1c` was left unchanged (it also has the requested
`codex/stt-ab-heap-watch` branch). Prerequisite `aa6508fd` already existed. All three
bundle refs match the handoff. A separate `../hw1-bench` worktree uses `9520a5b1`.

The isolated `p4-openclaw` baseline build passed under ESP-IDF **5.5.5**, after copying
that checkout's ignored Arduino component and running `tools/p4/prepare_sdk.sh`.
Actual generated sdkconfig: `CONFIG_CACHE_L2_CACHE_LINE_64B=y` and
`CONFIG_SPIRAM_SPEED_250M=y`. App size 6,029,008 bytes, below the recorded
0x715000-byte app slot. This is a build result, not physical qualification.
The additional worktree/build is retained for this active bench task; remove disposable
build output after retaining selected app/ELF/config/source identities and results.

The user authorized board access, then explicitly chose to let Claude's active bench
chain finish while preparations proceed. Claude finished at 21:07; Codex acquired its
own lock afterward. No concurrent serial access was attempted. The authoritative active
controller state is `private/resume-20261102/test-status.json`; scripts and logs are in
that directory. Three matched local x2f runs completed, all with 3.80% WER and 26/40
speaker labels correct (14 unknown). One run had an in-session IDLE0 watchdog warning,
no panic; further startup warnings are retained separately. The initial controller's
warning gate stopped after this completed batch and restored/verified the fixed
production image. `phase-one-status.json` preserves that stop. The remaining controller
continues bounded tests with nonfatal warnings counted, stopping on panics or failed
sessions, and restores the fixed production image afterward. Do not open the P4 while
this controller owns the lock.
The chain's `x2fes400` flash failed before any bench runs; preserve this harness failure
and fill that arm separately. Evidence and pickup scripts are under ignored
`private/resume-20261102/`. New tests must hold `~/claude-heaptw/busy.lock`, use the
specified Python and `heaptw_remote.py`, and flash only through its verified app-only
path. The fixed production rollback is `~/claude-heaptw/soak-app.bin`.

Conv2–4 were found on `/Volumes/Audiodrive/stt/hw1-work/device-tests/speaker/`, and their
WAV/manifest SHA-256 values match the previous qualification protocol. Three additional
24-turn PCM playlists were prepared from the **development speaker partition** in
`private/speaker/audio-window/plan.json` (LibriSpeech, AMI and VoxPopuli; 2/3/4 speakers).
Their source stores include names containing “test”, but only the already designated
development speaker IDs were selected. Reserved final-partition audio remains unused.
These bounded playlists are screening coverage, not corpus-wide qualification.

Existing host voiceprint replay (`spkrules.py`, 200 seeded shuffled orders on clean/session
sets; 180 corpus conversations in recorded order) still rejects hold/merge promotion.
Across corpus sets, hold 0.50/0.45 reduce splits by 4.00/5.46 per 100 scored phrases but
increase merges by 2.17/2.80 per 100. Merge-young3 increases merges by 2.82 per 100.
These are prior stored voiceprints, not new device results. New on-device diagnostics and
final speaker-rule recommendations are still pending; completed pacing/pause results follow.

### Completed conv1 pacing/pause screen

All timings below are seconds. WER and speaker scores are from `benchscore.py`; final latency is
`truelag.py` (true speech end to final caption), shown-text lag is `draftlag.py`. The original
`latsplit.py` reports are retained privately. Caption segmentation differs between pause arms.

| Arm | Runs | WER | Speaker accuracy | Unknown/run | Final median / p90 | Shown lag | Speaker-label lag |
|---|---:|---:|---:|---:|---:|---:|---:|
| Production pacing, 64 B | 3 | 3.80% | 64.10–65.00% | 14 | 2.008 / 3.189 | 1.576 | 19.486 |
| x2f, earlier Claude build | 10 | 3.80% | 65.00% | 14 | 1.866 / 2.854 | 1.337 | 2.273 |
| x2f, new local build | 3 | 3.80% | 65.00% | 14 | 2.084 / 3.261 | 1.762 | 4.063 |
| x2f + 400 ms long pause, new local build | 3 | 3.59% | 62.79% | 16 | 2.029 / 3.023 | 1.564 | 4.090 |
| x2f + 700 ms short pause | 3 | 4.22% | 65.85% | 14 | 1.911 / 3.093 | 1.670 | 3.505 |
| x2f + both pause changes | 3 | 4.01% | 68.18% | 14 | 1.793 / 2.995 | 1.559 | 3.538 |

**Recommendation:** x2f pacing with unchanged pauses is supported as a speaker-label-latency
improvement on conv1, with unchanged WER and speaker outcomes. Keep its tradeoffs visible: the new
local batch had slower final/shown-text timing than the earlier x2f batch, and one in-session watchdog
warning. This is a bounded recommendation for further qualification, not a production-default change.
**Do not adopt any tested pause change:** the 700 ms short pause and combined change increase WER;
the 400 ms long pause improves WER (17 rather than 18 errors / 474 words) but lowers speaker accuracy
and increases unknowns (16 rather than 14). Its modest timing gain against the matched local x2f arm
does not meet the user’s no-speaker-regression criterion.

Coverage and reliability qualifications:

- The production-pacing runs emitted 40 captions each, but two runs report `labelled=39 skipped=1`.
  Their 64.10% benchmark accuracy is 25/39; including the skipped label gives 25/40. x2f is 26/40.
- `benchscore.py` maps each cluster to its majority reference speaker; this can hide duplicate-cluster
  splits. The separate one-to-one `spkrules.py` replay remains necessary for speaker-rule decisions.
- The true-lag tool matched 31/32 clip ends per run. The omitted clip can change with segmentation
  (for example, zero-based clip 28 in production/x2f versus clip 24 in the combined-pause arm).
  These reported medians/p90s are tool-defined covered-clip summaries, not complete-clip guarantees.
- All 25 completed runs in this table reached `done` without a reported panic. In-session watchdog
  warnings: short-pause 1/3, combined-pause 1/3, new x2f 1/3; none in the other table batches.
  (Corrected 3 November against original per-run session counters; whole-log setup warnings
  had been mixed into the earlier combined-pause count.) Additional
  warnings outside the STT session window are preserved in raw logs and whole-log scores. Do not
  describe these batches as warning-free. The interrupted earlier production batch (one completed
  run) and failed original long-pause flash are retained separately, not pooled into this table.
- Repeated deterministic conv1 runs are timing repetitions of one conversation, not independent
  accuracy samples or broader/long-duration qualification. No production defaults, main branches,
  HardwareOne pushes, or outward-facing reports were changed.

New arms were built with `tools/device_tests/bench/build_arms.sh`, `HW1_BENCH` pointing to the
isolated worktree. Apps: x2f `eaacec59`, long-pause `480ac08c`, x2f diagnostics `c770fd98`. Matching
ELFs, sdkconfigs, build manifests and source diffs are retained under `private/resume-20261102/arms/`.
Both cache/PSRAM settings were checked in every arm. Source defaults were restored; the worktree
is clean. The diagnostic build enables full voiceprint logging and fixture self-checks; the
recognition model and speaker-rule knobs remain unchanged. Diagnostic timings are not substitutes
for the non-diagnostic arm comparison.

Broader device diagnostics are active/pending; consult `test-status.json` before board access.
The new conv1 diagnostic control completed 40 captions with no in-session watchdog/panic;
`benchsets.py check` agrees on all 40 speaker IDs/reasons. One-to-one replay reproduces
62.5% production accuracy versus 97.5% for hold 0.45/0.50 on this easy conversation.
This does not validate the rules on similar speakers.

The first conv2 upload failed after a confirmed 522,200-byte prefix, before any conv2
bench run. The old uploader matched any `success:true` response, including stale replies,
then retried sequential writes without recognizing an already committed offset. Raw logs
contain offset mismatches; no partial input was benchmarked. A subsequent resume attempt
failed at `loglink` setup before sending PCM. Both attempts restored/verified the fixed
production image; `phase-two-status.json`, `phase-three-status.json` and private upload
captures retain them. Repeated 30-second failed ring reconnects were also observed and
can stall the console; their contribution to earlier timing variability is not established.

`tools/device_tests/bench/upload_chunks.py` now checks the exact expected committed offset,
accepts an already committed same-chunk retry, and rejects stale/wrong acknowledgements.
Six host regression cases pass. The local `heaptw_remote.py` was backed up, then updated
for that module, explicit known-prefix resume and optional runtime-only Bluetooth quieting
while uploading. Sensor polling pauses are balanced. The optional `closeble` attempt
also failed before PCM transfer; the controller restored the fixed production image.
On explicit user request, ring auto-reconnect was then disabled with
`bleautoreconnect r1-ring off`, `closering` confirmed the link closed, and a query
confirmed auto-reconnect disabled. Flash was preserved as requested; no full erase
was performed. Evidence is in private `stop-ring-result.json` and its serial log.
The normal-mode retry failed at STT logging setup before PCM transfer. Upload setup
now requires authentication only, with 90-second startup allowance. Ring reconnection
was still seen after the first reopen; an explicit `savesettings` then returned success
and a fresh console boot confirmed auto-reconnect disabled. The saved-off state is
verified in `stop-ring-persist-result.json`. Temporary upload-only Bluetooth shutdown
is being retried after this durable ring-policy change; it remains unqualified.
The original helper and patch are private. Physical transfer recovery and conv2–4/corpus
bench results are still pending. The user explicitly chose to continue the broader tests
rather than stop because of the upload duration.

## Broader live accuracy completed — 2 November 2026

At the user's direction, bulk PCM uploads were stopped and the six prepared playlists
were played through the verified Mac mini Speakers at 50%, into the board microphone.
No broader PCM-file benchmark completed. These results are acoustic live tests of the
x2f diagnostic arm, with unchanged production speaker rules and closing pauses.

| Fixture | Captions | WER | Speaker accuracy (majority mapping) | Unknowns |
|---|---:|---:|---:|---:|
| conv2 | 38 | 18.44% | 73.68% | 2 |
| conv3 | 47 | 27.90% | 78.72% | 10 |
| conv4 | 33 | 20.21% | 93.94% | 2 |
| corpus1 | 26 | 8.76% | 96.15% | 1 |
| corpus2 | 24 | 28.64% | 70.83% | 7 |
| corpus3 | 28 | 25.00% | 78.57% | 6 |

All six runs ended `done`: 196 captions, zero audio overruns, zero in-session watchdog
warnings and zero panics. Speaker diagnostics replayed with the production rule are
recorded beside each run. Artifacts: ignored `private/resume-20261102/live-*`,
`live-metrics-summary.json`, `live-rule-comparison.json`, and `live-status.json`.
The controller verified restoration of `soak-app.bin` after the six tests; a subsequent
speaker-cost profiling run was then authorized by the user and owns the board separately.

A prior conv2 live attempt failed after 12 segments/11 retrieved captions, with an audio
overrun and watchdog warnings while console replies were delayed by reconnect activity.
It is preserved as `live-conv2-20261102-224129` and excluded from completed-run rule
comparisons. Other setup attempts and controller interruptions are retained privately.
Closing the ring and glasses runtimes before playback cleared the observed console
stalls; this observation does not reopen the closed cache-line fault investigation.
Ring auto-reconnect was explicitly disabled and saved; glasses closure was runtime-only.
The experimental full `closeble` setup was abandoned after teardown failures.

**Limits:** one live run per fixture, diagnostic overhead enabled, no paired production
pacing baseline on these six recordings, no held-out-speaker qualification, and no SD
power-loss testing. Playback alignment uses the board sample count immediately before
`afplay`, not measured acoustic onset. Per-run +/-0.5 s speaker-score sensitivity is
saved in `alignment-sensitivity.json`; speaker/reference metrics and true end-to-end
latencies remain provisional. Majority speaker mapping can conceal splits; the separate
one-to-one rule replay is the decision metric. No acoustic results are pooled with
conv1 SD-file timing results.

Across the six captured device voiceprint sets, 200 shuffled orders per set plus the
recorded order were evaluated. Relative to production:
- `hold_0.50`: split phrases/100 -2.11, merge phrases/100 +1.95; criterion passed: False.
- `hold_0.45`: split phrases/100 -2.22, merge phrases/100 +2.82; criterion passed: False.
- `merge_young3`: split phrases/100 +1.74, merge phrases/100 +4.53; criterion passed: False.

Retain production speaker rules: the conv1-only gains do not justify increased merges
on broader voices. No production STT defaults were changed.

## Speaker-processing cost investigation — 2 November 2026

The user requested immediate investigation of speaker-processing cost. Across the six
completed broader runs (196 jobs), median job wall time was 1,279.8 ms: neural-network
trunk 1,175.1 ms, frontend 60.5 ms, head 35.3 ms and clustering 2.9 ms. Medians do not
add. Aggregated time shares were trunk 82.58%, frontend 12.93%, head 3.49%, clustering
0.49%. Median `lag_ms - us/1000` was 11.0 ms; this residual includes queue wait,
diagnostic fixture checks and other pre-embed scheduling, not a pure queue timer.

A retrospective association with recognition drafts is substantial. Joining each
speaker job's wall interval to `TL draft s/e` intervals, median trunk wall time was
762.6 ms for <5% overlap (66 jobs), 1,180.9 ms for 5–50% overlap (89 jobs), and
1,702.7 ms for >=50% overlap (41 jobs). These are observational buckets, not a causal
A/B scheduling result; final recognition, preemption and memory contention are not
isolated. All use the fixed-size speaker input window. This makes scheduling draft
recognition against speaker work the strongest next experiment. Keep capture and
final recognition priorities; measure draft freshness and stable-label delay together.
Do not switch the speaker model to dual-core blindly: the code deliberately uses
single-core mode to avoid contention with recognition's ESP-DL workers.

A dedicated conv2 live profile kept the diagnostic session active beyond 240 seconds,
collecting all 234 layer timings. Ten layers consumed 50.2% of timed module execution;
the three largest were execution indices 192 (9.9%), 206 (8.4%) and 218 (7.3%). The
module-name accessor returned `?`, so these indices are not yet mapped reliably to
operator types or tensor shapes. Baseline mean measured module time was 1,075.5 ms,
versus mean trunk wall time 1,109.1 ms: instrumentation/yields/outside-module overhead
cannot explain the bulk of network time. Diagnostic heap probes and fixture checks
remain enabled; these are diagnostic-build timings, not production qualification.

A controlled experimental build gave only the speaker trunk a 65,536-byte internal
arena budget, keeping the fixed model, rules, pacing, cache lines and PSRAM clock.
Built through `build_arms.sh`: `bench-codex-spk-int64.bin`, SHA prefix `a8756827`.
HardwareOne tracked sources were restored after the build; this is not a default change.

| Conv2 diagnostic arm | Median job ms | Median trunk ms | Mean trunk ms | Mean timed modules ms | Arena internal / PSRAM bytes | Startup internal low-water bytes |
|---|---:|---:|---:|---:|---:|---:|
| Existing PSRAM arena | 1275.478 | 1168.659 | 1109.113 | 1075.484 | 0 / 600000 | 180744 |
| 64 KiB internal budget | 1256.101 | 1150.033 | 1127.595 | 1102.743 | 65536 / 576000 | 128716 |

Each trial completed 38 captions with zero overruns, watchdog warnings or panics.
Baseline versus internal-arena WER was 16.83% / 16.03%; majority-mapped speaker
accuracy was 76.32% / 73.68%. These separate acoustic captures cannot establish
model equivalence; the speaker-score drop is an additional reason not to adopt the arm.
The 19.4 ms median-job improvement (1.52%) is not persuasive: mean trunk time worsened
1.67%, and measured startup internal headroom fell 52,028 bytes. One acoustic run per
arm does not establish a speed or accuracy equivalence claim. **Reject adopting this
arena change.** No production speaker algorithm, model or scheduling default changed.

Artifacts are ignored under `private/resume-20261102/`: `speaker-cost.json`,
`speaker-draft-overlap.json`, `speaker-layer-profile.json`, `speaker-arena-comparison.json`,
the two `live-conv2-20261102-232554` / `233243` captures, and arm build/source manifests.
Both profiling controllers verified restoring fixed production `soak-app.bin`.
After the final restore, a fresh console boot confirmed ring auto-reconnect disabled;
`final-board-verification.json` records the result. The board lock was released.
Remaining: controlled draft/speaker scheduling A/B, reliable layer/operator mapping,
targeted kernel work if warranted, and longer stress/accuracy qualification.

## Overnight follow-on investigation

The user authorized at least 15 one-change experiments on speaker uncertainty,
recognition accuracy, and speaker cost. The 24-item plan and sequential results are
in `docs/STT_OVERNIGHT_EXPERIMENTS.md`. Experiment 01 is implemented and tested
offline; coverage improves, but extra identity merges fail the promotion gate.
Experiments 02 and 03 now also have independent implementations and replay results:
shorter admission and longer adaptation both regress broader speaker metrics and are
rejected. Experiments 04–05 have now been screened: history capping shows no measured short-session
gain (long-history check pending), and young-profile hold increases shuffled-order merges.
The user expanded the required plan to 24. Experiment 04 repeated-history stress and 06 deferred revisions are now measured,
with no promotion justified: sequential accuracy/coverage or identity errors regress.
Experiments 07 (capacity) and 08 (fixed-weight float window screen) are now measured.
Neither warrants promotion: no capacity gain; longer windows improve accuracy but
increase merges. Quantized/P4 window results remain unchecked. Experiment 09 has a positive fixed-weight float energy-window screen and a new
counterbalanced conv2/conv4 P4 comparison running. Device results are pending.
Experiments 10–12 have independent built scheduling/pacing arms and a P4 controller
queued behind 09; no measurements yet. Experiment 19 is screened and rejected;
20 has a positive float loudness-normalization screen and independent P4 validation
queued behind recognition. Experiments 10–18, 20 validation and 21–23 are independently built/queued, and 24 has a bounded-bonus mechanism test
and a built private-vocabulary arm plus frozen synthetic target/control fixture queued
for P4 measurement;
the goal stays active.

Recognition experiment arms 13–18 now have a serialized build pipeline and a P4
queue gated on successful completion/restoration of 09 and 10–12. Gain arithmetic
passes exhaustive sanitizer checks; no recognition improvement is claimed yet.
See the overnight plan for exact changes and required activation checks.

Experiment 09 P4 comparison is complete and mixed: one-to-one conv4 speaker accuracy
75.68% -> 91.67%, but conv2 75.68% -> 73.68% with an additional merge error.
All four captures have zero overruns/watchdogs/panics. No automatic promotion;
repeat testing and alignment checks remain necessary. Scheduling chain is now running.

All 24 planned items now have either measured screens or implemented experimental
arms/mechanism checks; this does not mean all 24 are complete. The serialized P4
chain (10–12, 13–18, 20, 21–23, 24) is still running/waiting. Final scoring, activation
checks, candidate repeat validation, restoration verification and reporting remain.

First scheduling conv2 pair confirms zero draft/speaker overlap and faster median
labels (1286.5 -> 883.0 ms), but shown-text lag and single-run WER regress. Full
scheduling chain/final baseline are still pending; no production recommendation.
Live scoring now includes missing speaker labels in coverage and runtime activation
checks; details and provisional counts are in the overnight plan.

The live chain continues. Experiment 22 gained a separate long-speech stress source
to guarantee hard-cut exposure; only idle successor queues were updated. Vocabulary
scoring now distinguishes target corrections from control insertions and ambiguous
attribution. Additional scheduling captures retain the speed/quality trade-off; final
baselines and all downstream physical measurements are still pending.

Scheduling 10–12 is complete: ten captures, zero panics/overruns/watchdogs, verified
production restoration before recognition tests took over. Full deferral cuts median
labels to ~0.88s but worsens WER and draft freshness against both surrounding controls.
Bounded deferral/x3 pacing have no general default-change case. Conv4 baseline speaker
accuracy itself varies substantially; see full counts and limitations in the overnight plan.

## Current overnight checkpoint — 1 November 2026

- Stable-PCM candidate b7598680 retains bit parity in host/target tests; its
  measured feature-task CPU cost is +1.07348%, not a speed win. Full live-speech
  qualification remains open and it is not installed.
- RTC store-watchpoint controls passed individually and with both cores armed.
  The dual test verified both firing and non-firing cores inactive after panic
  without reopening serial.
- Heap-watch e1044e86 completed two five-boot cohorts: 163,235 ms summed armed
  time, 60 forced checks, zero caught writes/fatal/watchdog/overrun markers. The
  longer cohort watched 8,478–10,847 ms past phase 321. This does not resolve
  the earlier invalid-control-pointer faults or establish ordinary-use rates.
- Scalar and 128-bit overlapping PSRAM controls passed on both CPUs. The
  corrupting writer is unknown. Next audit actual caller/alias paths and plan
  fault-time field/argument capture. An independent I2C bounds-guard candidate
  passes eight host cases; it is not applied or linked to the STT fault.
- Both fixtures removed and original full app slot restored/verified. Final
  baseline: 5,562,368 B LittleFS free, logging inactive, PDM preferred, model
  header/footer unchanged. All runs silent; future playback 50%.

See [AB_TEST_RESULTS.md](AB_TEST_RESULTS.md#both-core-synthetic-recovery-and-heap-field-watch)
for per-trial numbers, timer-source correction, source patches and limitations.
HardwareOne diagnostic sources remain local on codex/stt-ab-heap-watch at
570be9f8. The existing 1.1 GiB build is retained for the next diagnostic;
selected matching recovery/debug/source inputs are private. No automatic
production integration or HardwareOne branch push has occurred.

The original readability milestone was functionally qualified on 21 October 2026 on the connected P4X-EYE with its model card. That milestone confined source edits to HardwareOne_Speech_To_Text and did not modify HardwareOne. Later authorized A/B and diagnostic work has local HardwareOne candidates; its results and remaining qualification gaps are recorded below and in [AB_TEST_RESULTS.md](AB_TEST_RESULTS.md). The original milestone qualification does not qualify those later candidates.

Implementation checkout: `/Users/cadbecaimacmini/Documents/ChatGPT/HardwareOne_Speech_To_Text`.

The source baseline is commit `a2ef959e85b6bba95f1cecf57768bd1ff075f8c9`. The recovered implementation is now included in this repository; see Git history for its publication commit. No speech model training, punctuation model or diarization changes were made.

## Agreed behavior

- Improve readability using ordinary formatting: whitespace, paragraph starts, standalone I and its contractions, and configured term casing. Preserve raw recognition output.
- Let people add names and terms after model training, without retraining, rebuilding the language-model file or flashing firmware. One entry supplies recognition preference and display casing.
- Prepare shared transcript events and presentation for later browser/glasses/saved-reader parity.
- Save useful offline recordings with excerpt titles, completion state, optional calendar time and persistent power-cycle/boot/session ordering.
- Provide review/search/export through a lightweight interface appropriate to this standalone project.
- Exclude automatic punctuation classifiers, Mac punctuation models, semantic summaries and speaker-processing changes.

## Original implementation plan

1. Build a bounded portable C++ vocabulary and formatting component with host tests.
2. Connect the existing decoder custom-word mechanism to an editable SD vocabulary file; apply edits between phrases.
3. Add recordings with raw text and metadata, explicit start/end state and independent error reporting.
4. Persist boot/power-on counters in an isolated NVS namespace. Add USB commands for vocabulary, saving and review.
5. Build a localhost browser viewer and USB adapter. Exercise draft/final/label events with fixtures without adding a new draft or speaker producer to this minimal app.
6. Build the P4 application, inspect and preserve the device's existing partitions, back up its current firmware and use app-only flashing for hardware tests.
7. Update this document with actual behavior, evidence and integration limits.

## Plan compared with implementation

| Area | Implemented | Difference or limit |
| --- | --- | --- |
| Formatting | Bounded C++ whitespace normalization, paragraph-start casing, I contractions and exact whole-word display aliases. Raw words are retained separately. | No inferred punctuation or general name recognition. The standalone app treats a note as one paragraph; HardwareOne supplies speaker-turn boundaries. |
| Vocabulary | SD TSV file plus serial/browser add, remove, list and reload; connected to the decoder's existing CustomWords argument. | Single recognition words only: 256 entries, 31 ASCII characters each. Display aliases permit 63 printable ASCII characters with no spaces. No pronunciation learning. A valid LM is required for recognition preferences; display formatting also works with greedy recognition. |
| Storage | One append-only JSONL recording containing start, final and end records, raw/formatted text, excerpt title, clock flags, counters and sample positions. | The plan considered raw text plus a metadata sidecar. JSONL keeps both together in this formerly storage-free example. HardwareOne can preserve its existing text writer and use a sidecar for the equivalent metadata. |
| Startup ordering | Persistent boot count, power-on-reset count, per-boot session sequence, reset reason and random persistent ordering domain. | PowerCycleNumber counts ESP_RST_POWERON resets, not a perfect electrical plug/unplug history. Counts begin at feature installation; an NVS erase creates a new ordering domain. |
| Time | Optional UTC, explicit clock-valid flag and monotonic note duration. Explicit USB command/browser button sets time from the computer. | Offline cold boot can lose calendar time. Previously unknown dates are never replaced with download/reconnection time. |
| Viewer | USB live final captions, SD listing/paged read, file import, literal search of loaded notes, titles, per-recording speaker aliases, JSONL export, stable paragraphs and follow-live/manual review. | Titles/aliases are in browser memory and exported annotations; they are not written back to SD. Search does not index the entire card. |
| Draft and speaker parity | Shared event reducer consumes provisional drafts and existing late speaker assignments; fixture tests cover deduplication and grouping. | The minimal P4 microphone app still produces finals only. There is no new draft worker or speaker model. HardwareOne must connect its existing producers. |
| Porting | Portable module, standalone adapters, tests and the integration checklist below. | No automatic firmware/UI sync installer was added. The existing tools sync script does not transfer these components into the significantly newer HardwareOne application. |

## Source map

| Files | Purpose |
| --- | --- |
| `firmware/components/hw1_transcript/transcript.h`, `.cpp` | Portable vocabulary table, formatter and startup-counter arithmetic; no Arduino, VFS, BLE, USB, accounts or inference dependency. |
| `firmware/examples/p4_eye_captions/main/product.h`, `.cpp` | Standalone SD persistence, JSON events, serial commands, NVS and USB platform adapters. |
| `firmware/examples/p4_eye_captions/main/main.cpp` | Initialize the adapters, pass custom words to LM decode, poll commands between inference calls and publish accepted captions. |
| `tools/transcript/web/model.mjs` | Event reducer, stable phrase identity, draft/final handling, existing-speaker grouping, ordering and torn-final-write import recovery. |
| `tools/transcript/web/app.js`, `index.html`, `style.css` | Browser viewer/controller. `replay.jsonl` contains explicitly simulated drafts and labels. |
| `tools/transcript/serve.py` | Loopback-only USB/import adapter on the Mac; not an embedded web server or HardwareOne authentication replacement. |
| `tools/transcript/README.md` | Commands, limits, formats, vocabulary validation and recording-boundary semantics. |
| `tests/` | Portable C++ sanitizer tests, actual app persistence tests with SDK stubs, viewer tests and loopback HTTP tests. |

The speech engine files under `firmware/components/hw1_stt/stt/` were not changed. Do not copy that older engine snapshot over newer HardwareOne source.

## Vocabulary and formatting contract

`/sd/STT Models/user_vocab.tsv` accepts a display term alone, or a display term followed by a tab and an explicit lowercase recognition form. HardwareOne becomes recognition word hardwareone plus display HardwareOne. A display alias containing digits requires a supported spoken form. The current decoder accepts lowercase letters and internal apostrophes; multi-word mappings are outside this implementation.

Edits are validated and staged before replacing the active file/dictionary. The previous file is retained as `.bak`; a missing main file can recover from that backup. Invalid reloads retain the active dictionary. File replacement reduces interrupted-edit risk but does not guarantee FAT/card power-loss atomicity. The decoder uses a stable dictionary during each synchronous inference call.

Custom words bias existing decoder choices, including words absent from the main LM vocabulary. They do not teach a pronunciation or guarantee recognition. Hotword strength comes from the existing LM header. The acoustic model, decoder alphabet and LM file are unchanged. Display aliases are explicit user substitutions; ordinary formatting never invents replacement words or sentence punctuation.

## Recording and event contract

Files live under `/sd/STT Notes/` and contain schema-1 JSON records. Serial events use the `STT_EVENT ` prefix; files do not.

- `start`: sessionId, bootNumber, powerCycleNumber, sessionNumber, orderingDomain, bootNonce, resetReason, bootDurable, startedUptimeMs, clockKnown, optional startedUtc and source.
- `final`: sequence, immutable rawText, displayed text, startSample/endSample, forcedBoundary, cumulative droppedPhrases, formatted flag and excerpt title.
- `end`: outcome, elapsed duration and phrase count. A missing end is unfinalized/interrupted, never confirmed success.
- Viewer adapters also accept `draft` with independent version/sequence, `speaker` with original phrase sequence and existing assignment/readiness, and exported `annotation` with title and per-recording aliases.

Counters and sample offsets are decimal strings to preserve integer precision in JavaScript. Boot/session counters order notes within the same persistent ordering domain. Different devices or erased NVS generations have no shared counter chronology.

The importer retains complete records preceding an invalid unterminated final JSON line and reports recovery. Corruption in the middle is rejected. Raw records are never silently rewritten to manufacture a successful recording.

`note stop` closes saving results accepted through that command; microphone capture and inference continue in a separate unsaved session. A queued phrase can complete after a boundary. This simple accepted-result lifecycle is not sample-accurate recording control and must not replace HardwareOne's existing stop/drain/cancel semantics. Default startup note duration includes preparation time. Sample offsets refer to the continuous microphone stream.

## Host and browser verification

All four suites passed:

1. `python3 tests/test_transcript.py`: actual portable C++ under AddressSanitizer/UndefinedBehaviorSanitizer. Covers casing, whitespace, I contractions, exact aliases/whole-word matching, immutable raw input, output bounds/canaries, vocabulary capacity and startup arithmetic/overflow.
2. `python3 tests/test_product_storage.py`: actual product.cpp, real LM custom-word code and IDF cJSON with narrow SDK/NVS stubs and a temporary host SD directory. Covers vocabulary writes, invalid-edit retention, raw/formatted records, end finalization, unsaved-session separation, interrupted replacement recovery and counter failure disclosure. A regression also reads a valid escaped-alias record larger than 8 KiB. It does not emulate FAT or physical NVS transactions.
3. `node tests/test_viewer.mjs`: final deduplication/conflict detection, stale draft handling, late speaker grouping, unknown speakers, UTF-8, large counter sorting and incomplete-final-write recovery.
4. `python3 tests/test_bridge.py`: loopback assets, bounded event history/gap handling, missing-device behavior and Host/Origin restrictions.

Python/JavaScript syntax and whitespace checks passed. Real P4 JSONL was imported into the browser, displayed with its configured casing, renamed and exported. Export inspection confirmed that raw text and the title annotation survived. The USB viewer also listed and read recordings directly from the card and displayed a cold-boot note with Date unavailable, power cycle 1, boot 3 and recording 2. A later dated recording sorted ahead of it by the same boot/session order.

Fixture speaker paragraphs do not establish real speaker accuracy. This task did not alter or evaluate diarization.

## P4 hardware qualification

The successful test board is ESP32-P4 revision v3.2, MAC `e8:f6:0a:e3:a7:68`, at `/dev/cu.usbmodem1101` during testing. Its pre-test app identified itself as HardwareOne 0.99.98.4, built 16 October 2026. A complete 16 MiB flash backup and extracted original app slot were saved privately before replacement.

Built with ESP-IDF 5.5.5 and the existing patched ESP-DL 3.3.12. Application size: **635,584 bytes**. SHA-256:

`741c37a14a0954f03ad20e5bd0a680653a05dbdc6752adfc09bd93cd533e848a`

Actual target factory slot: offset `0x10000`, size `0x715000` (7,426,048 bytes). LittleFS begins at `0x725000`. Only the application was written, and esptool verified its hash. Bootloader, partition table, LittleFS, original model files and unrelated NVS namespaces were preserved.

The earlier no-card failure came from a different attached P4, MAC ending a7:73, with a smaller `0x615000` app slot. Its original 0.99.95 app was restored and the user disconnected it. Neither that board's layout nor the example's generated layout should be assumed for another device.

### Completed physical checks

| Check | Observed result |
| --- | --- |
| SD/model startup | Card mounted. Pinned 20,112,128-byte 15x5 gen2 model loaded and verified. Model warm-up about 15.6 seconds in the first captured boot; Listening followed noise calibration. |
| LM | Existing card LM loaded: 43,003 words, 87,348 bigrams, 23,831 trigrams, 1,599,996 bytes. Captions reported language-model decoding. |
| Vocabulary | Added terms through USB, saved and reloaded them, verified the active list. HardwareOne survived software restart and physical power loss. Temporary Camera casing was removed afterward. |
| Real microphone and formatting | Played a locally generated 26-word sentence through the Mac speaker into the P4 microphone. Saved/read back raw and displayed text; configured camera to Camera mapping worked. No added punctuation. |
| Recording integrity | Received start/final/end from the saved file through paged reads. Phrase sequence and raw/display fields matched. Both controlled runs reported zero dropped phrases. |
| Recognition observation | First controlled run had one word substitution out of 26; the cold-boot repeat had zero word edits. These two tiny acoustic runs are functional checks, not a representative accuracy benchmark or evidence of recognition improvement. |
| Timing observation | First 7.64-second captured phrase processed in about 2,445 ms: frontend 172, model 2,193, decode 75 ms. This is one phrase, not a latency distribution. |
| Software restart | Boot count 1 to 2, power-on count remained 0, ordering domain unchanged, vocabulary retained. |
| Physical power cycle | User unplugged/reconnected the board. Boot count 3, power-on count 1, reset reason 1, same ordering domain, vocabulary retained. |
| Unknown time | After physical power loss, clockKnown=false and startedUtc=null. A speech recording saved successfully and displayed Date unavailable with power/boot/session order. |
| Explicit time sync | Set clock from the computer, then created/finalized a new dated recording. The earlier unknown-date file remained unchanged. |
| Browser integration | Listed and read real card files over USB, compared dated/undated order, imported a readback file, edited its title and verified export. |
| Final build regression | After the reader-buffer fix, flashed the final hash, returned to Listening at boot 4 with the retained vocabulary, and read the original cold-boot start/final/end records successfully. Saving was then stopped. |

The final reader uses a 16 KiB buffer so valid formatted records with escaped aliases are not split at the former 8 KiB limit; this is covered by the production-code host regression.

Physical testing also caught an integration bug: the default IDF console could print but did not receive commands in this app. Installing the USB Serial/JTAG driver and selecting its VFS fixed reception; the tested image contains that fix. HardwareOne should retain its existing console infrastructure rather than install this standalone adapter a second time.

No sustained throughput, battery-life, broad vocabulary-benefit or long-duration accuracy benchmark was performed. Under this small functional workload the app completed inference, file writes, commands and readback. Long SD/USB operations can still put pressure on the bounded capture queue. No claim of complete power-loss atomicity or universal storage-failure recovery is made.

## Device state at October 21 qualification and private evidence

At the October 21 qualification, the remaining connected P4 was running the standalone tested app. This historical state is not the October 31 device state: that measurement used integrated firmware 0.99.99, as documented in GLASSES_LIVE_PROFILE.md. Saving is stopped after the tests; microphone/live captions continue. The browser USB viewer can start a new saved recording. The original 0.99.98.4 app is backed up for app-only rollback. The other P4's original firmware was restored before it was disconnected.

Private evidence is under ignored `private/product-retry-20261021/`: original flash/app backups, partition read, image hashes, hardware log, qualification reports, software-restart and physical-cycle status, speech recordings and browser export. Earlier-board evidence is under `private/product-validation-20261021/`. These folders contain private flash/transcript data; do not commit or forward them as part of the agent handoff.

## HardwareOne integration checklist

1. Inspect the current firmware first. Port `hw1_transcript` and its tests narrowly. Do not overwrite the current engine/runtime with this repository's older stt snapshot.
2. Adapt the platform layer to HardwareOne's existing boot identity, clock, authenticated account directories, guarded VFS and storage policy. The standalone SD folder and USB commands have no account model.
3. Feed a stable custom-word snapshot into each existing LM decode. Keep display aliases separate from raw recognition words and preserve owner/session cleanup rules. Evaluate new terms against actual audio rather than treating a successful edit as proof of recognition quality.
4. Preserve the existing raw transcript writer and finalization rules. Store corresponding metadata/annotations separately if the current format is plain text. IDs belong to original phrases; delivery byte receipts still reference raw producer text, not formatted length.
5. Expose existing finalized text, draft/version and speaker snapshots consistently to the browser. Connect those existing producers; the standalone example does not implement replacements.
6. Share grouping/casing policy while retaining each renderer's display budget. Preserve G2 changed-band drawing, page ownership and raw-source scroll anchors. Browser DOM code is not a glasses renderer.
7. Keep HardwareOne's stop/drain/cancel behavior. Simultaneous browser observation of a glasses-owned session requires a same-account read-only observer contract; do not compete for controller ACKs or transfer cancellation authority implicitly.
8. Titles/speaker aliases currently persist through browser export only. Decide how to save edits in HardwareOne metadata under its existing permissions. Full-card search/indexing remains optional future work.
9. Rebuild current required HardwareOne profiles and qualify on the glasses. Standalone P4 success does not establish firmware integration correctness.

`tools/sync_to_hardwareone.sh` copies selected tooling folders into experiments only. It does not install this firmware component or viewer. Review and integrate source changes explicitly against the current HardwareOne checkout.

## October 31 repository handoff

The recovered standalone transcript implementation, tests and viewer are versioned
alongside the October 31 reports and sanitized numeric measurements. See
[STT_OPTIMIZATION_PLAN.md](STT_OPTIMIZATION_PLAN.md) for proposed experiments,
[GLASSES_LIVE_PROFILE.md](GLASSES_LIVE_PROFILE.md) for measurement limitations,
and [stt-performance-graphs.html](stt-performance-graphs.html) for the readable graphs.
The optimization proposals have not been implemented. Raw device logs, settings,
recordings and rollback images remain in ignored private storage and are not
available through Git. No new device qualification was performed for publication.

The October 31 [source comparison](STANDALONE_PARITY.md) confirms newer
HardwareOne changes not yet reconciled here. The requested future direction is
standalone qualification first, then HardwareOne adaptation; direct source-copy
synchronization is not sufficient. October 31 host reruns passed all four suites
listed above. No fresh firmware build or device qualification was performed.

## October 31 standalone reconciliation

The identified HardwareOne runtime/memory/watchdog, LM, speaker-policy and SDK
fixes are now ported. The standalone also owns a portable streaming scheduler for
capture-time feature prefixes, drafts and optional speculative finals. See
[STANDALONE_PORT.md](STANDALONE_PORT.md) for exact profiles, validation, adapter
boundaries and remaining device acceptance. This supersedes the earlier
"not yet reconciled" status; it does not supersede historical hardware results.
No speed/accuracy gain is claimed.

The default profile was later boot-tested on the throwaway P4X-EYE: it boots, keeps
NVS counters and answers USB `status`, but that board had no microSD card, so model
load and captions were not reached. HardwareOne 0.99.98.5 was restored afterwards.
Details are in [the device smoke test](STANDALONE_PORT.md#october-31-device-smoke-test).

## October 31 HardwareOne A/B testing

See [AB_TEST_RESULTS.md](AB_TEST_RESULTS.md) for the test conditions, matched
session distributions, confidence intervals, conversation and technical
recordings, fault history, and limitations. Neither prepared candidate qualified
as a no-regression win. Speaker-off reduced sampled PSRAM use but removed speaker
labels; slower previews delayed first preview. Speaker-label results varied on a
repeated recording, primarily because unknown labels increased in one run.

The fixed model and onboard PDM microphone were used throughout. The original
app image was restored and its complete app slot verified after candidate tests;
the final session stopped STT, found file logging inactive and recorded 7,016,448 B
LittleFS free. The installed and rebuilt baseline binaries differed, so logging
results were not used as candidate A/B baselines. Watchdog warnings and assertion
reboots occurred under instrumented playback; the user reports ordinary use is
more stable, and these tests cannot establish ordinary-use frequency or causation.
Raw audio, logs, transcripts, backups and prepared candidate bundle remain private.

The LM sweep, bit-exact kernel experiments and full RAM attribution remain for a
future agent; no new firmware improvements or integration were performed here.

## Deferred speaker confirmation follow-up

An offline two/three-phrase confirmation prototype is documented in
[SPEAKER_PROVISIONAL_EXPERIMENT.md](SPEAKER_PROVISIONAL_EXPERIMENT.md), with
numeric results in [AB_TEST_RESULTS.md](AB_TEST_RESULTS.md). It recovers the
original duplicate-speaker clean-span replay but increases corpus merge errors;
neither variant passes the no-increased-merge gate. It also delays early labels,
and the three-phrase variant substantially reduces coverage. Production firmware,
the model and the device policy remain unchanged. Do not integrate this research
prototype as a qualified improvement; P4 memory/timing and independent recordings
were not tested. Voiceprints and per-run artifacts remain private.

The ranked [ten-experiment roadmap](SPEAKER_NEXT_EXPERIMENTS.md) starts with
an audit of the audio/feature path, voiced-window selection and separate-speaker
evaluation. Each approach has an evidence basis, a decisive comparison and its
main system cost; they are proposed experiments, not qualified improvements.

## Standalone audio-path round

The [audio experiment](SPEAKER_AUDIO_EXPERIMENT.md) adds an unused opt-in portable
window selector and native/Python audit tools. On 30 speech cases the frontend
implementations closely agree (minimum float-embedding cosine 0.99999940). A new
partition excludes prior reference IDs and separates 37 development IDs from
36 final IDs. Only development has been embedded/scored. Energy-window selection
has inconclusive pooled gains and domain regressions; aggressive end trimming
harms the original failure case. Neither qualifies for HardwareOne integration.
The production model/frontend behavior and clustering are unchanged. Full
quantized-path parity, actual microphone input and P4 latency/memory remain gaps.

## P4 audio and code-only overnight checkpoint

[AB_TEST_RESULTS.md](AB_TEST_RESULTS.md) now records 25 identical-input P4
parity trials and one bounded exact-microphone-PCM capture. Five fixed inputs
repeat across reboots, but a borderline clean same-speaker pair changes from
0.605987 on Mac float to 0.595828 on P4. Float replay alone cannot qualify target
speaker accuracy. The exact-input capture shows signal-path effects are not
uniformly harmful: its 7850 pair is 0.642508 on P4, 0.632405 on Mac using the
same microphone PCM and 0.585196 on waveform-aligned clean PCM. A successful
captured sequence has roughly 299 ms pre-roll; the original failure's actual
PCM is unavailable, so a timestamp-only suspected late onset is not proved.

Session replay now uses the retained speaker prefix instead of the full capture
span; six corrected replays are separate private artifacts. The earlier cached
session comparisons used longer captured inputs. Their historical numbers are
not rewritten; clean/corpus development rejection still stands. New tools and
synthetic cases cover prompt interleaving, vector log truncation, retained-span
reconstruction, nonce/checksum ownership, raw vector norms and waveform timing.

All temporary SD files/folders were removed and the original full app slot was
restored/digest-verified. Last probe: 6,520,832 B LittleFS free, logging inactive,
PDM preferred, model header/footer unchanged. Mac playback is now 50% by user
request; earlier 75% runs remain a separate condition. Overnight work is silent.
See [SPEAKER_OVERNIGHT_PLAN.md](SPEAKER_OVERNIGHT_PLAN.md) for the active queue.

The first code-only candidate clears the speaker frontend frame padding once
per computation instead of every frame. It preserves all 150 host reference
cases under normal and ASan/UBSan builds, with no workspace/model/settings
change. P4 output/performance qualification is pending; no production firmware
has received it. Additional work targets actual correctness and redundant work,
not configuration, model or CPU/RAM clock changes.


The subsequent silent target frontend microbenchmark completed five reboot
trials: 30/30 feature checks exact, average computation 55.381373 -> 54.709907 ms
(-1.212441%; paired boot-bootstrap saving 0.599460–0.743473 ms). This is not a
qualified end-to-end application win. Original app restored/full-slot-verified,
owned fixture removed; final free LittleFS 6,504,448 B, logging inactive/PDM.
A host cleanup read-framing error was fixed with strict bounded re-reads and a
synthetic regression; no device crash occurred. Portable boundary testing passed
720 chunk comparisons with exact source PCM, and the existing streaming suite
passed ThreadSanitizer. See the results report for scope and remaining gates.

The completed 44-condition offline boundary probe adds 1,485 float embeddings
and 8,800 order simulations on the four known conversations. Padding/cropping
changes the 7850 clip 0/2 pair from 0.538 to 0.629; effects are nonmonotonic.
Tail removal improves pooled in-order results but regresses Conversation 4 and
increases Conversation 1 shuffled splits. It is not a qualified default, a
production configuration change or evidence of an incorrect original mic cut.
Final speaker partitions remain unopened. Numeric tables are in the report.

The pointwise address-walk probe c6252b6e is complete and rejected for promotion:
5 reboot trials, 15 timed pairs, 50/50 identical feature/logit/greedy-text hashes.
Inference +1.157667 ms, boot-bootstrap 95% [-3.437533, +5.275533] ms, matching
headroom; zero reported watchdogs/overruns/fatal markers. No production setting,
model weight, tile size or clock configuration changed. The original full app
slot was restored/verified and owned fixture removed; final probe LittleFS free
6,422,528 B/logging inactive/PDM/model header and footer unchanged. Traffic and
complete export-fixture/length coverage remain open; no end-to-end gain is
claimed. The active queue next examines feature-row ownership and actual cache
measurement. Neither source suspicion establishes the cause of past faults.


## Feature-cache ownership checkpoint

The real HardwareOne row-writer/retirement race is reproduced on Mac and P4.
Normal repair 3fff3013 is a two-file patch: stage eight rows in existing worker
scratch, then copy/publish only for the same live generation under lock. The
shared frontend alias contract passes 1,251 host rows; normal production portable
StreamPipeline was already using private row publication. Forced P4 checks pass
42/42 across seven boots; both versions match 1,946 normal rows and use the same
3,072-byte task stack with matching 2,624–2,628 B normal-case headroom. The repair
leaves zero stale cache values versus 512 in the old late-write schedules.

Application qualification is incomplete. Five lifecycles completed, two failed
after STT stop despite all ownership checks passing: one hardware-watchdog reset
(0x7), one core-0 load-access fault in heap allocation (MCAUSE 5, MEPC 0x4ff37390,
MTVAL 0x0029607c). The intended matrix has four clean runs and two failed
attempts, plus one separate clean smoke run. No clean subset is substituted for
the full failure history. There is no established WER benefit or link to prior
crashes. The fix is prepared for review, not merged or left installed. The next
priority is teardown-phase/heap-integrity evidence; a live-ring concurrency
audit remains separate. See AB_TEST_RESULTS.md for numeric details and caveats.

The harness now rejects resets throughout command/drain/status polling,
invalidates stale tokens and preserves failure records. Both interrupted blocks
removed the owned fixture and restored/verified the full original app slot.
Latest original-app probe: 6,230,016 B LittleFS/logging inactive/PDM/model
header/footer unchanged, no new watchdog/fatal markers. Future playback remains
50%; this block was silent. Timeline/source review corrected earlier fixture
startup wording: PDM capture is already active, before the normal feature pool
and speaker worker start. Numeric historical results are unchanged.


Teardown follow-up 5e07c4d9: four silent PDM idle-capture lifecycles completed
(two without/two with fixture), zero watchdog/fatal markers/overruns. All 75
complete logged heap checks passed; one CLI-interleaved marker [301,1] leaves
three full 19-check diagnostics plus one partial. The first diagnostic build
also omitted three model phases; the owning policy and a compile guard now
prevent that silent omission, with synthetic coverage. These instrumented
samples do not explain the two prior shutdown faults or qualify the repair.
No new accuracy or speed benefit is claimed. Next isolate timing perturbation
and self-test effects rather than selecting clean retries. The separate ring
preemption attempt safely rejected stale work but did not establish a TSAN race.
The original app is restored/full-slot-verified and the fixture removed; latest
healthy probe 6,135,808 B LittleFS, logging inactive/PDM, model header/footer
unchanged, no new watchdog/fatal markers. Keep private evidence private.


Marker-only follow-up 002e3a0c: 5/5 no-fixture lifecycles completed; fixture
attempts were two complete and one fault, then the block stopped (two planned
runs unattempted). All 152 markers across eight attempts were intact, including
phase 321 before the fault. The six-frame saved-RA chain is checked against
matching ELF prologues: a 6,384-byte ExecReq allocation from the serial loop
exposed an invalid PSRAM heap-control pointer. The earlier ebe29cdf load fault
has the same validated allocation chain/size. The corrupting writer is unknown;
no qualification or causal claim follows. Next verify watchpoint ownership
before considering a both-core write watchpoint on the heap header.

A separate ring read/write race is now reproduced with actual producer/DSP
code after forcing TSAN ignore_interceptors_accesses=0. This Mac's default hid
memcpy races. Synthetic copy controls validate the setting; the cache-row repair
and actual portable pipeline pass their original suites with stricter checking.
No wrong committed prefix or WER loss is established. Prepare a stable-window
ring repair separately and measure P4 stack/copy cost without configuration
changes. See AB_TEST_RESULTS.md for counts, addresses and all failed attempts;
P4_CACHE_COUNTER_PLAN.md separates verified counter semantics from unmeasured
traffic. Original app restored/full-slot-verified, owned fixture removed; latest
healthy probe 6,021,120 B LittleFS/logging inactive/PDM/model unchanged. No
unqualified image is installed. HardwareOne changes remain local only.


Stable-PCM-window candidate b7598680 is prepared on the local HardwareOne
codex/stt-ab-feature-ring branch. It combines the prior row-staging repair with
locked producer writes / row snapshots and unchanged DSP on private PCM.
Source-bound host tests pass 104 cases / 12,904 exact checked rows per variant;
strict TSAN passes the new candidate and detects both old ring controls. The
normal full/incremental patches and a separate diagnostic patch are in
tools/device_tests/feature_cache/. HardwareOne changes are not pushed.

Five P4 diagnostic boots completed 25 matched pairs with 6,950 exact rows per
arm, zero watchdog/fatal/overrun markers. Task CPU cost is +604.40 us (95%
[557.56,653.32]) per 44,560-sample input, +1.07348%. Stack allocation stays
3,072 B, with 1,600–1,612 B measured free headroom. The 1,024-byte private array
uses existing stack, not a new heap buffer. This is not a performance win;
WER/speaker accuracy/full-app RAM and live-speech latency are unqualified.
The earlier heap-control-pointer faults are not resolved by these clean boots.
Next perform trigger ownership/readback/calibration per P4_HEAP_WATCH_PLAN.md
before watching stores to that heap field. No board trigger is armed.

The normal app was compiled but not flashed; the diagnostic was removed.
Original full app slot restored/verified, owned fixture removed; final healthy
probe 5,943,296 B LittleFS/logging inactive/PDM/model unchanged. Future playback
50%; this entire block was silent. See AB_TEST_RESULTS.md for bootstrap units,
raw numeric distributions, copy-timing limitations and remaining gates.


Heap-trigger discovery checkpoint (16bfb713 / 647e4858): two separate one-boot
read-only diagnostics completed with the original app restored/full-slot-verified
after each. At four lifecycle checkpoints both cores' three shared trigger slots
read TDATA1=0x21000000 (type 2, read-only maskmax 8, configurable bits zero),
TDATA2=0, TCONTROL=0, no debugger and restored selectors. The extended second
image additionally read all 24 TDATA3 values as zero. The first image did not
observe context qualifiers. No trigger was armed or cleared. The heap_data
field at 0x4809e434 held the expected 0x4809e438 at every checkpoint for these
matching images; this does not identify the earlier corrupting writer.

SDK configuration was byte-identical to 002e3a0c. Both runs passed six existing
forced ownership checks each, with zero watchdog/fatal/overrun markers; normal
capture had zero feature rows/speaker jobs. No audio playback occurred. Latest
healthy original-app probe: 5,935,104 B LittleFS free, logging inactive, onboard
PDM preferred, model identity unchanged. Future playback remains 50%.

Next: recheck trigger ownership immediately before a separately labelled
synthetic four-byte store-watchpoint calibration on each core, verify exact
trap PC/address/core and post-trap recovery, then watch the real heap field.
An empty readback is not a permanent lease. Do not probe potentially absent
TINFO or assume reset clears debug state. P4_HEAP_WATCH_PLAN.md records the
ownership and panic-context constraints. Current HardwareOne diagnostic branch
is local codex/stt-ab-heap-watch at 647e4858, based on the earlier cache-only
fault workload; the separately prepared ring repair remains unqualified for
full application use. Matching app/debug/source evidence is retained privately.


Synthetic trigger checkpoint: 18da8a44/core 0 and f8a2a5bc/core 1 each caught
one deliberate four-byte RTC-word store at matching ELF PC 0x4ff22cd0, MCAUSE 3.
Reads/adjacent writes returned, watched value stayed 0x13579bdf and adjacent
became 0x2468ace0. Both recovery STT lifecycles completed with zero new
watchdog/fatal/overrun markers. Expected calibration traps are recorded
separately from ordinary failures. Source-bound lease/release tests and strict
numeric parsing pass; the public incremental patch reproduces f8a2a5bc.

Core 0 recovery included serial reopening (which can reset the board); core 1
kept the same handle through panic/readback/cleanup. Both read inactive state
at recovery and all four later checkpoints, so actual recovery needed no
trigger-data/control clear. Do not infer core 0 panic-reset semantics alone,
pre-reset hit-bit capture, PSRAM/DMA coverage or corruption cure. Next perform
one bounded dual-armed synthetic test with a core-0 store and continuous serial
to verify the non-firing peer's reset state too, before the simultaneous
both-core heap-field watch. The original writer remains unknown.

Both blocks restored/full-slot-verified the original app. No SD fixture was
created. Latest healthy baseline: 5,869,568 B LittleFS free, logging inactive,
PDM preferred, speaker model header/footer unchanged, zero new fatal/watchdog
markers. Models/clocks/cache/configured stacks/policy remain fixed and no
panic-hook change is included. All work was silent; future playback stays 50%.
The local HardwareOne diagnostic branch is codex/stt-ab-heap-watch at f8a2a5bc.
Keep the owned P4 build for the next diagnostic; selected app/ELF/map/config
and bounded source bundles are private. HardwareOne branches are not pushed.


PSRAM scalar-control checkpoint: fcdc25dd/core 0 and 4404da4e/core 1 each
caught one deliberate store at exact ELF PC 0x4ff22cd0, MCAUSE 3, after both
cores' read/adjacent probes and lease verification. Both cores reset inactive
without serial reopening; both recovery STT sessions done with zero new faults/
watchdogs/overruns. Only pre-trap probe values were retained in RTC: no old
PSRAM allocation was read/freed after reset. No SD fixture or playback used.
Original app restored/full-slot-verified after each. Latest healthy baseline:
5,615,616 B LittleFS free/logging inactive/PDM/model header-footer unchanged.
Future playback remains 50%. Source patch and strict parser/tests are in the
feature_cache tools; matching app/debug/source evidence stays private.

Next control is wider-store overlap (aligned owned PSRAM, 128-bit store, watch
offsets 0 and 4). Preserve both trap and returned-store outcomes with exact
ELF instruction identity and owned cleanup. Scalar tests do not qualify wide
instructions, every alias or DMA. The earlier faults and ten negative watched
intervals remain unexplained; no ordinary-use crash rate or accuracy/speed
improvement is inferred. See AB_TEST_RESULTS.md for measured numbers and the
primary-source motivation. HardwareOne branch remains local at 4404da4e; no
model, production labelling, clock/cache geometry or configured-stack changes.


Overlap/source-audit checkpoint: 570be9f8 caught all three exact-PC 128-bit
store conditions (core/offset 0/0, 0/4, 1/4); both cores reset inactive after
each without serial reopening. Six unwatched execution and six read/adjacent
checks passed. Quiet STT smoke done, zero new faults/watchdogs/overruns; original
app restored/full-slot-verified. Final baseline: 5,562,368 B LittleFS/logging
inactive/PDM/model header-footer unchanged. Silent; future playback 50%.

The old fault's saved heap handle/load/call sequence was rechecked; its direct
heap-field contents were not dumped at the fault. An adjacent Arduino I2C cache
array prompted an independent audit: source-bound strict-sanitizer compilation
reproduces address-128 bounds read, and a prepared guard passes eight cases.
The actual SDK is untouched; no invalid I2C address or causal write during STT
is established. Keep this host-only candidate separate for review. Next audit
caller/alias paths and design minimal fault-time field/argument capture.
Cached scalar/vector controls do not establish alias/DMA coverage. Source
patches, numeric findings, sanitizer calibration and limits are in AB_TEST_RESULTS.md.
HardwareOne diagnostic branch stays local at 570be9f8; all private evidence and
selected matching app/debug inputs remain private. No model/policy/clock/cache
geometry/configured-stack change or production promotion has occurred.

### Model-switch resume: storage interruption (3 November 2026)

The 24-item investigation is incomplete. Three recognition captures were preserved
before a fourth failed at `savesettings`, prior to recognition start. Internal LittleFS
has only 4,096 bytes free; filesystem setup produced watchdog warnings. Fixed production
`soak-app.bin` was restored and verified. Downstream physical batches are stopped.
The proposed three-log backup/cleanup requires explicit user approval following an
automatic approval-review rejection; no full flash erase or log deletion occurred.
Runtime ring reconnect was disabled again, but persistence must be reverified after
storage recovery. See the detailed interruption entry in STT_OVERNIGHT_EXPERIMENTS.md.

### Approved storage recovery completed; tests resumed

After explicit user approval, only the three named diagnostic logs were backed up,
verified and removed. LittleFS recovered to 757,760 B free and settings saved. Recognition
resumed from its checkpoint; later physical groups are queued. Ring reconnect was confirmed
disabled after the arm13 reboot, before applying any setup command. Two watchdog warnings
occurred during that boot/setup before STT started and remain part of the stability record.
The full 24-item investigation and final restoration audit remain incomplete.

### Live timing correction (09–14 progress)

Earlier live true-lag figures are superseded: private capture manifests had left
`speech_end_s` unshifted. The scorer now rebuilds all clocks from verified original
references. A separate RMS/clock alignment check also identified stale status onset
(e.g. arm14 conv2 was early by ~1.83s). All 20 completed 09–14 captures passed the
secondary consistency gates and were rescored; original artifacts remain preserved.
Corrected tables and limitations are in the measurement-correction section of
STT_OVERNIGHT_EXPERIMENTS.md. Gain's apparent conv2 lag win shrinks to 12ms; no gain
promotion is supported. Arm14 is measured on both fixtures; arm15 is running. This
remains an incomplete, development-fixture comparison with trailing controls pending.

Arm15 (450ms pre-roll) is now captured on both fixtures: WER 20.44%/31.12%,
one-to-one identity 28/38 and 22/46, unknowns 2/19. This fails quality preservation
against the initial controls; trailing baselines remain pending. Mac mini speaker
route and volume 50 were independently verified. Arm16 is starting.

Arm16 (600ms retained tail) completed both fixtures, WER 20.04%/28.54%. Conv3
failed the fixed RMS alignment gate; its identity accuracy and true lag are withheld,
not silently replaced by the stale status estimate. Raw unknown coverage is 2/38 and
3/45 captions. Activation was verified in retained sample counts. Arm17 is decoding
successfully at measured LM strength 0.900. Trailing controls remain pending.

Arm17 (LM strength 0.9) completed both fixtures with actual 0.900 successful
decodes. WER is 23.85%/31.76%, worse than initial controls; one-to-one identity
27/37 and 24/46, raw unknowns 1/37 and 16/46. No adoption is supported from this
partial group. Arm18 is running; final controls and the shared slowdown audit remain.

Arm18 (compiled beam request 40 versus file beam 32) completed: WER
21.44%/30.26%, raw unknowns 2/37 and 15/45. Conv3 had one in-session watchdog
with CPU1 running `stt`; no panic, no decoder fallback status. This fails a clean
stability screen and is not a promotion candidate. The unchanged trailing baseline
image is now replaying both fixtures. Baseline/arm sdkconfigs are identical.

### Recognition group 13–18 complete; normalization running

All 16 recognition captures completed and fixed production was restored/verified before
the normalization controller took over. Fifteen RMS fits qualify; arm16 conv3 remains
explicitly unqualified for identity/true lag. One session watchdog (arm18 conv3),
38 boot/setup warning occurrences, zero panics and zero overruns. No 13–18 arm
demonstrates a general quality-preserving win.

The identical-image controls drift: conv2 WER 15.83 → 22.85%, conv3 24.89 → 30.47%;
speaker trunk medians 1167 → 2003ms and 1131 → 2748ms. Estimated noise floors change
4 → 12/10 RMS units, with higher idle levels. Do not attribute candidate results
inside those ranges solely to their code change. The cause is unresolved. SDKconfigs
match and host speaker route/volume were verified. Corrected final tables and source
hashes are recorded in STT_OVERNIGHT_EXPERIMENTS.md. Nineteen of 24 screens are now
measured; 20–24 remain in physical evaluation. No defaults changed or branches pushed.

### Speaker normalization screen complete; 20/24 measured

The four-capture normalization comparison completed and fixed production was restored
and verified. Conv2 correct speaker labels fell 28/38 → 18/38 and unknowns rose
1/38 → 19/38, despite fewer false merges. Conv4 also trailed its fresh control
(30/33 versus 33/35 correct). The positive float screen did not transfer into a general
P4 win. No promotion; actual P4 gain/DC/clipping telemetry was not instrumented.
Zero session watchdogs/panics/overruns; twelve setup warning occurrences. Detailed
corrected timings and limitations are in STT_OVERNIGHT_EXPERIMENTS.md. The serialized
21–23 group is taking over, followed by 24. No production defaults changed.

Arm21 paired natural captures are complete. Noise freezing improves WER versus the
initial controls (21.24 → 18.84%, 29.40 → 26.61%) but exchanges one conv2 unknown
for an extra merge and increases label lag. Trailing controls remain pending. Runtime
noise-level traces support activation. Global/clip-boundary word-error diagnostics were
added without changing captions or firmware; their causal limits are documented.
Arm22 is now exercising the long-speech fixture.

Arm22 completed its two natural fixtures and long22 stress. The shorter cap is
exercised (stress max 9670 → 7880ms; forced cuts 3 → 4), with zero sample gaps
between observed forced cuts and following emitted extents. Stress WER worsens
12.00 → 16.67%; both stress alignments fail the fixed gate, so true-end timing
is withheld. Natural WER improves versus initial controls but conv3 identity/unknowns
and label lag worsen. Trailing controls remain pending; arm23 is running.

Arm23 paired candidates completed: promotions 0/0 with speculative jobs still
running. Label medians rise to 7362.5/14744ms; conv3 has 19/44 raw unknowns,
including five audio-pressure rejections, and one session watchdog (CPU0 cmd_exec_task,
CPU1 ipc1). Conv3 RMS alignment fails, so identity/true-end timing remain unqualified.
This counterfactual is not a test of disabling speculation entirely. No promotion;
final controls are running.

### Actionable checkpoint and new watchdog requirement

The user requires matched watchdog reruns, including checking whether the warning recurs
at the same spot. The requirement is recorded in STT_WATCHDOG_RETESTS.md; qualification
is not complete merely because the initial 24 screens have been attempted. The 21–23
13-capture group completed and restored fixed production. Final controls erase a clear
noise-freeze WER win: candidate 18.84/26.61% versus final controls 19.04/26.39%.

Vocabulary's natural conv3 run failed with `STT audio queue full; backend cannot keep up`
and 21 in-session watchdog warnings, without panic. Fixed production was restored;
final controls remain missing. An exact-image/fixture reproduction is now running.
See STT_ACTIONABLE_FINDINGS.md for decisions: qualify earlier x2f pacing, preserve strict
speculative reuse, reject the tested normalization and pause changes, and prioritize
reproducing/profiling the vocabulary failure rather than adding tuning arms.

### 3 November checkpoint — storage recovery and actionable decisions

The initial experiment ledger now records 23 measured screens out of 24. This is not
qualification completion. See `docs/STT_EXPERIMENT_RESULTS.md` and
`docs/STT_ACTIONABLE_FINDINGS.md` for current decisions: preserve exact-coverage reuse,
reject the tested normalization/shorter pauses, do not promote noise freezing, and
prioritize broader x2f pacing qualification after reliability checks.

Both failed vocabulary conv3 attempts contain filesystem-full errors; the repeat was
interrupted with zero captions and cannot establish a vocabulary failure. Fixed production
was restored and verified afterward. Required same-test watchdog reruns remain pending.
The archived wider-beam watchdog samples are in decoder math; forced-redecode samples
are in flash/cache coordination. See `docs/STT_WATCHDOG_RETESTS.md` for the inventory
scope, signatures and uncompleted reproduction requirements.

A read-only storage inspection measured 352,256 bytes free. Audit-log rotation may
need 435,200 bytes of temporary storage, exceeding both that space and the earlier
128 KiB bench gate. A full LittleFS snapshot was read twice through the approved
helper; the independent reads matched. The verified private snapshot contains 953 files
with 1,242,003 content bytes, including 927 sensor files totaling 82,737 bytes across
892 boot directories. Directory/allocation overhead is substantial. This is separate
from the closed 128-byte L2 PSRAM fault.

Prepared proposal: remove 889 old sensor files (78,232 bytes)
and their 889 named boot directories below boot 1200. Every proposed file was extracted,
fsynced and reread privately; the full snapshot has independent readback verification.
The user subsequently explicitly approved this exact sensor-log cleanup. Execution is
underway with a fresh live-file hash check before each deletion; completion and recovered
capacity are not yet claimed. The scope preserves boot 1200 onward and every other path. No filesystem
image is to be flashed back or edited wholesale. Recovery must be measured afterward;
do not claim free space from file-content totals alone.

Private snapshot/proposal manifests are under
`private/resume-20261102/filesystem-snapshot-20261103-101810/` (ignored; never commit
contents). The board was returned to the approved fixed-production image after snapshot
verification and the controller released its lock. No tuning/default changes or pushes.

Required host regressions passed: transcript, product storage, viewer and bridge. Scoring
and NumPy alignment checks also passed. These do not qualify model accuracy, P4 realtime
performance, microphone equivalence, SD power-loss behavior or the incomplete watchdog
matrix. Goal remains active.

The fresh qualification runner now requires 770,048 bytes of pre-capture headroom:
the largest capped-log rotation tail, existing 100 KiB reserve, and twice the largest
observed between-start loss (36,864 bytes over 33 historical transitions), rounded up
to 4 KiB blocks. This is an operational bench guard, not proof of production storage
safety. It also rejects any filesystem-full message and reads capacity after each
session. Frozen images and WAVs are rehashed; production rollback remains mandatory.
The queued first batch repeats vocabulary with fresh before/after controls, then the
forced-redecode and wider-beam conv3 cases. No additional tuning variants are introduced.

### Approved cleanup execution — maintenance batch

The per-command serial cleanup was intentionally stopped after 62 acknowledged directory
removals; the in-flight final operation completed too (the batch observed 63 absent
targets). Repeated command-audit/metadata work made that route too slow. Both the old
cleanup process and its old waiting test supervisor terminated before the replacement
acquired the board. No test captures were started during the takeover.

A temporary maintenance app, SHA256
`255c078f3ec920c00cae58aa1fbf566c25ee2902d87e35d5c8ef159e896c277b`,
adds one admin-only, explicit-confirm command containing only the 889 approved paths.
All archived files share the same verified 88-byte contents. Every extant target must
match those bytes before deletion; an unexpected file or nonempty directory stops the
batch. Already removed targets are handled without deleting any additional paths.
Per-target absence is checked and progress is logged privately. This is maintenance,
not a new STT tuning arm, and its source was restored after the build.

The actual helper was host-checked with ASan/UBSan for complete cleanup, repeat,
changed bytes, extra unapproved directory contents, non-admin access, wrong size and
an interrupted prefix; unrelated files were preserved. The real P4 batch is currently
running under the approved helper/lock, with fixed-production rollback in its finally
path. Do not claim recovery complete before its final capacity and restoration checks.
The authoritative private state remains `private/resume-20261102/sensor-cleanup-status.json`;
raw batch progress is under `sensor-batch-cleanup-*`. The replacement test supervisor
starts the existing eight-capture queue only after successful recovery and lock release.

The broader pacing control also built: production pacing with the same speaker diagnostics,
64-byte L2, 250 MHz PSRAM, fixed models and 600/1000 ms pauses. Its SDK configuration is
byte-identical to the archived x2f diagnostic control; tracked HardwareOne source is clean.
A balanced twelve-capture production/x2f/x2f/production comparison across conv2–4 is
prepared, but has not run. Do not count it as measured qualification.

### Storage recovery independently verified; qualification resumed — 3 November, 12:05

All 889 approved target directories are now absent, verified against a complete,
non-paginated admin-visible listing of `/logging_captures/sensors` and the exact
approved folder manifest. The listing has 22 remaining entries. Free LittleFS capacity
is **7,618,560 bytes**, up from **331,776** before cleanup: a net recovery of
7,286,784 bytes during cleanup/normal device logging. Logical archived payload was only
78,232 bytes; all 889 files exactly matched the public sealed R1 CSV header, with zero
sample rows. Do not infer a precise allocation-per-directory from the net change.

The second native batch's final reply was lost because the device's synchronous dispatch
caller times out at 60 seconds while command execution may continue. A later `[CMD] ...
-> OK` entry established that execution had returned. The host observer was then stopped,
fixed production was restored and verified, and a fresh read-only console independently
verified target-directory absence, capacity, and persisted ring reconnect disabled.
No native final-result counters were fabricated. This successful independent readback is
the completion evidence; the former 875-target checkpoint was not treated as completion.
Private proof is in `sensor-cleanup-verification-20261103-120508/report.json` and its
listing/raw log under the existing private run root. The complete before-cleanup snapshot
and extracted backups are retained. No filesystem partition image was written.

The eight-capture frozen-image batch has now actually started, using the recorded
770,048-byte preflight gate, filesystem-error rejection, fresh vocabulary before/after
controls and prioritized conv3 watchdog reruns. It owns the board through the approved
helper/lock and restores fixed production in its finally path. Broader pacing comparison,
remaining watchdog matrix and the final 24-item qualification report are still incomplete.
The one-time maintenance command has been removed from the running app by production
rollback; tracked HardwareOne source remains restored. No production-default or model
change, push, main merge, or outward-facing report has been made.

The first clean-storage baseline has finalized: 16 captions on the synthetic vocabulary
fixture, WER 15.04% (20/133 edits), 1/8 target terms, no control-term insertions, no raw
unknowns, zero watchdogs including setup, zero overruns and no panic. Reference alignment
passed; free space stayed above 7.59 MB. This is one single-voice control, not a candidate
win or general stability claim. The natural conv3 baseline is active and remaining
candidate/controls and watchdog reruns are still pending in the serialized batch.

### All 24 initial screens measured; wider qualification remains active

The six clean-storage vocabulary captures and two priority conv3 watchdog reruns have
completed, with fixed-production restoration verified before starting the broader
pacing batch. Full numeric results and exclusions are in `STT_EXPERIMENT_RESULTS.md`.
The tested four-term vocabulary configuration has no target-term gain: hits 0/8 versus
controls 1/8 and 0/8, synthetic WER 21.05% versus 15.04/18.05%. Natural WER is 26.82%
versus 28.76/27.04%, only one word better than the late control; raw unknowns are 10
versus 9/3. Do not promote it. Stored user vocabulary and fixed models were unchanged.

All eight clean captures completed without panic, overruns or filesystem-full errors.
The vocabulary failure did not recur (100.15s original failed capture versus 234.368s
successful rerun across the full fixture), and the wider-beam warning did not recur.
Forced re-decode still had one watchdog, at a different position and sampled code:
ESP-DL convolution workers at capture +118.817s, versus original flash/cache IPC at
+50.612s. Its additional label delay after final-text publication was 11.461s versus
controls 2.037/2.111s, with no WER gain over the late control. Keep exact-coverage reuse.
One more clean same-image/input repeat is queued; no kernel defect is established.

Six of eight reference alignments passed. The late conv3 control and forced-redecode
repeat failed the unchanged RMS gate; their reference identity and true-end lag are
withheld. Global WER, raw unknown coverage and device-internal timing remain reportable.
Synthetic manifests lack speech-end annotations: the scorer now emits explicit
unavailability instead of a traceback, without substituting clip ends. Existing scoring
checks and functional checks on the real captures passed; no failed fit was relaxed.
Speaker lag throughout the benchmark is label timestamp minus final-caption publication,
not speech-end-to-label delay. Do not add separate medians to invent end-to-end latency.

The balanced twelve-capture production/x2f comparison across conv2–4 is now running.
The next serialized controller is queued behind its successful completion/restoration:
one fresh forced-redecode conv3 match plus 18 remaining original live warning cases,
with a bounded extra match if a new pacing warning has no later same-image/fixture
observation. Two legacy SD-input cases still need their separate reruns. These are
mandatory reproduction checks, not additional tuning arms. The goal is not complete:
broader pacing results, watchdog matrix, final visual/report/audit and final board
restoration/readback remain. No production defaults, branch pushes, main merges or
outward-facing filings have been authorized or performed.

### Broader pacing comparison completed; mandatory repeats active — 3 November

All twelve production/x2f ABBA captures across conv2–4 completed; all twelve reference
fits passed. The exact per-run table is in `STT_EXPERIMENT_RESULTS.md`. Mean WER
production → x2f is 21.145 → 20.340%, 29.185 → 28.435%, and 22.340 → 20.745%;
pooled one-to-one correctness is 52/72 → 55/74, 72/89 → 81/94, and 63/70 → 60/66.
Raw unknown counts are 3 → 3, 9 → 9, and 7 → 6 with caption denominators retained
in the report. Additional label-delay medians are 1.650–2.754s for x2f versus
5.436–23.503s for production. This supports x2f as the preferred pacing candidate
for further qualification, beyond the earlier conv1 result; it is not a new general
accuracy, held-out-speaker, long-soak or production-default qualification.

Tradeoffs: x2f shown text is slightly later, and conv4 final-text median is worse in
both x2f captures than either production control. Do not describe every latency as
improved. Production had 11 watchdog warnings across all six captures; x2f had zero
across six. Warnings recur in later production controls with varying sampled code/
positions. No panic, overrun or filesystem-full error occurred in the twelve captures.
Fixed production was restored and verified, then the queued mandatory live-repeat
controller started. Two legacy SD repeats and the final ring-off/capacity readback
are serialized behind it, using existing SD audio without uploads. The goal remains
active: finish those repeats, compare warning locations, update the final visual/
report and verify final restoration/lock release. No defaults/push/main/outward changes.

### Additional clean forced-redecode match completed

The required same-image/conv3 repeat completed 47 captions with two session/whole-log
watchdog warnings, no panic, no audio overruns and no filesystem-full errors. Both
sample CPU0 `dl_mc0` / CPU1 `dl_mc1` and ESP-DL convolution loops, at capture
+42.280s and +107.788s; the previous clean warning was +118.817s. RA is the same
`dl::base::conv_loop_pie`; sampled PCs are bias/relu convolution-loop variants.
This reproduces the DNN-worker warning family under clean storage, **not the same
input position or exact sampled instruction**, and does not establish a kernel defect.
The original flash/IPC warning at +50.612s remains a different signature. The required
additional clean match is now satisfied; do not rerun this reproduction set indefinitely.
Retain the rejection of forced re-decode. Eighteen original live cases and the two
legacy SD cases remain in the serialized queue, followed by final board readback.
Private evidence is retained in `watchdog-backfill-status.json` and the expanded
`overnight/watchdog-repeat-matrix.json` under the ignored run root.

### Original-six reference audit and hold/merge recheck

All six early development captures passed the same RMS/clock gate. Repaired onsets
are 0.301–0.386s later than the old status estimate, changing two mixed flags and
raising eligible phrases from 194 to 196. Speaker IDs, embeddings, phrase lengths,
order and device decisions are unchanged. The eight independent offline rules and
long-history stress were rerun with their original settings/seeds; no promotion
verdict changes. The corrected table in `STT_EXPERIMENT_RESULTS.md` supersedes the
old offline numeric summaries; source-audio float screens and later RMS-qualified
P4 comparisons are unaffected.

Hold/merge was rechecked too: all-order merges per 100 are production 3.84, hold0.50
5.83, hold0.45 6.74, young hold 5.20, and merge variants 8.25–8.83. More coverage is
not a safe identity improvement. These remain development replays, not held-out success.
All 21 locally built archived images match their recorded hashes and saved 64B/250MHz/
IDF5.5.5 SDK settings. Mandatory board repeats and final restoration audit remain active.

### Requested experimental sweep closed — 3 November, 15:38

All 24 agreed experiments have implemented, measured screens (eight device-embedding
replays, one fixed-weight float screen, fifteen P4 screens). The final report and
per-run tables are in `STT_EXPERIMENT_RESULTS.md`; this completes the requested
sweep and mandatory watchdog audit, not general production/model qualification.

Recommend x2f pacing with unchanged 600/1000ms pauses for an approved adoption step.
The twelve-run broader comparison preserves measured WER/speaker outcomes and reduces
label delay substantially, with the documented text-latency tradeoffs. Keep existing
speaker rules and exact speculative reuse. No defaults were changed.

Twenty final live reproduction captures and two legacy SD matches completed, with
no panic, audio overrun or filesystem-full error. Four warnings occurred in two forced-
redecode captures: conv3 repeats the worker family at different positions; conv2's two
new warnings did not recur on its additional unchanged-image/WAV match. Both SD matches
have zero warnings. All 37 warning-bearing image/input/mode groups have later completed
observations, with setup/session scopes, changed storage and legacy metadata limits
kept explicit. A warning-free repeat is not proof of a general fix; no causal kernel
or software-writer defect was established or outward report filed.

Nineteen of 20 final live RMS fits passed; forced-redecode conv3 identity/true-end lag
remain withheld. Long22 lacks speech-end annotations, so true lag is unavailable.
The reruns also expose variability: normalization's initial conv2 19-unknown failure
became one unknown in the clean repeat, while conv4 still has eight. Pre-roll's initial
conv3 19 unknowns became two. These unbracketed, changed-condition repeats do not prove
an isolated benefit or harm. The final tables supersede any blanket interpretation of
those initial single captures. No other candidate earns promotion from selected reruns.

Fixed production was restored/readback-verified through the approved MAC/partition-
checked app-only helper. Fresh readback confirms ring reconnect disabled and 7,196,672
free bytes. Required transcript/storage/viewer/bridge host checks passed; detailed
hashes, timing exclusions and unperformed product-level checks are recorded in the
final report. Private backups, raw logs/audio/captions and final numeric audits remain
ignored. No push, main merge, production-default change or external filing occurred.

### Approved production adoption — 3 November

The user approved trying x2f pacing and the identified storage prevention fixes.
Deploy **x2f-only**, local HardwareOne `04827588`, based on fixed production
`027eef22`; existing pauses, fixed models and speaker rules remain unchanged.
Hold combined storage commit `f68e4adc` for investigation. No push, main merge or
outward filing occurred. Full evidence and per-run numbers: `STT_X2F_ADOPTION.md`.

The isolated worktree is on `codex/stt-x2f-storage`. The storage proposal defers
automatic boot/day CSV creation until eligible data, advances R1 dedup only after
a complete write and reserves capped-log rotation copy space. Actual-code host
regression/failure checks passed. The combined image also passed three fresh-boot
no-data checks: R1 CSV logging is active/autostart ON, ring reconnect stays off,
and no target boot directory is created while waiting for data.

Six live smoke captures (three per image, 260 captions) have zero watchdog
warnings, panics or audio overruns. Their RMS/clock fits pass. However, combined
conv3 produced 17 unknown labels, then nine in the bounded follow-up comparison;
x2f-only produced five, then six. The combined repeat also has worse WER and
fewer correct speaker labels than the x2f-only repeat. This does not prove a
storage-code regression, but does not qualify the combined image for production.
Keep both storage changes reviewable; isolate and repeat them before integration.
The selected x2f-only image still has the old empty health-log creation behavior.

Both builds used IDF 5.5.5 and actual SDK 64B L2 / 250MHz PSRAM. App, ELF, SDK,
build identity, source patch/bundle and private evidence are preserved. A real
first R1 sample remains host-tested only; ring reconnection stays off. Physical
near-full-media and SD/FAT power-loss behavior are untested. Rotation headroom
is not a global storage quota; the no-SD fallback can still append to flash.

A pre-flash x2f-only audit found two CPU0 `cmd_exec_task` watchdog warnings on
`files json "/logging_captures/sensors"`; its fresh-boot same-image/command repeat
had one. Sampled instructions differ (initial flash-cache critical exit; repeat
LittleFS read/memcpy). This reproduces a directory-listing problem, not an STT
DNN warning or an established kernel/cache root cause. Narrow target checks pass.

Final x2f-only selection/readback passed: app SHA `b55bf0961564…`, ring reconnect
disabled, perf logging disabled, 7,106,560 free bytes, port and lock released.
After explicit user approval, all four disposable build/dependency directories
in the isolated worktree were removed (1.69 GiB of pre-removal allocation).
Saved firmware hashes were reverified; source, local commits, Git bundle/patch,
rollback images and private test evidence remain intact. Other checkouts and
concurrent training work are preserved. The board was not accessed for cleanup.

### Standalone STT runtime improvement — 3 November

Work has returned to this STT engine/app, separate from the concurrent training
pipeline session. `STT_RUNTIME_IMPROVEMENTS.md` records six code-backed targets:
draft pacing, capture-lock copy/clear cost, inference kernels, speaker-result
completion, decoder fallback visibility and actual standalone qualification.

Implemented an optional portable `DraftPacing::X2FastFirst` scheduler and
`CONFIG_CAPTIONS_X2F_DRAFT_PACING` / `sdkconfig.x2f` adapter. First previews retain
a one-second audio floor; subsequent previews use at least 600 ms of new audio
or twice the last draft compute time. A new phrase ignores the previous phrase's
slow draft. Legacy remains the default; model weights, speaker rules, endpoint
pauses, tail trimming and exact speculative reuse are unchanged. Wide arithmetic
prevents elapsed-time growth from wrapping on P4.

Actual scheduler tests pass under address/undefined sanitizers and ThreadSanitizer
(with positive/negative memcpy controls). Both modes exercise concurrent ownership
and cached-feature/draft preemption; threshold, phrase reset, explicit wall floor,
large elapsed time, final priority and existing promotion/cancel/overflow cases pass.
The P4 opt-in build passed on IDF 5.5.5 with actual 64B L2 / 200MHz PSRAM and the
new mode enabled; app size is 645,968 bytes. A stale cached ESP-DL override was
preserved privately and the current pinned override digest-verified before build.
The sandbox initially blocked ESP-IDF process inspection; the authorized build
rerun passed. Candidate app/ELF/config/source hashes are saved privately.

No board access, HardwareOne changes, training edits or default promotion occurred
in this task. Standalone device WER/speaker accuracy, preview/final/label latency
and long-session qualification remain pending; integrated x2f results are not
proof of the same gain here. The existing build folder now points to the private
candidate SDK configuration; the prior root config/build artifacts are preserved.

### STT capture-lock improvement plan — 3 November

The user selected streaming capture contention and requested an in-depth plan.
`STT_CAPTURE_LOCK_PLAN.md` is grounded in `stt_stream` and the standalone I2S/task
adapters. It includes whole-phrase queue copying and capture-triggered cache
clearing, not only the draft snapshot. Moving producer work outside the mutex
alone does not shorten the producer's read cycle.

Planned order: bounded instrumentation and an unchanged baseline; dirty-prefix
cache clearing with a complete-zero invariant; exclusive cleanup states/leases
if material contention remains; bounded snapshot copies or segmenter storage
handoff only if copy time justifies their extra ownership complexity. The plan
sets correctness/lifetime/privacy invariants, 36 targeted cases, sanitizer controls,
P4 capture/loss/latency/memory measurements, candidate gates, ABBA qualification
and the required same-test watchdog repeat rule. Training work stays separate.

This is a plan-only milestone: no runtime change, new test result, board access
or default change occurred. First implementation deliverable is instrumentation,
not an unlocked read from live capture memory. Actual contention and benefit
remain unmeasured; existing SDK/model/pacing conditions must be held fixed.

### Capture-lock instrumentation and first device smoke — 3 November

Goal remains active. Optional, default-off stream metrics are implemented without
changing PCM/cache ownership or clearing policy. Exact original-runtime replay
comparisons match all JSON, PCM and cached feature bytes (24 comparisons across
enabled/disabled probes and both pacing modes). Actual streaming sanitizer/TSan
checks, memcpy controls, telemetry parser and required product regressions pass.
P4 metrics and optional speakers build successfully; no training/export file is
modified or staged by this work. See `STT_CAPTURE_LOCK_RESULTS.md` for details.

The exclusive startup/quiet-room smoke passes with active features/speakers and
zero watchdog, panic, I2S overflow, phrase drop or feature overrun. Telemetry plus
the largest reporting page is exactly 4 KiB. Capture wait p99 is (1,10] us, max
18 us in that short sample; this is not evidence of loaded contention or a gain.
A cache retirement cleared 256,000 bytes / 2,566 us despite only 38,656 bytes of
feature writes. Full loaded baseline, overhead controls and optimization gates
remain pending. The selected x2f-only app was restored and read back with ring
reconnect/perf logging off; the port and lock were released.

The user separately requested a block-14 model RAM/fixture benchmark through the
training chat. That direct request was verified and queued for isolated runtime
work at a safe device window, separate from fixed-model capture-lock comparisons.
No mixed model is deployed and no device RAM result is claimed yet.


### Capture-lock loaded baseline and prefix candidate — 3 November

The unchanged standalone instrumented baseline completed conv2–4 with zero DMA
overflow, phrase drops, watchdogs or panics. Capture wait p99 is at most 50 us
and maxima range from 2,574 to 3,969 us. Conv4 records two feature-cache overruns;
these invoke uncached/batch frontend fallback and are not evidence of lost PCM.
An unchanged conv4 repeat and long-input baseline are in progress. All raw results
and the first controller's failure/restoration remain private.

The default-off committed-prefix clearing candidate retains full startup zeroing,
reader pins, generations and PCM ownership. Address/undefined and thread sanitizers
pass, including complete-region zero/canary checks and the 159-dirty-row versus
150-inference-row case. Twelve actual scheduler/frontend replays are byte-identical
to the pre-instrumentation baseline. The P4 candidate builds; its sdkconfig differs
only by enabling the experimental option. No device benefit is claimed yet.

Baseline acceptance gates and a waveform-only sample-clock alignment method were
frozen before candidate device scoring. Rejected fits remain retained; sparse RMS
and host receipt timings are estimates, not microphone recordings/display clocks.
See docs/STT_CAPTURE_LOCK_RESULTS.md for actual per-fixture counts and limitations.
The full ABBA comparison, instrumentation controls, remaining stress checks and
one-hour soak are incomplete. Models, speaker rules and production defaults remain
unchanged; training files belong to the other session.


### Prefix-clearing screen complete; balanced qualification next — 3 November

The unchanged conv4 repeat again has two feature overruns but no DMA loss, phrase
drops, watchdogs or panics. The long-input baseline has four feature overruns,
zero driver/phrase loss and a 230 us maximum capture wait. The candidate completed
conv2 and the same long input cleanly, retaining four long-input feature overruns.
Conv2 clearing falls from 10,240,000 to 3,422,464 bytes and 92.773 to 28.644 ms;
final-text lag is essentially unchanged. WER is 91/499 versus 78/499 and speaker
correctness 24/38 versus 23/38. One pair establishes neither quality improvement
nor noninferiority. The small clearing improvement merits the balanced comparison;
the tiny baseline wait does not justify a larger ownership redesign.

All controllers completed selected-app restoration/readback with ring reconnect
and perf logging off, and released the lock. Additional null-lock, zero-C++-
allocation, disabled-feature/snapshot, terminal-order and probes-off capture host
checks pass; 24 prefix replay comparisons match the old scheduler/frontend bytes.
The twelve-capture ABBA, device instrumentation controls, secondary pacing/speaker
checks and at least one-hour soak remain incomplete. No defaults were promoted.


### Capture-lock primary ABBA: speaker-quality gate raised — 3 November

Conv2 and conv3 four-run blocks are complete, with zero driver loss, dropped
phrases, watchdogs, panics or application errors; all timing fits qualify. Median
cache-clearing time is 71%/73% lower, but no corresponding caption speedup is
established. Conv2 quality spans overlap the controls. Conv3 speaker correctness
is 33/47 and 30/47 for baseline versus 28/47 and 26/47 for the candidate, with
unknown counts 9/8 versus 11/11. This blocks an adoption recommendation.

Conv4 is still running. One bounded conv3 follow-up is prepared using the exact
original capture snapshot and unchanged images/settings; preserve the original
cohort separately and hold the candidate if the concern remains unresolved. No
speaker threshold, recognition model or production default changes are authorized
by these measurements. Secondary controls/soak and exact-input P4 neural hashes
remain incomplete. A newly added nonzero-pre-roll/ring-wrap host replay also awaits
compilation. See docs/STT_CAPTURE_LOCK_RESULTS.md for actual counts and limitations.


### Capture-lock twelve-run cohort complete — 3 November

All twelve primary captures completed without DMA loss, dropped phrases, watchdog
observations, panics or application errors; all timing fits qualify. Median total
cache-clear time falls 71%/73%/67% on conv2/3/4. The conv3 speaker/unknown concern
still blocks adoption. Conv4 fallback counts are controls 1/1 versus candidates
2/0: equal totals, a higher candidate maximum, with earlier baseline 2/2 retained.
No unconditional quality/reliability pass or caption speedup is claimed.

The selected x2f-only app was restored/readback-verified and the primary lock
released. One bounded conv3 four-run follow-up now owns the board, using the exact
original capture snapshot and unchanged images/settings. No defaults changed.

Source review additionally identified a global SDK preparation flag consulted by
both recognition and speaker model operators without model/task ownership. An
isolated forced-exposure P4 probe with same-worker negative and recovery controls
is prepared but unbuilt/unrun. It is not proof of live incidence or the cause of
these quality scores. No SDK patch has changed. Exact neural hashes, added
pre-roll replay, secondary controls and soak remain incomplete; keep the goal
active and preserve training-agent changes.


### P4 execution-isolation defect reproduced; adoption held — 3 November

The bounded conv3 follow-up has baseline speaker correctness 31/48 and 27/47
versus candidate 28/47 and 27/47, with unknowns 12/10 in both arms. All four
fits qualify and no reliability/application faults occur. This does not erase
the primary concern; no noninferiority or production promotion is claimed.

The isolated P4 diagnostic completes six byte-identical recognition input/output/
text pairs across clearing modes. It independently reproduces the shared SDK
preparation-state defect: fixed input B matches normally on the same separate
worker, changes to cosine -0.003156489 when the parent holds the global flag,
and recovers exactly after clearing it. This proves the mechanism, not live
incidence or causation of the acoustic score differences. No SDK fix is applied yet.

The fixed speaker blob's embedded trunk fixture separately fails (first reported
770 expected, 717 actual; roughly one-unit tolerance). Its cause is unresolved.
The diagnostic explicitly reports complete_with_findings/all_checks_passed=false
and makes no RAM-fit claim. An initial assertion/reboot loop and the controller
matcher oversight are preserved; first-fault detection is fixed/tested. No
assertions were found in the sixteen acoustic captures. The completed diagnostic
restored/readback-verified the selected app and released the lock.

Twenty-eight host replay comparisons now include real nonzero pre-roll/ring wrap
and match the old engine. Secondary controls, continuous soak, final audit and
the separately queued block-14 fixture/RAM test remain incomplete. Next isolate
preparation ownership with fixed models and speaker rules; keep defaults unchanged
and preserve training-agent edits. See docs/STT_CAPTURE_LOCK_RESULTS.md.

### Model-local preparation repair and direct speaker fixture matrix

The default-off execution-isolation repair passed controlled P4 concurrency: 83
real preparations of another model left speaker output unchanged (cosine 1), and
six recognition pairs matched frozen pre-fix hashes. Runtime lifecycle tests pass
ASan/UBSan for both preparation APIs, resident/per-call models and probes off/on.
The direct embedded speaker fixture still fails identically with convolution
blocking off/on and single/multi-core execution: 9,386/9,600 values exceed tolerance,
maximum error 788. Those choices do not explain it; no accuracy pass is claimed.
A saved-export host reconstruction is also not byte-exact and remains unvalidated.

The latest diagnostic completed without watchdogs/panics, restored and readback-
verified the selected app, reconnect/perf logging off, and released the lock.
The SDK source tree is digest-verified; production defaults and training edits are
preserved. See STT_CAPTURE_LOCK_RESULTS.md for evidence and limits, and Section 13
of STT_CAPTURE_LOCK_PLAN.md for the updated staged qualification plan. Speaker
fixture localization, secondary controls, continuous soak, final gate audit and
the separate mixed-precision RAM request remain incomplete.

### Speaker numerical mismatch: actionable cause found — 4 November

The first Conv matches an independent int64 reference byte for byte. A 181-point
P4 diagnostic trace locates the first large sampled difference at a residual
ReLU. The model serializes 16 int16 residual ReLUs as 257-entry lookup tables
(step 256); an exhaustive host audit finds up to 128 units of approximation
error per operation. A diagnostic-only direct-ReLU control with the same weights
reduces final fixture maximum error 788→17 and total absolute error
891,692→10,591 in all four execution modes. This is a numerical fidelity result,
not a live speaker-accuracy result. The original one-unit fixture still fails;
no tolerance/default/model change is made.

One trace prototype faulted on an optional null SDK module name; first-fault
handling restored the board. Corrected trace and causal comparisons completed
without watchdogs/panics, preserved the independent isolation/recognition passes,
and restored/readback-verified the selected app, reconnect/logging off, lock
released. See STT_CAPTURE_LOCK_RESULTS.md and the reusable audit_relu_tables.py
for evidence and limits. Matched capture-lock controls are now building with
original serialized speaker math and the opt-in preparation repair; secondary
captures, continuous soak, final audit and the separate mixed-precision RAM
request remain incomplete. Training-agent work is preserved.

### Fresh capture-lock SDK cohort: first ABBA bracket measured — 4 November

Six model-local-preparation control images are built and hash/config verified.
Conv2 ABBA is complete: WER edits are B0 78, P1 78, P2 75, B3 81 (499 words each);
speaker correct is 29/38, 28/38, 28/38, 28/38; unknowns 1,2,1,2. All fits qualify
and all four captures have zero observed driver/phrase loss, watchdogs, panics or
application errors. Clearing time falls 68.9%; no caption speedup or formal
noninferiority is established. Original speaker lookup math is unchanged; the
numerical fixture remains failed. See STT_CAPTURE_LOCK_RESULTS.md.

The controller is actively running the remaining conv3–4 captures and owns the
board lock. It has not yet restored the selected app for this cohort. Secondary
controls, continuous soak, final audit and the separate block-14 RAM request are
still incomplete. Do not touch the board during the active chain.

### Fresh SDK twelve-run cohort finished; bounded conv4 follow-up active — 4 November

The model-local SDK cohort completed/restored/readback-verified the selected app,
then released its lock. All twelve sample-RMS fits qualify and all captures have
zero observed driver/phrase loss, watchdogs, panics or application errors. Clearing
cost falls 67–74%, without a demonstrated caption-speed gain. Conv4 raises a
speaker/unknown gate: controls 30/34 and 33/35 correct, unknown 4/2; prefixes 23/32
and 25/33, unknown 8/7. Preserve this concern; no adoption/default change is made.

Conv4 B0's receive timestamps jump backward 307 ms. Publication timing remains
withheld, while sample-clock identity/WER remain usable. A separately tested
monotonic receive-log adapter now supports future captures; old logs are unchanged.
The ONE bounded conv4 ABBA follow-up is currently active with unchanged images,
models and scoring, and owns the board lock. See STT_CAPTURE_LOCK_RESULTS.md.
Secondary controls, continuous soak and final audit remain incomplete. The optional
allocation-refusal probe is unbuilt source only; the separate block14 delta is
host-verified but not deployed or RAM-qualified. Training edits remain preserved.

### Bounded conv4 follow-up closed; secondary controls running — 4 November

The one new-SDK conv4 follow-up completed and restored/readback-verified the
selected app, then released the lock. Its B/P/P/B WER edits are 77/78/72/74 over 470;
speaker correct 32/34,30/34,32/34,26/33; unknown 2/4/2/7. All sample and monotonic
publication-clock checks qualify, with zero observed capture faults. The primary
separated pattern does not repeat; the original quality flag remains and adoption
is held. No more conv4 brackets are planned. Clearing time falls 64.8%, without a
demonstrated caption-speed gain or formal noninferiority.

The secondary twelve-run controller is now active and owns the board lock.
It uses the same fixed model math and recorded monotonic receive clock. Secondary
controls, continuous soak, unbuilt optional allocation-refusal check, final audit
and separate model/RAM benchmark remain incomplete. See STT_CAPTURE_LOCK_RESULTS.md
and private/stt-capture-lock/next-actions.json. Production defaults remain unchanged.

### Secondary controls and preparation-failure check complete; soak active — 4 November

All twelve secondary captures completed. Their controller restored/readback-verified
the selected app, reconnect/logging off, and released the lock. The x2f clearing
bracket raises a label-after-caption p90 flag (controls 2.020/1.817 s, candidates
2.231/2.443 s), despite a 61.1% reduction in clearing work. No caption-speed gain
or promotion is established. The speaker-load controls show capture-wait p99 in
(1,10] us throughout; speaker-off does not establish better final-caption p90.
No secondary watchdog/panic/phrase drop was observed; probe-off DMA loss is
unmeasured. Primary conv4 quality and speaker numerical-fixture holds remain.

The isolated P4 preparation-refusal check passed: 104 optional requests rejected,
activation bytes unchanged, fallback/recovery exactly matching the ordinary
fixture-matrix output. Six recognition pairs match pre-fix hashes; independent
model output remains unchanged during 82 preparations. This does not simulate
physical heap exhaustion or warmed-block growth failure. The embedded speaker
fixture remains failed, so overall status is complete_with_findings. That
controller also restored/readback-verified the selected app and released its lock.

The >=1h single-boot mixed-session diagnostic reliability soak is now running
with explicit quality/fixture holds retained. Its results and final restoration
are pending. No default change or HardwareOne synchronization occurred.

The separate block-14 benchmark now has a bounded diagnostic delta decoder,
ASan/UBSan bounds/failure checks, and exact actual-candidate host reconstruction.
Prior actual-device logs and the pinned envelope show a stored control model,
allowing immutable payload reads without a 20 MB scratch card write. Device
header/base/target hash checks remain mandatory; no candidate model has been
loaded or numerically/RAM-qualified on the device. See STT_CAPTURE_LOCK_RESULTS.md
and private/stt-capture-lock/next-actions.json for continuation evidence.

### Capture-lock investigation executed; adoption held — 4 November

The plan in STT_CAPTURE_LOCK_PLAN.md has reached its recorded dispositions.
All 44 bracketed acoustic captures (original/new SDK primary cohorts, their bounded
follow-ups and twelve secondary controls) are complete. STT_CAPTURE_LOCK_RUNS.md
contains every row's WER/label denominators, qualified timing, lock wait/hold,
copy/clear work and queue/loss counters. Raw audio/captions/logs remain private.

Prefix clearing reduces clearing work roughly 61–74%, without an established
caption-speed gain. Hold adoption: the new primary conv4 speaker/unknown concern
and x2f label-after-caption p90 flag remain. The one permitted conv4 follow-up did
not repeat the original pattern; it does not erase that hold or prove noninferiority.
Do not restart a favorable-sample search or implement the more complex ownership
rewrite; measured capture contention does not justify C/D.

The model-local SDK preparation repair remains default off. Actual P4 recognition
hash equality, independent-model overlap and 104 optional-storage refusals with exact
fallback/recovery pass. Arbitrary shape changes, same-model reentry, physical-OOM
recovery and unrelated prebuilt-consumer ABI compatibility remain unqualified.
The independent speaker fixture is still failed: coarse int16 ReLU tables explain
the dominant error; the causal direct-ReLU probe still has residual error. Neither
speaker model/thresholds nor production defaults were changed.

The continuous diagnostic reliability soak completed twenty mixed-length sessions
on one boot: 4,003.987 device seconds (66m44s), 621 final captions, no observed DMA
overflow, phrase drop, watchdog, panic, unexpected session/model restart or clock
reset. Reader pins/queues drain each time. PSRAM-free/largest-block checkpoints are
constant through five cycles; internal free changes 36 bytes after the first conv2
checkpoint, then matched-fixture values remain stable. Cumulative 31 feature-cache
fallbacks are not lost microphone audio. This is bounded diagnostic reliability,
not overall accuracy, indefinite reliability or transient-peak qualification.

The separately requested block-14 fixture/RAM experiment is also finished with a
failed numerical gate. Each model was compared against ITS OWN exported fixture
at identical input bytes: control passes all three runs; candidate fails all three
with 8,069/9,628 unequal output bytes and maximum error 37, despite stable cold/warm
outputs. Therefore additional 100/1,000/2,000-frame workloads were not run; candidate
RAM viability and full-application fit remain unqualified. The delta travelled in
the diagnostic firmware; no separate full-model/audio upload or SD scratch write
was used. First divergent operation/root cause was not localized. A future numerical
investigation should compare ordinary/prepared and single/multicore paths, then
trace conversions/the changed block before reopening RAM benchmarking.

The final controller restored and hash/readback-verified the selected x2f app
(b55bf096...), confirmed reconnect/perf logging off, closed the port and released
its lock. No controller remains running. No HardwareOne synchronization/push,
main merge, outward issue or production-default promotion occurred. Preserve
concurrent training-agent edits; these are not part of this work's commits.

The seven-cohort comparison has all 44 bracketed captures with missing metrics
explicit. Data and selection/legend/state behavior were checked; browser layout
was not verified after the local-preview URL policy rejection, and no workaround
was attempted. Dedicated silence false-caption behavior, physical-display/word
alignment, physical FAT power loss, formal noninferiority and general OOM behavior
remain unchecked. See STT_CAPTURE_LOCK_RESULTS.md for the coverage audit, artifact
identities and accept/reject/hold decisions. Do not describe these findings as an
adoption pass or silently promote the default-off options.

### Numerical-correctness takeover and paired training trials, 4 November 2026

The follow-up to ec22e39 reproduced both numerical failures and corrected their distinct causes. The corrected speaker package uses direct ReLU and a host reference that preserves integer accumulation precision. Its own fixture and an independent synthetic fixture passed cold/warm, ordinary/prepared and single/multicore P4 checks. The product speaker loader's built-in test returned zero. The package is private and ready for integration review. The installed speaker package still fails its original test. Host speaker labeling improved by one correct turn on 170.

The original block-14 export passes on the P4 when the isolated firmware links the bias-free signed-16 depthwise kernel for dispatch key 0x0315. The 2,000-frame candidate uses 1,579,696 more bytes of peak PSRAM and takes approximately one second longer per warm call. Keep the existing int8 recognizer. The standalone diagnostic is not full-application memory qualification.

On 24 matched meeting excerpts, RMS matching increased distant-mic errors from 110 to 117 on 292 words. A matched output-head training experiment gave 112 distant errors after training on the headset view and 113 after training on the distant view. Keep the existing gain and checkpoint. The final controller restored and readback-verified the selected x2f app and released the port. No default was changed.

See [STT numerical qualification](STT_NUMERICAL_QUALIFICATION.md) for the original and corrected identities, exact numerical references, matched device RAM/timing, training A/B results and remaining limits. Source implementation checkpoint 829e863 is local to this standalone repository.

## Distant-mic encoder adaptation follow-up, 4 November 2026

Keep checkpoint 25397 and the current P4 app. On 48 matched meeting spans (635 words per microphone), the deployed int8 model made 282 distant errors, head-only adaptation 290, and last-block-plus-head adaptation 293. The new candidate regressed in all four meeting series and made 147 versus 146 errors on the frozen 687-word release suite. Host comparison only; no flash or default change. The next training comparison should use the paired headset recording as a teacher for the distant recording. See the [numerical report](STT_NUMERICAL_QUALIFICATION.md#last-encoder-block-on-distant-speech-4-november-2026) for controls, identities and limitations.

## Matched acoustic capture and firmware replay, 4 November 2026

Four playback runs compared eight fixed phrases at two placements and two source-level settings. The host and P4 matched on every raw transcript from 32 actual microphone captures. Original-source playback made 31 errors on the Mac chassis and 34 at one foot, versus 24 and 23 when the four quiet meeting clips were played louder. No new model or production firmware setting was selected. One feature rounding boundary explains the only integer output mismatch and did not change a decoded word. The separate simultaneous microphone was unavailable, so the user repositioned the same P4 for the placement comparison. See the [acoustic path report](STT_ACOUSTIC_PATH_REPORT.md) for all counts, controls and scope.

## Microphone orientation at one foot

The [orientation A/B](STT_ORIENTATION_AB.md) retained the starting position with the P4 mic facing the Mac speaker. Turning it away increased quiet errors from 45 to 58 on 73 words. Ordinary errors tied at 28 on 73 words with offsets across phrases. The candidate failed screening. Loud, overlap, noise and live qualification were not run for this rejected placement.

## Quiet-speech threshold screening

Retain adaptive speech floor 45. A matched 83-case, four-floor replay found release speech gains at floors 32, 24 and 16, but no quiet aggregate gain on the facing-speaker microphone recordings and extra background words (4 to 8 across six minutes). Ordinary captions also had per-phrase regressions. No board flash was needed for these rejected candidates. The [admission threshold report](STT_ADMISSION_THRESHOLD_AB.md) records the full results, controls and live-test limitations. The [microphone endpoint replay](STT_MICROPHONE_ENDPOINT_REPLAY.md) describes the initial admission failure.

## Dual-source microphone quality A/B

The [P4/G2 quality report](STT_DUAL_MIC_QUALITY.md) pins the installed source and verifies both sources reach STT as raw 16 kHz mono PCM. Recorder gain/filtering is separate. On actual recordings, the full recorder chain reduced 73 to 65 errors on each source’s 146-word set, but some phrases regressed and the fixed gain clipped louder LC3 compatibility inputs. Retain the current shared path. Two owned-recording G2 rearm attempts stalled; a continuous 56.55-second G2 recording completed and the original source preference and disabled/idle recorder state were verified. See the report for all arms, alignment, evidence and qualification limits.

## Shared STT conditioning A/B, 4 November 2026

The [conditioning report](STT_SHARED_CONDITIONING_AB.md) audits 1,815 arm records across 11 policies, physical P4/G2 audio, 131 regression/confirmation cases and two continuous-sequence replays. Conditioning only detection while preserving raw model input reduced continuous G2 edits 97→74 and concatenated P4 edits 88→65 on 146 words each. No candidate passed all speech, quiet-recovery and background gates. The strongest detection policy worsened noisy read speech 33→35 errors and background output 4→7 words across six minutes, with incidental-voice caveats. Preserve the default. No candidate was flashed; the G2 rearm fix was excluded.

### Detector follow-ups completed; training comparison pending, 4 November 2026

Two host investigations audited 2,640 arm records across 16 detector configurations. None passed every gate. See `docs/STT_DETECTOR_FOLLOWUP.md` and `docs/STT_RELATIVE_DETECTOR_AB.md`. The measured gain-ramp/calibration and histogram-range mismatches explain some triggers, but their combined correction lost the P4 quiet gain. Raw detection at 1.25× noise with onset confirmation recovered quiet speech without amplification (actual continuous G2 97→68 errors; constructed P4 88→70), while distant/noisy speech and recorded-background retention still failed. No production model, settings or firmware changed; no candidate advanced to hardware. G2 remained saved-audio only while the user had the glasses.

The broader main-chat goal remains active for the training comparison. The training chat is actively fitting its matched compact16k arms; early A1024 export exists but is unselected and unqualified. Do not use physical microphone regressions to select early checkpoints. `private/stt-model-comparison/protocol.md` fixes the later comparison, including separate recognition-only and caption-admission scores. `GOAL_STATUS.md` tracks the remaining requirement and training-chat cursor. Private detector evidence and completed job handles are recorded in each experiment's SESSION_STATUS.md. All detector replay and finish jobs exited successfully; the local reports are the completed detector deliverable, not a claim that training or live qualification is finished.

The [separator P4 preflight](STT_SEPARATOR_P4_PREFLIGHT.md) now includes a successful isolated ESP32-P4 compile/link proof for the corrected, unselected A4096 export. It enabled all 16 graph operators and selected Conv kernels; ELF inspection pinned the embedded model and six normalization forward implementations. Execution is disabled and nothing was flashed. Static activation payload is 6,523,904 bytes versus a 553,728-byte model file; this is not total application RAM. Runtime numerical parity, bounded device adapters, peak memory and speed remain pending. Main comparison baseline/scoring are prepared privately; checkpoint selection and qualification still belong to the active training chat.

A bounded host overlap-add reference is prepared under `private/stt-model-comparison/bounded_runtime.py`. Its frozen check report records 104 byte-exact comparisons against the training adapter snapshot and ten minutes of fixed retained-array storage (1,344,000 bytes, excluding model/transient/caller memory). It does not change the training runtime or production firmware and is not a P4 RAM measurement. Recheck the snapshot against the final admitted runtime before porting. Training A has completed; B and the first caption/speaker evaluation remain active, with no selected qualified candidate yet.

The [early separator comparison](STT_EARLY_SEPARATOR_COMPARISON.md) now compares two completed, audited 243-case development runs. A1024 is worse: global profile-attributed errors 2,462→4,556 on 3,400 words; ordinary/quiet single-speaker outputs contain substantial unwanted second-stream text. This is an unselected warmup checkpoint, not the teacher-assisted/final result. Both results passed cached-logit, actual cluster replay, mapping and error-total audits. Remaining checkpoints, selection and held-out qualification are still running; main microphone comparison and hardware qualification remain pending. Do not suppress the second stream or alter the matched run based on this diagnostic.

Reference caveat added to the early comparison: 11/16 reserved AMI headset utterances overlap other annotated turns, so full audible-word coverage is not established there. Frozen primary scores remain intact. The separate all-LibriSpeech diagnostic still shows the early duplication failure: ordinary errors 24→314 and quiet 27→315 on 287 words each; both heads emit text in all 64 clean single-speaker cases. This diagnostic does not replace development selection or held-out qualification.

The known-source development control is complete and audited: 886 global profile-attributed errors versus the mixture baseline's 2,462/3,400 words; clean LibriSpeech two-speaker oracle errors 151 versus 1,359/1,722 words. The audit verifies the control really supplies padded individual PCM sources, not separator outputs. This is an ideal-input diagnostic showing separation headroom, not a deployable model or proven P4 gain. Source/headset reference caveats remain disclosed. Later checkpoint evaluation is active.

A separate [additive rescue routing replay](STT_RESCUE_ROUTING_AB.md) completed 163 cases and two continuous sequences using cached recognition outputs. It preserves baseline job samples/publication times and admits disjoint quiet rescues after a causal pre-roll/live-candidate guard. All release/read/loud/overlap text stays unchanged; background output rises 4→16 words, so it fails the prospective gate. Constructed P4 errors improve 88→74/146 words; actual continuous G2 remains 97/146. Isolated gains include 17 session-end-only rescues. The 165-record audit checked 249 cached inputs, no later raw overlap and unchanged scores/ranges after a timing-marker clarification. No neural worker, device scheduler or firmware change was introduced. Current defaults stay unchanged; later training evaluations remain active.

A4096 development is complete and independently audited (243 cases/486 streams): 4,302 attributed errors versus A1024's 4,556 and baseline's 2,462/3,400 words. Lower insertions drive the improvement; deletions rise 770→783. The second-stream failure persists in every clean single-speaker case. See the updated early comparison; final supervised and teacher-assisted evaluations remain pending. The model/PCM/cache/cluster consistency audit passed, not P4 qualification.

All supervised checkpoints are complete and independently audited: A8192 has 4,471 attributed errors, versus A4096 4,302, A1024 4,556 and baseline 2,462/3,400 words. A4096 remains the best supervised development checkpoint. Longer training does not solve the extra-stream failure; A8192 still emits both heads in every clean single-speaker case. This is not the final A/B or qualification decision. Teacher-assisted development evaluation is now active; no main microphone candidate or firmware change yet.

B1024's pre-assistance control completed and passed independent audit. It matches A1024 exactly across all 486 saved output PCM hashes, hypotheses, embeddings and logit/sample metadata, with 4,556 attributed errors. This validates the observed matched warmup, not teacher benefit or universal graph equivalence. Post-assistance B4096/B8192 evaluations remain pending; no selection or promotion yet.

The first post-teacher separator checkpoint, B4096, completed its 243 development cases and passed the main read-only audit. Its 4,342 profile-attributed errors exceed matched A4096's 4,302 and baseline's 2,462. Both outputs still transcribe all 64 clean single-speaker cases, adding 285 ordinary and 270 quiet words on the empty-reference output. A controlled nine-case check of the unchanged loss confirms a quiet coherent copy incurs a quadratic penalty; this is a possible objective mismatch, not a proven cause or changed training policy. See docs/STT_EARLY_SEPARATOR_COMPARISON.md and private/stt-model-comparison/B4096-development-summary.json. B8192, frozen selection, held-out qualification and conditional microphone/device testing remain unfinished. Production defaults remain unchanged.

All six compact16k-round2 development checkpoints and both controls are complete and passed the main result audit. Frozen selections are A4096 (4,302 errors) and B8192 (4,071), both worse than baseline (2,462) on 3,400 reference words. B8192 reduces extra words but still duplicates single-speaker speech and misses more words than selected A4096. Held-out qualification has started under the original evaluator; no deployment acceptance is established. A single main comparison controller (session58952) is waiting for all qualification reports and the decision audit before auditing artifacts and running the selected models on saved microphone/regression audio. No hardware or default change. See docs/STT_EARLY_SEPARATOR_COMPARISON.md and private/stt-model-comparison/GOAL_STATUS.md.

Selected A4096 held-out qualification completed 355 cases / 9,011 reference words and passed the main 710-stream artifact/logit/profile/count audit. Its total is 11,177 profile-attributed errors, including 6,982 extra words. Qualification controls are not complete, so this is not yet a comparative acceptance result; do not compare its raw total with the smaller development partition. B8192 qualification is now running. See docs/STT_SEPARATOR_QUALIFICATION.md. Main saved-microphone comparisons remain queued behind all qualification reports and the decision audit. User requested checks every five minutes with no routine progress notifications; monitor-cadence.json records the next check. Defaults and hardware remain unchanged.

Both selected separator qualification results are now complete and audited: A4096 has 11,177 primary profile-attributed errors and B8192 has 11,524 on the same 9,011 words. B has 527 more missed words, partly offset by fewer insertions/substitutions; its better development total did not yield a better primary qualification total. Oracle acoustic counts and real-overlap totals are reported separately in docs/STT_SEPARATOR_QUALIFICATION.md and cannot replace the primary metric. Baseline qualification is running; both controls, full decision audit and main saved-microphone comparisons remain unfinished. Defaults and device remain unchanged.

The raw-baseline qualification completed and passed audit: 6,447 primary errors versus A4096 11,177 and B8192 11,524 on the same 9,011 words. Both separators fail ordinary/quiet oracle error nonregression and real-overlap total-error improvement under primary and oracle metrics, despite reducing real-overlap missed words. These candidates therefore do not justify live firmware promotion. The known-source control is running; complete decision audit and saved P4/G2 microphone comparisons remain pending. See docs/STT_SEPARATOR_QUALIFICATION.md. Current model/firmware defaults are retained.

All four separator qualification results and the final decision audit are complete: source-input control has 1,808 primary errors versus baseline 6,447, A4096 11,177 and B8192 11,524. Source control bypasses separation and uses paired headsets for real recordings; it is diagnostic headroom, not a deployable result. Both models fail four of seven necessary checks, so no live promotion is justified. The main audit was corrected for 64 real-headset records without the synthetic sample-count field; both source-control schemas then passed, with no scoring changes. Main comparison controller58952 ended on that audit error and was replaced after the fix by session47316; it is waiting on the shared evaluation lock behind selected-checkpoint floating-point diagnostics. Saved microphone comparisons and actual result audits remain pending. See docs/STT_SEPARATOR_QUALIFICATION.md and private/stt-model-comparison/GOAL_STATUS.md; retain five-minute checks and unchanged production defaults.

The selected A4096 floating-point development diagnostic completed and passed the main 486-stream audit: 4,351 primary errors versus exported A4096 4,302 and no-separator baseline 2,462 on the same 3,400 words. A's regression therefore exists before separator quantization; this does not prove a particular training cause or extend to B yet. See docs/STT_FLOAT_EXPORT_DIAGNOSTIC.md. Saved-microphone A comparison has actually started (8/163 cases at the user status check), with B's float diagnostic queued on the shared lock. Main controller session47316 remains active; completed main result audits and B float interpretation are still pending. Production defaults remain unchanged.

Selected A4096 has now actually completed and passed the saved-microphone result consistency audit: 163 regression cases, 32 whole physical microphone windows, 210 caption segments, 484 decoded-stream checks and two continuous controls. It fails: caption errors rise from 609 to 2,221 on 2,168 words; actual G2 continuous errors rise 97->155 and constructed P4 continuous 88->158. Full-window recognition also worsens in all four microphone/level groups. Quiet clips rejected by baseline detection remain all misses under unchanged cuts. See docs/STT_SELECTED_MICROPHONE_COMPARISON.md. B's float diagnostic is computing, with B's main microphone comparison queued under the shared lock. Both B results and their actual audits remain pending; retain current production defaults and five-minute checks.

Both selected floating-point development diagnostics are complete and audited. Float B8192 has 3,971 primary errors versus exported B8192 4,071 and baseline 2,462; float A4096 has 4,351 versus exported 4,302. Both regress before separator quantization under the shared inference pipeline, so precision alone cannot resolve their measured failures. The exact training/target/loss/common-preprocessing cause remains unproved. See docs/STT_FLOAT_EXPORT_DIAGNOSTIC.md and private/stt-model-comparison/float-comparison-audit.json. B's saved-microphone comparison is now actually running (6/163 at the scheduled check); its complete result audit and the campaign completion audit remain pending. Current production defaults remain unchanged.

Round-two detector/separator work is complete and reconciled in docs/STT_AB_ROUND2_OUTCOME.md and private/stt-model-comparison/round2-closure-audit.json. Final B saved-microphone audit passed: 609->1,949 caption errors on 2,168 words; actual G2 continuous97->137 and constructed P488->125. Both models fail full-window microphone retention and continuous controls; no live promotion. Controller47316 exited0. The broader goal remains ACTIVE: the separate training chat has already launched compact16k-loss-round3, a frozen matched loss-only A/B with existing training/export/evaluation workers. Main work must audit and follow those new selected candidates without restarting round two or duplicating their workers. Old real-overlap cases in the next round are regression-only, not fresh real qualification. Own five-minute heartbeat was updated to the current state; the training chat's separate monitor was left intact. Production defaults remain unchanged.

Main read-only review of the active loss-only round passed: launch/prior/scoring hashes, unchanged numerical functions and runtime/metrics/rules, exact reused development, fresh synthetic qualification construction (320 source-sum checks /608 PCM paths), local source/voice separation and 177-tensor A1024 control replay. The original objective's tiny-clean-duplicate preference was independently reproduced; the candidate active-source reconstruction loss removes that analytic preference. This is not a fitted accuracy result, and the silence penalty is unchanged. See docs/STT_LOSS_ROUND3_MAIN_REVIEW.md and private/stt-model-comparison/round3-contract-audit.json. Full matched-input/export/selection/qualification and selected-microphone evidence are still pending; old real data are regression-only. Leave the frozen training-chat experiment and its existing workers untouched, retain host-only operation and current defaults.
