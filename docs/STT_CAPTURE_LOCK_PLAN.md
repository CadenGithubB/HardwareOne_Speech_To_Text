# STT capture-lock contention: implementation and qualification plan

Status: investigation executed, 4 November 2026; adoption held. Instrumentation,
host/sanitizer and exact P4 checks, original and model-local SDK primary cohorts,
bounded follow-ups, twelve secondary controls and a 66m44s single-boot diagnostic
soak are complete. Clearing work falls; caption speedup is unproven. Conv4 quality,
x2f label-delay and speaker numerical-fixture gates remain held. The separate
block-14 experiment completed with its own-fixture failure, so longer RAM workloads
were gated off. Section 15 records requirement dispositions; earlier sections
retain their design contracts and dated execution sequence. Actual evidence is in
STT_CAPTURE_LOCK_RESULTS.md and all 44 bracketed runs in STT_CAPTURE_LOCK_RUNS.md.
Starting runtime: `9a0f14e`. This is standalone STT engine work; training/data work
remains with the other agent. No production default was promoted.

## 1. Outcome and boundaries

Reduce the time microphone capture waits for shared streaming state, without
changing accepted audio, phrase boundaries, recognition weights, speaker rules,
decoder settings or transcript semantics. A shorter mutex hold is an intermediate
result; the product outcome is smoother capture with no extra missing audio,
phrase drops, feature overruns or caption/label delay.

Do not promise a speedup before measuring. Inference can remain the limiting
stage even if capture waiting improves. Moving memory operations outside the
mutex still consumes PSRAM bandwidth and CPU time, so measure total effects.

Work in these owners:

- `firmware/components/hw1_stt/stt/stt_stream.{h,cpp}`: portable scheduler,
  cache/PCM ownership, optional bounded counters.
- `firmware/examples/p4_eye_captions/main/main.cpp`: mutex timing, microphone
  diagnostics and private qualification input/telemetry integration.
- `tests/stt_stream_test.cpp`, `tests/test_stt_stream.py` and focused new harness
  code only where the existing fixture cannot express an interleaving.
- A standalone qualification runner under `tools/device_tests/` if needed to
  consume this app's real events. Reuse existing scoring/alignment code.

Leave training files, model exports, speaker algorithms and unrelated HardwareOne
maintenance untouched. Do not synchronize another checkout. Keep x2f versus legacy
pacing, endpoint pauses, tail policy, model identity and PSRAM speed fixed within
an experiment; qualify their interactions separately. No default promotion, push,
main merge or outward filing is included.

## 2. What the current source actually does

The mutex is a FreeRTOS mutex, not an interrupt-disable lock. DMA/interrupts can
continue while the capture task waits. That does not provide unlimited buffering.
The example reads 1,024 samples at 16 kHz, nominally 64 ms of audio, and requests
four DMA descriptors. The nominal aggregate is 256 ms; this is not a proven safe
stall budget. Verify effective driver behavior, queue overflow and read cadence.

| Path | Work done while holding the stream mutex | Example maximum / significance |
|---|---|---|
| `push` | Ring writes, segmenter/VAD work and loop over the incoming block | Usually 1,024 input samples; internal subdivisions do not release the outer mutex |
| `queue` called from `push`/`finish` | Copy a completed phrase into a queue slot; pad very short phrases; release/rearrange segmenter storage | Up to 160,000 int16 samples = 320,000 bytes |
| `take` for draft/speculation | Copy the current capture prefix into the snapshot | Up to 320,000 bytes |
| `retire`, sometimes from capture | Clear the entire retired feature cache after its last pin | 1,000 rows x 64 floats x 4 = 256,000 bytes per cache |
| `complete` | Unpin/retire cache and clear completed slot or snapshot | PCM clearing is already limited to the used span; a final can also trigger cache clearing |
| `cancel` | Retire caches and clear queued PCM while keeping active-reader ownership | Several queued buffers may be involved |
| `featureTake` / `featureComplete` | Copy a bounded private frame window / publish one 64-float row | Much smaller operations, still measured |
| `enableFeatures` | Zero ring and both complete caches | Startup before microphone capture; keep separate from steady-state figures |

These sizes are source-derived maximums, not measured P4 stall times. The code
already clears used PCM spans in normal completion: do not claim that changing
those operations to used spans is a new optimization.

Important constraint: clearing in `push` is work on the capture task. Moving it
outside the mutex but keeping it on that task can still delay its next I2S read.
Likewise, unlocking around `memcpy(snapshot, live_capture, ...)` is unsafe because
the segmenter can close, rotate pre-roll, carry a hard-cut suffix or reuse storage.

## 3. Correctness invariants before any optimization

1. A buffer has one writable owner. No writer overlaps an inference reader,
   snapshot preparation, cleanup owner or feature-prefix reader.
2. `Free` means safe to reuse and cleared according to the privacy contract.
   Cleanup-pending buffers are not free capacity.
3. PCM work retains its original sequence, start sample, length, hard-cut flag and
   exact bytes. No later phrase is relabeled as a dropped earlier phrase.
4. Feature rows are a contiguous committed prefix for one start sample/generation.
   Counts become visible only after the corresponding row bytes are written.
5. Cache readers pin their data. Retired pinned caches cannot be cleared/reused;
   stale feature completions and cleanup completions cannot publish into a new owner.
6. `cancel` invalidates work without clearing memory still read by active inference.
   `finish` drains valid final work and does not enable session-end speculation.
7. A ready final keeps priority over preview work. Exact speculative reuse remains
   available when coverage/identity are valid; no forced final re-decode is introduced.
8. No heap allocation, file I/O, serial output or arbitrary observer callbacks occur
   inside the streaming mutex. Diagnostics are fixed-size and emitted outside it.
9. The existing single producer / single transcription consumer / optional feature
   consumer contract remains explicit. Null-lock single-threaded use still works.
10. Every claimed buffer is eventually completed, discarded or cleaned. Waiting
    for cleanup must not silently exhaust the two-cache / three-final-slot pools.
11. Caller-owned buffers outlive every reader and cleanup lease. `cancel` does not
    join workers today. Do not introduce hidden post-return cleanup that accesses
    buffers after the caller has joined the previously documented owners.

