# Isolated P4 execution/equality diagnostic

This test app reuses the actual standalone card/model/LM adapters and portable
scheduler/frontend/runtime. It does not enter the captions app loop, start PDM
capture or play audio. All PCM is generated in memory; no audio upload is needed.

It performs two distinct checks:

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

`STT_EXACT` JSON separates the isolation observation from the six recognition
pairs. A failed embedded speaker fixture stays an explicit failed contract;
the app reloads a fresh model for the independent isolation/equality checks.
A passed recognition-equality result does not imply that the speaker fixture or isolation passed. This app
is not an accuracy, realtime, production RAM-fit or soak benchmark.

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
