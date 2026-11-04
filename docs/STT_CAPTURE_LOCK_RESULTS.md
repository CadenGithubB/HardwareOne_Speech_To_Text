# STT capture-lock work: actual progress and evidence

3 November 2026. Goal active. This is an implementation record, not a claim that
capture contention has been reduced or that device qualification is complete.
The controlling requirements remain in `STT_CAPTURE_LOCK_PLAN.md`.

## Instrumentation milestone

Implemented optional `CONFIG_CAPTIONS_STREAM_METRICS` (default off). The portable
engine counts/times its existing copies and clearing, attributed to the calling
operation. Optional tagged synchronization callbacks retain the old lock-pair API
and reject incomplete pairs. No unlocked memory ownership change or prefix-clear
optimization was present in the frozen baseline. A separate default-off
prefix-clearing candidate is described below; it is not yet qualified for adoption.

The standalone adapter adds lock wait/hold histograms, I2S read/push timing,
ISR-safe DMA-completion and receive-queue-overflow counters, accepted-sample/cache/
queue state, heap checkpoints and allocator-reported boot minima. `perf dump`
requests a report from the app owner, outside the stream mutex and inference.
Short report pages avoid a second full diagnostics object on the device stack.
The build statically checks telemetry plus its largest reporting page against
4 KiB; it also emits compiler stack-usage files. The ESP-IDF owner stack high-water
API reports **bytes**, and the field is named accordingly.

The pinned I2S driver creates `dma_desc_num - 1` queue entries: three for this
example's four descriptors. Configuration telemetry includes the actual API's
total DMA bytes. Neither nominal storage nor a delivered-sample counter is proof
that capture never lost audio; overflow evidence stays separate.

An eight-entry bounded level queue transfers 200 ms sample-indexed RMS/noise
observations from capture to the app owner. Drops in this diagnostic queue are
reported separately from driver loss. It enables acoustic alignment against the
actual accepted-sample clock; no serial output occurs in capture or the ISR.
The app also records per-inference decoder use, timing and receipt identity and
SHA-256 identities of the loaded language/speaker blobs. Speech identity remains
pinned by the unchanged model header/runtime. No new model is used for lock tests.

## Host evidence completed

- Existing streaming tests pass under address/undefined sanitizers with metrics
  disabled and enabled. Added tests cover tagged lock-pair validation, exact byte
  attribution, small/full diagnostic pages, histogram edges/scales/saturation and
  cleared cache contents.
- The instrumented streaming tests pass ThreadSanitizer. Positive/negative memcpy
  controls confirm that the sanitizer observes copy races.
- Twelve deterministic traces exercise both cadence modes through normal speech,
  maximum-length continuation, queue pressure, speculative promotion/invalidation,
  cancellation, feature-disabled short session end and ring overwrite.
- Compared against a frozen `9a0f14e` component: **24 comparisons** (12 disabled,
  12 enabled) have identical JSON work traces and byte-for-byte identical PCM and
  cached frontend payloads. Private manifests include SHA-256 and payload lengths.
  These execute the real scheduler/frontend, not neural inference or an LM.
- Telemetry parser tests reject malformed histogram mass, duplicate/missing pages,
  byte-attribution inconsistency and excess reporting storage, and retain incomplete
  reports. Percentiles are reported as bucket ranges, not invented exact samples.
- Required transcript, product storage/commands, viewer and bridge regressions pass.
  Viewer ran in the bundled Node runtime because `node` is absent from shell PATH.
  Bridge used its required loopback execution permission and did not open USB.

## Device/build state

The instrumented standalone baseline built with IDF 5.5.5, actual 64-byte L2 /
200 MHz PSRAM, legacy pacing, capture features and speaker support. The exclusive
20-second startup/quiet-room smoke completed: features and speakers were active;
zero watchdogs, panics, receive-queue overflows, phrase drops or feature overruns.
The selected x2f-only app was restored/readback-verified, ring reconnect and perf
logging remain off, and the port/lock were released. No new default was promoted.

Actual telemetry storage is 3,720 bytes plus its largest 376-byte reporting page:
4,096 bytes total. The owner had 11,360 bytes of minimum remaining stack. Capture
lock wait p99 fell in (1,10] us; maximum was 18 us in this short room sample.
This is not the speech/inference-load baseline and proves no contention benefit.
One cache retirement cleared 256,000 bytes in 2,566 us, while 38,656 bytes of feature
rows were written during the sample. That is a useful hypothesis for prefix
clearing, not an accepted optimization. Collect matched loaded workloads first.

The driver reported 8,192 DMA bytes and three queue slots. Loaded identities were
language model `7bae9ff540be…` (2,499,996 bytes) and speaker model `650f48bd23f8…`
(1,994,544 bytes). Speech remains pinned to the unchanged identity. Reports and
source/build hashes are preserved privately. The first flash request was rejected
by automatic review due to inferred competing board ownership; verified direct
user authorization, the training chat's idle/no-board commitment and an empty
port/lock preflight resolved that concern. The approved retry completed normally.

