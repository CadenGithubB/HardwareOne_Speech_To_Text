# HardwareOne STT improvements ported to standalone

31 October 2026. **Source port and host/build validation complete; fresh device
performance and accuracy qualification remains pending.** No HardwareOne source
was modified or synchronized back, and no device firmware was flashed.

This work follows the [confirmed divergence](STANDALONE_PARITY.md) and
[optimization plan](STT_OPTIMIZATION_PLAN.md). It imports existing HardwareOne
improvements; it does not claim the proposed new kernel tuning, preview-cadence
experiments or accuracy experiments have already produced measured gains.

## What is now implemented

| Area | Standalone implementation |
| --- | --- |
| Runtime and memory policy | Current HardwareOne admission fixes: separate cold/resident internal SRAM floors, total and contiguous-block checks, no eviction of a PSRAM LM solely for internal SRAM pressure, bounded task-owned allocation observations and diagnostic-only global heap deltas |
| Watchdog | Keeps both idle-task subscriptions; periodically blocks after completed model stages instead of changing the global watchdog configuration |
| ESP-DL patch | Current prepared-factor scratch reuse and metadata-backed temporary argument vectors; updated pinned patch and staged-tree digests |
| Capture features | Portable two-cache/stream-ring ownership; low-priority adapter computes stable log-mel rows while capture continues, and runtime receives the cached prefix |
| Drafts | Real provisional USB/viewer events, a shared snapshot buffer, cooperative preemption by finals/speculation, and cadence gated by new audio and prior inference duration |
| Early finals | Opt-in 500 ms retained tail; exact speculative input is promoted only if final start, voiced end and ordinary pause closure match. Resumed speech, hard cuts and session end invalidate it |
| Full-audio control | Default board-microphone profile keeps every captured sample. A lean final-only profile is supplied for comparisons |
| LM controls | Runtime-validated strength in [0,1], coupled alpha/beta/hotword scaling, history diagnostics; default strength 1 preserves existing behavior |
| Speaker policy | Current abstention and decision-evidence behavior in the optional clustering component |
| Speaker adapter | Optional model-defined centre-window jobs, four bounded PCM slots, lower-priority single-core inference, late result events and recording-specific receipts. Queue overflow yields unknown rather than blocking caption processing |
| Diagnostics | Logical model-file read bytes/calls and elapsed read/open-stat time, per-work phase times, cache reuse, promotions, sampled RAM/free largest internal block |
| Transcript behavior | Existing raw-text preservation, vocabulary, display formatting, SD JSONL recordings, startup ordering and localhost viewer remain; blank/error finals clear obsolete previews |

The acoustic model identity and acoustic frontend/segmenter algorithms are
unchanged. Speaker clustering and optional LM-strength behavior are deliberate
imports from HardwareOne, not claims of improved measured accuracy.

## Reusable component boundaries

`firmware/components/hw1_stt/stt/stt_stream.{h,cpp}` is a portable scheduler with
caller-provided PCM buffers and lock/unlock callbacks. It has no FreeRTOS,
microphone, filesystem, account, Bluetooth or display dependency. Its methods
support one PCM producer, one transcription consumer and one optional feature
consumer. `begin` occurs before those consumers start. Each pipeline instance
represents one capture session; callers join active workers before reclaiming
buffers or creating a replacement instance.

- `push` feeds mono 16 kHz signed int16 PCM through the existing segmenter.
- `take` hands the worker a final, draft or speculative job and optional feature
  prefix. PCM and committed feature rows remain owned until `complete`.
- `cancelled` is the runtime cancellation callback. Finals outrank drafts;
  speculative results are retained only while a matching phrase can still use them.
- `featureTake` snapshots a stable raw-sample window while holding the lock;
  FFT/mel computation happens outside the lock; `featureComplete` commits only
  to the original live cache generation. The producer never runs an FFT.
- `finish` seals the remaining qualified tail; `cancel` abandons pending work.
  Neither frees an active job's buffers underneath inference.

Three bounded final slots and two generation-tagged feature caches preserve
ownership through backlog and cancellation. A retired cache cannot be reused
while a worker holds a prefix. Samples and cache rows are wiped on release.
A ready speculative result is copied into the job, so concurrent cancellation
cannot mutate the worker's result text.

The P4 example owns FreeRTOS/mutex, SD/NVS, PDM, USB and optional speaker adapters.
A future glasses/HardwareOne adapter should feed PCM and consume work/events
through these boundaries while retaining HardwareOne's own session, account,
VFS, display, BLE and shutdown contracts. The standalone example does not
implement native glasses Bluetooth audio.

## Build profiles and runtime controls

Requires ESP-IDF 5.5.5, its ESP32-P4 tools and the model/LM files described in
[the firmware guide](../firmware/README.md). Stage the pinned SDK once:

```sh
python3 firmware/tools/prepare_esp_dl.py
```

For a reproducible clean profile build, run this from the repository root
with ESP-IDF exported. Absolute build/config paths avoid ambiguity in `idf.py -C`:

```sh
project="$PWD/firmware/examples/p4_eye_captions"
build_dir="$project/build/latency"
mkdir -p "$build_dir"
idf.py -C "$project" -B "$build_dir" \
  -DSDKCONFIG="$build_dir/sdkconfig" \
  -DSDKCONFIG_DEFAULTS="$project/sdkconfig.defaults;$project/sdkconfig.latency" \
  -DHW1_STT_SPEAKER_LABELS=ON build
```

Use `sdkconfig.lean` and `HW1_STT_SPEAKER_LABELS=OFF` for the lean control.
For default settings, use only `sdkconfig.defaults` and speaker labels OFF.
Existing sdkconfig files retain their selected settings; use a new build/config
path or menuconfig rather than assuming defaults overwrite an old configuration.

