# HardwareOne Speech To Text

On-device speech-to-text for the ESP32-P4 (HardwareOne's P4X-EYE): the engine that runs on the chip, a
minimal app that uses it, and the tools that train, export, deploy and test the models.

**Run it on a P4X-EYE:** [`firmware/`](firmware/README.md) has the engine as an ESP-IDF component and a
microphone-to-serial captions example; the model and language model it needs are attached to the
[model-gen2-25397 release](https://github.com/CadenGithubB/HardwareOne_Speech_To_Text/releases/tag/model-gen2-25397).

- [Version report](https://cadengithubb.github.io/HardwareOne_Speech_To_Text/) (`docs/index.html`, served by
  GitHub Pages): how caption speed, memory and accuracy changed across test versions 1.1-2.0.
- `firmware/components/hw1_stt`: the speech engine (frontend, ESP-DL runtime, segmenter, LM decoder) as an
  ESP-IDF component; `firmware/examples/p4_eye_captions`: the minimal app.
- `tools/stt_train_15x5`: QuartzNet 15x5 fine-tuning, data stores and benchmarks.
- `tools/stt_train`: data preparation, the earlier 5x5 trainer, the word language model (`lm/`) and the tech
  vocabulary build (`techvocab/`).
- `tools/stt_p4`: int8 export, model packing, deploy scripts and the speaker-label model exporter (`speaker/`).
- `tools/device_tests`: the speaker-to-P4-microphone test harness and its analysis.
- `tools/report`: regenerates `docs/index.html` (the version report) from recorded test sessions.
- `tools/speech_portable`, `tools/translation_p4`: earlier portable speech and translation experiments.

The `stt_*`, `speech_portable` and `translation_p4` folders are the same folders as HardwareOne's
`experiments/`, kept in step with `tools/sync_to_hardwareone.sh`; `firmware/components/hw1_stt/stt` is a copy of
HardwareOne's `components/hardwareone/stt`. A few `stt_p4` tools work on the
HardwareOne firmware tree (they use paths from its repository root) and run from a HardwareOne checkout.

No speech data, recordings, models or checkpoints are kept here. Paths come from the environment:

| Variable | What |
|---|---|
| `STT_ROOT` | data root: speech stores, training work, logs |
| `CARD` | the mounted microSD card (deploy steps that copy to the card) |
| `HW1_STT_PYTHON` | a Python with the export tooling (esp-ppq) |
| `HW1_STT_P4` | the `stt_p4` folder holding the private firmware trees (`private/`) |
| `HW1_STT_SESSIONS` | recorded device sessions (default `tools/device_tests/speaker/sessions`) |