## 4. Milestone A: instrument the existing implementation

First deliverable: an instrumented baseline plus a report, before changing ownership.

### Lock and work attribution

- In the existing platform lock/unlock adapters, measure acquisition wait and
  hold time with a microsecond monotonic clock. Keep per-caller operation/role
  state in bounded task-local or preallocated storage; no shared unprotected
  timestamp and no counter feedback into scheduling.
- Attribute `push`, `take`, `complete`, `cancel`, `finish`, feature operations and
  status queries separately. Attribute the large inner copies/clears by operation,
  byte count and whether they ran on capture or another task.
- Record count, sum, maximum and bounded histograms. Report percentile bin ranges
  when bins are approximate; do not present histogram estimates as exact samples.
- Include source/destination tier, phrase length, cache frames and pins where useful.
  Never copy raw PCM into telemetry or retain text/audio in public results.
- Snapshot metrics under a brief lock and write them from an application-owned
  diagnostic path outside the lock. No per-frame serial/file flood.
- Budget optional telemetry storage at no more than 4 KiB initially; record actual
  target bytes and stack impact. Disabled production instrumentation must avoid
  timing/logging work in these paths.

### Capture and downstream measurements

Record read interval, bytes returned, short/odd reads, timeout/error counts, time
from read completion to `push` completion, total `push` duration, and driver RX queue
loss/overflow through the appropriate ISR-safe callback/counter. Verify the pinned
IDF callback restrictions before implementation; do not log or take the stream
mutex in an ISR. Observe task affinity/priority and scheduling delays.

Also record accepted sample totals, segment sequences, final queue occupancy and
high-water mark, drops, cache availability/pins, feature misses/overruns, canceled
previews, promotions, final/first-draft/text/label timings, free/largest memory
blocks and minima. Distinguish a cache miss from actual lost microphone input.
A sample counter that advances only for delivered samples cannot prove that DMA
never lost samples; retain driver-level evidence.

Measure diagnostics overhead using matching instrumented/uninstrumented controls
and a cheap empty-lock timing control. Separate model warmup, startup clearing,
steady state, phrase close, cancellation and session drain.

### Baseline workloads

1. Deterministic host replay through the actual C++ scheduler with controlled
   completion order and synthetic PCM; preserve a machine-readable trace.
2. Concurrent producer/feature/inference stress using real frontend rows.
3. P4 short, medium and maximum-ten-second phrases; continuous hard cuts; frequent
   short phrases; silence; stop/cancel near boundaries; producer under inference load.
4. Final queue pressure and feature ring pressure, with explicit expected overflow
   behavior. Do not compare an intentionally saturated run against a clean run.
5. Fixed existing conv2–4 acoustic fixtures, with comparable model/config/settings.

Freeze source/config/model hashes and raw private results. Verify current actual
SDK: 64-byte L2; retain the standalone profile's 200 MHz PSRAM for the primary
experiment. A 250 MHz comparison is a different experiment. No inference from
historical HardwareOne timing is accepted as this baseline.

Gate: identify which operation/task contributes materially to capture waiting or
read delay. If capture wait p99 is below 1 ms, maximum below 4 ms, and there is no
related backlog/loss in the defined workloads, avoid a large ownership redesign
unless another measured cost justifies it. These are engineering triage targets,
not assertions about the driver's deadline. Freeze final numeric gates before
examining candidate results.

## 5. Milestone B: reduce unnecessary cache clearing first

This is the preferred first optimization: small code change, no unlocked ownership
transition and no new full-size buffer.

Current feature writes commit exactly one 64-float row at `frames`, then increment
`frames`. Both caches start fully zeroed. A retired cache rejects later feature
writes. Therefore, if those facts remain true, clearing the committed row prefix
is sufficient: bytes beyond it stayed zero from initial setup or previous cleanup.
Prove this invariant in tests before changing `retire`.

- Capture the committed/dirty high-water count before resetting any cache metadata.
- Clear only that prefix when the last pin is gone. If any future writer can dirty
  bytes before committing `frames`, track dirty high-water independently.
- Keep full startup clearing, bounds checks, generation changes and pin rules.
- Test the complete reusable cache region for zero after retirement, not only the
  portion that the next inference happens to read.
- Retain current PCM clearing/padding behavior; it is already span-bounded.

Gate: exact traces/feature bytes pass; fewer bytes cleared for partial caches;
full-length caches preserve existing behavior. Repeat the short P4 attribution
workload to confirm that byte reduction yields an actual cost reduction.

## 6. Milestone C: clear exclusively owned buffers outside the mutex

Only proceed if remaining clearing is material. Implement one buffer type at a
time, preferably consumer-owned snapshot/final completion before producer cleanup.

Proposed state transitions (design, not existing implementation):

| Resource | Proposed ownership transition | Reuse condition |
|---|---|---|
| Final slot | `Running -> Clearing -> Free` | Its exact PCM span is cleared and the cleanup lease is current |
| Snapshot | `Reading -> Clearing -> Available` | No active/preparing reader and clearing completed |
| Feature cache | `Live/Attached -> Retired -> Clearing -> Free` | No pins, no valid writer, current generation/cleanup lease, cleared dirty prefix |

Under the mutex, detach ownership into a bounded cleanup descriptor containing
buffer identity, pointer, byte span and generation/lease. Mark it unavailable and
invalidate stale publishers. Release the mutex, clear only that owned span, then
reacquire and publish free capacity only if the descriptor still owns that buffer.
A pointer match alone is insufficient: test stale completion/ABA reuse attempts.

Do not publish `Free` early. Do not recreate speculative results after a concurrent
cancel. `take` cannot hand out the snapshot while it is preparing/clearing. Stop,
finish and cancellation must handle cleanup in flight without double clearing,
double unpinning or forgetting a resource. No-lock callers retain correct ordering.

For capture-triggered retirement, first evaluate handing bounded cleanup to an
existing non-capture owner. Prove prompt service during inference/idle, bounded
queue capacity, and explicit full-queue behavior. Do not add a low-priority cleanup
worker that can starve indefinitely, and do not hide dropped phrases behind a
larger queue. If housekeeping cannot be serviced without reducing cache/slot
availability, retain the simpler Milestone B implementation. Define a quiescent
cleanup/drain point for cancel, finish and destruction. Prefer completing a
consumer's cleanup before its public method returns; any asynchronous producer
handoff must explicitly extend and test the documented join/lifetime contract.
Do not free the pipeline, its lock context or caller buffers with leases pending.

