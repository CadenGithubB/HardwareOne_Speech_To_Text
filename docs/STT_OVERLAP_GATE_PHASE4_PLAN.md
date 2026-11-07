# Overlap gate phase four · flag-only on the P4 · plan (6 November 2026)

Status: plan only; no code or firmware change yet. Candidate model: G2c
([STT_OVERLAP_GATE_PLAN.md](STT_OVERLAP_GATE_PLAN.md) section 16),
`private/training-track/overlap-gate/phase3c/export-int8/g2.espdl`, 56,096 bytes, ESP-DL W8A8 for
esp32p4, fixture byte-exact. This phase puts that model on the standalone P4 example, measures it,
and emits an overlap flag beside the speaker label. It changes no caption text, no recognizer, no
speaker algorithm, no production default. HardwareOne integration is a separate decision
(AGENTS.md: this checkout owns the standalone example and does not synchronize into HardwareOne).

## 1. What the device will compute

Per final caption segment, after the caption event has already been emitted:

1. Take the raw 64-bin log-mel rows of the whole segment (pre-normalization, dither off): the
   capture-time feature cache already holds the prefix rows raw (`main.cpp:263-295`,
   `System_STTLocal.h:40-47`, pinned in `work.features` until `complete()`); the tail rows that
   `transcribe()` computes itself are recomputed with `log_mel_frame(work.pcm, ...)`, which is
   bit-identical. No runtime code path changes; the copy happens before `gPipeline.complete()`.
2. Run the gate in fixed **200-frame chunks** (the training window), channel-last input
   `[1, 200, 1, 64]` int8 with the export's input exponent (−3), last chunk padded with the
   silence log-mel constant. Output `[1, 100, 1, 3]` int8, exponent −3.
3. Softmax per 20 ms frame; P(two or more) ≥ 0.5 marks a frame; the segment score is the fraction
   of marked frames over the segment's frames; **flag = score ≥ 0.2451**, the threshold frozen on
   AMI validation for G2c. No collar on device; the collar is a scoring convention.
4. Emit `STT_EVENT {"type":"overlap", sequence, overlap, fraction, frames, ready:true}` with the
   same identity fields and guards as the speaker event. Then submit the speaker job as today.

The chunked, collar-free rule differs slightly from the host protocol (whole segment, collar
excluded). **Step 0 below re-scores G2c under exactly this device rule on the host first**, so the
device is compared against numbers computed the same way.

Cost estimate: about 23k multiply-accumulates per 20 ms frame, 11.5 M for a 10 s segment; the
recognizer runs 942 M per second of audio at roughly 0.3× real time, so the gate should take a few
milliseconds per segment. This is an estimate until measured.

## 2. Integration, copying the speaker pattern

