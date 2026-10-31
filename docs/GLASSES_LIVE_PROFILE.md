# Glasses STT profile — 31 October 2026

## What was measured

Firmware 0.99.99 on the connected P4X-EYE, native G2 Conversate, live speech from
the wearer. The useful observation window was 48.27 s, with six complete final
segment records and 21 memory snapshots. All six segments completed successfully
with the language model. Captured segments were 2.95–5.66 s long. Cold startup was
not captured: the wearer had already started the session.

All requested STT/microphone/Bluetooth debug flags and per-frame microphone logs
were enabled. `loglink on` routed ESP-IDF output through the firmware queue.
Showcase polling was paused during the observation and resumed afterward.
File logging and transcript saving were off. The session was neither started
nor stopped by the observer; it remained under the wearer's control.

An earlier observation captured 12 useful memory samples and several final
records, but raw ESP-IDF output interleaved byte-by-byte with a JSON memory
reply. That observation's sampler timed out. It was preserved privately and
excluded from the primary statistics below. The second observation, with
`loglink` enabled, had zero missed memory reports. Logging synchronization itself
can change overhead, so do not combine the two conditions as one benchmark.

Reproduce the numeric summary from the private capture with:

```sh
python3 tools/report/analyze_glasses_profile.py private/performance/active-glasses-20261031-104631
```

`performance-glasses-live.json` contains numeric-only evidence. Raw serial text
and per-session records remain under ignored `private/performance/`.

## Caption path

| Mean per final segment | Time |
| --- | ---: |
| Load/setup | 7.5 ms |
| Frontend | 24.5 ms |
| Acoustic inference | 1,214.8 ms |
| LM decode | 55.3 ms |
| Remaining handoff/worker time | 25.8 ms |
| Worker start to final processing done | 1,328.0 ms |

Acoustic inference was **91.5%** of worker elapsed time in this sample. This is
not a speedup claim against the earlier 8–10 s phrases; these phrases and audio
conditions are different.

Segment-close to final-processing-done averaged 1,080.7 ms (range 340–1,956 ms).
Four finals adopted speculative inference that had already started before the
segment closed. Therefore worker duration and post-close delay must not be added:
they overlap. These delays exclude the earlier endpoint decision and physical
display drawing. Audio-sample clocks and VAD estimates are not a ground-truth
speech-end reference. Use device `q`, `s`, and `e` timestamps for these comparisons,
not serial arrival times or the ESP-IDF log prefix.

Five final caption acknowledgements were observed, 45–63 ms, with `err=0`.
One segment has no matching send/ACK in the capture. ACK confirms the protocol
reply, not that text was physically drawn at that instant. Save-hook intervals
were 0–1 ms with saving off, so they do not measure SD saving performance.

Capture-time features supplied 94.1% of the final feature rows. The frontend
is already a small part of the caption path; replacing it is a lower-priority
speed target than inference.

## All acoustic-model work, including previews

Complete before/after snapshots of all 201 stage counters were received. Their
completed-run count increased from 407 to 428: **21 complete model passes for
six final segments**. The timeline also shows 15 successful drafts and six
canceled/failed draft attempts; four finals were speculative promotions.

The counter delta contained approximately 17.94 s of accumulated stage wall time:

| Layer class | Share |
| --- | ---: |
| 512→512 pointwise convolutions | 57.1% |
| Other pointwise convolutions | 14.1% |
| Depthwise convolutions | 24.2% |
| Add/ReLU | 4.6% |

Shares use the bundled 201-node graph mapping. Firmware reports integer average
microseconds; reconstruction from rounded averages has a combined stage-total
rounding bound of about 168 ms for this delta. Snapshots are not synchronized
with model execution, and canceled partial-stage work can contribute without
incrementing completed runs. These are approximate wall-time shares, not an
exclusive CPU-utilization measurement or a standardized five-second inference.

## Memory

The reported PSRAM heap was 32,851,892 B. Lowest sampled free PSRAM was
2,763,720 B (**2.64 MiB**), versus about 3.18 MiB free in quieter snapshots.
Lowest sampled internal free heap was 199,347 B (**194.7 KiB**); its largest
free internal block was 100,352 B (**98 KiB**).

The log also reported boot-wide minima of 2,502,104 B PSRAM and 92,200 B internal
heap. Those counters include earlier activity. They are not newly measured
phase peaks or attributable to these six phrases. Two-second snapshots can miss
transient allocations and do not establish the true session peak.