Initial budget: no additional full PCM/feature buffer or hot-path allocation;
aim for at most 1 KiB of ownership/cleanup metadata and measure the actual figure.
Any larger design requires an explicit documented memory/latency tradeoff.

## 7. Milestone D: shorten copies only if they remain dominant

Keep both snapshot preparation and final-queue transfer separate from clearing.
They have different owners and hazards. Do not make both changes in one candidate.

### Snapshot candidate: bounded copies with revalidation

Reserve the snapshot and a preparation token. Capture start/sequence, exact target
length, speculative ID where applicable and feature-prefix identity. Copy bounded
chunks while holding the mutex, releasing it between chunks. Revalidate identity
and source validity at every reacquisition and before publishing work. An initial
4 KiB chunk is a tuning candidate, not an assumed safe time bound: measure it under
PSRAM contention. Keep the smallest design that gives a useful hold-time bound.

Appended live audio can be harmless to a stable prefix; close, hard-cut carry,
pre-roll rotation or source reuse cannot. If the prefix cannot be proven unchanged,
discard the preparation, clean its partial snapshot and let a pending final run.
No unprotected live-source reads, unbounded retry loop or stale speculative
promotion. Pin a valid immutable feature prefix or deliberately omit it and measure
the recompute cost; never associate another phrase's cache.

### Final-copy candidate: ownership handoff

If `queue`'s whole-phrase copy dominates, evaluate passing the closed capture
buffer to a final slot and switching capture to a clean available buffer. This
requires an explicit segmenter storage-handoff contract. Simply calling `reset`
would change noise calibration, sample coordinates and continuation state.
Preserve pre-roll and quiet-point/overlap carry, slot capacity and overflow policy.
Copying a small required carry may remain necessary. Do not add a full-size spare
buffer without first showing the measured benefit and safe contiguous RAM reserve.

This is a later architectural option, not a prerequisite for shipping a useful
clearing improvement. Reject it if it complicates ownership without measurable
capture benefit.

## 8. Correctness and interleaving matrix

Extend the actual C++ tests, not a second implementation of the scheduler. Use
barriers/latches for important interleavings; randomized scheduling is supplementary.
Replay failing seeds and record their schedule. Introduce test-only scheduling
hooks only at explicit ownership boundaries, compiled out of production.

| IDs | Cases and required assertions |
|---|---|
| C01–C05 | Empty, one-row, partial, full and overrun-retired caches: bounds/canaries intact; complete reusable region cleared; correct dirty-byte count |
| C06–C10 | Retire with a reader pin, last unpin, feature work in flight, late old-generation row, repeated retirement: no early clear/reuse or duplicate release |
| C11–C15 | Cleanup lease in flight, stale cleanup completion, producer during consumer cleanup, dirty slot/snapshot unavailable, cancel during cleanup: no data race or resurrection |
| C16–C20 | Finish/drain during cleanup, bounded housekeeping under starvation, null-lock caller, stable prefix append during snapshot preparation, phrase close between chunks: defined terminal state and final priority |
| C21–C25 | Resumed speech invalidates speculation, exact speculative promotion, hard-limit continuation, quiet-point carry/pre-roll rotation, cancellation after partial preparation: exact valid PCM and correct invalidation |
| C26–C30 | Sub-160/1,024-sample input partitions, session-end span below 320 with padding, maximum-length phrase, full final queue, feature ring overwrite: correct sample/sequence accounting and explicit fallback/drop behavior |
| C31–C36 | Snapshot/features disabled, legacy and x2f cadence, no hot-path allocation, cleared-before-reuse privacy invariant, cached rows equal batch frontend, overlapping finish/cancel/feature completion: contract unchanged |

Apply cases to the milestones they exercise; do not build elaborate lease/chunk
fixtures if Milestone B alone is sufficient. Keep the existing x2f, exact-reuse,
stop, feature-generation and queue-overflow tests passing.

Run AddressSanitizer/UBSan and ThreadSanitizer independently. Calibrate TSan with
`tests/test_tsan_memcpy.py` positive/negative controls so an ignored memcpy race
cannot make a clean run misleading. Check the touched path's zeroing output and
actual code ownership; a clean sanitizer run is not a proof by itself.

## 9. Device comparison and acceptance gates

Run short attribution/stress comparisons after each candidate. Only the finalist
receives the full recognition/latency matrix, avoiding a long microphone sweep for
every rejected micro-change.

Use matching baseline and candidate instrumentation. On conv2, conv3 and conv4,
run baseline/candidate/candidate/baseline (ABBA): twelve captures total, two per
image per fixture. Rotate fixture order between cohorts where practical, keep
speaker output at 50% on this Mac, and record room/noise observations. Repeat
instrumentation-off controls on the selected configuration. Never upload audio;
use existing local WAVs or already-present private device fixtures.

The runner must support the standalone product events, not send HardwareOne's
`stt start` commands to this app. If that adapter is missing, build the smallest
required runner before the baseline and record its source identity. Use canonical
reference manifests, qualified clock/acoustic alignment and explicit exclusions.
No timing number is published from an unqualified fit.

Freeze the following gates with the baseline report before candidate scoring:

- **Correctness:** zero new races, corrupt bytes, invalid ownership, lost accepted
  samples or sequence mistakes in deterministic tests; identical valid final PCM
  and features. Under equal inputs/weights/decoder, require identical logits/text
  for the same inference inputs. Changed preview opportunities are reported,
  not confused with corruption.
- **Reliability:** zero new driver loss, panics, watchdogs or deadlocks in normal
  workloads. Candidate drops/feature failures cannot exceed matched controls;
  overloaded fixtures must retain explicit, correct drop accounting.
- **Useful performance:** initial target is at least 25% lower p99 capture lock
  wait with at least 0.25 ms absolute reduction when baseline contention is
  material. If baseline wait is already negligible, a complex new state machine
  does not earn adoption merely from a better microbenchmark. Report affected
  operation hold time, total read-to-push delay and tails too.