Reports are paged during a bounded begin/end time window while capture continues.
Each page is internally synchronized, but separate pages are not one atomic global
snapshot. Capture read/interval histograms use 64 us scaling; lock/memory/push bins
use 1 us scaling. Saturated histograms do not produce percentile estimates.
Boot heap minima include startup and are not per-inference peaks.

Private evidence: `private/stt-capture-lock/`, including original/enabled/disabled
trace payloads, equivalence report, sanitizer/regression logs, configuration and
build records. The initial smoke and the loaded runs below are complete;
the full ABBA comparison, overload controls and soak remain pending.

## Loaded baseline and candidate checkpoint

The unchanged instrumented image completed one acoustic run each of conv2–4.
All three have zero DMA overflow, phrase drops, watchdogs and panics. Conv4 has
two feature-cache overruns: this invalidates cache availability, not accepted PCM.
Source review confirms that inference computes uncached frontend rows or uses
the batch frontend when the retained prefix is insufficient. Preserve the
overruns as a cost/reliability outcome; do not describe them as microphone loss.
The first controller stopped on them and restored/readback-verified the selected
app. A separate unchanged conv4 repeat and long-input baseline are in progress.

| Baseline fixture | Capture wait p99 bin | Maximum wait | Maximum push hold | Cache bytes cleared | WER edits / words | Speaker correct / eligible |
|---|---|---|---|---|---|---|
| conv2 | (1,10] us | 3,969 us | 6,644 us | 10,240,000 | 91 / 499 | 24 / 38 |
| conv3 | (1,10] us | 2,574 us | 6,128 us | 13,312,000 | 116 / 466 | 23 / 48 |
| conv4 | (10,50] us | 3,470 us | 9,605 us | 9,984,000 | 80 / 470 | 19 / 33 |

These single acoustic runs are a baseline, not a measured optimization win.
Speaker results use per-capture best one-to-one identity assignment; raw
unknown/missing labels are 3/38, 13/48 and 8/33 respectively, with no missing
speaker-update events. No reference/mixed-phrase exclusions occurred in these
three runs. Conv3 has two unmatched annotated speech ends; retain that denominator
when interpreting latency summaries.

The original conv2 onset estimate was early and its first score was rejected.
A baseline-only waveform search, frozen as `sample-rms-v1`, requires independent
even/odd and temporal-half agreement, minimum correlation and a unique peak.
All three runs pass these checks. Sparse sample-indexed RMS is not a recording
of microphone PCM, and host receipt is not an exact display timestamp. Private
scores retain these limitations and the rejected fit. No old HardwareOne result
was relabeled with this method.

Capture wait is small in these workloads. There is currently no evidence to
justify clearing leases, asynchronous cleanup or segmenter buffer handoff.
The remaining baseline/stress checks can change that decision. Prefix clearing
is still a reasonable small experiment because partial caches currently cause
large unused regions to be cleared repeatedly. Acceptance gates were saved
before examining candidate device results; caption speedup is not assumed.

### Default-off prefix candidate: host evidence

`StreamConfig::clear_committed_features` and the example's experimental Kconfig
option remain false by default. When enabled, retirement clears every committed
feature row after the last reader releases its pin. Full startup clearing,
generation checks, PCM ownership and all existing synchronization stay intact.
The proof depends on feature publication being the sole writer and committing
a contiguous prefix under the mutex. Trimmed inference length is not a safe
clearing bound: a test covers 159 dirty rows with a 150-row inference prefix.

Tests inspect the entire reusable region and surrounding canaries after empty,
one-row, overrun fallback, repeated partial/maximum-length retirement, pinned
cancellation and stale-generation completion. Concurrent tests exercise both
cadences with the option enabled and disabled. Address/undefined sanitizers and
ThreadSanitizer pass. Twelve deterministic candidate traces and payloads are
byte-identical to the pre-instrumentation `9a0f14e` baseline, including real
frontend rows. This proves scheduler/frontend equivalence, not model accuracy.

The candidate P4 build passes and its frozen app is 787,056 bytes, 16 bytes
larger than the instrumented baseline. The saved sdkconfig differs only by
enabling the prefix option. No candidate device performance result is available
at this checkpoint. Matched runs, instrumentation controls and soak remain
required; no production default or board model changed.

### First candidate device screen

The unchanged conv4 repeat reproduced two feature overruns, with no driver loss,
drops, watchdogs or panics. Its WER is 74/470 and speaker correctness 22/34;
the first run was 80/470 and 19/33. Both pass the frozen alignment checks. This
within-baseline variation is a reason to run the bracketed comparison, not to
claim a candidate quality change from one microphone pass.

The candidate then completed conv2 and the long-input fixture with zero driver
loss, phrase drops, watchdogs or panics. Each controller restored and verified
the selected app, ring reconnect/perf logging off and lock released.

| Screen | Baseline | Prefix candidate |
|---|---|---|
| conv2 cache-clear bytes | 10,240,000 | 3,422,464 |
| conv2 total cache-clear time | 92.773 ms | 28.644 ms |
| conv2 maximum cache-clear time | 2,583 us | 1,453 us |
| conv2 capture wait p99 | (1,10] us | (1,10] us |
| conv2 maximum capture wait | 3,969 us | 1,173 us |
| conv2 WER edits / words | 91 / 499 | 78 / 499 |
| conv2 speaker correct / eligible | 24 / 38 | 23 / 38 |
| conv2 final publication median / p90 | 1.969 / 2.765 s | 1.942 / 2.768 s |
| long-input cache-clear bytes | 1,536,000 | 423,680 |
| long-input total cache-clear time | 14.029 ms | 3.489 ms |
| long-input feature overruns | 4 | 4 |