The allocation reference combines the pinned graph, card listing and the
inspected integrated firmware's allocation constants:

| Reference allocation | Bytes | Evidence |
| --- | ---: | --- |
| Cached speech model | 20,112,128 | Pinned raw graph size; model stays in PSRAM |
| LM blob | 1,599,996 | Current `meeting.lm` card size; finals report LM use |
| Five 10 s PCM buffers | 1,600,000 | Working buffer + three queued slots + draft buffer |
| Capture feature pool | ~651,272 | Two float row caches + PCM ring + workspace |

At the sampled PSRAM low point, these reference sizes leave about **5.84 MiB
of used heap unattributed**, in addition to 2.64 MiB free. That remainder includes
the speaker runtime, resident activation arena, model metadata/prepared arguments,
decoder workspaces and other app allocations. This is not an allocator trace:
do not treat source-derived sizes as phase-by-phase measured ownership. The
speaker file on SD is 1,994,544 B; its file size is not its total runtime RAM cost.

Four speaker completions were observed. Their reported wall durations ranged
from 921 to 6,938 ms, with label lags of 1,117–6,960 ms. Speaker work is scheduled
in the background and can be preempted by higher-priority acoustic work, so
these durations do not prove that a speaker inference consumes seven seconds
of exclusive CPU. They must not be added to caption delay. Two final speaker
completions were not captured in this window.

## Bluetooth and storage

Native audio counters increased by 1,060 packets across 53.267 s of their own
audio-span clock, about 19.90 packets/s. Before/after counter queries bracket a
slightly longer interval than the memory sampling window. There were zero new
reported lost packets, duplicates, LC3 decode failures, PLC frames or overruns.
The session maximum inter-packet gap counter reached 107 ms; that is a
session-to-date maximum, not a maximum isolated to this window.

These observations support a healthy packet path in this sample. They do not
measure absolute microphone-to-P4 transport latency or long-run radio reliability.

The speech-model weights are cached in PSRAM, not streamed from SD/flash for
every layer. The inspected runtime still validates a 96 B logical SD model
header per call. File open/stat/header/close latency was not independently timed;
the 7.5 ms setup metric must not all be labelled storage reads. Physical SD
transactions can differ from logical byte requests because of buffering/caches.

Internal SPI-flash instruction/rodata fetches, cache misses, PSRAM bandwidth and
bus contention were **not instrumented**. File logging being off does not prove
there were no other background audit/event writes. Internal storage remained
healthy after the sample: 8,343,552 B free, 10% used.

## Best next experiments

1. **Draft cadence A/B.** Compare the current preview policy with fewer preview
   passes on identical audio, keeping final decoding unchanged. Measure first
   useful draft, final latency, acoustic-model stage totals, RAM and dropped audio.
   Fifteen successful previews for six finals make this a concrete aggregate-work
   target. Speculative promotion demonstrably helps some final delays, so avoid
   removing it blindly.
2. **Pointwise kernel/cache blocking.** About 71% of observed stage time is in
   pointwise layers, especially the 512-channel blocks. Profile instruction/data
   cache events and PSRAM traffic before changing memory placement. Preserve
   bit-exact logits for kernel/layout changes. Larger cache configurations need
   an internal-RAM/fragmentation check; free bytes alone are not sufficient.
3. **Speaker isolation.** Repeat with speaker labels enabled/disabled on the same
   audio. Separate true speaker compute from preemption and queue delay; attribute
   its live model/arena bytes. The long label lags and low PSRAM headroom justify
   this comparison, but the current sample does not establish a speaker-caused
   caption slowdown.
4. **Fill the measurement gaps.** Add bounded per-phase live-allocation accounting,
   largest-block sampling, SD read-call timing/counts, and chip-supported cache/bus
   counters. Keep a lean control run to quantify profiling overhead. Serial logs
   alone cannot establish physical flash-read traffic.
5. **Accuracy corpus.** Use known reference speech for names/technical words, soft
   endings, noise and silence before judging trimming, LM/custom-word changes or
   retraining. No WER or speaker-accuracy score can be inferred from this unlabelled
   live conversation. Formatting is separate from recognition accuracy.

No recognition algorithm, model, training data, firmware image or device partitions
were changed. The only new device setting in this observation was runtime
`loglink on` for reliable diagnostics; it remains on. Requested debug flags remain
enabled, and system file logging remains off.