- **No displaced problem:** lower hold time cannot come at the cost of longer
  capture-task work, unbounded cleanup backlog, fewer usable caches/slots or
  worse CPU/PSRAM pressure. Report maxima as well as medians/p99.
- **Caption/label latency:** flag a repeatable increase beyond 5% and 100 ms
  (both exceeded) in fixture median or p90 for investigation; do not mask a final
  regression with a first-preview win. This is an engineering gate, not a
  statistical confidence bound. Report all underlying values and drift.
- **Quality:** deterministic input equivalence is mandatory. For acoustic runs,
  report WER edits/denominators, speaker correctness with explicit exclusions,
  raw unknown coverage and false captions in silence. A repeatable degradation
  blocks promotion; do not average it away across fixtures. Do not claim formal
  noninferiority from two runs. Resolve a concerning result with one bounded
  bracketed follow-up set, then hold the candidate if uncertainty remains.
- **Memory:** no hot-path allocations, existing max phrase length and queue depth
  preserved, stated metadata budget, no reserve violation and no growing leak
  across repeated sessions. Publish free and largest-block minima.

Every watchdog-bearing image/input/mode must be rerun unchanged at least once,
per the user's instruction. Compare task, sampled location and input time; a
warning-free repeat does not erase the original. Keep the repetition set bounded.
If a normal baseline already loses samples or warns, document and repeat it;
reduce/repair the qualification setup before claiming an uncontaminated gain.

Freeze pacing for primary comparisons. Exercise both modes in host tests and
run a smaller secondary bracketed device check of the finalist under the other
pacing mode. Keep speaker-off and speaker-on contention controls distinct.
Finish with repeated mixed-length sessions and a minimum one-hour soak of the
finalist; this is a bounded soak, not proof of indefinite reliability.

## 10. Device safeguards, evidence and rollback

Before device work, own the board-use lock and confirm no competing owner. Use
the approved Python/helper, MAC e8:f6:0a:e3:a7:68 and actual partition validation.
Keep private verified rollback/partition evidence before flashing. The currently
selected x2f-only HardwareOne app is a rollback destination, not the standalone
performance baseline. Flash only the app at the verified address through the
approved helper; do not flash generated partition tables or erase the device.

Keep ring reconnect off. Preserve accounts/settings and other source checkouts.
Keep credentials out of logs. Audio is local Mac mini speaker output at 50%; raw
PCM, captions, model paths/hashes as appropriate, device logs and flash artifacts
stay in ignored private folders. Public reports contain aggregate results only.

On test failure, save evidence and restore the verified rollback. At the end,
restore the agreed app, verify identity/settings as supported by that app, stop
diagnostics/audio, close serial and release the lock. Do not silently replace
production defaults with a candidate. HardwareOne integration remains a separate
explicitly authorized step after standalone qualification.

Each milestone yields a small source commit and private evidence manifest: runtime
source/build/SDK/model hashes, task/core/config settings, test commands and exits,
raw traces, all captures including failures, rejected timing fits and comparison
tables. Update this plan's status and `STT_PRODUCT_HANDOFF.md` with actual outcomes
and incomplete checks. Preserve selected app/ELF/config/rollback/source evidence;
inspect disposable build output before any separately authorized cleanup.

## 11. Execution order and stop points

1. **Audit and specification (this document):** code paths, invariants, workloads,
   proposed gates and ownership risks recorded. No runtime change in this step.
2. **Instrumentation:** bounded counters and deterministic trace harness; validate
   probe overhead and keep instrumentation off by default.
3. **Baseline:** quantify producer/consumer hold and wait, memory traffic and
   capture continuity. Select the smallest useful candidate from evidence.
4. **Prefix-clear candidate:** prove the zero invariant and measure the result.
   Stop here if it supplies the useful gain or further contention is negligible.
5. **Exclusive cleanup candidate, conditional:** one buffer type at a time, with
   explicit leases/liveness and adversarial interleavings.
6. **Copy candidate, conditional:** snapshot chunking or final storage handoff,
   only for the measured remaining dominant path. No combined ownership rewrite.
7. **Final qualification:** full fixed-fixture comparison, secondary pacing/speaker
   checks, soak, rollback/readback and a concise accept/reject decision.

The first implementation milestone is instrumentation, not a blind unlock around
`memcpy`. No extra model training, filesystem maintenance or unrelated feature
work is needed to begin it. Timing estimates should be updated after the baseline:
final ABBA audio alone is roughly an hour with boot/drain overhead, and the soak
adds at least another hour. Architectural copy changes may take substantially
longer than the initial prefix-clear change and are not assumed necessary.

## 12. Execution checklist and reviewable deliverables

The requested improvement is target 2 in `STT_RUNTIME_IMPROVEMENTS.md`: reduce
capture-lock contention. Success means a useful measured reduction in capture
cost with preserved audio and recognition behavior. Finding that contention is
too small to justify a rewrite is also an actionable decision, provided the
baseline and limiting operation are documented. It is not a claim of a speedup.

| Step | Concrete output | Exit decision |
|---|---|---|
| Reconcile current work | Identify committed instrumentation, uncommitted prototypes, completed runs and missing checks; preserve other agents' files | Reuse valid evidence; do not rerun solely because it predates this checklist |
| Complete loaded baseline | Per-fixture table of lock wait/hold, read-to-push delay, copy/clear bytes and time, driver loss, queue pressure, captions and labels | Freeze gates before candidate scoring; identify the actual dominant path |
| Validate prefix clearing | Default-off candidate, documented zeroing invariant, exact PCM/features and sanitizer results | Reject on any stale data, ownership, bounds or sequence failure |
| Short matched device comparison | Same build configuration, models, inputs and probes; compare partial and maximum-length caches | Continue only if saved work produces measurable benefit without a displaced cost |
| Decide on further ownership work | Written proceed/skip decision for clearing leases and copying changes independently | Skip complexity when baseline contention is negligible or the small change is sufficient |
| Qualify finalist | Twelve ABBA captures, instrumentation controls, secondary pacing/speaker checks and at least one-hour soak | Accept, reject or hold with the precise unresolved check stated |
| Close out | Aggregate comparison, source/evidence identities, handoff update, small source commits and verified board restoration | Recommend adoption separately; no automatic production default change |

