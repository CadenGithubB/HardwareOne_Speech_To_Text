# STT capture-lock work: actual progress and evidence

3 November 2026. Goal active. This is an implementation record, not a claim that
capture contention has been reduced or that device qualification is complete.
The controlling requirements remain in `STT_CAPTURE_LOCK_PLAN.md`.

## Instrumentation milestone

Implemented optional `CONFIG_CAPTIONS_STREAM_METRICS` (default off). The portable
engine counts/times its existing copies and clearing, attributed to the calling
operation. Optional tagged synchronization callbacks retain the old lock-pair API
and reject incomplete pairs. No unlocked memory ownership change or prefix-clear
optimization has been applied.

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
build records. Next action: collect the unchanged speech/inference-load baseline and freeze
its acceptance gates before selecting an optimization. The initial smoke is
complete; the full ABBA comparison, overload controls and soak remain pending.

## Separately queued user request

The training chat's explicit user request for the block-14 RAM benchmark was
verified in that chat. It is queued for an isolated model/fixture benchmark at a
safe device window. Its model/kernel/runtime work must remain separate from the
fixed-model capture-lock A/B. No mixed model has been deployed, no device RAM
claim is made, and training/export files remain owned by that session.