| Piece | Pattern copied | New |
|---|---|---|
| Build flag | `option(HW1_STT_SPEAKER_LABELS OFF)` in `components/hw1_stt/CMakeLists.txt:17`, sources appended, PUBLIC define, `esp_dl_compile_add_yml` | `option(HW1_OVERLAP_GATE OFF)`; `stt/overlap_gate.cpp`; `stt/overlap_gate.compile_req.yml` listing Conv, Add, Relu, RequantizeLinear int8 (the export's operator set; operators not listed are not compiled) |
| Model file | `/sd/STT Models/speaker.spk` read in 64 KB chunks into 16-aligned PSRAM, admission on free PSRAM (`speaker_adapter.cpp:83-104`) | `/sd/STT Models/overlap_gate.espdl` plus `overlap_gate.sha256`; bare ESP-DL file, embedded test values kept so `dl::Model::test()` can self-check at load |
| Model construction | `dl::Model(ptr, MODEL_LOCATION_IN_FLASH_RODATA, 0, MEMORY_MANAGER_GREEDY, nullptr, false)`, metadata allocator hook, `get_arena_size`, one int8 input/output with exponents (`speaker_model.cpp:94-113`) | `OverlapGate::load()` identical checks; input shape `[1,200,1,64]`, output `[1,100,1,3]`; log blob SHA-256 via `captions_perf::modelIdentity("overlap", ...)`, arena bytes, self-test result |
| Admission | free PSRAM ≥ bytes + 1 MB + reserve; after load free internal ≥ 140 KB, largest PSRAM block ≥ contiguous (`speaker_adapter.cpp:90,129-132`) | same thresholds; when not admitted the gate is absent and no overlap event is emitted (never a false "no overlap") |
| Where it runs | speaker: background task core 1, priority 1 | gate: **synchronous on the main thread** right after `product::caption` (`main.cpp:559`) and before `captions_speaker::submit` (`:561`), since the estimated cost is milliseconds; if measured cost exceeds 50 ms per 10 s segment, move it to the speaker worker's queue pattern |
| Event | `product::speaker(Receipt, label)` (`product.cpp:315-323`) | `product::overlap(Receipt, bool, float fraction, uint16_t frames)` with the same note/sequence guards; `caption()` untouched so the final event stays byte-identical |
| App switch | `CONFIG_CAPTIONS_*` Kconfig with `#ifndef` fallbacks | `CONFIG_CAPTIONS_OVERLAP_GATE` default n |
| Viewer | reducer in `tools/transcript/web/model.mjs` | out of scope for phase four; the event is logged and saved, not displayed |

Host-portable parts (int8 quantization of rows, softmax, fraction, threshold) go in a plain C++
unit with a host test against Python on the embedded fixture, like the existing
`tests/*.cpp` harnesses. The ESP-DL inference itself is verified on the device by the embedded
fixture and by replaying clips whose host decisions are known.

## 3. Steps

**Step 0 · host, no board.** Re-score G2c on every panel under the device rule of section 1
(200-frame chunks, silence padding, no collar, threshold 0.2451) using the *int8 native graph*,
and compare with the protocol scores: saved-microphone single-speaker false alarms must stay 0,
AMI test recall and false alarms within one point of 33.2% / 2.74%. Write
`phase4/device-rule-scores.json` and the per-clip expected decisions for the 32 whole saved
microphone windows and the 8 overlap clips: these are the device's answer key. Produce
`overlap_gate.sha256` and the silence constant file.

**Step 1 · code, host-built.** The CMake option, the yml, `overlap_gate.{h,cpp}`,
`product::overlap`, the main-loop call, Kconfig; a host test for the portable unit; build the
latency profile with `-DHW1_OVERLAP_GATE=ON` and the lean profile with it OFF; confirm the OFF
build is byte-identical in behaviour (same sources compiled out, as the speaker adapter's `#else`
stubs do).

**Step 2 · board preparation (handoff rules).** Identify the test P4 by MAC through
`tools/device_tests/find_p4_port.py`; read the partition table at `0x8000` and compare with the
recorded table (factory app `0x10000`, size `0x715000`, LittleFS `0x725000`; `flash_variant.sh`
refuses to flash on mismatch); read and hash the current app slot into a private rollback image;
record the running firmware's identity line. Nothing is written in this step.

**Step 3 · model to card.** Copy `g2.espdl` as `overlap_gate.espdl` and its `.sha256` into
`STT Models/` with the `copy_speaker_to_card.sh` procedure (temp file, rename, hash verify, normal
eject). Other card files untouched.

**Step 4 · flash and boot.** App-only flash at `0x10000` through the helper (MAC check, table
check, hash verified). Capture the boot log: model identity hash equals the host SHA, arena bytes,
`dl::Model::test()` pass. If load or self-test fails the gate stays absent and the session still
captions.

**Step 5 · parity replay.** Replay the 32 whole saved-microphone windows and the 8 overlap clips
through the PCM-source path twice: gate OFF build and gate ON build, same playlist. Compare
caption `STT_EVENT` lines byte-for-byte between builds (must be identical), and compare the
device's overlap decisions and fractions with the step-0 answer key (decisions identical;
fractions within int8 rounding of the host int8 native graph).

**Step 6 · memory and time.** `perf dump` before load, after load, and at the end of a 16-phrase
session, gate OFF versus ON: free PSRAM, free internal, largest internal block, boot minimums. Per
segment: the `TL stream` line plus a new `TL overlap ms=` line. Then a 30-minute live soak with
the gate ON, checking for watchdog or fatal markers and heap drift.

**Step 7 · restore and record.** Restore the rollback image unless the user wants the flagged
build left on the board; verify the restore hash; write results into this document and the
handoff.

## 4. Gates for calling phase four done

- Caption events byte-identical between gate OFF and gate ON on the replay playlist.
- Device overlap decisions identical to the step-0 answer key on all 40 clips; no decision on
  any of the 32 single-speaker windows.
- Model identity, arena size and self-test logged and matching host values.
- Added memory: PSRAM ≤ 300 KB and internal RAM ≤ 20 KB with the gate loaded; largest free
  internal block not below 90 KB during the session (reference low: 98 KB). Simultaneous total
  application peak reported and within 30,000,000 bytes.
- Gate time ≤ 50 ms per 10 s segment on the main thread, or moved to the worker.
- No watchdog, fatal or heap-drift marker in the 30-minute soak.
- Rollback image preserved and restore verified.

## 5. What this phase does not do

It recovers no words and routes nothing: the flag is metadata. It does not change HardwareOne,
Bluetooth, the detector, the recognizer, the speaker path or any default. It does not raise the
G2c real-meeting false-alarm figure above what was measured (2.74% on AMI test); a tighter number
needs the larger validation subsample noted in section 16 of the main plan, not a device change.

## 7. Step 0 result · the device rule needs its own threshold (6 November 2026)

`tools/overlap_gate/device_rule.py` scored G2c on every panel with the int8 native graph under
the exact device rule of section 1: explicit int8 input quantization at exponent −3 (the silence
constant saturates to −128 in every bin), 200-frame chunks padded with that constant, int8 output
at exponent −3, softmax, P(two or more) ≥ 0.5, fraction over the segment's own 20 ms frames, no
collar. Labels unchanged. Outputs: `phase4/device-rule-scores.json`, `device-rule-cases.json`
(per-case fractions), `answer-key.json`, `overlap_gate.sha256`, `silence-constant.json`.

