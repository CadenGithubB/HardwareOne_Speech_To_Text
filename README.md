# HardwareOne Speech To Text

On-device speech-to-text for HardwareOne's ESP32-P4 (P4X-EYE): the tools that train, export, deploy and
test the models. The firmware side (the speech engine, language-model decoder and speaker labels) lives in
the HardwareOne repo under `components/hardwareone/stt`.

- `docs/Version Report.html`: how caption speed, memory and accuracy changed across test versions 1.1-2.0.
- `tools/stt_train_15x5`: QuartzNet 15x5 fine-tuning, data stores and benchmarks.
- `tools/stt_train`: data preparation, the earlier 5x5 trainer, the word language model (`lm/`) and the tech
  vocabulary build (`techvocab/`).
- `tools/stt_p4`: int8 export, model packing, deploy scripts and the speaker-label model exporter (`speaker/`).
- `tools/device_tests`: the speaker-to-P4-microphone test harness and its analysis.
- `tools/report`: regenerates `docs/Version Report.html` from recorded test sessions.
- `tools/speech_portable`, `tools/translation_p4`: earlier portable speech and translation experiments.

The `stt_*`, `speech_portable` and `translation_p4` folders are the same folders as HardwareOne's
`experiments/`, kept in step with `tools/sync_to_hardwareone.sh`. A few `stt_p4` tools work on the
HardwareOne firmware tree (they use paths from its repository root) and run from a HardwareOne checkout.

No speech data, recordings, models or checkpoints are kept here. Paths come from the environment:

| Variable | What |
|---|---|
| `STT_ROOT` | data root: speech stores, training work, logs |
| `CARD` | the mounted microSD card (deploy steps that copy to the card) |
| `HW1_STT_PYTHON` | a Python with the export tooling (esp-ppq) |
| `HW1_STT_P4` | the `stt_p4` folder holding the private firmware trees (`private/`) |
| `HW1_STT_SESSIONS` | recorded device sessions (default `tools/device_tests/speaker/sessions`) |
