# PCM-file bench for the P4X-EYE

These tools measure STT speed, accuracy and stability on the board with deterministic input. The
firmware reads a 16 kHz PCM file from the SD card at real-time pace instead of the microphone
(`sttperf pcmsrc PATH`). Identical audio then gives identical word error rate (WER) and speaker
labels on every run. Model speed varies about ±0.5% and close latency about ±3%.

## Firmware

HardwareOne branch `claude/stt-bench` adds `sttperf pcmsrc`, tuning knobs and off-by-default crash
diagnostics. It builds on `claude/p4-l2-64` (64-byte L2 cache lines). Every knob defaults to
production behaviour.

`build_arms.sh "NAME X FIRST_FAST END_SILENCE_MS SHORT_CLOSE_MS" …` builds one image per arm. Its
first line explains the macros it sets and where the output goes. Other knobs in `System_STT.cpp`
and `System_STTLocal.cpp` (speaker core, cluster rules, diagnostics) are set the same way, by
editing their `#define` defaults.

## Running (on the machine with the P4 attached)

`heaptw_remote.py` works in `~/claude-heaptw`, which holds the following:
- `device-login`: mode 600; the tool never prints it, and logs scrub it.
- `find_p4_port.py`: a copy of `../find_p4_port.py`.
- The bench images.
- `conv1/` (`playlist.wav` and `manifest.json`).

| Command | What it does |
|---|---|
| `heaptw_remote.py flash bench-NAME.bin` | Checks the board MAC and partition-table hash, then writes and verifies the app slot at 0x10000 only. |
| `heaptw_remote.py bench LABEL /sd/recordings/bench_conv1.pcm N` | N runs, about 4.5 minutes each, with a fresh boot per run. Writes `bench-LABEL-<time>/serial-K.log` and `bench.json`, and ends each run with `sttperf stages` (per-layer model time). |
| `heaptw_remote.py startloop LABEL PCM\|mic N` | Session starts only, about 40 s each. This is the crash reproducer for the session-start class. |
| `heaptw_remote.py soak LABEL CLIP PCM\|none N SECONDS` | Production soak: live sessions with the clip played on the speaker. It never stops on a failure. |
| `heaptw_remote.py upload WAV DEST` | Converts a WAV to PCM on the SD card. |

The console sets `TIOCEXCL` on the serial port. Another program's open, such as an esptool probe
whose connect sequence resets the P4 into download mode, fails with EBUSY instead. Chains such as
`arms1-chain.sh` hold `~/claude-heaptw/busy.lock` while they use the board; leave the board alone
while that file exists.

## Scoring

| Tool | Reports |
|---|---|
| `benchscore.py MANIFEST DIR…` | WER, speaker accuracy and unknowns, close latency, speaker-label lag, model ms per audio ms and drafts. Writes `score.json`. |
| `truelag.py MANIFEST DIR…` | Time from each clip's true speech end (from the manifest) to its final caption. It does not depend on segmentation, so it compares arms with different phrase-closing rules. |
| `latsplit.py DIR…` | Each phrase split into pause, queue, model and decode time, by phrase length and by whether a speculative final was used. |
| `draftlag.py DIR…` | First-draft delay and the time-averaged lag of the shown text. |
| `benchsets.py` | Device voiceprints (`TL spke2`, with speaker diagnostics on) as `../speaker/spkrules.py` sets. `check` replays the production clusterer decision for decision. |
| `crashsum.py DIR…` | One line per serial log, with the crash signature. |
| `mmanalyze.py` and `mmstate.py` | Decode the memmove and SDMMC DMA logs of the diagnostic arms. |

Host results do not prove model accuracy, realtime performance or SD power-loss behaviour on the
board; only board runs do.

## Upload acknowledgements

`upload_chunks.py` supplies `write_chunk(console, destination, offset, payload)` for the local
`heaptw_remote.py` uploader. It accepts only a reply carrying the current chunk's expected end
offset. A delayed success for an earlier chunk cannot advance the upload; a retry whose write
already committed can accept the firmware's `Offset mismatch` response at that exact end offset.
An unexpected pre-existing end offset on the first attempt is rejected.

Run `python3 tools/device_tests/bench/test_upload_chunks.py` for the delayed-reply, duplicate-retry,
wrong-offset, write-failure and command-size regression cases. The helper module must be installed
beside the local remote script when that script imports it.

The mini's local uploader also supports `upload WAV DEST START_OFFSET [quiet-ble]`. Resume only an
owned partial file from the same converted PCM, using its recorded committed offset. `quiet-ble`
is an explicit bench upload mode for the configured Bluetooth-enabled boot state: it temporarily
attempts to close the Bluetooth runtime and restores it afterward, without changing saved settings.
The first physical attempt failed to stop the ring owner; this mode is not yet qualified.
The normal upload path needs authentication only and allows 90 seconds for startup replies;
it does not require STT live logging. Sensor polling is paused only for
the transfer and resumed if this upload acquired the pause. Bench runs use their normal fresh boot;
upload quieting is not a change to the measured STT configuration.