Conv2 clearing traffic falls 67% and total clearing time 69% in this screen;
the long-input reductions are 72% and 75%. These are small absolute costs over
the full recordings. Maximum-wait differences are descriptive; a one-run pair
cannot prove a general tail improvement. Conv2 timing alignment qualifies; there
is no material final-text latency gain in this pair. Lower WER and one fewer
correct speaker phrase do not establish either a quality win or noninferiority.
Proceed to the twelve-capture ABBA comparison before deciding on adoption.

Additional host checks exercise the null-lock lifecycle with prefix/features/
snapshots independently enabled/disabled and count C++ allocation calls. No such
calls occur; source inspection finds no explicit allocator calls in the touched
scheduler/segmenter/frontend. Six serialization orders of finish, cancel and
feature completion preserve a pinned reader and eventually clear both caches,
with the prefix option off/on. Updated address/undefined and thread sanitizer
runs pass. Both probes-on and probes-off prefix replays match the old baseline
byte for byte (24 comparisons). The probes-off capture branch has a host control
that requires probe rejection and Console cleanup, but a device probes-off run
is still pending. ABBA, secondary controls and the one-hour soak remain open.

### Primary ABBA complete: conv3 quality concern; bounded follow-up active

All twelve captures completed with zero DMA loss, phrase drops,
watchdog observations, panics or application errors. All twelve timing fits
qualify. The original source/config/model/harness identities remain fixed.

| Fixture | Baseline word errors | Candidate word errors | Baseline speaker correct | Candidate speaker correct | Baseline unknown labels | Candidate unknown labels |
|---|---|---|---|---|---|---|
| conv2 | 85, 77 / 499 words | 76, 77 / 499 | 15, 25 / 38 | 21, 17 / 38 | 14, 3 | 3, 13 |
| conv3 | 113, 116 / 466 words | 110, 107 / 466 | 33, 30 / 47 | 28, 26 / 47 | 9, 8 | 11, 11 |
| conv4 | 88, 80 / 470 words | 79, 78 / 470 | 11/34, 19/34 | 15/33, 15/35 | 15, 10 | 10, 13 |

Median total cache-clear time falls 71% on conv2, 73% on conv3 and 67% on conv4. These are
operation-cost reductions, not evidence of a comparable caption speedup. Conv2
quality spans overlap the controls; its closing baseline erases a simple claim
that the candidate necessarily improves WER.

Conv3 triggers the predefined repeatable-quality concern: both candidate speaker
scores fall below both controls, and both unknown counts exceed both controls.
This blocks adoption. The bounded four-run conv3
follow-up is running with the identical frozen capture source, images, playback and settings.
Keep that cohort separate from the original result; do not average away the
concern or change speaker thresholds. Hold the candidate if uncertainty remains.

Conv4 feature-overrun counts are 1/1 in controls and 2/0 in candidates. The
candidate maximum exceeds this immediate control range, so the report retains
that flag. Totals are equal and the earlier unchanged baseline twice recorded
two overruns. Do not call this new microphone loss, a proven repeatable increase
or an unconditional reliability pass. Compare all individual counts.

The primary controller restored/readback-verified the selected x2f-only app with
ring reconnect/perf logging off and released its lock before the follow-up took
exclusive ownership. No default was promoted.

The remaining controls/soak are prepared but have not run. At the first-cohort
checkpoint an isolated P4 harness for six real neural input/output/text hash
comparisons was prepared; its subsequent results are recorded below.
It reuses the card/model/LM adapters, generates synthetic PCM and
does not start the microphone or the production speaker worker. It will establish exact-input
neural equality, not acoustic quality, realtime behavior or production RAM fit.
A requirement audit also found that the previous streaming traces fixed pre-roll
to zero. A nonzero-pre-roll/ring-wrap case is added in the working tree and awaits
compilation after acoustic testing. Prior reported 12/24-trace evidence remains
retained and is not being relabeled as coverage of that new case.

### Execution-state isolation defect reproduced on P4

Source inspection found a process-global `hw1_dl_prepare_mode` and generation
set by recognition's resident-model preparation pass. SDK Conv/Add/LUT/Relu
operators consult this flag without checking the model or calling task; the
speaker task calls those same operators. `Model::run` provides no enclosing
cross-model exclusion. This is a concrete isolation hazard in the source, not
proof that it caused the acoustic speaker-score difference.

The isolated P4 harness includes a forced-exposure control: repeated A and
distinct B speaker inputs, normal B on the separate worker as a negative control,
then B on that worker while the parent holds the global preparation flag, followed
by exact normal-B recovery. It validates the installed speaker identity and its
embedded trunk fixture first. The corrected diagnostic completed with the
following independent outcomes; no SDK fix has been applied yet.