| Device rule, int8 graph | Protocol threshold 0.245 | Device-selected threshold 0.443 |
|---|---:|---:|
| AMI validation: recall / false alarms | 38.2% / 5.5% | 21.8% / 1.9% |
| AMI test: recall / false alarms / precision | 35.7% / 4.3% / 88.5% | 23.4% / 1.95% / 91.8% |
| Saved microphone: single-speaker false alarms (of 155) | 0 | 0 |
| Saved microphone: overlap clips caught (of 7) | 3 | 1 |
| Synthetic two-speaker caught (of 128) / single flagged (of 128) | 29 / 0 | 3 / 0 |
| Real32 caught (of 25) / false alarms (of 7) | 5 / 1 | 1 / 0 |
| Frame ROC area, AMI test (protocol collar) | 0.831 | 0.831 |

**Finding.** Without the collar, real-meeting false alarms at the protocol threshold are 4.3% on
test, not 2.7%. The frames within 200 ms of a speaker boundary, which the protocol excluded, are
where the model is least certain and they count toward the device fraction. Re-selecting the
threshold on AMI validation negatives under the device rule (the frozen 2% ceiling, same rule as
before) gives 0.443; at that point the device meets the ceiling on the held-out test (1.95%) with
92% precision, but recall drops to 23.4% and the saved panel catches 1 of 7 overlap clips instead
of 3. The adoption gate passes at either threshold. The AMI test was read a second time here, at a
threshold chosen on validation; it was not used for the choice.

**Decision for the user.** Three ways forward, none of which changes the model:

- **A.** Flash with threshold 0.443: real-meeting false alarms at the 2% ceiling, about one
  overlapped segment in four flagged, 92% precision. Conservative and honest.
- **B.** Before the board, try a label-free boundary-suppression rule on the host: require marked
  frames to form runs of at least 5 or 10 consecutive 20 ms frames before they count, which
  targets the isolated boundary flickers the collar used to hide. Choose the rule and threshold on
  AMI validation only, then report test once. Costs a few minutes of host inference; may recover
  part of the recall at 2% false alarms, or may not.
- **C.** Flash with threshold 0.245 and accept about 4% real-meeting false alarms for 36% recall.

The answer key carries both decisions per clip so whichever threshold is chosen, the device
replay has a reference. Steps 1 to 7 are otherwise unchanged.

## 8. Step 0b result · boundary suppression recovers little; device rule settled (6 November 2026)

`tools/overlap_gate/suppression.py` tried six label-free rules on the saved device posteriors
(`phase4/posteriors/`), each with its threshold chosen on AMI validation at the 2% ceiling, and
scored only the winner on test:

| Rule | Validation recall at ≤2% false alarms | Threshold |
|---|---:|---:|
| R0 plain fraction of marked 20 ms frames | 21.8% | 0.443 |
| R3 / R5 drop marked runs shorter than 3 / 5 frames | 21.9% / 21.4% | 0.418 / 0.416 |
| **R10 drop marked runs shorter than 10 frames (200 ms)** | **24.1%** | **0.360** |
| S3 / S5 posterior smoothed over 3 / 5 frames | 22.5% / 22.3% | 0.460 / 0.460 |

R10 on AMI test, scored once: **24.7% recall, 2.1% false alarms, 91.6% precision**. Saved
microphone panel: 0 of 155 single-speaker clips flagged, 2 of 7 overlap clips caught (R0: 1 of 7),
no-speech 0. Synthetic two-speaker: 16 of 249 caught, 0 false alarms.

The collar's effect was therefore not mainly isolated boundary flickers: no label-free filter
recovers more than about two points of real-meeting recall. At a 2% false-alarm rate on real
meetings the device flags roughly one overlapped segment in four, whatever the rule. R10 is the
small free gain and costs one run-length pass over 100 frames per chunk.

**Device rule, settled:** int8 input at exponent −3; 200-frame chunks padded with the silence
constant; softmax per 20 ms frame; mark P(two or more) ≥ 0.5; drop marked runs shorter than 10
frames; fraction of remaining marked frames over the segment's own frames; **flag when
≥ 0.360**. `answer-key.json` carries this decision per clip (`flag_at_suppression_rule`) beside
the two threshold-only decisions. Results: `phase4/suppression-rules.json`.

Steps 1 to 7 proceed with this rule. The recall figure to carry forward is one in four, not one in
three; the gate's value is unchanged (protection of the single-speaker path, a high-precision
marker where it does fire), and a higher-recall gate is a training question for a later variant,
not a device question.

## 9. Step 1 result · host-built firmware code, off by default (6 November 2026)

Everything compiles for the esp32p4 in both profiles and nothing runs unless two switches are on.

