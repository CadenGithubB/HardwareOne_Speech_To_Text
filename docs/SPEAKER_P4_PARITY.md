# Known-PCM P4 speaker diagnostic

This checks the existing quantized P4 speaker path against the unchanged Mac
float model using identical int16 PCM. It bypasses playback, the microphone and
live segmentation. It is a diagnostic, not a new speaker rule or a qualified
accuracy/performance improvement.

`tools/device_tests/speaker/patches/p4-speaker-parity-aa6508fd.patch` applies only
to HardwareOne aa6508fd. It enables the existing diagnostic mode, changes its
optional fixture to a separately owned test filename, and emits the normalized
embedding in eight-value chunks with an explicit end marker. The normal model,
frontend and cluster policy are unchanged. This patch must not be integrated
as an enabled production feature: diagnostic mode adds other probes and work.
The private source bundle preserves commits f91cd415 and 0637d23f.

`p4speakerparity.py` does not flash. `prepare` exclusively creates the named SD
test fixture and records ownership, uploads it, then reads it back byte for byte.
`run` reads it back before every boot trial, starts normal PDM STT, collects the
vector, waits for warm/capture readiness and the speaker-load summary, compares
the vector against the firmware cosine, and stops/drains. `cleanup` deletes only
that owned file after verifying its bytes (or an interrupted upload's matching
prefix). The speaker model file is never written. Existing output is preserved.
All commands require ignored private output paths. Credentials are supplied via
`STT_TEST_USER` and `STT_TEST_PASSWORD`; the only allowed MAC is
`e8:f6:0a:e3:a7:68`.

```sh
python3 tests/test_p4speakerparity.py
python tools/device_tests/speaker/p4speakerparity.py prepare \
  private/speaker/example.bin private/speaker/example-test
python tools/device_tests/speaker/p4speakerparity.py run \
  private/speaker/example.bin private/speaker/example-test --trials 5
python tools/device_tests/speaker/p4speakerparity.py cleanup \
  private/speaker/example.bin private/speaker/example-test
```

Use the serial-capable IDF Python environment. A fixture consists of little-endian
uint32 sample count and embedding dimension, int16 PCM, then float32 reference
embedding. The exporter's original fixture reference is simulated-quantized,
not float; the experiment regenerates the reference with the unchanged float
checkpoint and verifies that its projection head matches the shipped model.
Do not accidentally describe the export fixture as a float reference.

Before app-only flashing, verify the device MAC and actual partition table, keep
the original full app-slot image privately, and check image size. Only the app at
0x10000 is written. Never use the generated whole-device flash command. Restore
and verify the original app even after a failed trial. Check LittleFS above
2 MiB and system file logging inactive before and after each test. No microphone
recording or playback is necessary for this comparison.

Long log lines were truncated on the real device. Counting numeric tokens alone
was insufficient because a truncated final number can remain syntactically
valid. The current parser requires the end marker, bounded eight-value chunks,
complete dimensions, finite values, a tight unit-norm check, and agreement with
the firmware's four-decimal fixture cosine. Synthetic cases cover truncation
and the later arrival of the load-summary line. Earlier incomplete measurements
are excluded. Captured vectors and raw logs remain private.

Results and limits are recorded in [AB_TEST_RESULTS.md](AB_TEST_RESULTS.md).
Identical-input cosine is not speaker accuracy. Five reboots of a fixed input
measure repeatability, not generalization. Session-span inputs are clean source
audio projected onto estimated device spans; they are not the original captured
microphone PCM. This diagnostic cannot attribute microphone/channel loss or
establish float-versus-int8 P4 RAM or runtime tradeoffs.


## Exact microphone-input probe

The additional local source commit 8692ce8d and
`patches/p4-speaker-pcm-aa6508fd.patch` add a bounded diagnostic writer.
`p4speakerpcm.py prepare private/...` exclusively creates four 32-byte arm files
in the SD captures directory, each with a fresh 128-bit nonce, sequence and
47,840-sample limit. The worker writes only matching pre-existing armed files,
after embedding/assignment/publication, holding the filesystem lock. It never
creates files itself or overwrites completed captures. Normal model/rules are
unchanged, system file logging is never enabled, and this instrumented app is
not a performance candidate.

The output format is `<8s16sIIII`: magic `SPKPCM1`, nonce, sequence, retained
phrase samples, model-input samples and dimension, followed by int16 model-input
PCM, raw float32 FC embedding and SHA-256 over preceding bytes. Raw FC output
is finite/nonzero but unnormalized; cosine consumers normalize it.
`fetch` validates identity, bounds and checksum and stores data privately;
`cleanup` removes only nonce-owned files, preserving incomplete data for recovery.
After the diagnostic run the original app must be restored and verified.

`spkpcmaudit.py` compares actual-input P4 and unchanged float embeddings and
aligns microphone PCM to the clean waveform independently of console timing.
`spkcuts.py` audits captured/retained/center-window geometry against manifest
energy envelopes. Neither energy envelopes nor a low correlation are human
phonetic/voice annotations. Synthetic tests cover retained tails, coverage,
known waveform delay/polarity, checksum/nonce validation and unnormalized vectors.
No PCM, voiceprints or raw logs belong in Git or the numeric report.