- Six real recognition input/output/text hash pairs match across clearing modes,
  cold construction and warm reuse, with actual cached features and verified
  speech weights. This closes the equal-input recognition check for these cases.
- The fixed speaker blob's embedded trunk fixture fails: its first reported
  expected value is 770, actual 717, tolerance approximately 1.00001. This is a
  failed baseline contract, not missing fixture data or a passed accuracy check.
  The cause may involve the model/export/runtime contract and is not established.
- Repeated A and different A/B inputs behave as required. B on the independent
  worker with the flag off matches normal B exactly. Holding the global flag
  from the parent changes B's embedding: cosine against normal B is -0.003156489.
  Restoring the flag recovers normal B byte for byte. Thus the shared-state
  mechanism is reproduced, independently of the fixture's numerical mismatch.
- This forced exposure does not establish live incidence or causation of the
  acoustic speaker-score differences. It does establish that an unrelated
  task's preparation state can alter normal speaker inference.

The diagnostic reports `complete_with_findings` and `all_checks_passed=false`.
It makes no production RAM-fit/accuracy claim. The selected app was restored and
verified, ring reconnect/perf logging off, and the lock released. No watchdog or
panic occurred in the completed diagnostic run.

The first diagnostic instead asserted on the fixture failure before other checks
could run. Its controller inherited a matcher that missed plain assertions,
allowing repeated reboots before being stopped. That failed log/source/image
remain preserved. First-failure detection now includes assertions, aborts and
stack faults, has an archived-log regression check, and finds no assertions in
the sixteen acoustic captures. The corrected diagnostic retains the failed
fixture explicitly, reloads a fresh model, and runs the independent checks; it
does not loosen the fixture tolerance or declare an overall pass.

Existing conv3 wall-time logs show no gross whole-trunk skipping anomaly.
This concerns model execution isolation, not the closed 128-byte L2 fault or a
new claim about a software writer.

### Bounded quality follow-up and remaining work

The frozen-source conv3 follow-up has controls 31/48 and 27/47 speaker correct,
versus candidates 28/47 and 27/47. Unknown counts are 12/10 in both arms. Word
errors are controls 113/113 versus candidates 111/109, each over 466 words.
All four alignment fits qualify and all runs have zero driver/phrase loss,
watchdogs, panics or application errors. Clearing time again falls 73%.
The original separated speaker pattern does not repeat, but that does not erase
the original concern or establish noninferiority. Hold adoption while execution
isolation and the independent speaker fixture contract remain unresolved.

The new pre-roll/ring-wrap replay passes: 28 exact trace/payload comparisons match
the old component with probes enabled/disabled. The original twelve traces stay
unchanged; segmenter boundary tests also pass. Remaining work includes isolating
prepared-argument ownership without changing weights/rules, required secondary
controls and continuous soak, final gate audit and the separate mixed-precision
RAM request. No production default or HardwareOne checkout has changed.

## Separately queued user request

The training chat's explicit user request for the block-14 RAM benchmark was
verified in that chat. It is queued for an isolated model/fixture benchmark at a
safe device window. Its model/kernel/runtime work must remain separate from the
fixed-model capture-lock A/B. No mixed model has been deployed, no device RAM
claim is made, and training/export files remain owned by that session.

### Model-local preparation: controlled P4 pass, fixture cause narrowed

Implemented `CONFIG_HW1_STT_MODEL_LOCAL_PREPARE`, default off. The runtime uses
an owner-only Model preparation method; only Conv prepares reusable arguments.
Other operators do no arithmetic during preparation, and normal inference ignores
another model's legacy global preparation flag. Prepared arguments are invalidated
before each pass and consumed once. Same-model reentry remains unsupported; all
SDK modules/callers must share the configuration because the opt-in adds a virtual
entry point. No weights, speaker rules or production defaults changed.

The initial fixed P4 diagnostic completed 83 real preparations of model A while
model B ran: B's embedding remained byte-identical to normal/recovery (cosine 1).
Six recognition pairs also matched input/output/text hashes across clearing modes
and the frozen pre-fix results. A second diagnostic retained those checks and
added a direct embedded-fixture matrix. Both runs completed without watchdogs or
panics and restored/readback-verified the selected app, reconnect/perf logging off,
with the board lock released. These are controlled mechanism tests, not proof of
historical acoustic causation or full accuracy qualification.

The direct speaker fixture gives identical output hashes in all four combinations
of convolution blocking disabled/24 KiB and single/multi-core execution. All fail:
9,386 of 9,600 values exceed the existing one-unit tolerance, maximum error 788,
sum absolute error 891,692. Thus those execution choices do not explain this
fixture discrepancy. The exact local export matches the installed speaker blob;
its trunk and embedded input/output are present. This bypasses microphone/frontend,
float pooling and clustering, narrowing the discrepancy to the trunk/export
numerical contract. It does not yet identify the offending operator.

A host reconstruction using saved ONNX/quantization JSON was attempted. Correctly
folding isolated BatchNormalization into depthwise Conv (as the exporter does)
reduces its discrepancy, but it still fails the embedded reference: maximum error
18, 4,531 values over tolerance. It is an unvalidated diagnostic, not an oracle for
per-layer correctness. Do not replace the embedded reference with it or loosen
tolerance. The next discriminating work is to reproduce the original exporter
execution/reference exactly or construct independently checked operator fixtures.