## Live experiment scoring

`score_experiments.py STATUS.json [...] --out private/report.json` reads finalized
captures from the experiment controllers. It never opens a device port. Outputs are
numeric metrics and provenance, without caption text. Incomplete entries and scoring
errors remain visible; successful builds or queued controllers are not results.

The report includes pooled WER, both majority and actual one-to-one speaker metrics,
unknown/missing-label coverage, ±0.5 s reference-alignment sensitivity, speaker wall
cost and draft overlap, memory low-water observations, decoder status/strength and
file beam, hard boundaries, speculative promotions and vocabulary activation. Captions
without embeddings or speaker labels stay in the applicable speaker denominator as
unknowns; diagnostic-only metrics are reported separately. Mixed/no-reference phrases
are still excluded explicitly, so compare counts as well as percentages.

`truelag.py`, `latsplit.py` and `draftlag.py` outputs are retained per capture. Live
manifest-end latency depends on estimated playback onset and reference clip endpoints;
it is provisional. The printed LM beam is the file beam: a requested override requires
checking its compiled source and successful decoding; do not read it as the effective
beam. Cancellation/preemption and decoder unavailability are separate status counts.
A positive `vocab_test` flag proves term presence, not transcription improvement.

Run `python3 tests/test_experiment_scoring.py` for clock, activation, and missing-label
coverage checks. A report is evidence for review, not an automatic promotion decision.

For vocabulary trials, add `--vocab-config private/.../experiment.json`. Exact canonical
term hits, control insertions and global excess term occurrences are separate metrics.
Captions spanning multiple reference clips receive no clip-level credit; their term
occurrences remain in a mixed-attribution counter and the global count. Terms outside
all reference clips are also counted separately. Missing target captions remain in the
target denominator. Pooled raw WER is unchanged; no alias or formatting rewrite hides
spelling/tokenization differences. Treat clip attribution as provisional when audio
alignment is uncertain, and never interpret zero attributable insertions as proof when
mixed/unattributed terms are present.

`playback_alignment.py` provides a tested estimator for future instrumented repeats:
combine a board-status round trip, an observed CoreAudio output-IO start and output
pipeline estimate. It explicitly rejects already-running output, missing transitions
and invalid clock data. It does not measure acoustic onset or snapshot age, and is
not retroactively applied to earlier captures. Existing queued controllers still use
their recorded sample-offset estimates; keep their timing limitations visible.

`close_test_peers.py` handles setup teardown acknowledgements without conflating an
explicit deferred response with silence. It retries only recognized transient
`closering`/`closeg2` replies, with bounded waits; authentication errors and real
command timeouts fail immediately. It uses the already-owned approved Console,
opens no port, and must run before recording. Existing completed captures retain
their original setup path. Run `tests/test_close_test_peers.py` for observed deferred
reply, success, bounded exhaustion, authorization and timeout cases.

## Live-speaker experiment alignment

Live microphone playback is less deterministic than SD PCM input. A status reply's
sample count can already be stale when `afplay` starts. Keep the original capture,
manifest and status estimate; do not select a timing shift by speaker accuracy or WER.

`align_experiments.py STATUS.json --out private/alignment.json` (requires numpy)
fits a secondary estimate using the logged host/device clock bridge and playlist
RMS envelope against capture-task `TL level` telemetry. It never reads caption text
or speaker labels to fit the offset. At least 50 level points, correlation ≥0.65
in all/even/odd subsets, split agreement within 100ms, and an interior search peak
are required. These checks reject weak/inconsistent fits; agreement does not prove
absolute precision. The level timestamps are wall-clock samples, not recorded raw
microphone audio or sample-clock acoustic correlation. Retain ±0.5s sensitivity.

`score_experiments.py STATUS.json --alignment-report private/alignment.json --out private/corrected.json`
requires a usable fit for every scored capture and matching log, bench and WAV hashes.
It retains the original estimate and correction provenance in the numeric output.
Use a distinct output file from the original-estimate report. No capture or original
manifest is overwritten. Missing/rejected fits are errors, not silent fallbacks.

For live captures, scoring rebuilds reference times from `FIXTURE/manifest.json`
next to the status file/capture directories and verifies the original clip boundaries.
It translates **all** clock fields, including `speech_end_s`, before invoking `truelag`.
Early private live harnesses shifted only `start_s`/`end_s`; their direct `truelag`
outputs overstated latency and must be rescored. Caption-based WER is unaffected by
this clock-field repair. Speaker attribution and true lag still depend on alignment.
SD PCM bench input and production firmware are unchanged by these analysis tools.