For every acoustic comparison, show each fixture/run as well as totals. Include
WER edits/reference words, speaker correct/eligible, raw unknown/missing labels,
final-text median/p90, first-preview freshness and speaker-label lag. Keep
unqualified timing fits visible as excluded results. Use deterministic equality
to establish algorithm preservation; acoustic repeatability measures product
behavior and cannot prove exact equality.

### Failure handling

- A correctness or race failure stops that candidate before further device runs.
- A watchdog triggers one unchanged rerun at minimum, with both outcomes retained;
  compare input position and sampled task/location before changing anything.
- Audio loss or queue exhaustion must be attributed and reported, including in
  controls. Do not silently enlarge buffers or change pacing to make a run pass.
- Failed or ambiguous acoustic alignment withholds the affected latency/identity
  claims. Improve the measurement using baseline evidence, then freeze the method
  before candidate comparisons; never tune it to favor a candidate.
- If benefit remains uncertain after the bounded follow-up set, hold the candidate
  and name the next discriminating experiment rather than reporting a win.

### Effort and elapsed time

These are planning ranges, not a completion promise. Reuse already-valid results.
Baseline reconciliation and remaining short controls may take one to three hours;
the prefix candidate and focused correctness work may take another two to four.
Full finalist qualification needs roughly one hour of ABBA audio, at least one
hour of soak, and additional build/flash/drain/scoring time. A small-change path
therefore merits roughly one working day, possibly spilling into a second if
measurement or reliability checks fail. Lease-based cleanup or segmenter buffer
handoff can add multiple days and should receive a revised estimate only after
the baseline demonstrates a need.

The separately requested mixed-precision RAM benchmark is outside these timing
estimates. Keep its models, images and results distinct so it cannot confound the
fixed-model capture comparison. No firmware flash or new test is required merely
to review this plan.

## 13. Current detailed execution plan — 3 November 2026

### Objective and current decision

Determine whether the small prefix-clear optimization earns inclusion in the
standalone STT runtime, while preserving audio, recognition and speaker behavior.
First qualify the model-execution isolation repair needed for trustworthy
concurrent inference. Keep the two changes separately selectable and report
their effects separately. Neither option becomes a production default here.

The existing measurements argue against a larger capture-buffer ownership rewrite:
loaded capture wait p99 is already small and the measured maximum is below 4 ms.
Clearing time falls approximately 67–73%, but that saves roughly tens of
milliseconds across a multi-minute recording. That is a memory-work reduction,
not evidence of faster captions. Milestones C/D stay conditional.

### Phase 0 — reconcile evidence and freeze experiments

1. Inventory owned source changes, other-agent changes, build identities and
   controller status. Preserve uncommitted work and archive manifests before
   replacing any private build artifact. Do not update/switch repositories merely
   to restart this task.
2. Retain the original twelve-run cohort and four-run follow-up unchanged.
   Publish their flags and denominators; do not average away the conv3 concern.
3. Record the latest isolated diagnostic separately: six recognition pairs pass
   and match pre-fix hashes; 83 real preparations of another model leave the
   speaker embedding unchanged with the fix. The speaker fixture remains failed.
   This demonstrates controlled isolation, not live incidence or accuracy.
4. Confirm final controller state before another board action. The latest saved
   status reports selected-app restoration, rollback readback and lock release.
5. Freeze a manifest per image: source, SDK patch/tree, model, LM, vocabulary,
   decoder, pacing, clearing, probes, speaker mode, L2 and PSRAM settings. Existing
   sdkconfig values must be checked directly, not inferred from defaults.

Deliverable: evidence inventory and configuration table. Exit when each existing
result has a known profile and each planned comparison changes one named factor.

### Phase 1 — qualify execution isolation independently

Review the default-off SDK/runtime patch before expanding acoustic testing.
Model preparation must visit only that model's modules, perform no arithmetic,
invalidate stale prepared arguments and leave other models' execution untouched.
Keep weights, kernels' arithmetic and speaker thresholds fixed.

| Case | Required observation |
|---|---|
| I01: option disabled | Legacy execution path and existing runtime tests remain valid |
| I02: cold model | First preparation and inference succeed with correct arguments |
| I03: warm repeated model | No stale arguments or changed output hashes |
| I04: alternating supported shapes | Each shape uses its own valid allocation and parameters |
| I05: invalid/preparation failure | No previous successful preparation is accidentally reused |
| I06: mixed operator graph | Non-Conv preparation does not execute activation arithmetic |
| I07: activation sentinels | Preparing A leaves A's activation bytes unchanged |
| I08: concurrent independent model B | B matches its normal embedding during repeated A preparation |
| I09: forced old global flag | Fixed B ignores unrelated global preparation state |
| I10: recovery/negative controls | Repeat same input matches; different inputs differ; recovery is exact |
| I11: lifetime | Reconstruct/free models without leaked arguments or dangling owners |
| I12: recognition equality | Same feature inputs yield identical output/text hashes across clearing modes and pre-fix control |

Reuse passing checks; add tests only for a real uncovered contract. Host fakes
can test lifetime/control flow but cannot validate P4 kernel arithmetic. Require
actual P4 equality for device claims. Record memory layout/binary size changes;
do not call free-heap checkpoints peak-memory measurements.

Exit: either a reviewable isolation fix with explicitly scoped evidence, or a
failed/held repair with a minimal reproducer. A clean controlled test does not
prove that the defect caused any historical acoustic score.

### Phase 2 — explain the independent speaker fixture failure

1. Verify the exact installed blob, embedded test presence, input/output types,
   shapes, quantization metadata and SDK version against its export contract.
2. Reproduce in an otherwise idle single-model process with the isolation option
   off and on. Retain first mismatch, expected/actual values and tolerance.
3. Check whether the wrapper's preprocessing/layout or the vendor embedded test
   path changes the compared tensor. Keep direct-trunk and wrapper tests distinct.