Actual runtime lifecycle tests now exercise both preparation settings, per-call
and resident models, diagnostics off/on under ASan/UBSan: all eight combinations
pass. Host fakes verify control flow/lifetime, not ESP-DL arithmetic. P4 DWARF
inspection shows unchanged object sizes (vendor Model 144 B, Module 40 B, Conv
108 B); equal sizes do not prove vtable ABI compatibility or peak RAM fit.
Normalized patch context formatting round-trips against the pinned pristine SDK
with unchanged patched source-tree digest.

Private evidence: `exact-local-status.json`, `exact-fixture-matrix-status.json`,
`speaker-fixture-host-inventory.json`, `speaker-host-reconstruction/result.json`,
`runtime-both-prepare-host.log` and `module-local-object-sizes.json` under
`private/stt-capture-lock/`. Overall status remains complete-with-findings, not a
passed speaker fixture. Secondary controls, continuous soak and the final adoption
audit remain incomplete; see the updated execution sequence in Section 13 of
`STT_CAPTURE_LOCK_PLAN.md`. The separate mixed-precision fixture/RAM request stays
queued and has no device result.

### Speaker fixture localized to coarse residual ReLU tables — 4 November

A diagnostic trace sampled 181 actual execution-plan outputs. The first Conv's
complete output SHA matches an independent int64 convolution using the existing
ESPDL input, blocked weights, biases, exponents, padding/stride and fused ReLU.
Early sampled stages differ by at most two units; the first large sampled jump
is stage 15, `/layer1/layer1.0/relu_1/Relu`, at 126 units. Other host reconstruction
points remain unvalidated; this is localization, not a whole-network pass.

The SDK deserializes a Relu node carrying a `lut` attribute as a lookup module.
The installed model has 16 such int16 residual ReLU nodes, using two unique
257-entry tables with step 256. Exhaustively applying the pinned P4 nearest-even
index rule to all 65,536 int16 inputs finds maximum deviation 128 units from exact
ReLU in every case. The table grid itself is correct; precision is lost between
its grid points. `tools/device_tests/stream/audit_relu_tables.py` reproduces this
from an existing trunk without board access. This audit characterizes tables;
it does not independently qualify the P4 SIMD kernel.

A causal P4 comparison loads the same weights/input with the SDK's existing
direct ReLU operator in place of those tables, only inside the diagnostic.

| Embedded fixture result | Serialized ReLU tables | Direct ReLU diagnostic |
|---|---:|---:|
| Values over the unchanged one-unit tolerance | 9,386 / 9,600 | 2,501 / 9,600 |
| Maximum absolute error | 788 | 17 |
| Sum absolute error | 891,692 | 10,591 |
| Execution modes with identical output within this arm | 4 / 4 | 4 / 4 |

Each arm covers blocking off/24 KiB and single/multi-core execution. Total absolute
error falls 98.8%, but the fixture still fails. This identifies a dominant cause;
it neither explains every remaining numerical difference nor establishes live
speaker accuracy. Do not loosen tolerance, promote direct ReLU, or change speaker
rules based on this fixture alone. The factory is restored before the normal
speaker self-test, isolation probe and six recognition pairs; their unchanged
results verify that the diagnostic switch did not persist into those checks.

The first trace prototype dereferenced optional null Module::name in strcmp and
faulted before comparisons. The controller detected it and restored/readback-
verified the selected app. The corrected trace uses the exact topological order
used to build the model's plan. Failed image/log and SHA-verified source remain
private; no watchdog was observed. Corrected trace and causal runs both completed
without watchdogs/panics and restored/readback-verified the selected app, ring
reconnect/logging off, lock released. This diagnostic fault is not evidence of a
new cache-line or model-execution fault.

Private evidence under `private/stt-capture-lock/`: `exact-layer-trace-status.json`
(failed), `exact-layer-trace-v2-status.json`, `exact-relu-probe-status.json`,
`speaker-first-conv-scalar.json`, `speaker-trace-localization.json` and
`speaker-relu-table-audit-reviewed-tool.json`. The last image also archives its
source files. No production default, model file, training file or HardwareOne
checkout changed.

The diagnostic investigation is now bounded: retain the residual failed fixture
as an adoption hold, and finish the original capture-lock performance/reliability
controls using unchanged serialized speaker math in both arms. Six matched
module-local-preparation profiles are building; exact ReLU is excluded from those
images. Any future exact-ReLU accuracy experiment is a separate comparison.

### New SDK cohort: conv2 bracket complete, wider runs active — 4 November

The six matched control images built successfully with model-local preparation,
64-byte L2 and 200 MHz PSRAM. Original serialized speaker math is retained; the
diagnostic exact-ReLU option is absent. Source/SDK hashes match across clearing
arms and the generated baseline/prefix sdkconfigs differ only in the clearing
flag. The frozen build source is 4e5bf32; later diagnostic/docs commits do not
change the control images.

The first fresh ABBA bracket (conv2) is complete:

