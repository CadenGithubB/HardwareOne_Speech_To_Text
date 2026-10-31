# Transcription performance audit — 31 October 2026

Fresh native-glasses measurements are now available in `GLASSES_LIVE_PROFILE.md`
and `performance-glasses-live.json`. They supersede the older ring-buffer-only
evidence for the current glasses path. Earlier failed/awaiting-start attempts
below are retained as provenance, not the final test outcome.

## Scope and evidence

This workspace was restored from `HardwareOne-STT-Handoff-2026-10-21.zip/source/`.
Its baseline is `a2ef959e85b6bba95f1cecf57768bd1ff075f8c9`, with the archive's additional
standalone transcript features. During this audit the user connected a P4X-EYE running
HardwareOne firmware 0.99.99. Its retained profiling records and a current memory
snapshot were read over USB; no fresh controlled audio test has been run yet.

## Connected device: firmware 0.99.99

`docs/performance-device-summary.json` contains numeric-only evidence extracted from
`sttperf show` and `memreport json`. Raw serial output remains in ignored
`private/performance/`. The STT ring buffer's last 16 segments contain 8.1–9.7 s of
audio each; all used the LM. Mean recorded phases: load/setup 9.69 ms, frontend
49.0 ms, inference 2,736.19 ms and decode 69.19 ms. Inference accounts for about
95.5% of their phase sum (2,864.06 ms). The reported aggregate RTF was 0.32;
backlog was zero on these retained records. These are previous work in this device
boot, with unknown audio/recording conditions, not a new benchmark. They cannot
establish WER, true speech-end latency or a regression against the older test corpus.

The current heap snapshot was taken with STT weights absent: PSRAM free 32,466,620 B
of 32,851,892 B reported heap; internal free 238,167 B of 495,203 B, largest internal
block 102,400 B. Internal boot-wide minimum was 92,200 B; this cannot be attributed
to STT or a particular phase. The allocation traffic counter's 84,971,162 requested
PSRAM bytes are cumulative allocation churn, not simultaneous live usage.

At the user's request the following persistent flags were enabled and verified in
the device's final mask: BT, BT_CORE, BT_GATT, BT_DATA; G2 and its six subflags;
SR and its five subflags; MIC and its three subflags. Six preexisting LLM flags
remained enabled, for 27 named flags total. `sttperf log on` was also verified;
that live-log switch is runtime state. There is no separate STT flag in the inspected
debug-family table. These changes enable existing firmware diagnostics; they do not
add compile-time instrumentation. Firmware was not rebuilt or flashed.

The `sttperf stages all` response was truncated before all 201 values arrived, so
it was excluded from layer-share analysis. Other serial status polling was visible
during collection. Measurements with these verbose flags must be labelled accordingly
and compared with a lean logging control before deciding performance wins.

The historical measurements in `tools/report/{breakdown,layers,versions}.json` describe
October 10–11 builds and microphone/loudspeaker tests. They are useful evidence about
the engine, **not fresh measurements of this standalone application's end-to-end path**.
Raw sessions were excluded from the handoff, so their aggregates cannot be independently
recomputed here. `docs/index.html` and the report scripts describe the methodology.

`tools/report/make_performance_audit.py` generates a portable evidence JSON file from
these checked-in aggregates and constants read from the current source. The conversation
visual uses that evidence. Regenerate with:

```sh
python3 tools/report/make_performance_audit.py
```

## Time: what is known

Historical v1.8, all phrases: interquartile mean speech-end-to-caption 1,064 ms;
median 1,004 ms; 14 phrases from one session, 8 in the middle-half aggregate.
The additive breakdown is approximately 599 ms pointwise convolution, 191 ms depthwise,
34 ms other model work, 33 ms LM decoding, 13 ms frontend, 4 ms setup, 8 ms delivery,
and 183 ms combined residual endpoint/trigger/queue time. The layer-type allocation
is inferred from per-stage fits, not a separate stopwatch for every phrase. The split
includes overlap effects and must not be interpreted as a standalone scheduling trace.

The c12 fitted layer profile at five seconds of audio puts about 59% of layer execution
in 512→512 pointwise convolutions (836 ms out of 1,409 ms), about 72% in all pointwise
convolutions. It excludes endpointing, preparation, yields, frontend and decode. This
makes pointwise kernels and PSRAM/cache reuse the first compute targets to investigate.

Current standalone code differs materially:

- `captureTask` waits for a completed segment before queueing it. It has no speculative
  early-final path or capture-time feature-prefix cache; transcribe receives a null prefix.
- Endpointing uses 600 ms silence for eligible longer segments and 1 s for short-close;
  the 4 s minimum and 10 s hard cap also affect when a phrase is released. These are
  configuration values, not a measured latency distribution. DMA blocks are 1,024
  samples (64 ms of audio), which introduces collection granularity, not a fixed 64 ms delay.
- Tail trimming is disabled. Captured trailing silence goes through the frontend and model.
- `ms` in the existing serial caption line measures the transcribe wrapper only. It
  excludes endpoint waiting, time queued, caption printing, `product::caption`, JSON
  serialization, SD append/flush/fsync, and the later return of the audio slot.