| File | What |
|---|---|
| `firmware/components/hw1_stt/stt/overlap_rule.h` | Portable decision rule, header-only, no heap: per-frame softmax of the three int8 logits, mark at P(two) ≥ 0.5, `Accumulator` over the whole segment, runs shorter than 10 frames dropped, fraction, flag at ≥ 0.360; `quantize_bin` for the int8 input |
| `tests/overlap_rule_test.cpp`, `tests/test_overlap_rule.py` | Host test with ASan/UBSan: constructed cases (run split across chunks counts, sub-minimum run dropped, threshold edge, capacity overflow, silence saturates to −128) and 300 random int8 sequences compared with the Python reference `suppression.py` uses: decisions identical, fractions within 1e-6 |
| `firmware/components/hw1_stt/stt/overlap_gate.{h,cpp}` | `overlap::Gate`: same `dl::Model` construction as the speaker trunk and resident recognizer (in place on the PSRAM copy, internal limit 0, PSRAM metadata allocator); checks one int8 input `[1,200,1,64]` and one int8 output `[1,100,1,3]` with scalar exponents; optional `dl::Model::test()` at load; `input()` / `run()` for one chunk |
| `firmware/components/hw1_stt/stt/overlap_gate.compile_req.yml` | Add, Conv, Relu, RequantizeLinear and a superset of the s8 conv/depthwise/add/relu kernels the graph can bind; trim after the device's kernel-bind log |
| `firmware/components/hw1_stt/CMakeLists.txt` | `option(HW1_OVERLAP_GATE OFF)`: source, `-O2`, the yml, PUBLIC define, exactly the speaker pattern |
| `firmware/examples/p4_eye_captions/main/overlap_adapter.{h,cpp}` | `begin(reserve)`: `/sd/STT Models/overlap_gate.espdl`, size and PSRAM admission, 64 KB reads into 16-aligned PSRAM, identity hash under stream metrics, load with self-test, `FrontendWorkspace` in PSRAM, post-load reserve and 140 KB internal checks, `TL overlap_load` line. `run(receipt, work)`: for each 200-frame chunk, cached raw rows quantized directly, uncached tail rows recomputed with `log_mel_frame` (bit-identical), pad frames at the silence value computed from the model's input exponent, `Gate::run`, accumulate; then `product::overlap` and a `TL overlap` line with frames, marked, fraction, flag, cached/tail rows and ms. Any failure logs and emits nothing. Compiled to empty stubs unless `HW1_OVERLAP_GATE` and `CONFIG_CAPTIONS_OVERLAP_GATE` |
| `main/product.{h,cpp}` | `product::overlap(Receipt, flag, fraction, frames)`: `STT_EVENT {"type":"overlap", ..., "sequence", "overlap", "fraction", "frames", "ready":true}` with the speaker event's guards; saved when saving. `caption()` untouched |
| `main/main.cpp` | `captions_overlap::begin(speakerReserve)` after the speaker; `captions_overlap::run(product::receipt(), work)` after `product::caption` and before the speaker submit, inside the Final branch, before `complete()` |
| `main/Kconfig.projbuild`, `sdkconfig.overlap` | `CONFIG_CAPTIONS_OVERLAP_GATE`, default n; a one-line defaults fragment that turns it on |

Builds (ESP-IDF 5.5.5, patched ESP-DL 3.3.12), from `build/off` and `build/overlap`:

| Profile | Flags | Binary |
|---|---|---:|
| Gate off, `sdkconfig.defaults` | `HW1_STT_SPEAKER_LABELS=OFF HW1_OVERLAP_GATE=OFF` | 646,912 bytes |
| Gate on, `sdkconfig.defaults;sdkconfig.latency;sdkconfig.overlap` | `HW1_STT_SPEAKER_LABELS=ON HW1_OVERLAP_GATE=ON` | 788,928 bytes |

One compile fix along the way: `dl::Model::prepare_args` is not callable from outside the
model; `run()` prepares its own arguments. The off build compiles the adapter to stubs and never
calls `product::overlap`, so the caption path is the pre-change code. Expected gate memory on the
device, to be measured in step 6: 56 KB blob, about 26 KB arena, ESP-DL metadata, a 7 KB frontend
workspace and 1.5 KB of marks.

Step 2 onward needs the board, the card and the go-ahead to flash after the inspection and
backup.

## 10. Step 2 result · board inspected and backed up, nothing written (6 November 2026)

Two P4 boards were attached. The documented test unit `e8:f6:0a:e3:a7:68` (ESP32-P4 revision
v3.2, `/dev/cu.usbmodem101`) was used; `e8:f6:0a:e3:a7:73` was not touched. esptool confirmed the
MAC; the partition table read from `0x8000` is byte-identical to this checkout's
`partitions.csv` build (factory app `0x10000` 7,252 KB, LittleFS `0x725000`). The app slot was read
in 51 s: 7,426,048 bytes, SHA-256 recorded in `phase4/board/app-slot-backup.sha256`.