| Run | Clearing | Word edits / words | Speaker correct / eligible | Unknown |
|---|---|---:|---:|---:|
| B0 | Full | 78 / 499 | 29 / 38 | 1 |
| P1 | Prefix | 78 / 499 | 28 / 38 | 2 |
| P2 | Prefix | 75 / 499 | 28 / 38 | 1 |
| B3 | Full | 81 / 499 | 28 / 38 | 2 |

All four waveform alignment fits qualify, with zero observed DMA loss, phrase
drops, watchdogs, panics or application errors. Median per-recording clearing time
falls 88.282→27.430 ms (68.9%); no separated quality/latency gate is raised in this
bracket. That is not proof of noninferiority or a caption-speed gain. Keep this
SDK cohort separate from the original twelve runs; historical acoustic scores
cannot establish that the isolation defect caused their variation.

Evidence: `primary-local-score-4.json`, `primary-local-status.json`,
`local-controls-verified.json` and raw captures under private/stt-capture-lock/.
The same controller is now running conv3–4. The board remains reserved and on a
test app; this cohort's restoration is still pending. Secondary controls and the
continuous soak remain unrun. The baseline numerical fixture still fails, so no
production adoption or overall numerical qualification is claimed.

### Fresh model-local SDK cohort complete: conv4 quality hold — 4 November

All twelve new ABBA captures completed with the matched module-local SDK images
and original serialized speaker math. All sample-RMS fits qualify; zero observed
DMA loss, phrase drops, watchdogs, panics or application errors occurred. The
selected app was restored/readback-verified and the board lock released afterward.

| Fixture | Run | Word edits / words | Speaker correct / eligible | Unknown |
|---|---|---:|---:|---:|
| conv2 | B0 | 78/499 | 29/38 | 1 |
| conv2 | P1 | 78/499 | 28/38 | 2 |
| conv2 | P2 | 75/499 | 28/38 | 1 |
| conv2 | B3 | 81/499 | 28/38 | 2 |
| conv3 | B0 | 123/466 | 41/47 | 3 |
| conv3 | P1 | 115/466 | 43/47 | 1 |
| conv3 | P2 | 112/466 | 45/48 | 1 |
| conv3 | B3 | 107/466 | 43/47 | 2 |
| conv4 | B0 | 81/470 | 30/34 | 4 |
| conv4 | P1 | 70/470 | 23/32 | 8 |
| conv4 | P2 | 82/470 | 25/33 | 7 |
| conv4 | B3 | 81/470 | 33/35 | 2 |

Median per-recording clearing time falls 68.9%, 73.7% and 67.3% on conv2, conv3 and
conv4. No caption speedup or formal noninferiority is established. Conv2–3 raise
no separated quality/latency flags. Conv4 does: both prefix speaker rates are below
both controls, and both prefix unknown counts are worse. This is an adoption hold,
not a result to average away with WER gains or other fixtures.

Conv4 B0 also has a genuine 307 ms backward host-wall-clock transition, including
recognized receive events. The approved helper's logger uses time.time() in its
single receive loop. Publication/label/draft latency remains withheld for that
original capture. Its waveform/sample-clock speaker identity and WER remain
available. No timestamp repair, alignment tuning or tolerance change was applied.

A new logger adapter preserves the approved serial transport, scrubbing, sends
and deadlines, while timestamping its writer with a wall anchor plus monotonic
elapsed time. It records an exclusive clock sidecar and source identity. Host
tests cover the 307 ms backward-wall case, payload preservation, existing sidecar
protection, incompatible transport and a regressing monotonic source. They pass;
this does not by itself prove device timing. Existing capture/scoring rules stay
unchanged. This adapter applies only to subsequent captures, not the completed
cohort. See tools/device_tests/stream/console_clock.py and tests/test_console_clock.py.

The plan's ONE bounded conv4 ABBA follow-up is now active with the exact same
images/models/configuration and scoring, using the stable receive clock in all
four runs. Retain the primary flag and clock-invalid record even if it passes.
Evidence: primary-local-score-12.json, primary-local-status.json and
conv4-baseline-host-clock-audit.json under private/stt-capture-lock/.
The follow-up owns the board lock and will restore the selected app in finally.
Secondary controls, continuous soak and final audit remain incomplete. A separate
optional prepared-block refusal diagnostic is source-only/unbuilt; do not count
it as a passed test. Production defaults and training-agent work remain unchanged.

### Bounded conv4 follow-up complete; secondary controls active — 4 November

The one permitted new-SDK conv4 follow-up completed using unchanged frozen images,
models, decoder, audio and scoring. Its only measurement change is the recorded
monotonic receive-log clock. All four sample fits and publication clocks qualify;
zero observed DMA loss, phrase drops, watchdogs, panics or application errors
occurred. The selected app was restored/readback-verified, reconnect/logging off,
and the lock released before the next controller acquired it.

| Run | Word edits / words | Speaker correct / eligible | Unknown | Final publication median / p90 (s) |
|---|---:|---:|---:|---:|
| B0 | 77/470 | 32/34 | 2 | 2.367 / 3.265 |
| P1 | 78/470 | 30/34 | 4 | 2.370 / 3.315 |
| P2 | 72/470 | 32/34 | 2 | 2.382 / 3.307 |
| B3 | 74/470 | 26/33 | 7 | 2.413 / 3.410 |

