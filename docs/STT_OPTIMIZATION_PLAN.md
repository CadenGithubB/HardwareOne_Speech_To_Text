# STT performance and accuracy improvement plan

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
- Next: a bounded allocated-PSRAM store-watchpoint positive control. RTC tests
  do not establish that memory path; do not calibrate by writing the heap header.
- Both fixtures removed and original full app slot restored/verified. Final
  baseline: 5,689,344 B LittleFS free, logging inactive, PDM preferred, model
  header/footer unchanged. All runs silent; future playback 50%.

See [AB_TEST_RESULTS.md](AB_TEST_RESULTS.md#both-core-synthetic-recovery-and-heap-field-watch)
for per-trial numbers, timer-source correction, source patches and limitations.
HardwareOne diagnostic sources remain local on codex/stt-ab-heap-watch at
e1044e86. The existing 1.1 GiB build is retained for the next diagnostic;
selected matching recovery/debug/source inputs are private. No automatic
production integration or HardwareOne branch push has occurred.

Original plan: 31 October 2026. Subsequent experiments, prepared candidates, rejections and remaining gates are recorded in [AB_TEST_RESULTS.md](AB_TEST_RESULTS.md) and the checkpoints below. The proposal sections preserve the starting rationale; they do not describe the current implementation status.

## Evidence and scope

This plan follows the [live glasses profile](GLASSES_LIVE_PROFILE.md) and
[numeric measurements](performance-glasses-live.json). Open
[the interactive graphs](stt-performance-graphs.html) locally in a browser after
pulling this repository. The graphs load a pinned D3 library from a CDN, so an
internet connection is required for rendering.

The measured device was a P4X-EYE running integrated HardwareOne firmware 0.99.99,
using the glasses microphone and native G2 Conversate. The useful window covered
48.27 seconds, six final phrases and 21 RAM samples. Extensive debugging was
enabled; cold startup was not captured. The standalone app in this repository
has different scheduling and feature-caching behavior. These observations guide
experiments in the integrated application; they do not establish identical
performance in the standalone app.

## Source parity comes first

[Direct source comparison](STANDALONE_PARITY.md) confirms that HardwareOne has
changes not present in the standalone. The [source port](STANDALONE_PORT.md) now reconciles those portable changes and
passes host/build checks. Fresh device qualification is still required before
treating integrated timings as a standalone baseline. The intended
workflow is standalone development/qualification followed by HardwareOne adaptation.

## Main conclusion

Neural inference and repeated preview work offer the strongest speed opportunities.
RAM headroom is tight, but the measurements do not establish a memory-bandwidth
bottleneck. Recognition accuracy cannot be judged without reference transcripts.

| Priority | Opportunity | Evidence | First experiment |
| --- | --- | --- | --- |
| 1 | Avoid unnecessary preview passes | 21 completed model passes for six final phrases; 15 successful previews | Compare current preview cadence against fewer previews on identical audio, retaining speculative final processing |
| 2 | Optimize large pointwise layers | Inference is 91.5% of final-worker time; 512-to-512 pointwise layers are about 57.1% of accumulated model-stage wall time | Measure cache and memory behavior of those layers, then compare kernel/data-layout changes |
| 3 | Isolate speaker identification | Four observed speaker-label delays span 1.117–6.960 seconds | Compare labels enabled/disabled; separate queue wait, execution and preemption |
| 4 | Attribute live RAM before resizing | Sampled free PSRAM reaches 2.64 MiB; about 5.84 MiB of used heap is unattributed by the allocation reference | Track live model, arena, decoder, speaker and queue allocations |
| 5 | Establish an accuracy corpus | No reference transcript or WER measurement exists for this run | Test fixed speech with names, technical words, quiet endings, noise and silence |
| 6 | Quantify debugging cost and bound file logging | Extensive debugging was enabled; an uncapped system log previously filled internal storage | Compare lean logging against debug logging; qualify a capped writer with reserved free space |

## 1. Reduce preview work without losing early final processing

Try fewer draft updates while speech continues, and a fresh update near a pause.
Keep early/speculative final processing: four observed finals adopted work that
had already started before the segment closed. Removing that mechanism could
make final captions slower even if total compute falls.

Measure completed and canceled model passes, accumulated stage time, first useful
draft, draft update intervals, post-close final latency, audio drops and peak RAM.
Accept a policy only if it reduces work without unacceptable preview staleness,
final latency or recognition regressions. The observed count does not imply
that every extra pass can be removed.

## 2. Focus compute optimization on the pointwise kernels

Mean final-worker duration was 1,328.0 ms, including 1,214.8 ms of acoustic
inference. Within accumulated stage measurements, 512-to-512 pointwise layers
accounted for about 57.1%, other pointwise layers 14.1%, depthwise layers 24.2%,
and Add/ReLU 4.6%.

Inspect kernel implementation, cache reuse, data layout and blocking before
changing memory placement. Measure instruction/data cache behavior and PSRAM
traffic where the chip and tooling support it. Check largest contiguous internal
blocks before increasing internal workspaces or cache-related allocations.
Preserve bit-exact logits for changes that should leave the arithmetic unchanged;
otherwise compare logits, decoded text and word errors explicitly.

Illustrative sensitivity calculation: halving acoustic-inference time, with all
other final-worker work unchanged, would reduce the mean from 1.328 s to about
0.721 s, a 45.7% reduction. This is not an achievable-speedup prediction. Model-stage
shares include previews, partial canceled work and scheduling delays; they are
not exclusive CPU measurements or exact final-only shares.

## 3. Measure speaker work independently

Observed speaker wall durations ranged from 0.921 to 6.938 s. Background work can
be preempted, so a seven-second wall duration does not prove seven seconds of CPU
execution or a caption slowdown. Two final speaker completions were not captured.

Compare identical audio with speaker labels enabled and disabled. Record queue
wait, execution/preemption, label readiness, caption latency and live model/arena
memory. If repeated identity computation dominates, evaluate less frequent
identification or reusing a confident identity across nearby segments. Validate
speaker-change accuracy before accepting that tradeoff.

## 4. Improve RAM attribution, then reuse or right-size allocations

Reported PSRAM heap capacity was 31.33 MiB; sampled free heap fell from about
3.18 MiB to 2.64 MiB. The cached speech model reference is 19.18 MiB, the LM blob
1.53 MiB, five PCM buffers together 1.53 MiB, and the feature pool about 0.62 MiB.
About 5.84 MiB of used heap remains outside those references, including runtime
arenas, speaker work, metadata, decoder workspaces and other application state.

Record per-phase allocation lifetimes, free bytes and largest contiguous blocks.
Look for reusable workspaces, redundant buffers and unnecessarily retained
allocations. Do not shorten audio capacity blindly: captured phrases here reached
5.66 seconds, and this small sample does not establish the longest supported use.
Model compression or replacement would require a separate accuracy qualification.

Two-second heap samples miss transient peaks. Boot-wide minima include earlier
activity and cannot be attributed to these six phrases. File size is not runtime
RAM cost, particularly for the speaker model.

## 5. Make accuracy measurable

Build a repeatable, consented reference set covering ordinary conversation,
names and technical vocabulary, quiet word endings, background noise and silence.
Keep reference transcripts and recordings in ignored private storage. Report
word error rate, errors in selected terms, false captions during silence and
speaker-change errors separately from display formatting.

Use that set to evaluate LM/custom vocabulary changes, endpointing and trimming.
Preserve raw recognized text so formatting cannot conceal recognition errors.
The present uncontrolled speech provides no evidence that any such change would
improve accuracy.

## 6. Separate diagnostic overhead from production behavior

Repeat a fixed workload with minimal logging and with the current debug settings.
Keep other configuration and input constant. Measure worker/final latency,
preview counts, packet counters and RAM under both conditions. No debug settings
were disabled merely to prepare this plan.

For the system-file logger, add a retention/size cap, a reserved-free-space
threshold, checked write/flush results and a visible stopped/full state. Use
existing overflow handling where appropriate. Test low-space, failed-write,
failed-flush and SD-removal cases while protecting settings storage. Avoid
prolonged capture of routine polling replies and verbose command/auth traces.
See the [storage incident and settings validation](SYSTEM_LOG_STORAGE_INCIDENT.md).

## Lower-priority targets and measurement gaps

Feature extraction averaged 24.5 ms and already reused 94.1% of final feature
rows. LM decode averaged 55.3 ms, and load/setup 7.5 ms. These are smaller speed
targets than inference. Bluetooth reported no new packet losses, duplicates,
LC3 decode failures, PLC frames or overruns in its bracketing interval.

Weights are cached in PSRAM. A logical 96-byte SD model-header validation remains
per call, but physical SD transactions and its isolated time are unknown. Physical
SPI-flash/cache reads, PSRAM bandwidth and bus contention were not instrumented.
Do not attribute all setup time to storage or label flash reads a bottleneck yet.

Caption delay here starts when the audio segment closes; it excludes endpointing
and screen drawing. It overlaps worker processing and must not be added to worker
time. Protocol ACKs do not prove the display has finished drawing.

## Recommended execution order

1. Establish repeatable audio and a lean-logging control; retain a correctness baseline.
2. Compare preview cadence while preserving early final processing.
3. Isolate speaker computation and its memory footprint.
4. Profile and optimize the large pointwise kernels and their memory traffic.
5. Use allocation attribution to guide RAM changes and the accuracy corpus to
   qualify any recognition-policy changes.

Keep one change per comparison and report distributions over repeated runs,
not a speedup inferred by comparing these short phrases against older, longer
phrases. No firmware optimization, model change or new device test was performed
in writing this plan.

## October 31 A/B results

[AB_TEST_RESULTS.md](AB_TEST_RESULTS.md) records the logging control, stage
profile, five-run comparisons of both prepared candidates, conversation speaker
scores, technical recordings and fault history. Neither candidate met the
no-regression win criterion. Speaker-off freed sampled PSRAM but removed labels;
the preview candidate delayed first preview. The 512→512 pointwise profile did
not measure cache misses or PSRAM traffic. The original app was restored and
verified. The user reports ordinary transcription is more stable than this
instrumented workload, which cannot estimate ordinary-use crash frequency.

The LM sweep is blocked by absent production controls or replay; bit-exact kernel
trials and complete memory attribution remain future work. No optimization was
integrated from these measurements.

The subsequent [standalone audio experiment](SPEAKER_AUDIO_EXPERIMENT.md) found
close native/Python frontend parity on audited speech. Two fixed energy-window
selectors did not qualify on development data; a new disjoint final speaker
partition remains unscored. The selector is opt-in and no production caller
uses it. Quantized-path parity and actual P4 timing/memory are still required
before a successful future candidate can be integrated into HardwareOne.


## Code-only overnight continuation

The active [work queue](SPEAKER_OVERNIGHT_PLAN.md) holds models, production
settings and CPU/RAM clocks fixed. It prioritizes actual input/boundary evidence,
portable capture/scheduler correctness, redundant allocations/copies/computation,
and bit-exact pointwise-kernel/data-layout candidates. The first frontend buffer
clear candidate passes 150 frozen-reference cases and sanitizer checks; target
output/speed qualification remains pending. No source-level change or host-only
speed result is treated as an end-to-end P4 win. Subsequent playback uses 50%,
separate from the historical 75% results, and overnight replay is silent.

### Silent code-only checkpoint, 2026-10-31

The speaker frame-clear candidate preserves 150 host feature cases and 30 P4
cases. Five matched reboot trials give mean frontend time 55.381373 -> 54.709907
ms: -1.212441%, paired boot-bootstrap 95% saving 0.599460–0.743473 ms. This is an
isolated computation saving, not a qualified caption latency/accuracy/RAM win.
The diagnostic keeps the normal model's original frontend; source, clocks,
settings and compiler choices are otherwise matched. Original full app slot was
restored/verified and the temporary SD fixture removed. No observed watchdog,
overrun or fatal markers; final LittleFS free 6,504,448 B.

Portable segmentation passed 720 chunk comparisons under ASan/UBSan, exact PCM
source checks, continuous-voice and pending-cut conservation; the unchanged
streaming suite passed ThreadSanitizer. These checks found no cut/ownership bug
and do not prove the HardwareOne transport or original failure's missing PCM.
Next code-only performance work should prioritize the measured pointwise stage,
including repeated address/division work without changing tile sizes, weights,
clocks or arithmetic reductions. Frozen/reference fixtures and target matched
runs are required before claiming a gain. End-to-end qualification remains open. The completed 44-condition known-clip
boundary probe shows nonmonotonic similarities and cross-conversation tradeoffs;
no universal boundary policy qualifies from it. See AB_TEST_RESULTS.md.


The first pointwise address-walk experiment has now completed: 50 hash-equal
model calls across five boots but no measurable inference improvement
(+1.157667 ms, 95% [-3.437533, +5.275533] ms). It is rejected for promotion;
measured headroom matches and the original app is restored. The next bounded
code audit concerns feature-row writer/retirement ownership; the next profiling
gap is actual cache/bus behavior. Neither has a reproduced result yet. No tile,
model, production cadence or CPU/RAM timing change is proposed from this result.


A confirmed cache-row ownership repair is now prepared (HardwareOne 3fff3013):
private staging in existing workspace plus locked generation-checked batch
publication. Host race controls and 42 forced P4 checks support the narrow fix;
normal features remain byte-identical with no new workspace allocation and no
measured stack-headroom change. This is not an application qualification:
two shutdown faults remain in seven diagnostic boots (one watchdog reset, one
core-0 heap-allocation load-access fault). The next priority is instrumenting
teardown and heap integrity, with all failures retained. Direct-ring concurrency
and cache/PSRAM traffic remain separate gaps. The original app is restored.


The initial teardown diagnostic is complete: four idle-capture lifecycles,
75 passing fully logged heap checks, three complete 19-check marker sets and
one partial set due to interleaved CLI output. Both fixture conditions can
complete; the earlier faults remain unexplained. No qualifying reliability,
WER or speed claim follows. Next reduce instrumentation perturbation and
isolate load-time self-test, keeping the original failures. The first ring-wrap
schedule rejected stale batches but did not reproduce a TSAN race; no ring
rewrite is justified yet. Source 5e07c4d9/app and matching debug metadata are
private/local only; the original app is restored and future playback stays 50%.


The marker-only follow-up now locates two observed heap faults in synchronous
serial command-request allocation (6,384 B), with the latest after all 19
cleanup boundaries. It does not locate the corrupting writer. The fixture
matrix remains incomplete: 5 no-fixture successes, then 2 fixture successes/1
fault/2 unattempted. Verify both-core hardware-watchpoint ownership before
instrumenting heap-header writes; keep every failure in qualification history.

The first live-ring negative was a sanitizer-visibility limitation: the Mac
runtime ignored memory-interceptor accesses. Explicit checking plus positive
and negative copy controls now reproduces the ring producer/DSP race in both
original and cache-row-repaired workers. Portable StreamPipeline and the narrow
row-retirement repair pass their existing tests under the stricter setting.
Prepare a separate stable-PCM-window repair, keep configured stacks/clocks and
models fixed, and prove parity plus actual P4 headroom/copy overhead. This is
correctness work, not a measured speed or WER win. Counter register semantics
are now pinned in P4_CACHE_COUNTER_PLAN.md; actual traffic remains unmeasured.


The stable-window ring repair is now prepared (normal b7598680) and passes
source-bound host concurrency/parity tests plus five known-input P4 diagnostic
boots. Target rows are byte-identical (6,950 per arm). Its measured feature-task
CPU cost is +604.40 us, 95% [557.56,653.32] us (+1.07348%), per 44,560 samples;
this is a correctness tradeoff, not a performance winner. The same 3,072-byte
stack retains at least 1,600 B observed headroom; no new heap buffer/configuration
change is used. Full live-speech latency/WER/RAM and app reliability remain
unqualified, and the command-allocation heap faults remain open.

Next apply the source-audited P4_HEAP_WATCH_PLAN.md through readback-only
ownership checks and expected-trap calibration before monitoring the heap field.
Breakpoint/watchpoint resources are shared on this RISC-V target, so do not
assume a slot is unused. No board trigger is armed. Actual cache-counter traffic
measurement remains pending; model, clocks, cache configuration and raw captions
are unchanged. Original firmware is restored after the diagnostic block.


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
