# Standalone capture-lock qualification tools

These tools exercise the portable C++ scheduler and the standalone product-event
protocol. They do not use HardwareOne commands or upload audio.

## Deterministic replay

Run from the repository root:

```sh
python3 tools/device_tests/stream/replay_stream.py --out private/replay-control
python3 tools/device_tests/stream/replay_stream.py --metrics --clear-committed --out private/replay-prefix
python3 tests/test_stt_stream.py --metrics
python3 tests/test_stt_stream.py --metrics --thread-sanitize
```

The replay compiles the actual scheduler/frontend with address/undefined
sanitizers. Each output directory contains fourteen traces, raw PCM/frontend payloads
and a digest manifest. Compare the JSON and payload digests for corresponding
cadence/scenario pairs. This does not execute the acoustic model or LM.
`--component` can select an independently frozen older component. Do not request
`--clear-committed` with a component that predates that configuration field.

## Acoustic capture

`standalone_capture.capture(remote, wav, directory, fixture)` is a Python helper,
not a board ownership manager. Its caller must hold the board lock exclusively,
verify the actual MAC/partition table and private rollback, flash through the
approved helper, and restore/readback-verify the selected app in a finally block.
Do not run it against an active board owner. The helper resets via the approved
Console, uses standalone JSON events, stops note saving while retaining live
microphone capture, and plays an existing mono int16 WAV through Mac mini Speakers
at 50%. It does not upload the WAV or change vocabulary/decoder settings.

The instrumented image must have a 1,000-row feature pool and speaker support.
A fresh private directory receives capture.json and raw serial.log. The capture
records source WAV identity, helper identity, decoder strength, vocabulary digest,
playback launch timestamps, complete events, diagnostics and failure outcomes.
Firmware/source/config/model identity and board ownership/rollback evidence belong
to the enclosing controller manifest. Partial and failed runs must be retained.

`metrics=False` supports a separately built probes-off overhead control. It sends
no perf commands and rejects unexpected probe events. This mode has no DMA-loss
counters or qualified sample-RMS alignment: a complete capture is not evidence
of zero DMA loss, and the instrumented scorer must not be used to invent timings
for it. Compare available outcomes and existing worker timing logs separately.

## Scoring

The scorer requires NumPy in the selected Python environment:

```sh
python3 tools/device_tests/stream/score_standalone.py private/RUN \
  --manifest private/FIXTURE/manifest.json --out private/RUN-score.json
```

Use the canonical reference manifest. Scoring verifies the WAV digest, parses
complete bounded telemetry, and fits sample-indexed RMS independently of text and
speaker labels. The sample-rms-v1 gates require correlation, even/odd and temporal
half agreement, and a unique peak in a fixed search region. Invalid evidence
withholds reference-identity/timing claims while retaining WER and raw label
coverage. A rejected fit is not a reason to widen gates after candidate scoring.

WER is word edits/reference words. Speaker identity uses a best one-to-one
assignment with explicit no-reference/mixed exclusions. Unknown and missing
updates remain separate coverage outcomes. Publication lag uses host receipt,
qualified onset and a minimum-delay host/device clock bridge; it is not a direct
measurement of pixels appearing on screen. Sparse scalar RMS is not captured
microphone PCM. Preserve missed reference-end counts beside latency distributions.

`telemetry.py` validates paged counters and histogram mass/storage. Percentiles are
bucket ranges; saturated histograms yield no percentile. Diagnostic level-queue
loss, feature-cache fallback, phrase drops and driver DMA loss are distinct.
Report startup/boot minima separately from steady-state or inference peaks.

The controlling gates, ABBA order, mandatory watchdog repeats and soak requirement
are in docs/STT_CAPTURE_LOCK_PLAN.md. Actual results and unchecked items belong in
docs/STT_CAPTURE_LOCK_RESULTS.md and the product handoff. No helper grants
permission to promote production defaults or synchronize another checkout.