The backup is **HardwareOne integrated firmware 0.99.99** (project `hardwareone-idf`, compiled
3 November 2026, ELF SHA `82c9c1d9…`, image checksum and hash valid). This board is running the
production firmware, not the standalone example. Step 4 therefore replaces production firmware on
this board until the backup is restored in step 7, as the 21 October qualification did; the user's
explicit go-ahead is required for that flash. The 25 s boot log confirms the same identity and a
32 MB PSRAM pool. The microSD card was not mounted on the Mac during step 2; step 3 needs it (the
card currently sits in the P4). Manifest: `phase4/board/step2-manifest.json`.

## 11. Step 3 and a correction to step 5 (6 November 2026)

**Step 3 done.** `overlap_gate.espdl` (56,096 bytes, SHA `a7c3dbc1…`) and `overlap_gate.sha256`
copied into the card's `STT Models/` beside `quartznet15x5-gen2-25397.p4.stt`, `meeting.lm` and
`speaker.spk`, with the temp-file, rename, hash-verify and normal-eject procedure. No other card file
touched.

**Correction.** The deterministic PCM-file replay this plan assumed for step 5 (`sttperf pcmsrc`)
exists in HardwareOne's `claude/stt-bench` branch and its `heaptw_remote.py` tooling, not in the
standalone example, which reads only the microphone. On this build the step-5 evidence is
therefore:

- *Model numerics on the device*: `dl::Model::test()` at load on the file's embedded test
  input/output, logged in `TL overlap_load test=`. A pass means the P4's int8 kernels reproduce the
  host quantized graph on the fixture; that is the same proof the speaker trunk relies on.
- *Decision rule*: host-pinned (`tests/test_overlap_rule.py`); *raw rows*: bit-identical by the
  frontend's documented contract.
- *Behaviour*: live-microphone sessions rather than bit-exact replay: a single speaker for a run
  of phrases (expect no flags), silence and room noise (expect none), and two people talking over
  each other or a played two-speaker recording (expect flags, with their fractions logged).
- *Caption identity*: structural, not acoustic: the gate runs after `product::caption` returns and
  the caption code is unchanged; two live sessions never hear identical audio, so no byte
  comparison of captions across builds is made on this build. A bit-exact device replay remains
  possible later through the HardwareOne bench tooling if the gate is carried into that firmware.

## 12. Step 4 result · flashed, booted, self-test passed (6 November 2026)

With the user's go-ahead, the gate-ON latency build (788,928 bytes, SHA `49dbaeaf…`) was written
app-only to `0x10000` after a fresh MAC check and partition-table compare; esptool verified the
hash. The first boot ran without the card ("No microSD card detected", app halted cleanly). With
the card back, the boot log (`phase4/board/boot-gate-on-card.txt`) shows:

- `p4_eye_captions` version `model-gen2-25397-144-gc6f4d9a-d`; recognizer loaded in 9.9 s
  (20,112,128 bytes), 7,441 KB PSRAM free after; speaker labels ready.
- `TL overlap_load bytes=56096 modules=16 arena_psram=25600 arena_internal=0 in_exp=-3 out_exp=-3
  build_us=9009 test=0 test_us=5081 rule=0.50/10/0.360`: **the embedded self-test passed on the
  device** (`test=0`), the arena is the 25,600 bytes the host screen predicted, nothing landed in
  internal RAM, model build 9 ms, one 200-frame forward about 5 ms.
- Two final segments closed from room noise with no caption text, so no overlap event: the gate
  runs only after a real caption, as designed.

Remaining on the board: live speech checks (steps 5 and 6) and the restore (step 7).

## 13. Overnight run 1 · launched 6 November 2026, 00:18

**Device (board `e8:f6:0a:e3:a7:68`).** New build `build/night` (802,784 bytes, SHA `2b7e282d…`):
gate on, speaker labels on, latency profile, **stream metrics on in both arms**, plus test-only
additions, all off unless commanded:
- `overlap on|off|log on|log off|status`: skip the gate at run time without unloading it.
- `STT_OVERLAP {…"logits":"<hex>"}`: every segment's raw int8 gate output, so any rule, threshold or
  run length can be re-evaluated on the host from one night.
- `TL overlap_mem`: free PSRAM and internal RAM just before and after the gate loads. Measured
  cost: **117,352 bytes PSRAM, 96 bytes internal**.
- ESP-DL kernel-bind log (`TL kbind`) switched on before the gate loads: 14 bindings recorded.
- `pcm save on|off`: every final segment's 16 kHz PCM to `/sd/STT PCM/b<boot>/s<seq>.pcm` with
  an `index.jsonl`, so device-microphone audio can be re-scored on the host bit-exactly (card had
  29.5 GB free).

Playback: 14 blocks of about 12 minutes (`tools/overlap_gate/night_playlists.py`; WAVs on the
Audiodrive, manifests in `phase4/night1/`): 1,270 clips, 541 with overlap. They are AMI validation
(600) and test (400) distant-mic windows, the 32 real pairs, synthetic two-speaker (128),
ordinary (32) and quiet (32), LibriSpeech test-clean (100) and DEMAND noise (10). Speech is
levelled to −26 dBFS (quiet −44, noise −40), peak-limited, with a 2.5 s gap after each clip. It
plays through the Mac mini's built-in speaker at **volume 70** (user's choice), with the P4 about
1 ft away and the mic facing it. A 75 s dry run gave 7 captioned segments at volume 50 and 12 at 70.
The source audio is far-field, often accented meeting speech; it is the same in both arms.