4. Where a matching host/export reference is available, compare the same fixture
   at intermediate tensors to locate the earliest divergence. If it is absent,
   record that limit rather than substituting an unrelated model or fixture.
5. Separate a test/export contract defect from a real inference error using that
   evidence. Do not loosen tolerance, replace weights, or label the result a
   silicon defect to obtain a pass.

Time-box the initial localization to one focused investigation session. If the
cause remains unknown, write a bounded next experiment and keep speaker accuracy
and adoption on hold. Independent performance evidence can still be reported;
it cannot be described as full qualification.

Deliverable: minimal reproducer and an explained result, or an explicit unresolved
contract with the first divergence and missing evidence named.

### Phase 3 — build a matched qualification cohort

Prepare the following explicit profiles after Phase 1; use the same validated
SDK isolation setting in both sides of each clearing comparison. Earlier images
used the shared preparation path and are historical evidence, not interchangeable
controls for these images.

| Profile | Clearing | Cadence | Probes | Speakers | Purpose |
|---|---|---|---|---|---|
| A | Full | Legacy | On | On | Matched control |
| B | Committed prefix | Legacy | On | On | Small optimization |
| C | Committed prefix | Legacy | Off | On | Probe overhead |
| D | Full | x2f | On | On | Secondary cadence control |
| E | Committed prefix | x2f | On | On | Secondary cadence candidate |
| F | Committed prefix | Legacy | On | Off | Speaker contention control |

Verify 64-byte L2 and standalone 200 MHz PSRAM in every built sdkconfig. Preserve
the verified rollback app and actual partition evidence. Recheck scoring and
panic detection before unattended captures. No audio upload is required: play
existing local WAVs through the Mac mini speakers at 50%.

Deliverable: frozen images/configs and comparison manifest. Exit only when no
unintended model, decoder, memory-speed or pacing difference confounds an A/B.

### Phase 4 — bounded acoustic qualification

If Phase 2 permits a meaningful speaker qualification, run one fresh matched
primary cohort on conv2–4: A/B/B/A per fixture, twelve captures. This cohort
qualifies the changed SDK context; retain the original cohort separately.
If the fixture remains unresolved, explicitly choose diagnostic-only runs and
withhold adoption rather than spending a full cohort to claim an overall pass.

Then complete the previously required secondary controls on conv2:

| Comparison | Order | Captures | Question |
|---|---|---:|---|
| Instrumentation | B/C/C/B | 4 | Do probes materially alter measured product behavior? |
| Other pacing | D/E/E/D | 4 | Does prefix clearing remain safe under x2f scheduling? |
| Speaker load | B/F/F/B | 4 | How much contention comes from concurrent speaker execution? |

These are twelve secondary captures, not twelve new algorithm variants. Speaker-off
runs have no speaker-accuracy comparison. Probe-off runs cannot claim zero driver
loss from unavailable counters. Use retained timing fields only within their
documented measurement limits.

For every acoustic run retain WER edits/reference words, speaker correct/eligible,
unknown and missing labels, qualified final lag median/p90, shown-text and label
lag, queue/cache pressure, loss/fault counters and memory checkpoints. Use the
already frozen waveform alignment method; keep rejected fits visible. Do not
change alignment parameters after seeing candidate scores.

Apply Section 9 gates per fixture. A concerning acoustic result gets at most one
bounded bracketed follow-up for this new cohort, with a reason recorded first.
An unresolved result means hold, not repeated testing until a favorable sample.
Every watchdog-bearing image/input/mode receives at least one unchanged rerun;
retain both outcomes and compare location and input position.

Deliverable: run-by-run comparison and accept/reject/hold table. Exit when each
gate has evidence or a clearly named failed/unmeasured status.

### Phase 5 — continuous reliability check

Only a finalist that passes the preceding correctness gates receives the full
soak. Run at least one continuous hour on one boot, mixing conv2–4 and long
phrases with repeated start/stop/drain sessions. Do not reset between fixtures
or silently reload models to hide memory/lifetime problems.

Check sample continuity, DMA loss, drops, watchdogs, panics, queue/pin drainage,
unexpected session/model restarts, free/largest-block trends and playback coverage.
Checkpoints establish observed memory trends, not transient peaks. Apply the
unchanged-test watchdog repeat rule to the same sequence from boot. Preserve the
failed sequence; limit repetitions to the defined diagnostic purpose.

Finish by restoring the selected app, verifying readback and ring reconnect off,
closing serial/audio and releasing the board lock. If there is no qualified
finalist, record the soak as not run and why; do not soak an unsafe candidate
merely to fill a checklist.

### Phase 6 — reviewable conclusion

Update `STT_CAPTURE_LOCK_RESULTS.md` and `STT_PRODUCT_HANDOFF.md` with actual
outcomes, raw evidence identities, exclusions, incomplete checks and board state.
Keep source changes small and stage only owned paths/sections; preserve training
agent changes. Provide a comparison visual with clearing cost, capture wait,
WER, speaker correctness/unknowns and qualified lag, showing all runs and separate
SDK cohorts. Never draw a speedup bar from clearing time alone.

Make separate recommendations for the isolation repair, prefix clearing and any
further ownership work. Possible outcomes are accept for explicit integration,
reject for insufficient benefit/regression, or hold for a named unresolved gate.
No production-default change, HardwareOne push, main merge or outward issue is
part of this plan; those require the user's approval.

### Scheduling, scope and completion

Execute Phases 0–2 first; they determine whether a new acoustic qualification is
worth running. Budget several hours for focused isolation/fixture work, then
roughly two to four hours for builds, the 24 planned primary/secondary captures,
flashes, drains and scoring. The continuous soak adds at least an hour plus
restoration/reporting. A clean path is roughly one working day; an unresolved
fixture may extend it and must receive an evidence-based revised estimate.
These are planning allowances, not measured completion times or a promise that
the fixture can be explained in a day.

Do not count tests by inflating every parameter into a new goal. The contract
matrix, twelve isolation cases, primary cohort, secondary controls and continuous
soak cover different failure modes; report which are completed, failed, not
applicable or not checked. Reuse existing valid host/sanitizer/replay evidence.

The separately requested block-14 mixed-precision fixture/RAM benchmark remains
queued as its own experiment. It changes the model and needs its own numerical
fixture and memory methodology; it cannot replace fixed-model capture tests.

