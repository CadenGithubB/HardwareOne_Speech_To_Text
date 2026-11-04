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

## Separately queued user request

The training chat's explicit user request for the block-14 RAM benchmark was
verified in that chat. It is queued for an isolated model/fixture benchmark at a
safe device window. Its model/kernel/runtime work must remain separate from the
fixed-model capture-lock A/B. No mixed model has been deployed, no device RAM
claim is made, and training/export files remain owned by that session.