Driver `tools/overlap_gate/night_driver.py`: 28 runs (each block gate ON and OFF, order
alternating, fresh boot each via esptool, which re-verifies the MAC), `perf dump` before and
after each run, every serial line recorded with host wall and monotonic time in
`phase4/night1-runs/runs/<run>/serial.log`, events in `events.jsonl`. It holds
`~/claude-heaptw/busy.lock`. At the end, or at the 08:30 deadline, it restores the production
0.99.99 backup app-only after re-checking the MAC, partition table and backup hash, and records the
production boot. The restore checks were exercised on the board without writing before launch.
The expected end is about 06:40.

**Host, in parallel.** `tools/overlap_gate/night_host_queue.sh`: four recall variants of G2c,
declared in `g2_common.PROTOCOLS` before training, one change each: G2d width 64 (34,819
parameters), G2e fourth block at dilation 8 (26,547), G2f 24,000 steps, G2g two-speaker class
weight 2. Each one is trained, exported to int8 and scored by `variant_eval.py` under the exact
device rule on AMI validation. The threshold is re-chosen at ≤2% false alarms on AMI negatives.
G2c re-scored by the same code: R10 threshold 0.360, recall 24.1%, false alarms 1.99%,
matching section 8. AMI test is not read; only a winner gets it, once, after review.

**Noted for the morning.** On-device gate time was 30 ms for a 4 s segment and 91 ms for an 8 s
one, above the 50 ms per 10 s target. It probably comes from recomputing uncached tail rows, since
`TL overlap` logs cached and tail row counts. The fix would be to reuse rows the recognizer already
computed, not to change the gate.

## 14. Overnight run 1 · results and diagnosis (6 November 2026)

**Runs.** All 28 runs completed (00:18–06:13). Production 0.99.99 was restored automatically:
the write was verified and the board booted with `App version: 0.99.99`. The two arms produced
1,368 and 1,372 finals. 2,897 PCM segments were saved with 0 failures. The only failure-pattern
hit was the normal boot reset line in b02-on. Gate time per segment: median 33 ms, p95 114 ms,
max 190 ms (the time issue in section 13 is confirmed).

**Result: the gate never fired.** 0 of 1,368 gated segments were flagged and no frame was
marked. On the device the per-segment maximum P(two) had a median of 0.20, p99 0.41 and max
0.59. The playlist predicted about 130 flags.

**Diagnosis** (`tools/overlap_gate/night_rescore.py` → `phase4/night1-rescore.json`; the card's
PCM was copied to `/Volumes/Audiodrive/stt/overlap-gate/night1-card`, linked as `phase4/night1-card`):
- *Device implementation is correct.* The host int8 gate on the PCM the P4 saved reproduces the
  device's logged posteriors: median max difference 1.8e-8, max 0.043, on all 1,368 segments.
  0 host flags, 0 device flags.
- *The playlist was right.* The host gate on the source clips as played gives 130 flags,
  121 of them on the 541 overlap clips (22%). Overlap vs no-overlap separation of the max-P(two)
  ranking (AUC) is 0.79.
- *The replay chain removes what the gate uses.* After the loudspeaker, the room and the P4 mic,
  that separation falls to 0.59. Every category's median score collapses: AMI 0.70 → 0.22,
  synthetic two-speaker 0.84 → 0.18, and real AMI two-speaker pairs 0.80 → 0.24 (see the correction in section 17).
  Segments were labelled by aligning device sample counters to clip times. All 101 tested segments
  of b01 sat at the same −296 ms lag in cross-correlation with the source, so the labels hold.
- *Not level.* Captured speech is at −61 dBFS against −26 dBFS at the source. Adding +6 to
  +30 dB gain (an exact log-mel offset) gives 0 flags at every step.
- *Not a fixed spectral tilt.* A per-bin EQ fitted on even blocks and scored on odd blocks only
  moves the AUC from 0.60 to 0.62. Per-segment mean normalization gives 0.60. Recall stays 0.
- The speech's frame-energy spread is 14 dB on the device against 16 dB at the source, and the
  quietest frames sit near −78 dBFS. The loss looks like loudspeaker and room smearing more than
  noise, but tonight's data cannot separate the two.

**What this means.** Acoustic replay through the Mac mini speaker is not a valid bench for this
gate: the gate does not survive the replay channel, and its device results say nothing about live
rooms. Phase 4 has shown the implementation, memory and timing on device. Detection on live audio
remains unproven. The 2,897 saved segments are a labelled corpus of the replay channel. They are
useful for a channel-robustness study, but must not be the only adoption evidence. Phase 5: no
variant beat G2c (G2d 21.5%, G2g 20.7%, G2f 20.5%, G2e 14.7% vs 24.1% at 2% FA), and AMI test is
untouched. Caption WER on vs off is not scored yet. Captions are expected to be identical because
the gate runs after the caption.