- The last point matters for throughput: storage runs on the transcribing thread before
  the slot becomes free, so slow card writes can increase backlog/drops even after the
  visible text was printed. Two slots limit the backlog.

Do not present a simulated sum of endpoint constants and old inference times as a
measurement of the current device. No new throughput or accuracy claim is established.

## RAM: allocation map versus measured free memory

The board configuration specifies 32 MiB PSRAM. Known requested allocations are:

- Pinned raw model: 20,112,128 B = 19.18 MiB, loaded once and retained in PSRAM.
- Three 10 s PCM buffers: capture work plus two slots, 960,000 B = 0.916 MiB total.
- LM blob: actual card-dependent size; archive asset is 2,499,996 B = 2.384 MiB,
  while the qualified October 21 device used a roughly 1.6 MB LM. Neither proves the
  LM currently on the user's card. It can fail to load or be released under pressure,
  causing greedy fallback; report `lmUsed` for every phrase.
- Frontend float matrix: `ceil(samples/160) × 64 × 4` bytes, up to 256,000 B at
  10 s, plus an approximately 8 KiB workspace. These allocations are transient,
  released before inference; the resident activation arena remains allocated.

The visualization's physical-capacity remainder is **unattributed allocations plus
free capacity**, not measured free heap. It includes resident activation tensors,
metadata, prepared convolution arguments, decoder workspace, task/driver allocations,
allocator overhead and unavailable/reserved capacity. It cannot establish peak use.

The runtime's `2048 × outputFrames + 64 KiB` arena budget and 1 MiB metadata margin
are admission estimates, not allocation measurements. Resident mode keeps its ten-second
arena between phrases even when the current phrase is shorter. Obtain actual arena
bytes from the existing `TL e3 resident=1 ... arena=... arena_int=...` startup log.
That log also reports resident retained PSRAM and metadata allocator counters; gross
metadata requested bytes include freed/growth allocations and must not be summed as
live memory.

Historical v1.8 reports 8.0 MB free PSRAM after warm-up, 6.25 MB at its session low
and 143.1 kB minimum internal RAM. The report's `_mb` and `_kb` fields divide by
decimal units (`versions.py`); the visual converts them to MiB/KiB. These are from a different application build and
must not be filled into the current standalone's memory map. The optional background
speaker model is absent from this standalone; do not subtract its historical 3.4 MB cost.

Internal RAM attribution and transient peaks are not available from the bundled current
standalone logs. Boot-wide minimum-free values are cumulative and cannot by themselves
attribute a new peak to a particular phase. Track largest free block alongside total
free heap because fragmentation can refuse a large allocation despite enough total space.

## Storage: SD card, internal flash and PSRAM are different paths

| Path | Startup | Recurring path | Evidence limit |
| --- | --- | --- | --- |
| SD speech model | 96 B envelope plus 20,112,128 B raw payload, verified and retained | `fopen`/`fstat`, 96 B logical header read, `fclose` on every transcribe, even with cached weights | FAT cache and stdio buffering can turn this into different physical read sizes/counts; not timed separately |
| SD language model | Lazy whole-file read at first decode during warm-up | Decoding accesses PSRAM; no per-phrase LM file read on normal reuse | A failed/released LM produces greedy fallback; no automatic reload after release |
| SD transcript | Start record | Append final record, `fflush`, `fsync`, close per saved accepted caption; end record at note stop | Latency and SD controller/internal flash behavior unmeasured; card writes may cause card-internal reads |
| SD vocabulary/review | Vocabulary load | Explicit edits/reload, recording list/read commands | User-driven traffic, not continuous model weight streaming |
| Internal SPI flash / NVS | Firmware execution and startup counter transaction | Cached/mapped firmware instruction and rodata fetches as caches miss; no explicit per-phrase NVS transaction in this app | Bus traffic, cache misses and contention with PSRAM have not been measured; SD counters cannot answer this |
| PSRAM | Model, arena, LM, PCM allocations | Repeated reads of weights/LM/activations and writes of activations | Bytes transferred, effective bandwidth and cache miss rate unmeasured |

The `MODEL_LOCATION_IN_FLASH_RODATA` vendor enum in the model constructor is not
evidence that weights are streaming from flash: the actual pointer is `weights.raw_`,
allocated in PSRAM. Likewise a 96 B logical header read is not a 96 B physical SD transaction.

## Prioritized experiments

1. **Establish the current baseline first.** Identify chip/revision, app hash/build,
   model hash, LM bytes, actual CPU/PSRAM/cache settings, resident-build success and
   speaker enablement. Capture a cold boot and warm-up separately from warm phrases.
2. **Separate scheduling from math.** Timestamp last classified voiced sample,
   segment-ready, worker-start, inference end, caption emitted, persistence complete
   and slot returned. Last-VAD-voiced is a proxy; use reference audio alignment to
   measure true speech-end latency and avoid rewarding clipped words.