Completion means the evidence supports a recorded decision, the required checks
are complete or explicitly block adoption, owned changes are reviewable, and the
board is restored. It does not require inventing a latency win or implementing
the conditional buffer-ownership redesign.

## 14. Remaining-work plan — 4 November 2026

### Goal and success criteria

Reach separate, evidence-backed decisions on (1) model-local SDK preparation,
(2) committed-prefix cache clearing and (3) any larger ownership rewrite. The
intended product benefit is reliable capture without worse recognition, speaker
labels or caption delay. Reduced clearing cost alone does not establish that
benefit. A documented rejection or hold is a valid result; default promotion is
not required for completion.

The model-local primary cohort has twelve captures. The single permitted conv4
follow-up is also complete. Its concerning speaker pattern did not repeat, but
that does not establish noninferiority or erase the original hold. Do not run
additional conv4 brackets to seek a favorable outcome. The independent embedded
speaker fixture is still failed. Keep both limitations visible throughout.

### Step 1 — finish the secondary controls already in progress

Continue the existing controller, preserving its state and lock ownership. At
this checkpoint seven of twelve captures are recorded; the closing x2f control
is running. Observe the same process rather than launching another controller.

| Group | Order | Purpose | Interpretation limit |
|---|---|---|---|
| Instrumentation | On / off / off / on | Identify probe effects | Probe-off DMA counters and aligned timing are unavailable |
| x2f | Full / prefix / prefix / full | Check clearing under the other cadence | This is not a fresh legacy-versus-x2f adoption study |
| Speaker load | On / off / off / on | Attribute concurrent speaker cost | Speaker-off cannot establish speaker accuracy |

Keep images, local waveforms, speaker volume, scoring and alignment parameters
frozen. Preserve each run's reference denominator, missing/unknown labels and
clock qualification. A feature-cache fallback is not microphone sample loss.
Record absent metrics as unmeasured, never zero. Worker categories are final=0,
draft=1 and speculative=2; descriptive duration buckets are not equal-input
kernel benchmarks.

Exit: all twelve captures scored, or a named fault stops the sequence; controller
termination, selected-app restoration/readback and lock release are verified.
A watchdog requires the same image/input/mode rerun at least once, retaining both
outcomes and comparing task/location/input position.

### Step 2 — close the preparation-failure correctness gap

Build the optional isolated P4 preparation-refusal probe after acoustic playback
has stopped. Keep it outside production images and leave its flag off by default.
It is currently source-only and has no device pass result.

1. Establish the ordinary output for the actual fixed speaker fixture.
2. Reject the optional prepared-argument storage requests using the scoped
   diagnostic allocator policy; record that a rejection actually occurred.
3. Require preparation to leave activation input/output snapshots unchanged.
4. Run ordinary inference through the fallback and require the same output hash.
5. Restore allocation policy, prepare again and require exact recovery.
6. Retain the existing recognition-equality and independent-model checks.

This tests allocation-policy refusal, not real heap exhaustion or production RAM
fit. The known numerical fixture failure stays failed even if fallback equality
passes. If this probe fails, hold the SDK repair and produce the smallest
reproducer before scheduling additional performance work.

Exit: explicit pass/fail for refusal, fallback and recovery, with image/config
identities and verified board restoration. Reuse valid host lifetime/equivalence
coverage rather than rerunning every test for documentation-only edits.

### Step 3 — make the soak decision before reserving another hour

Apply the existing correctness and quality gates after Steps 1–2. The original
speaker-quality hold and independent fixture failure currently prevent overall
qualification. Do not describe this candidate as a qualified finalist.

If there is a safe, correctness-qualified configuration and an explicit remaining
reliability question, a minimum one-hour run may provide diagnostic reliability
evidence only. State that scope before starting. Otherwise record the soak as
not run because its prerequisite is unmet, as Section 13 requires.

The prepared sequence uses one boot and repeated conv2/3/4/long-phrase sessions,
with no hidden model reloads. Check elapsed host/device time, sample continuity,
DMA loss, drops, watchdogs, panics, session/model identities, drained queue/pins,
and free/largest-block trends. These heap checkpoints are not transient peaks.
A watchdog requires an unchanged repeat of the sequence from boot. Stop on unsafe
state, restore the selected app and preserve the failed sequence.

Exit: scoped reliability result or an explicit prerequisite-blocked result;
never imply broad accuracy or indefinite reliability from the soak.

### Step 4 — audit evidence and make three independent recommendations

Map the original 36-case contract matrix and twelve isolation cases to actual
artifacts. Mark each completed, failed, conditional/not applicable, or unchecked.
An inventory script listing files does not establish that the requirements pass.

| Decision | Evidence required | Current constraint |
|---|---|---|
| SDK isolation repair | Model-local ownership, no preparation arithmetic, equality, independent-model safety, fallback/lifetime behavior | Controlled isolation passes; refusal probe remains unrun |
| Prefix clearing | Exact input/output preservation, useful benefit, no displaced capture/quality problem | Clearing cost improves; caption benefit unproven; conv4 quality hold |
| Larger ownership rewrite | Material remaining capture stalls that justify more states and lifetime complexity | Existing small waits do not currently justify implementation |

Publish per-run WER edits/reference words, speaker correct/eligible and unknowns,
qualified publication/label timing, capture wait/hold, clearing cost, faults and
memory observations. Keep old/new SDK cohorts separate. Withhold the old conv4
control's publication timing because its receive clock stepped backward; never
repair its timestamps after the fact. New monotonic receive clocks measure host
receipt, not physical display latency.

Deliver an updated comparison visual, results document and handoff with raw
private evidence identities and all exclusions. Commit only owned source and
owned handoff sections, preserving the training agent's uncommitted changes.
The recommendation may be accept for explicit integration, reject, or hold with
a named missing gate. Production defaults remain unchanged.

### Step 5 — keep the separately requested block-14 benchmark isolated

This model-changing experiment is outstanding and cannot replace fixed-model
capture qualification. Coordinate board time after the current controller ends.