## 15. G2h · training on replayed audio (6 November 2026)

**Data.** `tools/overlap_gate/replay_store.py` turns the night's saved segments into a labelled
store: features in `/Volumes/Audiodrive/stt/overlap-gate/replay1`, split in `phase5/replay-split.json`.
- *Alignment.* Each run's clock offset comes from segment/clip time matching. The lag is the centre
  of the largest cluster of per-segment cross-correlation lags. 96–100% of segments sit within 20 ms
  of it, except b10-on, where the capture slipped mid-run and only 48 of 98 segments were kept.
  Segments more than 40 ms off are dropped.
- *Labels.* Frames take the playlist clip's counts and collar, plus a 200 ms collar at every clip edge.
- *Split.* Seeded 20261106, by block, both arms together: train 1, 2, 3, 4, 6, 10, 11, 13;
  validation 7, 8, 12; test 5, 9, 14.
- *What may train.* Only replayed AMI-validation clips from training blocks (709 segments). AMI
  test, LibriSpeech test, the synthetic qualification suite, the 32 saved-microphone windows and the
  test noise are frozen evaluation material.
- *Validation change.* The 343 AMI-validation ids replayed in training blocks are removed from the
  AMI validation subsample for every comparison (`g2_common.reduced_validation_subsample`).

**Recipe.** G2h is G2c with 25% of the speech share as replay windows (gain ±10 dB), declared in
`g2_common.PROTOCOLS['g2h']` before training. Checkpoint rule: highest mean of the reduced-AMI and
replay-validation frame ROC areas. Step 8000 was selected. The int8 export has the same size as
G2c: 23,811 parameters, 56,096 B, 25,600 B activation peak.

**Device-rule comparison** (`tools/overlap_gate/replay_eval.py` → `phase5/replay-eval.json`; test
blocks and AMI test not read):

| | G2c | G2h |
|---|---|---|
| Reduced AMI validation: recall at ≤2% FA | 23.6% (2.0%) | 24.8% (1.9%) |
| Replay validation, all clips: frame AUC | 0.578 | 0.759 |
| Replay, all clips, at the AMI threshold: recall / FA | 0% / 0% | 36.0% / 8.9% |
| Replay, all clips, threshold at ≤2% replay FA: recall / FA | 0% | 13.2% / 1.0% |
| Replay, AMI clips only, at the AMI threshold | 0% / 0% | 33.9% / 4.8% |
| Replay, AMI clips only, threshold at ≤2% replay FA | 0% | 28.8% / 1.2% |

**False alarms by clip type**, replay validation at the AMI threshold:

| Clip type | Overlap segments caught | Single-speaker segments falsely flagged |
|---|---|---|
| LibriSpeech test | none in set | 14 of 69 |
| AMI validation | 40 of 118 | 8 of 168 |
| AMI test | 14 of 64 | 5 of 112 |
| Synthetic two-speaker | 22 of 34 | 6 of 34 |
| Real P4 recordings | 6 of 12 | 0 of 2 |

**Reading.** Replay training restores detection through the speaker channel without costing clean
AMI. At the deployable threshold, false alarms on replay are 4–9 times the ceiling. The worst case
is clean read speech (LibriSpeech, 20%): replay training contained only AMI content, so the
replay-channel model has not seen replayed single speakers from other corpora. This is the corpus
shortcut G2b showed, now inside the replay channel. Replay validation is small (118 AMI overlap
segments, about ±8 points on recall) and shares the training channel: same night, room, speaker,
position and volume. It shows the gate can learn a channel. It is not evidence for live rooms.
G2h is not adopted; replay test blocks and AMI test stay unread.

**Next, if replay is pursued.** A second night whose playlist is drawn from *training* splits only:
AMI train, non-AMI single speakers from the G2b/G2c training stores, and training-store two-speaker
mixtures. Then replay covers both classes across corpora, and night 1's validation and test blocks
stay clean. Live labelled recordings remain the evidence that matters for adoption.

## 16. Night 2 (daytime session) and G2i (6 November 2026)