3. **Pointwise kernels / memory locality.** Profile all 201 stages with the existing
   `stageProfile` counters. Attribute stage IDs with `graph_nodes.json`. Collect
   instruction/data-cache events or bus observations supported by this exact chip/SDK,
   keeping instruction flash misses distinct from PSRAM data traffic. Do not infer bus
   utilization from wall time alone. Compare bit-exact logits and real-time throughput.
4. **Endpoint / tail / scheduling.** Compare the existing policy against carefully
   tested trimming or an early-final path on identical short, long, soft-final-word,
   noisy and continuous clips. Historical 100 ms trim cost ~1.1 accuracy points;
   the standalone explicitly disabled trimming after soft words were lost. Measure
   word errors, final-word deletions, duplicate/lost text, drops and latency together.
5. **Storage cost.** Count/time logical model-reader calls/bytes, file open/header/close,
   LM reads, and transcript append/flush separately. Compare saving enabled/disabled
   on identical audio; retain durability as an explicit tradeoff. Consider a session-held
   validated model stream/header only if its measured overhead matters, preserving
   card-removal/error handling and identity checks.
6. **RAM pressure.** Record free and largest-block internal/PSRAM at boot, after PCM,
   weights, LM and resident build; sample during frontend, inference, decode and saving.
   Separate retained memory, phase live peaks, boot minimum and gross allocation churn.
   Use an instrumented run plus a lean timing control because tracing itself costs time/RAM.
7. **Accuracy.** Validate a small reference corpus with names/tech terms, soft endings,
   noise and silence. Compare greedy/LM/custom vocabulary on identical logits, then
   acoustic model/training changes. Historic LM-size reductions mainly saved RAM;
   the report found little decode speed or accuracy change. Formatting is not acoustic
   accuracy, and a vocabulary bias does not teach pronunciation.

## Device session required

The user subsequently selected glasses only and declined speaker playback. A
glasses-only live-speech attempt was made after both BLE links became available.
The serial-owned `stt start` path did not receive microphone frames: it logged
the plugin as silent, then `TL warm ... ok=0 lm=0` with `Cancelled` before the
test-ready announcement. No fresh transcription benchmark or accuracy result
was produced. The original `micsource=auto` preference was restored in RAM and
Showcase polling resumed. Internal storage was simultaneously reporting full
and settings writes failed. Do not claim persistence based only on a toggle's
`enabled (persistent)` reply; live flags were confirmed, disk saves were not.

Inspection of the integrated firmware shows distinct legacy plugin and native
Conversate microphone paths. A native Conversate run, opened by the wearer,
is the next appropriate way to test this glasses firmware after storage recovery.
See `SYSTEM_LOG_STORAGE_INCIDENT.md` for the authorized log backup and cleanup.

Storage recovery subsequently completed: the 8,331,031 B system capture log was
verified against a complete independent device read and removed from LittleFS,
restoring 8,351,744 B free. Both settings files passed before/after validation,
and an explicit settings flush succeeded. A timed native Conversate test was then
armed; no native STT warm-up/start arrived during the 150 s readiness window.
The timed test was stopped, user-ended mode was requested again, and Showcase
polling resumed. No fresh transcription measurements were produced by that wait.

Connect the P4X-EYE and identify its current firmware. Initial work can read serial
without flashing. Capture boot/model/resident/LM logs plus short and long utterances,
10 s continuous phrases and silence/noise. Record at least three repetitions per
condition after warm-up; use identical playback audio for controlled comparisons.

The standalone serial logs expose frontend/model/decode times, total wrapper time, LM use,
drops and some startup allocation diagnostics. Fresh per-phase RAM peaks, endpoint
and queue/persistence timings, and flash/cache traffic require additional instrumentation.
No ordinary serial log can establish physical flash bus reads without such counters
or external measurement. Do not enable `HW1_STT_RUNTIME_DIAGNOSTICS` blindly: that
mode re-hashes cached weights on each call and adds tensor hashing, distorting timing.

Before any firmware replacement inspect the actual partition table and preserve a
private rollback image, as required by this project's AGENTS.md. Keep device logs,
recordings and transcripts under ignored `private/`. No flashing or hardware tests
were performed on the standalone build as part of this audit; the live USB inspection
and debug configuration above were performed on firmware 0.99.99.

## Source anchors

- `firmware/examples/p4_eye_captions/main/main.cpp`: phrase constants, captureTask,
  loadLanguageModel, readModel, transcribe wrapper and app_main loop.
- `firmware/examples/p4_eye_captions/main/product.cpp`: saveEvent and startupCounters.
- `firmware/components/hw1_stt/stt/quartznet_runtime.cpp`: transcribe, buildResident,
  callBudget, stageProfile; `quartznet_frontend.h`: workspace; `stt_segmenter.h`: defaults.
- `firmware/components/hw1_stt/stt/stt_model_container.h`: 96 B per-call envelope;
  `stt_model_identity.h`: exact raw model size.
- `tools/report/breakdown.py`, `layers.py`, `versions.py`: aggregate derivation.
- `docs/STT_PRODUCT_HANDOFF.md`: October 21 hardware qualification and integration limits.