The original separated speaker/unknown pattern does not repeat: this bracket has
no separated quality/latency flags. Clearing time again falls 64.8%. Neither that
result nor the broader control variation erases the primary conv4 flag, establishes
noninferiority, or demonstrates a caption-speed gain. Adoption remains held; no
more conv4 follow-up brackets are planned. The clock-invalid original capture
remains in the evidence with publication timing withheld.

Evidence: followup-conv4-local-score-4-final.json, followup-conv4-local-status.json
and per-capture clock sidecars under private/stt-capture-lock/. The twelve secondary
controls are now active (probes on/off, x2f clearing control/candidate, speakers
on/off). They retain original serialized speaker math and the stable receive
clock. The secondary controller currently owns the board lock; its restoration
is pending. Probes-off has no DMA-loss or sample-aligned timing claim, and
speaker-off is not an accuracy arm. Continuous soak, optional prepare-refusal
hardware check, final audit and the separate model/RAM benchmark remain incomplete.

### Secondary x2f bracket: label-delay gate raised — 4 November

The matched x2f full/prefix/prefix/full bracket is complete with unchanged models,
SDK isolation setting and original speaker arithmetic. All four host clocks and
sample fits qualify. WER edits are 82/72/76/78 over 499 words; speaker correctness
is 28/38, 28/38, 29/38 and 30/39, with one unknown/missing label in each run.
No DMA overflow, phrase drop, watchdog or panic was observed in these four runs.

| Run | Final publication median / p90 (s) | Label-after-caption median / p90 (s) |
|---|---:|---:|
| B0 | 1.909 / 2.731 | 1.164 / 2.020 |
| P1 | 1.938 / 2.789 | 1.120 / 2.231 |
| P2 | 1.947 / 2.642 | 1.162 / 2.443 |
| B3 | 1.933 / 2.683 | 1.166 / 1.817 |

The predefined comparison flags the separated label-after-caption p90 increase:
both candidates exceed both controls by more than 5% and 100 ms. This acoustic
bracket is evidence of a concern, not proof that clearing causes it. It reinforces
the adoption hold. No additional follow-up is scheduled to seek a favorable
sample. There is no separated WER/speaker-correctness flag or final-caption
latency flag. Median total clearing cost falls 61.1% (89.203 to 34.737 ms per
recording); this does not establish faster captions.

Evidence: private/stt-capture-lock/secondary-local-score-8.json and matching
controller run directories. The instrumentation bracket is also complete; the
speaker-load bracket remains active. Board restoration is pending until the
existing controller finishes. Overall speaker numerical qualification still
fails, and the primary conv4 quality hold remains unchanged.

### Contract coverage audit checkpoint — 4 November

This maps the original plan to inspected production-code tests and retained
execution evidence. It is not an overall pass: device quality/latency holds,
preparation-refusal hardware execution, final reporting and the separate model
benchmark remain outstanding.

| Plan cases | Actual coverage and scope |
|---|---|
| C01–C05 | `committed_prefix_clearing` tests empty/one-row/repeated partial and full-capacity prefixes, overrun retirement, complete reusable-region zeroing and guards. Dirty high-water 159 rows remains cleared when inference uses only 150. Full 160,000-sample production capacity is additionally exercised by replay. |
| C06–C10 | Same test pins a reader through repeated cancel, compares retained bytes, releases the last pin, and attempts late old-generation feature completion. `queue_overflow_and_stale_features` checks stale publication and explicit fallback. |
| C11–C17 | Cleanup leases, chunked/unlocked copies and asynchronous housekeeping belong to conditional Milestones C/D, which are not implemented. Their new-state tests are not applicable to the retained synchronous Milestone B. Existing finish/cancel/pin semantics remain covered; no claim of tested lease behavior is made. |
| C18 | `no_hot_allocations_and_null_lock` runs both clearing modes with features and snapshot independently enabled/disabled. |
| C19–C20 | Concurrent producer/feature/consumer exercise validates exact cached rows, sequence accounting and both cadences. Chunked snapshot preparation was not introduced, so chunk-revalidation tests are conditional rather than claimed passed. Existing phrase close/final preemption is covered by `features_and_draft_preemption`. Random concurrent scheduling is not an exhaustive interleaving proof. |
| C21–C25 | `exact_promotion_and_resumed_speech`, `hard_cut_finish_and_cancel`, replay scenarios 0/2/3/6 and segmenter boundary tests cover speculative invalidation/promotion, hard continuation, pre-roll/ring rotation and cancellation. |
| C26–C30 | Replay uses 29/31/37/71/79/127/160/1,024-sample partitions, a 160-sample final span, 160,000-sample capacity, full queues and feature-ring overrun. Exact original-versus-prefix payload comparison complements explicit drop/fallback assertions. |
| C31–C35 | Null-lock allocation watcher, features/snapshot combinations, both cadences, zero/guard assertions, and actual frontend row comparisons cover retained contracts. Heap allocation watcher applies to the tested scheduler thread; it is not whole-firmware allocation instrumentation. |
| C36 | All six mutex serialization orders of finish/cancel/late feature completion are tested with a pinned reader, for both clearing modes; retained bytes and terminal drainage are asserted. |

