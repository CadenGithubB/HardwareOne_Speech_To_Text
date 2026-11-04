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

The remaining controls/soak are prepared but have not run. An isolated P4 harness
for six real neural input/output/text hash comparisons is also prepared but not
built or run. It reuses the card/model/LM adapters, generates synthetic PCM and
does not start the microphone or the production speaker worker. It will establish exact-input
neural equality, not acoustic quality, realtime behavior or production RAM fit.
A requirement audit also found that the previous streaming traces fixed pre-roll
to zero. A nonzero-pre-roll/ring-wrap case is added in the working tree and awaits
compilation after acoustic testing. Prior reported 12/24-trace evidence remains
retained and is not being relabeled as coverage of that new case.

### Separate execution-state hazard under investigation

Source inspection found a process-global `hw1_dl_prepare_mode` and generation
set by recognition's resident-model preparation pass. SDK Conv/Add/LUT/Relu
operators consult this flag without checking the model or calling task; the
speaker task calls those same operators. `Model::run` provides no enclosing
cross-model exclusion. This is a concrete isolation hazard in the source, not
proof that it caused the acoustic speaker-score difference.

The isolated P4 harness now includes a forced-exposure control: repeated A and
distinct B speaker inputs, normal B on the separate worker as a negative control,
then B on that worker while the parent holds the global preparation flag, followed
by exact normal-B recovery. It validates the installed speaker identity and its
embedded trunk fixture first. This probe is unbuilt/unrun. No SDK fix has been
applied, and a forced reproduction alone will not establish live incidence.
Existing conv3 wall-time logs show no gross whole-trunk skipping anomaly.
This concerns model execution isolation, not the closed 128-byte L2 fault or a
new claim about a software writer.

## Separately queued user request

The training chat's explicit user request for the block-14 RAM benchmark was
verified in that chat. It is queued for an isolated model/fixture benchmark at a
safe device window. Its model/kernel/runtime work must remain separate from the
fixed-model capture-lock A/B. No mixed model has been deployed, no device RAM
claim is made, and training/export files remain owned by that session.
