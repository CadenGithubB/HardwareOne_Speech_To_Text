# Firmware: the speech-to-text engine and a minimal P4X-EYE app

Everything needed to run the models on an ESP32-P4 without the rest of HardwareOne.

| Folder | What |
|---|---|
| `components/hw1_stt` | The engine as an ESP-IDF component: log-mel frontend, ESP-DL int8 QuartzNet runtime, phrase segmenter, word-trigram language model with CTC beam search, model container check. `stt/` is HardwareOne's `components/hardwareone/stt` unchanged (branch `stt-speedups`, commit 2e56063); the three headers beside it replace the firmware's own. |
| `examples/p4_eye_captions` | Microphone to captions on the serial console. About 400 lines, no network, no accounts, no display: the smallest program that uses the engine the way HardwareOne does. |
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

On the console you will see the model load (a few seconds for the 20 MB file), then
`Listening`, then a caption after each pause in speech, with the time each stage took:

```
[   12.4 s] okay so the next thing we need to look at is the schedule
            4.6 s of audio in 1180 ms: features 14, model 1011, decode 92 ms, language model
```

Flashing writes only the app partition at 0x10000 when you use `esptool write_flash 0x10000`;
the partition table matches HardwareOne's P4X-EYE image, so a HardwareOne device can run this
example and be flashed back the same way. `idf.py flash` writes the bootloader and partition
table too, which is fine on a board that has never run HardwareOne.

## Using the engine in your own program

`main.cpp` is the whole recipe. The parts, in order:

1. **Audio in**: 16 kHz mono int16 PCM, pushed in any block size into `hw1::stt::Segmenter`
   (`stt/stt_segmenter.h`). It returns a `SpeechSegment` when a phrase ends on a pause or at the
   10 s cap. The settings in `captureTask` are the ones HardwareOne uses for this microphone.
2. **Trim** (optional, off here): cut a pause-ended phrase shortly after its last voiced frame
   (`voiced_end_samples`) to save inference time. HardwareOne keeps 200 ms; in a test here with a
   quiet loudspeaker that lost soft final words, so the example sends the whole phrase.
3. **Transcribe**: `hw1::stt::transcribe(...)` (`stt/quartznet_runtime.h`) with a `ModelReader`
   over the model file, a `ModelCache` kept for the whole run (so the 20 MB weights are read and
   verified once), and an optional `Decoder`.
4. **Decode**: the `Decoder` wraps `hw1::stt::lm::decode` (`stt/stt_lm.h`) over a `.lm` blob held
   in PSRAM; return `Fallback` and the engine decodes greedily instead.

The component needs CONFIG_SPIRAM (hex mode, 200 MHz on the P4X-EYE) and leaves the task watchdog
alone except for one thing: while the model runs it stops watching core 0's idle task, because
inference deliberately keeps both cores busy (`quartznet_runtime.cpp`, top).

### Another model

A model you export yourself (`tools/stt_p4/export_quartznet.py`, then `pack_model.py`) comes with a
generated `stt_model_identity.h`. Replace `components/hw1_stt/stt/stt_model_identity.h` with it,
point `kModelPath` in `main.cpp` at the new file name, rebuild. The engine refuses any model whose
size, SHA-256 or frontend contract does not match the header it was built with.

### Speaker labels

`stt/speaker_*.{cpp,h}` (a small speaker-embedding model that labels who is talking) are included
but not compiled by default: configure with `-DHW1_STT_SPEAKER_LABELS=ON`. The example does not use
them; HardwareOne's `System_STTLocal.cpp` shows how.

## Keeping in step with HardwareOne

The engine source is a copy, not a fork: `components/hw1_stt/stt/*` should stay byte-identical to
`components/hardwareone/stt/*` in HardwareOne except `stt_model_identity.h` (HardwareOne pins its own
deployed model). The patch and `prepare_esp_dl.py` mirror HardwareOne's `tools/p4/`. When either side
changes, copy the files across and rebuild the example.