**Session.** 08:03–10:03, user-requested. A training-split-only playlist (`night_playlists.py --set
train`, seed 20261107): 10 blocks, 1.87 h, 900 clips, 397 overlapped. It covers AMI train,
2–8 s crops of one non-AMI training utterance, two-speaker mixtures of non-AMI training crops, and
training noise. The driver gained `--flash-app` (the test app written app-only at 0x10000 with the
restore's MAC, partition-table and hash checks, then the boot to Listening confirmed) and `--arms on`.
- *Device.* Gate on in all 10 blocks: 919 finals, 971 PCM segments saved, 0 failed, 0 crashes.
  Production 0.99.99 was restored (write verified, booted).
- *Noise.* The user showered during blocks 9–10 (water noise, no voices).
- *Store.* `replay_store.py --night 2` → `/Volumes/Audiodrive/stt/overlap-gate/replay2`: 962
  labelled segments, all trainable. 96–100% sit within 20 ms of their run lag in every block; one
  segment fell outside the playlist and is never labelled.

**G2i** (declared in `g2_common.PROTOCOLS['g2i']` before training): G2h with the replay share drawn
from night 1's training-block segments and all night-2 segments. Step 9000 was selected.
Validation and test are unchanged: night 1 blocks 7/8/12 and 5/9/14.

**Device-rule comparison** (`replay_eval.py`; replay test blocks and AMI test unread):

| | G2c | G2h | G2i |
|---|---|---|---|
| Reduced AMI validation: recall at ≤2% FA | 23.6% | 24.8% | 20.5% |
| Replay, all clips, at the AMI threshold: recall / FA | 0% / 0% | 36.0% / 8.9% | 18.0% / 1.0% |
| Replay, all clips, threshold at ≤2% replay FA | 0% | 13.2% / 1.0% | 31.1% / 1.8% |
| Replay, AMI clips only, at the AMI threshold | 0% / 0% | 33.9% / 4.8% | 20.3% / 0.0% |

**At the AMI threshold, by clip type** (overlaps caught, then false alarms):

| Clip type | G2h caught | G2h false alarms | G2i caught | G2i false alarms |
|---|---|---|---|---|
| AMI validation | 40/118 | 8/168 | 24/118 | 0/168 |
| AMI test | 14/64 | 5/112 | 8/64 | 0/112 |
| LibriSpeech test | — | 14/69 | — | 4/69 |
| Synthetic two-speaker | 22/34 | 6/34 | 9/34 | 0/34 |
| Real P4 recordings | 6/12 | 0/2 | 0/12 | 0/2 |

**Reading.** G2i is the first gate within the 2% false-alarm ceiling on replayed audio at the
deployable threshold. Night 2's single speakers fixed most of G2h's read-speech false alarms
(LibriSpeech 20% → 6%). It is more conservative everywhere, though:
- clean AMI recall drops about 3 points (roughly two standard errors on 961 positives);
- it misses all 12 replayed real P4 overlap recordings, where G2h caught 6.

A replay-tuned threshold (0.258 vs 0.368) buys 31% recall at 1.8% FA, so one threshold does not
transfer between clean and replayed audio. The gate's score scale shifts with the channel.

G2i is not adopted. The small panels and the shared channel (same room, speaker, position and
volume) still hold. Live labelled recordings remain the deciding evidence. Night 2's audio is at
`/Volumes/Audiodrive/stt/overlap-gate/night2-card`, its manifests in `phase4/night2`, runs in
`phase4/night2-runs`.

## 17. Live session 1 (6 November 2026, evening, solo)

**Session.** `live_prepare.py --mode solo` and `live_session.py`: a cue page at
127.0.0.1:8765, with the test app flashed using the restore checks and production restored
afterwards (verified, booted). 78 trials of 10 s each:
- 24 *you*: the user reads aloud;
- 24 *voice*: a LibriSpeech test-clean clip from the Mac speaker at volume 70, user quiet;
- 30 *both*: the user reads over the voice.

The P4 saved 118 segments, 0 failed, 0 crashes. The audio is copied to
`/Volumes/Audiodrive/stt/overlap-gate/live1-card` and verified. Segments map to trials by
serial-log time (the trials are 16 s apart).
- *Labels.* Segment level only: a *both* trial counts as overlap. The user was told any words are
  fine; only continuous speech in the go window matters. Frame-level labels were not attempted.
- *Level.* Median −59.8 dBFS (both −57.8, you −60.3, voice −60.6). The earlier P4 recordings
  (`p4-ordinary`, −59.8; `p4-quiet`, −64.0) show this is the P4's normal capture level, about
  17 dB below AMI distant-mic.

**Result** (`phase4/live1-score.json`; host int8 device rule on the saved PCM):

| Gate | AUC of max P(two), overlap vs not | Flagged at its AMI threshold: both / you / voice |
|---|---|---|
| G2c | 0.75 | 0/40, 0/37, 0/32 (also 0 on the device itself) |
| G2h | 0.72 | 0/40, 0/37, 0/32 |
| G2i | 0.76 | 0/40, 0/37, 0/32 |

All three rank overlap above single speech (median max P(two) on *both*: G2c 0.22, G2h 0.66,
G2i 0.67). None reaches the segment rule: R10 marked-frame fraction ≥ 0.36.
- *Voice false positives.* G2h scores the replayed voice alone almost like overlap (0.56).
- *Not a level problem alone.* Boosting the live audio by +9 or +18 dB, an exact log-mel offset,
  gives 0 flags for every gate. G2i's fraction AUC goes from 0.62 to 0.68.

**Correction.** Sections 14–16 described `real32` as real P4-microphone overlap recordings.
They are the 32 real two-speaker AMI validation pairs at the AMI distant microphone (see
`night_playlists.py`). The point stands that the replay chain, not overlap itself, lowered
their scores. They are not evidence about the P4 microphone.

## 6. What is needed from the user

Which P4 to use (MAC), the microSD card for the model copy, and the go-ahead for flashing after
step 2's inspection and backup. Steps 0 and 1 need neither the board nor the card.