| Profile | Capture features | Drafts | Trim / early finals | Speakers | Owned-allocation hooks |
| --- | --- | --- | --- | --- | --- |
| Default | On, allocation permitting | On, snapshot permitting | Off; full audio | Off | On |
| Latency + optional speakers | On | On | 500 ms tail / on | On if compiled, model present and reserves permit | On |
| Lean control | Off | Off | Off; full audio | Off | Off |

The feature pool is optional and checks free/contiguous PSRAM against the runtime
call budget plus decoder reserve. Optional speaker loading similarly preserves
caption memory reserves. Mandatory capture/queue allocations fail explicitly.
Allocation hooks observe only the owning transcribe task; child workers and
other task allocations are not attributed to it. Conservative admission floors
remain even when no complete observation is available. When embedding this
component in an application with its own heap hooks, reconcile the hook owner
rather than defining a second pair of global ESP-IDF hook functions.

The optional speaker file is `/sd/STT Models/speaker.spk`. Missing/invalid files,
insufficient memory or task allocation failure leave captioning available.
Speaker clustering resets at the next recording's first speaker job. Labels
arriving after a recording boundary are omitted rather than attached to another
note; draining/persisting them into an already-ended recording is not implemented.

USB commands include:

```text
lm strength 1
lm strength 0.75
status
```

Strength changes apply to subsequent inference; they are session settings, not
persisted to NVS or written into the LM blob. Strength 0 is acoustic-only CTC
beam search, not greedy decoding. Drafts are live events and never saved as final
records. Existing vocabulary and recording commands are unchanged.

## Validation completed

Host checks compile the actual production sources. They cover:

- Cached and resident runtime lifecycle/admission/failure behavior, with
  diagnostics both enabled and disabled, under AddressSanitizer/UBSan.
- Bounded internal allocation hooks and policy with hooks both on and off.
- Prepared Conv scratch ownership, alignment, allocation failure and reuse
  against the actual staged SDK definitions.
- LM default/strength-1 parity, context isolation, invalid factors and immutable
  blobs, plus independent synthetic reference comparisons at strengths 1 and 0.75.
- 788 speaker clustering checks using synthetic embeddings, including ambiguous
  matches, short evidence, capacity and invalid inputs.
- Streaming cached-feature bit equivalence to the batch frontend, exact promotion,
  resumed-speech cancellation, hard cuts, finish/cancel, queue overflow, stale
  cache generations and three-thread ownership; AddressSanitizer/UBSan and
  ThreadSanitizer runs pass.
- Actual speaker submit/poll functions with bounded queue fakes: centre cropping,
  nonblocking overflow, failed publication cleanup and recording-receipt routing.
- Existing formatter/vocabulary, actual production SD/command adapter, viewer and
  localhost bridge regressions. Production adapter checks now include LM command
  validation, live drafts, preview clearing and late-label recording isolation.

All three standalone P4 configurations build: default, latency with speakers,
and lean. SDK provenance is ESP-IDF v5.5.5-dirty (the installed local SDK has
modifications); this is not a pristine-SDK portability certification. One upstream
ESP-DL JPEG initializer warning remains outside the STT code. The example's
partition fit check is not evidence of the connected device's actual partition
layout. Built firmware hashes/sizes are in
[standalone-build-validation.json](standalone-build-validation.json).

Reproduce host checks with a C++17 Clang compiler, Python, Node and cJSON from
ESP-IDF (`IDF_PATH` exported, or `CJSON_DIR` pointing at its cJSON folder):

```sh
python3 tests/test_transcript.py
python3 tests/test_product_storage.py
node tests/test_viewer.mjs
python3 tests/test_bridge.py
python3 tests/test_stt_internal_memory.py --sanitize
python3 tests/test_stt_speaker_cluster.py --sanitize
python3 tests/test_quartznet_cache.py --sanitize
python3 tests/test_stt_conv_scratch.py
python3 tests/test_stt_lm.py
python3 tests/test_stt_stream.py
python3 tests/test_stt_stream.py --thread-sanitize
python3 tests/test_speaker_adapter.py
```

The bridge test binds localhost; Conv scratch checks require the staged SDK.
The allocation/cache tests use bounded host fakes and do not emulate device
allocation timing. None of these checks qualifies model accuracy or kernel
numerics on the P4.

## Remaining device acceptance

No new standalone image was flashed in this port. The connected 0.99.99 glasses
measurements remain measurements of integrated firmware, not this build.
Before a device run, inspect its actual partition table and preserve a new private
rollback image. Application-only flashing must use that verified slot and fit;
never replace its bootloader, partition table or settings merely to run this app.

Then compare fixed/reference audio across default, lean, latency, and
speaker-on/off conditions. Capture cold load separately from warm distributions,
first draft and final delay, original sample boundaries and quiet endings,
drops/cancellation work, RAM peaks/largest blocks and WER/speaker decisions.
The board microphone is inside the user's case; its input quality cannot be
assumed equivalent to the glasses microphone. A controlled PCM adapter or an
accessible microphone is needed for useful standalone accuracy comparisons.

Logical SD request bytes/read times are now observable. They are not physical
SD transactions, SPI-flash instruction fetches, cache misses or PSRAM bandwidth.
Those hardware counters still need appropriate instrumentation. No speedup,
RAM-peak improvement or accuracy gain is claimed until this acceptance is run.

The [after-port source inventory](stt-source-parity-after-port.json) shows the
shared LM, speaker policy, memory helpers and ESP-DL patch reconciled. Remaining
file differences are the standalone's pinned model/build packaging, its separate
portable transcript component and the newly extracted streaming component. Future
HardwareOne adaptation follows standalone device qualification.
