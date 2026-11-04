# Firmware: the speech-to-text engine and a minimal P4X-EYE app

Everything needed to run the models on an ESP32-P4 without the rest of HardwareOne.

| Folder | What |
|---|---|
| `components/hw1_stt` | The engine as an ESP-IDF component: log-mel frontend, ESP-DL int8 QuartzNet runtime, phrase segmenter, word-trigram language model with CTC beam search, model container check. HardwareOne runtime/memory/LM/speaker improvements are ported into standalone adapters; model identity remains pinned independently. See the port report below. |
| `examples/p4_eye_captions` | Microphone to serial captions with SD vocabulary, offline JSONL recordings and persistent startup ordering. No network, accounts or on-device display; an optional localhost USB viewer runs on the Mac. |
| `tools/prepare_esp_dl.py` | Stages the patched ESP-DL 3.3.12 the engine needs (see below). `esp-dl-3.3.12-hw1.patch` is the patch. |

## What you need

- An **ESP32-P4X-EYE** (Espressif's ESP32-P4-EYE board, 32 MB PSRAM, 16 MB flash). The example's pin
  table is for that board: PDM microphone on GPIO22/21 with GPIO12 powering its rail, microSD on
  SDMMC slot 0 (GPIO39-44) with GPIO46 as the card power switch and LDO channel 4. Another P4 board
  means editing the constants at the top of `main.cpp`.
- **ESP-IDF 5.5.5**, exported in your shell.
- A FAT-formatted **microSD card** with a folder `STT Models` holding:
  - `quartznet15x5-gen2-25397.p4.stt`: the packed int8 model (20 MB). The build is pinned to this exact
    file by `components/hw1_stt/stt/stt_model_identity.h`.
  - `meeting.lm`: the word language model (2.5 MB). Optional; without it decoding is greedy and
    noticeably less accurate.
  Both are attached to the `model-gen2-25397` release of this repository.

## Build, flash, run

```bash
cd firmware/examples/p4_eye_captions
python3 ../../tools/prepare_esp_dl.py      # once per checkout
idf.py set-target esp32p4 build flash monitor
```

The staging step copies the published `espressif/esp-dl` 3.3.12 package (from the IDF component
manager cache, or downloaded from components.espressif.com) into `firmware/.sdk-overrides/esp32p4/`
and applies the patch; the component manifest points at that copy. The patch makes the 15x5 model
run about twice as fast on the P4 (conv tiling for its cache, prepared conv arguments, ReLU lookup
tables as a vector max) and adds an allocator hook so the model's metadata lives in PSRAM. Every
change is bit-exact with upstream; the script checks digests before and after patching.

The [standalone port report](../docs/STANDALONE_PORT.md) describes selectable
default, lean and latency/speaker profiles and the completed validation.

On the console you will see the model load (a few seconds for the 20 MB file), then
`Listening`, then a caption after each pause in speech, with the time each stage took:

```
[   12.4 s] okay so the next thing we need to look at is the schedule
            4.6 s of audio in 1180 ms: features 14, model 1011, decode 92 ms, language model
```

Flashing writes only the app partition at 0x10000 when you use `esptool write_flash 0x10000`;
inspect the actual device partition table first and confirm the app fits. Some HardwareOne devices
have a smaller factory slot than this example declares. Back up the installed application and flash
only the app; do not replace an existing partition table to match this example. `idf.py flash` writes the bootloader and partition
table too, which is fine on a board that has never run HardwareOne.

## Using the engine in your own program

`main.cpp` is the whole recipe. The parts, in order:

1. **Audio in**: 16 kHz mono int16 PCM, pushed in any block size into `hw1::stt::Segmenter`
   (`stt/stt_segmenter.h`). It returns a `SpeechSegment` when a phrase ends on a pause or at the
   10 s cap. The example passes the microphone policy into the portable streaming scheduler.
2. **Trim** (optional, off here): cut a pause-ended phrase shortly after its last voiced frame
   (`voiced_end_samples`) to save inference time. The opt-in latency profile keeps 500 ms;
   default full-audio mode preserves quiet endings pending device qualification.
3. **Transcribe**: `hw1::stt::transcribe(...)` (`stt/quartznet_runtime.h`) with a `ModelReader`
   over the model file, a `ModelCache` kept for the whole run (so the 20 MB weights are read and
   verified once), and an optional `Decoder`.
4. **Decode**: the `Decoder` wraps `hw1::stt::lm::decode` (`stt/stt_lm.h`) over a `.lm` blob held
   in PSRAM; return `Fallback` and the engine decodes greedily instead.

The component needs CONFIG_SPIRAM (hex mode, 200 MHz on the P4X-EYE). Inference
periodically blocks after joined model stages so both idle tasks can run; it does
not reconfigure or unsubscribe from the global watchdog.

### Another model

A model you export yourself (`tools/stt_p4/export_quartznet.py`, then `pack_model.py`) comes with a
generated `stt_model_identity.h`. Replace `components/hw1_stt/stt/stt_model_identity.h` with it,
point `kModelPath` in `main.cpp` at the new file name, rebuild. The engine refuses any model whose
size, SHA-256 or frontend contract does not match the header it was built with.

### Speaker labels

`stt/speaker_*.{cpp,h}` (a small speaker-embedding model that labels who is talking) are included
but not compiled by default: configure with `-DHW1_STT_SPEAKER_LABELS=ON`. Enabling that option compiles the standalone background
adapter, which loads `/sd/STT Models/speaker.spk` if the file and caption memory
reserves permit. The model runs single-core below caption inference; a full job
queue produces an unknown label without blocking captions.

### Optional x2f draft pacing

`CONFIG_CAPTIONS_X2F_DRAFT_PACING` enables compute-scaled draft scheduling with a
fresh first-preview budget for each phrase. Layer `sdkconfig.x2f` over
`sdkconfig.defaults` to test only this scheduler change; it does not enable
trimming or change closing pauses. The default remains the legacy scheduler.
Host scheduler/ownership checks pass; standalone P4 quality and latency still
need qualification. See [runtime improvements and evidence](../docs/STT_RUNTIME_IMPROVEMENTS.md).

## Keeping in step with HardwareOne

The engine and ESP-DL patch originated as HardwareOne snapshots. The
[October 31 port](../docs/STANDALONE_PORT.md) reconciles the identified runtime,
LM, speaker-policy and SDK fixes, and extracts a portable streaming scheduler.
Fresh standalone device performance/accuracy qualification is still pending.
Do not overwrite either tree wholesale. Reconcile portable improvements here,
qualify the standalone build and behavior, then adapt the qualified components
for HardwareOne while preserving its platform/session integration.

## Vocabulary and offline recordings

See [the standalone viewer guide](../tools/transcript/README.md) and
[the implementation handoff](../docs/STT_PRODUCT_HANDOFF.md). The app automatically opens a recording
after storage initialization. Serial commands edit vocabulary and start/finish saving notes. Startup
status remains available even when the model card cannot mount. NVS startup counters use only the
`hw1_stt_demo` namespace and never erase the NVS partition on initialization errors.

The browser now receives real provisional drafts and optional background speaker
assignments, alongside explicitly simulated replay fixtures. Word preferences
require a valid optional `meeting.lm`; formatting is independent. `lm strength
0..1` changes the next inference's LM weighting; `status` reports the selected
strength. The default value 1 preserves the existing decoder behavior.