1. Verify candidate/control hashes and identical input lengths and build settings.
2. Implement and review the isolated fixture/RAM harness; retain production model
   guards. Validate supported mixed-precision operators and allocation failures.
3. Prefer the host-verified small reconstruction delta over uploading a complete
   model. Any device scratch source must use fresh private paths with checked
   capacity; verify reconstructed bytes before loading. No audio upload is needed.
4. Require each model's own embedded fixture to pass before interpreting its RAM
   result as a viable candidate. Record a failure honestly rather than weakening
   fixture tolerance.
5. Compare matched cold/warm load and inference behavior. Distinguish checkpoints,
   conservative heap-derived bounds and actual event-level peaks. Name the
   allocation stage/capabilities and contiguous-block failure when observed.
6. Report isolated-probe overhead and limits: this is not full-application RAM
   qualification. Restore/read back the selected app afterward.

Exit: numerical result and defensible matched memory result, or an explicit
failure/blocker with the missing measurement named. No model/default adoption.

### Schedule, stop conditions and completion

Finish the running controls first. Allow approximately one to three focused hours
for the refusal diagnostic, evidence audit and report if no new fault appears.
A permitted soak adds at least an hour plus setup/restoration; an unchanged
watchdog repeat adds the same sequence again. The mixed-precision harness is a
separate several-hour engineering task, with a revised estimate after its first
fixture/build result. These are remaining-work estimates, not measured results.

Stop expanding the capture optimization if useful product benefit is absent or
a quality hold persists. Do not reopen the closed 128-byte cache-line fault hunt.
Do not combine new speaker arithmetic, training weights or decoder changes with
this fixed-model comparison. Any later speaker numerical-contract repair needs
its own plan, equal-input reference and separate acoustic qualification.

Board operations retain MAC/partition checks, app-only flashing through the
approved helper, private rollback evidence, owned locking, local speakers at
50%, and ring reconnect off. No flash erase or filesystem cleanup is part of
this plan. Pushes, main merges, production-default changes and outward filings
require the user's approval.

Completion requires reviewable decisions and evidence, explicit incomplete
checks, owned changes recorded, and verified restoration/lock release. It does
not require manufacturing a speedup or claiming that a held candidate passed.

## 15. Execution disposition — 4 November 2026

The investigation has reached the plan's accept/reject/hold exits. This is not
an overall qualification pass. Failed numerical/quality gates remain failed;
measurements deliberately gated off are named below rather than treated as zero
or promised as pending background work.

| Requirement | Actual disposition |
|---|---|
| Baseline and bounded instrumentation | Complete; optional probes default off, 3,720 bytes plus largest 376-byte page, loaded capture attribution and direct loss counters retained |
| Prefix clearing invariants | Applicable host/real-C++ sanitizer, canary, pin/generation, allocation and exact replay checks pass; actual P4 inputs/logits/text match across clearing arms and pre-fix control |
| Original 36-case contract matrix | Mapped to source and evidence in the results document; new lease/chunk-housekeeping cases are conditional/not applicable because C/D were not implemented |
| Calibrated race checks | Separate ASan/UBSan and TSan evidence, including positive/negative memcpy controls, retained |
| Pre-roll/ring boundaries | 28 original-versus-prefix replay comparisons include nonzero pre-roll/ring rotation; segmenter boundary checks pass |
| Preparation repair and twelve isolation cases | Reviewed default-off repair, real independent-model overlap and 104 optional-allocation refusals pass their scoped checks; arbitrary shapes, same-model reentry, warmed growth failure and physical exhaustion remain unqualified |
| Independent speaker fixture | Failed; dominant coarse int16 ReLU-table error explained by a causal probe, residual mismatch retained. No tolerance/default/model promotion |
| Matched profiles | Six model-local images verified, fixed model/decoder context, actual 64B L2 and standalone 200 MHz PSRAM; old SDK cohort kept separate |
| Primary device comparisons | Original twelve and new twelve complete; one bounded four-run follow-up per raised quality concern complete; no repeated favorable-sample search |
| Secondary controls | Twelve complete: instrumentation, x2f clearing and speaker load. Missing probe-off metrics and intentional speaker-off labels remain explicit |
| One-hour reliability | Twenty mixed-length sessions over 4,003.987 device seconds on one boot; no observed driver/phrase loss, watchdog/panic or reset/reload. Stable matched-fixture memory checkpoints; diagnostic scope only |
| Larger ownership work | Skip C/D: measured capture contention does not justify added ownership/lifetime complexity |
| Separate block-14 benchmark | Executed: control passes own fixture, candidate fails all three repeats. Both-model prerequisite fails, so additional 100/1,000/2,000-frame workloads are not run and candidate RAM viability is unqualified |
| Per-run reporting and visual | All 44 bracketed runs have quality, timing and capture/memory-work tables; seven-cohort visual retains unavailable metrics. Data/interaction checks pass; browser drawing/layout remains unchecked after local-preview URL policy rejection |
| Host product regressions | Actual transcript, persistence, bridge and viewer evidence retained; final viewer assertions run in a fresh Node runtime with source-identified proof |
| Privacy and restoration | Raw artifacts stay private/ignored; approved helper verifies MAC/PT and app-only writes. Every completed controller restores/readback-verifies the selected app and releases its lock |
| Production/integration boundaries | No default promotion, HardwareOne synchronization/push, main merge or outward issue. Those require separate authorization |

Adoption decisions: retain the default-off SDK repair as a reviewed integration
candidate with ABI/consumer limits; hold prefix clearing; skip the complex buffer
rewrite; reject this block-14 artifact for adoption until its numerical contract is
corrected. The results document names the next discriminating numerical experiments.
They are follow-on work, not a basis for claiming the failed models qualified.

Not checked: physical SD/FAT power-loss behavior, every real acoustic condition,
statistical noninferiority, word-level physical-display lag, dedicated silence
false-caption behavior, general physical-OOM recovery, unrelated prebuilt-consumer
ABI compatibility, and indefinite reliability. The internal memory benchmark gives
multi-heap bounds rather than an exact global internal peak. The failed candidate's
longer-shape and full-application RAM requirements remain unqualified. These limits
are explicit consequences of scope and failed prerequisites, not silently passed
requirements. Production defaults remain unchanged.
