# HardwareOne Speech To Text

On-device speech-to-text for HardwareOne's ESP32-P4 (P4X-EYE): the tools that train, export, deploy and
test the models. The firmware side (the speech engine, language-model decoder and speaker labels) lives in
the HardwareOne repo under `components/hardwareone/stt`.

- `docs/Version Report.html`: how caption speed, memory and accuracy changed across test versions 1.1-2.0.
- `tools/train_15x5`: QuartzNet 15x5 fine-tuning, data stores and benchmarks.
- `tools/train`: data preparation, the earlier 5x5 trainer, the word language model (`lm/`) and the tech
  vocabulary build (`techvocab/`).
- `tools/p4`: int8 export, model packing, deploy scripts and the speaker-label model exporter (`speaker/`).
- `tools/device_tests`: the speaker-to-P4-microphone test harness and its analysis.
- `tools/report`: regenerates `docs/Version Report.html` from recorded test sessions.
- `tools/legacy`: earlier portable speech and translation experiments.

No speech data, recordings, models or checkpoints are kept here. Paths come from the environment:

| Variable | What |
|---|---|
| `STT_ROOT` | data root: speech stores, training work, logs |
| `CARD` | the mounted microSD card (deploy steps that copy to the card) |
| `HW1_STT_PYTHON` | a Python with the export tooling (esp-ppq) |
| `HW1_STT_P4` | HardwareOne's `experiments/stt_p4` folder with its private firmware trees |
| `HW1_STT_SESSIONS` | recorded device sessions (default `tools/device_tests/speaker/sessions`) |
