# Isolated P4 execution/equality diagnostic

This test app reuses the actual standalone card/model/LM adapters and portable
scheduler/frontend/runtime. It does not enter the captions app loop, start PDM
capture or play audio. All PCM is generated in memory; no audio upload is needed.

It performs independent checks:

- Six recognition input/output/text hash pairs compare full-cache and committed-
  prefix clearing. Short, medium and maximum-length phrases repeat across cold
  model construction and warm resident reuse. Every retired cache is checked
  completely for zero. Model integrity and actual cached-row use are required.
- A forced speaker execution-isolation probe holds the existing global preparation
  flag in the parent while a separate worker embeds input B. Repeated input A,
  distinct A/B inputs, normal B on that same worker and exact B recovery are
  controls. The installed speaker identity and its embedded trunk self-test are
  checked. A changed/failed forced embedding demonstrates a mechanism; it does
  not prove live overlap or explain an acoustic quality result by itself.
- A direct embedded-trunk fixture matrix reloads the same model/input for
  convolution blocking disabled/24 KiB and single/multi-core execution. It reports
  complete output hashes, unequal/over-tolerance counts and absolute errors.
  Frontend, float pooling and clustering are absent from this comparison.

With `CONFIG_HW1_STT_MODEL_LOCAL_PREPARE=y`, the isolation probe also repeatedly
prepares a real independent model while the worker executes. Preparation must
leave that independent model's input/output bytes unchanged. This is controlled
cross-model concurrency; a single model remains non-reentrant.

`STT_EXACT` JSON separates the isolation observation from the six recognition
pairs. A failed embedded speaker fixture stays an explicit failed contract;
the app reloads a fresh model for the independent isolation/equality checks.
A passed recognition-equality result does not imply that the speaker fixture or isolation passed. This app
is not an accuracy, realtime, production RAM-fit or soak benchmark.

Optional diagnostic CMake settings:

- `-DHW1_SPEAKER_TRACE_REFERENCE=/absolute/private/reference.h` embeds private
  per-layer sample comparisons. The header defines `SpeakerTracePoint` and
  `kSpeakerTracePoints`: module/tensor names, element count, scalar exponent,
  sample count (at most 64), indices and int16 values. The execution plan's
  topological order supplies names because SDK `Module::name` can be null.
  Records explicitly mark the reconstruction unvalidated. Sampling cannot
  establish full-tensor equality; a matching full SHA can only do so when its
  reference was independently checked.
- `-DHW1_SPEAKER_EXACT_RELU_PROBE=ON` doubles the fixture matrix with the SDK's
  existing direct ReLU implementation instead of serialized ReLU lookup tables.
  It changes the creator only during those model loads and restores normal
  deserialization before the self-test, embedding and recognition checks.
  It is a numerical causal probe, not a production configuration or an accuracy
  claim. Model bytes and the original tolerance stay unchanged.
- `-DHW1_SPEAKER_PREPARE_FAILURE_PROBE=ON` requires model-local preparation.
  With the independent worker blocked, it temporarily delegates the installed
  metadata allocator while refusing the fixed speaker model's optional prepared
  blocks. It compares activation bytes, fallback output and normal recovery
  against an ordinary run. This tests allocator-policy rejection, not physical
  heap exhaustion or RAM fit. Build/run this separately; it is off by default.

Keep reference headers, model fixture values and generated artifacts private.
Retain a failed fixture explicitly even when another comparison improves it.

Use ESP-IDF 5.5.5 and the repository's verified staged ESP-DL. For example, from
the repository root, with a reviewed private sdkconfig:

```sh
idf.py -C tools/device_tests/stream/p4_exact -B private/exact-build \
  -DSDKCONFIG="$PWD/private/sdkconfig.exact" -DIDF_TARGET=esp32p4 \
  -DHW1_STT_SPEAKER_LABELS=ON build
```

Defaults supplement the example's 200 MHz profile with 64-byte L2 lines and
assertions. They cannot override an existing sdkconfig. Inspect the generated
configuration, source identities and app size before device use. The build CSV
is only a link-size layout; it must never replace the board's actual table.

The exclusive device controller must verify MAC/partition/rollback, flash only
the app through the approved helper, retain raw logs privately, repeat every
watchdog-bearing image/input/mode unchanged at least once, and restore/readback-
verify the selected app before releasing the lock. Never run during another
owner's bench chain or flash generated partition/bootloader images.