Execution evidence: `host-metrics-asan.log`, `host-off-asan.log`,
`host-metrics-tsan.log`, `prefix-tsan.log` and `host-tsan-controls.log` under
private/stt-capture-lock/. The TSan memcpy positive control detects the unlocked
race with interceptor accesses enabled; the locked negative control stays clean.
`preroll-host-status.json` records four exit-zero commands;
`preroll-equivalence.json` records 28 equal replay comparisons and unchanged
original twelve traces. The segmenter log reports 720 chunk comparisons and
1,076 reference segments with exact source-sample conservation.

Host SDK/runtime lifetime coverage is retained in runtime-both-prepare-host.log
across preparation flag, resident/per-call execution and diagnostics combinations.
Those SDK fakes establish control flow/lifetime, not P4 arithmetic. Actual P4
recognition equality and independent-model isolation have separate diagnostic
artifacts; the failed speaker numerical fixture stays failed. The optional
allocation-refusal device probe has not run and must not be counted as coverage
of actual device failure recovery yet.

### All twelve secondary controls completed — 4 November

The controller terminated successfully with all twelve captures scored, selected
app restoration/readback verified, reconnect/perf logging off and lock released.
A subsequent separately locked preparation-refusal diagnostic is now running;
that later controller's restoration remains pending.

The probe on/off/off/on bracket has WER edits 81/86/71/90 over 499 words and one
unknown/missing label in each capture. This small acoustic sample cannot establish
zero instrumentation overhead or an accuracy benefit. Probe-off DMA loss and
sample-aligned publication/identity metrics remain unmeasured. Worker duration
buckets are descriptive; their inputs are not controlled equal-input kernel pairs.

The speaker on/off/off/on bracket is:

| Run | Word edits / words | Speaker correct / eligible | Unknown or missing | Final publication median / p90 (s) | Capture wait max (ms) |
|---|---:|---:|---:|---:|---:|
| On 0 | 78/499 | 29/38 | 1 | 1.969 / 2.664 | 2.631 |
| Off 1 | 81/499 | Not applicable | 38 intentional | 1.931 / 2.734 | 4.983 |
| Off 2 | 77/499 | Not applicable | 38 intentional | 1.896 / 2.792 | 2.290 |
| On 3 | 74/499 | 28/38 | 2 | 1.945 / 2.699 | 1.309 |

All four sample fits/publication clocks qualify. Capture-wait p99 stays in the
(1,10] microsecond histogram bucket throughout. Disabling the worker does not
establish better capture contention or final-caption p90. This is a load control,
not a speaker-algorithm recommendation or exact paired inference benchmark.
The 4.983 ms maximum is retained; the earlier below-4-ms statement describes its
earlier cohort and is not a bound on all subsequent runs.

Across all twelve secondary captures there were no observed phrase drops,
watchdogs or panics; instrumented captures report zero DMA overflow. The two
probe-off captures have no DMA-loss claim. The x2f label-delay flag above remains,
as do the primary conv4 quality hold and independent numerical-fixture failure.
The secondary controls do not authorize promotion. A continuous soak and final
review remain outstanding; so does the separate block-14 device fixture/RAM test.
Evidence: secondary-local-score-12-final.json, secondary-local-status.json and
per-run private captures/clock sidecars under private/stt-capture-lock/.

### P4 preparation-refusal recovery passed; diagnostic soak active — 4 November

The optional isolated probe built at 699,472 bytes and completed on the P4.
It refused 104 optional prepared-storage requests at a 528-byte threshold while
the other model worker was blocked. Input/output activation snapshots were
unchanged by preparation; ordinary fallback and restored normal preparation
produced the exact same output hash as the unchanged four-mode fixture matrix.
This is allocator-policy refusal, not physical heap exhaustion, a warmed-block
growth-failure test, or production RAM-fit qualification.

The independent worker also remained unchanged during 82 real preparations of
another model. Six recognition input/output/text pairs passed and matched the
pre-fix control hashes. There were no observed watchdogs or panics. The original
speaker embedded fixture still fails; therefore the controller explicitly reports
complete_with_findings and all_checks_passed=false. It restored/readback-verified
the selected app, reconnect/logging off, and released its lock.

Evidence: exact-prepare-refusal-status.json, exact-prepare-refusal-ready.json,
private image/source snapshots and serial logs under private/stt-capture-lock/.
The diagnostic remains optional and off by default.

The planned continuous mixed-length reliability sequence has now started under
its own exclusive controller, following that verified restoration. It uses the
frozen model-local prefix image on one boot, with five cycles of conv2/3/4/long22.
Its prerequisite records retain both the numerical-fixture failure and acoustic
adoption holds. The question is sustained sample continuity, session drainage,
reset/reload/fault behavior and observed memory trends. It is diagnostic reliability
evidence, not a qualified-finalist or accuracy claim. At least one continuous hour
is required; any watchdog triggers the unchanged sequence from boot once more.
The soak is running, not passed, and its final selected-app restoration is pending.
