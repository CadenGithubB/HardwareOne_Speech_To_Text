# P4 STT A/B results

31 October 2026. **In progress; no optimization has been qualified.** The
fixed gen2-25397 model, onboard PDM microphone and Mac speaker are used. The
historical speaker-to-microphone recordings used 75% output. Future playback is
50% by user request; overnight work is silent. Raw audio, captions, logs and flash images are
private and are not included here.

## Qualification and safety

- USB MAC matched the designated P4. The read-back partition table places the
  app at `0x10000`, length `0x715000`, and LittleFS at `0x725000`.
- A complete 7,426,048-byte app-slot rollback image was saved privately before
  testing and verified against the device. The matching rebuilt baseline was
  subsequently flashed at `0x10000` only. The preview-cadence and speaker-off
  candidates were tested there, then the original full app slot was restored
  and verified. Subsequent diagnostic blocks use temporary app-only images with
  mandatory original-slot restoration and verification. No other partition
  was flashed; per-block restoration results appear with their measurements.
- A 75% qualification run completed 39 final chunks with zero reported audio
  overruns and no fault markers; LittleFS afterward had 7,507,968 bytes free.
- One earlier qualification run reported an IDLE1 task-watchdog warning during
  inference and was excluded. It subsequently drained 40 segments with zero
  reported overruns and 7,524,352 bytes free.
- In the measured debug block, five sessions completed without fault markers or
  reported overruns. The fifth and its first replacement asserted in the TLSF allocator during
  shutdown and rebooted. Two later replacements reported task-watchdog warnings
  without reboot. These four attempts are excluded from complete-playback
  statistics and retained in the fault count.
- The reduced-logging block has five clean sessions, one FreeRTOS queue
  assertion followed by reboot, and one watchdog warning without reboot.

## Comparisons

| Comparison | Evidence / sample counts | Outcome |
| --- | ---: | --- |
| Debug vs lean logging | 5 / 5 | No clear difference; fault-affected attempts retained separately |
| Preview cadence | 5 / 5 | Fewer previews, later first preview; not a qualified win |
| Speaker labels and conversation accuracy | 5 / 5 standard; 7 conversation runs | Speaker-off is not a qualified replacement; speaker diagnostics below |
| Pointwise kernels and traffic | 1 profile; 5 reboot comparisons | Address-walk candidate preserves hashes, no measurable gain; traffic remains unmeasured |
| Feature-cache ownership | 7 forced-schedule boots; 5 complete lifecycles, 2 faults | Narrow repair passes 42 checks; application qualification incomplete |
| RAM attribution and right-sizing | 5 / 5 speaker on/off; phase observations | Sampled speaker attribution; transient peaks and resizing pending |
| LM strength and technical vocabulary | 5 technical recordings; no strength A/B | Descriptive WER recorded; no configuration tuning in the code-only queue |

No win is claimed without the requested matched runs and confidence intervals.

These are stress-test outcomes under serial polling, periodic memory reports and
repeated start/stop cycles. The user reports that crashes are uncommon in their
ordinary STT/transcription use. These experiments do not establish real-world
crash frequency or isolate the cause of an assertion.

## Logging control

Five complete standard-playlist sessions per arm at 75% on the original
installed app; debug and control runs were collected in blocks, not randomized.
The installed image differed in bytes from the later local rebuild, so these
measurements are not reused as a matched baseline for the candidate images. The control disabled the
microphone and Bluetooth debug families and live STT performance logging at
runtime. Timeline logging, private caption polling and 10-second memory
sampling remained enabled in both conditions. Each row below reports the mean
of paired per-session differences (control minus debug) and a 10,000-resample
paired-session bootstrap 95% interval; the lists are session distributions.

| Measure | Debug | Control | Difference, 95% CI |
| --- | --- | --- | --- |
| WER, % | 14.6, 15.4, 14.4, 15.8, 17.4 | 15.8, 15.8, 14.0, 14.6, 14.2 | −0.64 percentage points [−2.08, +0.56] |
| Median close-to-final, ms | 1395, 1377, 1284, 1276.5, 1318 | 1337.5, 1300, 1398, 1381, 1302 | +13.6 [−57.0, +82.3] |
| Median worker, ms | 1437.5, 1387, 1327, 1302.5, 1340 | 1347.5, 1378, 1430, 1402, 1370 | +26.7 [−35.9, +87.0] |
| Median inference, ms | 1200, 1191, 1150, 1097.5, 1200 | 1171, 1174, 1303, 1184, 1195 | +37.7 [−19.4, +103.3] |
| Median decode, ms | 88, 100, 86, 86.5, 83 | 100, 82, 81, 92, 92 | +0.7 [−9.4, +9.5] |
| Preview count | 144, 143, 149, 149, 157 | 150, 148, 151, 151, 153 | +2.2 [−1.0, +5.0] |
| Lowest sampled free PSRAM, B | 1808248, 1978152, 1808000, 1808256, 1806936 | 1973504, 1806924, 2398488, 1955516, 1980712 | +181110 [−34930, +418500] |
| Lowest sampled largest internal block, B | 147456, 147456, 147456, 147456, 147456 | 147456, 147456, 147456, 147456, 147456 | 0 [0, 0] |
| Reported audio overruns | 0, 0, 0, 0, 0 | 0, 0, 0, 0, 0 | 0 [0, 0] |

Pooled WER was 388/2505 words (15.49%) for debug and 372/2505 (14.85%) for
control. All 27 clips were retained. Empty results were counted; missing
serial segment records were reconstructed only when their sample boundaries
were available. Close-to-final is the device's segment-close to final-processing
interval; it excludes endpointing and display rendering. Negative per-segment
queue waits can occur when speculative work starts before closure.

The complete-run intervals do not show a clear improvement in WER, caption
latency, worker, inference, decode, preview count, or sampled PSRAM free space.
The reported boot-wide PSRAM low-water mark differed by +6,109 B [1,281,
10,937] B, but includes prior boot activity and cannot establish a
session-attributable memory win. Largest PSRAM blocks were not sampled during
playback. Ten-second heap samples may miss transient peaks.

Faults are **not** omitted from reliability reporting: debug had two assertion
reboots and two watchdog-affected attempts among nine measured attempts;
control had one assertion reboot and one watchdog-affected attempt among seven.
The separate qualification run had one additional watchdog warning. The
sample is small, the conditions were not randomized, and these events do not
establish ordinary-use crash frequency or causation. No win is claimed.

## Existing-firmware stage and memory observations

One additional complete standard-playlist run collected all 201 stage counters
across 158 completed model passes, including previews. Reconstructing from the
reported integer mean microseconds gives about 940.82 ms of accumulated stage
wall time per completed pass. The 53 pointwise 512→512 layers account for
approximately 549.0 ms, or 58.3%; other pointwise layers, depthwise layers and
Add/ReLU account for the remainder. Canceled partial work may contribute
without incrementing the completed-pass count; averages are rounded and are
not exclusive CPU time. Neither PSRAM traffic nor cache misses were measured.
No kernel or memory-layout change has been tested by this profile.

One debug-baseline warm-up reported 6,820,936 B free PSRAM and a 6,684,672 B
largest PSRAM block. The speaker load then reported 3,348,240 B of PSRAM used
for its load, including a reported 600,000 B arena and 185,616 B work area;
the feature pool reported 651,272 B. These are phase observations, not a
complete non-overlapping allocation ledger. The pinned speech graph is
20,112,128 B and the LM file is 1,599,996 B; file sizes alone do not establish
all runtime allocations. The five complete sessions' sampled lows and largest
internal blocks are above. Attribution and transient peak measurement remain
incomplete; no RAM resizing has been implemented or qualified.

### Subsequent baseline protocol

The locally rebuilt baseline differs from the original installed app in
257,973 of the first 6,025,664 bytes. Source and build inputs were prepared
from `aa6508fd`, but byte identity to the original was not established. A
separate rebuilt-baseline arm is therefore used for candidate comparisons.
After two rebuilt-baseline attempts stopped on task-watchdog warnings and
successfully drained, the harness was adjusted to record a watchdog warning
while allowing a responsive session to finish. Assertions, unexpected reboots
and unresponsive commands still terminate the run. Warning-affected complete
runs and warnings are identified separately in the final statistics; this
protocol change does not retroactively change the logging comparison above.

The rebuilt baseline completed five full sessions with zero reported overruns
and no watchdog warnings in those complete sessions. Two earlier attempts were
stopped after watchdog warnings and drained without reboot. After a fresh MAC
and partition-table check, the preview-cadence candidate was app-only flashed
and hash-verified for its matched sessions.


## Preview-cadence candidate

The prepared `codex/stt-ab-cadence` commit increases the minimum new-audio
spacing between preview snapshots from 0.6 s to 1.2 s; speculative final
processing remains enabled. The arm was compared with five full runs of a
baseline rebuilt from `aa6508fd` with the same prepared toolchain. Both arms
used the same standard playlist, 75% volume, PDM input, diagnostic settings and
10-second heap samples. Runs were collected in blocks, not randomized.

| Measure | Rebuilt baseline | Cadence candidate | Difference, 95% CI |
| --- | --- | --- | --- |
| WER, % | 15.2, 15.4, 14.8, 16.2, 17.2 | 15.6, 15.6, 16.6, 16.8, 15.6 | +0.28 percentage points [−0.80, +1.20] |
| Median close-to-final, ms | 1254, 1302, 1461.5, 1341.5, 1313 | 1331, 1476, 1311, 1413, 1408 | +53.4 [−55.9, +134.1] |
| Median worker, ms | 1299.5, 1358, 1523.5, 1378.5, 1327 | 1341, 1517, 1345, 1419, 1421.5 | +31.4 [−79.9, +112.0] |
| Median inference, ms | 1114.5, 1216, 1313, 1204, 1119 | 1204, 1251, 1196, 1200, 1229.5 | +22.8 [−49.2, +87.0] |
| Median decode, ms | 77.5, 90, 86, 87.5, 86.5 | 84, 100, 88, 87, 92 | +4.7 [+1.4, +7.7] |
| Preview attempts | 140, 153, 149, 151, 154 | 114, 110, 107, 112, 112 | −38.4 [−42.4, −32.0] |
| First-preview median, ms | 1159.8, 1211.9, 1203.9, 1185.1, 1234.1 | 1467.1, 1426.4, 1462.9, 1408.5, 1447.9 | +243.6 [+216.0, +278.9] |
| Lowest sampled free PSRAM, B | 1839176, 1811764, 1804252, 1975020, 1808216 | 1811960, 2050752, 1804576, 1808012, 1808208 | +9016 [−100142, +138014] |
| Lowest sampled largest internal block, B | 147456, 147456, 147456, 147456, 147456 | 147456, 147456, 147456, 147456, 147456 | 0 [0, 0] |
| Reported audio overruns | 0, 0, 0, 0, 0 | 0, 0, 0, 0, 0 | 0 [0, 0] |

Pooled WER was 394/2505 words (15.73%) versus 401/2505 (16.01%). All 27 clips
were retained. The candidate reduces preview attempts, but first-preview delay
increases and the decoder median also increased in this sample. The candidate
had two assertion reboots in seven attempts and watchdog warnings in two
complete runs; the rebuilt baseline had no assertion reboot in seven attempts,
but two earlier partial attempts had watchdog warnings. These small, unrandomized
bench samples do not prove causation or real-world fault rates. Under the stated
acceptance rule, this is **not a qualified win**. The boot-wide PSRAM low-water
mark is not a session-attributable allocation measurement.

## Speaker-off candidate

The prepared `codex/stt-ab-speaker-off` candidate disables speaker labels in
continuous CLI transcription. Five complete standard-playlist sessions were
compared against the same five rebuilt-baseline sessions, with the same 75%
volume, onboard PDM microphone, diagnostics and sampling as the cadence test.
The runs were collected in blocks and were not randomized. Differences are
candidate minus baseline, with paired-session bootstrap 95% intervals.

| Measure | Rebuilt baseline | Speaker off | Difference, 95% CI |
| --- | --- | --- | --- |
| WER, % | 15.2, 15.4, 14.8, 16.2, 17.2 | 18.0, 14.2, 15.0, 14.8, 16.8 | 0.00 percentage points [−1.12, +1.48] |
| Median close-to-final, ms | 1254, 1302, 1461.5, 1341.5, 1313 | 1332, 1397.5, 1396, 1424, 1356 | +46.7 [−11.6, +86.8] |
| Median worker, ms | 1299.5, 1358, 1523.5, 1378.5, 1327 | 1339, 1406.5, 1424.5, 1456.5, 1368 | +21.6 [−41.5, +63.2] |
| Median inference, ms | 1114.5, 1216, 1313, 1204, 1119 | 1209, 1238, 1289, 1240, 1218 | +45.5 [+6.4, +84.6] |
| Median decode, ms | 77.5, 90, 86, 87.5, 86.5 | 86, 79, 83, 90.5, 89 | 0 [−5.6, +5.1] |
| First-preview median, ms | 1159.8, 1211.9, 1203.9, 1185.1, 1234.1 | 1179.55, 1208.4, 1205.3, 1192.6, 1209.05 | +0.02 [−13.25, +12.4] |
| Lowest sampled free PSRAM, B | 1839176, 1811764, 1804252, 1975020, 1808216 | 5157036, 5156896, 5160872, 5160808, 5155644 | +3310566 [+3246369, +3350646] |
| Lowest sampled largest internal block, B | 147456, 147456, 147456, 147456, 147456 | 159744, 159744, 159744, 159744, 159744 | +12288 [+12288, +12288] |
| Reported audio overruns | 0, 0, 0, 0, 0 | 0, 0, 0, 0, 0 | 0 [0, 0] |

Both arms pooled to 394 errors in 2505 reference words (15.73%), with all 27
clips retained. All five speaker-off attempts completed, with no watchdog
warnings or assertion reboots; the baseline fault history is above. The
sampled PSRAM increase is consistent with avoiding the speaker model load,
but does not measure transient peaks or establish a causal timing effect.
Speaker identity is removed and inference time was higher in this small sample,
so this is **not a qualified replacement or win** under the no-regression rule.

The original app image was restored to the verified app slot after the two
candidate arms, and the entire 7,426,048-byte slot passed digest verification.

On the five rebuilt-baseline standard-playlist runs, the median speaker-label
lag per run was 1788.5, 2055, 1865, 1693 and 1920 ms. The corresponding
median of `lag_ms - us/1000` was 16.2, 74.6, 18.5, 15.9 and 20.4 ms;
this approximates time outside the reported speaker computation, including
queue wait and overhead, rather than measuring exclusive queue wait. The
speaker-off arm has no speaker labels or comparable queue-lag measurement.

## Conversation speaker labels

Five runs on four different conversation recordings (the first repeated)
completed on the restored original app. For each session, the scorer aligns a
labelled phrase's midpoint with a reference clip and selects the best one-to-one
mapping between predicted labels and reference speakers within that session;
unknown labels count as incorrect. These are descriptive phrase scores, not a
matched A/B comparison or a measure of general diarization accuracy.

| Recording | Phrases scored / labels logged | Accuracy | Reference / detected labels | Median label lag, ms |
| --- | --- | --- | --- | --- |
| Conversation 1, first | 41 / 41 | 58.5% | 2 / 4 | 1860 |
| Conversation 1, repeat | 41 / 41 | 95.1% | 2 / 3 | 1764 |
| Conversation 2 | 39 / 39 | 71.8% | 4 / 4 | 3717 |
| Conversation 3 | 44 / 46 | 84.1% | 3 / 6 | 5734.5 |
| Conversation 4 | 33 / 33 | 93.9% | 3 / 4 | 22734 |

The repeat differed substantially, and the scorer excludes unmatched phrases;
these numbers should not be extrapolated to live conversations. Conversation 4
completed with two watchdog warning entries and no assertion or reboot; the
other three distinct recordings completed without watchdog warnings or crash.

For the repeated first conversation, the first run assigned the unknown label
(`-1`) to 16 scored phrases from one reference speaker, versus 2 on the repeat.
This accounts for most of the score difference under the unknown-is-incorrect
rule. The cause of the different unknown-label frequency was not established;
playback, segmentation and speaker-clustering behavior warrant investigation.

Scorer note, added after the campaign: the detected-label column counted `-1`
as a label, so a run with unknown labels shows one more than its real clusters.
Conversation 1 therefore created three clusters in the first run and two in the
repeat; Conversations 2 to 4 are one lower wherever they contain unknowns. With
24/41 and 39/41 correct, the first run's 17 errors are its 16 unknowns plus one
phrase in a single-phrase third cluster, and the repeat's 2 errors are its
unknowns. Labelled phrases were 24/25 and 39/39 correct, and 61% and 95% of
scored phrases received a label: the difference is coverage, not confusion
between the two speakers. Phrases refused, failed or lost before a label line
are not scored. `spkeval.py` now reports real clusters (`speakers_found`) and
unknowns (`unknown_scored`) separately. `spkdiag.py` reports each unknown's
clustering reason, the phrase that created each cluster and the clips it covers,
refused or failed phrases, saved-transcript labels and a clip-by-clip comparison
of two runs. The diagnostics below were run on the five private sessions and
tested with `tests/test_spkdiag.py`.

### Conversation diagnostics

The recorded `TL spk_load` threshold was 0.600 in all five runs. The local
`export_final/speaker.spk` header specifies 0.6000000238 and a 2,000 ms
minimum (32,000 samples at 16 kHz); the alternative `export_2s` header specifies
0.5. The matching threshold does not prove byte identity with the file on the
unmounted device SD card, so its minimum is an assumption based on the matching
export. All scored decision reasons below come from `TL spk_match`, not derived
reasons. Speaker IDs and cluster labels are identifiers, not text.

| Conversation 1 | First | Repeat |
| --- | --- | --- |
| Scored accuracy | 58.5% (24/41) | 95.1% (39/41) |
| Coverage | 61.0% (25/41) | 95.1% (39/41) |
| Labelled accuracy | 96.0% (24/25) | 100.0% (39/39) |
| Text accuracy | 58.5% (24/41) | 95.1% (39/41) |
| Saved accuracy / saved lines | unavailable / 0 | unavailable / 0 |
| Pipeline labelled / missing / lost | 41 / 0 / 0 | 41 / 0 / 0 |
| `spk_match` / derived | 41 / 0 | 41 / 0 |
| Unknown: ambiguous / no_match_short | 15 / 1, speaker 7850 | 0 / 2, speaker 7850 |
| Ambiguous pairs; first sequence | 0/2: 11, 2/0: 4; 7 | none; unavailable |
| Near threshold (within 0.05), sequences | 3: 3, 5, 15 | 1: 22 |
| Submit-to-label median / max, ms | 1860 / 8679 | 1764 / 11893 |
| Capture-end-to-label median, ms | 2992 | 3072 |
| `spk_end` submitted / labelled / skipped | 41 / 41 / 0 | 41 / 41 / 0 |
| Drain outcome / pending / wait ms | complete / 0 / 0 | complete / 0 / 0 |
| Alignment delta ms / text similarity median | 0 / 0.84 | 240 / 0.89 |

Cluster mapping and phrase counts: first run 0→7850: 7, 1→6241: 17,
2→unmapped: 1; repeat 0→7850: 22, 1→6241: 17. The additional first-run
cluster 2 was created at sequence 3, clip 2, speaker 7850, `mixed=false`,
39,200 samples, best previous similarity 0.558, 0.042 below the 0.600
threshold. Clip membership is an alignment estimate and `mixed=false` does not
prove the audio contained only one voice.

The clip comparison covers 32 clips. First outcome divergence: clip 2;
segmentation-differs clips: none; outcome pairs first/repeat: right/right 20,
wrong/right 1, unknown/right 11. At clip 2, first sequence 3 created cluster 2
and scored wrong while repeat sequence 4 matched cluster 0 and scored right;
at clips 6 and 10, first sequences 8 and 13 were ambiguous while repeat
sequences 9 and 14 matched cluster 0. The first ambiguous phrase was sequence 7;
not every phrase is represented as a distinct clip in the clip comparison.

| Conversation | Real scored clusters | Unknown scored | Unknown by reason (reference speaker: count) | Pipeline labelled / missing | Lag median / max / capture-end median, ms |
| --- | --- | --- | --- | --- | --- |
| 2 | 3 | 2 | no_match_short 6313: 1; ambiguous 3853: 1 | 39 / 0 | 3717 / 13272 / 5163 |
| 3 | 5 | 5 | no_match_short MIO036: 1; ambiguous FIE038: 3, MIO036: 1 | 45 / 0 | 5621 / 16590 / 6423 |
| 4 | 3 | 2 | ambiguous 28132: 2 | 33 / 0 | 22734 / 40659 / 24614 |

For conversation 3 the diagnostic has 45 aligned phrase rows and 44 with a
reference; the scorer has 46 label records, 44 scored. One speaker sequence (2)
has no matching analysis phrase and one diagnostic phrase (46) has no reference;
they are not counted in the reference-specific reason totals. Firmware reports
46 submitted / 46 labelled / 0 skipped. No loss marker was observed; absence
of an analysis row is not proof of a device pipeline loss.

The logged decisions support the duplicate-cluster/ambiguity hypothesis for the
first run: sequence 3 created cluster 2 near cluster 0, and all 15 ambiguous
unknowns involved that pair. A short no-match accounts for one additional first
run unknown and both repeat unknowns, rather than most of the first-run gap.
No observed submission refusal, embedding failure or lost-result marker explains
the gap; firmware counters report 41/41 and complete drains in both runs. The
reason that sequence 3 had a borderline similarity, and any effect of physical
playback or unobserved audio, remains unknown. These observations do not prove
what would happen on independent real-world recordings.

A diagnostic parser fix recovers intact ESP-IDF events preceded by an extra
capture prefix. Before this fix it missed 7 and 8 speaker-label records in the
first and repeat sessions respectively, plus some session totals; a synthetic
prefixed-decision and end-counter regression case was added. No firmware, model,
or device contents were changed.

### Similarity and clean-audio replay

The device-log summary pools the logged best and second cluster similarities only; the samples are not independent and are not all possible speaker pairs. At threshold 0.600, the logged same-speaker-below and different-speaker-at-or-above fractions are 0.117 and 0.101. Values are empirical sample proportions, not measured end-to-end error rates.

| Device-log group | n, min, p10, p25, median, p75, p90, max |
| --- | --- |
| Pooled same | 205, 0.407, 0.574, 0.689, 0.766, 0.827, 0.861, 0.915 |
| Pooled different | 168, 0.115, 0.34, 0.389, 0.441, 0.5, 0.594, 0.849 |

Pooled AUC: 0.937; skipped: {"no_reference":1,"unknown_identity":9}. Per-session AUC and skips (first/repeat/2/3/4): 1 first: 0.987, {}; 1 repeat: 0.988, {}; 2: 0.911, {}; 3: 0.839, {"no_reference":1,"unknown_identity":9}; 4: 0.998, {}.

| Threshold | Same below | Different at or above |
| ---: | ---: | ---: |
| 0.50 | 0.039 | 0.256 |
| 0.55 | 0.049 | 0.155 |
| 0.60 | 0.117 | 0.101 |
| 0.65 | 0.18 | 0.077 |
| 0.70 | 0.273 | 0.06 |

Logged split/merge structures by session: 1 first split `7850: {0:7, 2:1}`; 1 repeat none; 2 merged `cluster 1: {3081:11, 6313:9}`; 3 split `MIE085: {0:1, 3:8}` and `MIO036: {2:18, 5:1}`; 4 none.

Centroid groups, n/min/p10/p25/median/p75/p90/max:
- 1 phrases: same 46, 0.416, 0.464, 0.554, 0.648, 0.713, 0.737, 0.825; different 40, 0.115, 0.31, 0.387, 0.436, 0.504, 0.618, 0.787; AUC 0.859; at 0.6 same below 0.413, different at or above 0.15.
- 4+ phrases: same 129, 0.407, 0.694, 0.744, 0.808, 0.837, 0.873, 0.915; different 110, 0.167, 0.357, 0.389, 0.446, 0.515, 0.584, 0.849; AUC 0.953; at 0.6 same below 0.031, different at or above 0.091.

The clean clip replay uses perfect clip segmentation, 300 ms pre-roll and 500 ms tail, the float Mac model, and the unchanged firmware clusterer. The device trunk is quantized. Shuffled orders are sensitivity experiments, not realistic turn orders. In the following tables split and merge entries map IDs to phrase counts. Shuffled split/merge values count orders out of 200; coverage columns are percent.

| Conversation | Threshold | Accuracy / coverage / labelled accuracy % | Clusters | Split speakers | Merged clusters | Shuffled split / merge | Shuffled coverage median / min % |
| --- | ---: | --- | ---: | --- | --- | --- | --- |
| 1 | 0.5 | 100.0 / 100.0 / 100.0 | 2 | `{}` | `{}` | 0 / 2 | 100.0 / 93.8 |
| 1 | 0.55 | 100.0 / 100.0 / 100.0 | 2 | `{}` | `{}` | 16 / 0 | 100.0 / 56.2 |
| 1 | 0.6 | 100.0 / 100.0 / 100.0 | 2 | `{}` | `{}` | 45 / 0 | 100.0 / 56.2 |
| 1 | 0.65 | 81.2 / 84.4 / 96.3 | 3 | `{"7850":{"0":11,"2":1}}` | `{}` | 118 / 0 | 84.4 / 25.0 |
| 1 | 0.7 | 68.8 / 87.5 / 78.6 | 8 | `{"7850":{"0":1,"2":1,"3":1,"4":7,"5":1,"6":1,"7":1}}` | `{}` | 188 / 0 | 81.2 / 40.6 |
| 2 | 0.5 | 84.8 / 84.8 / 100.0 | 4 | `{}` | `{}` | 40 / 67 | 84.8 / 69.7 |
| 2 | 0.55 | 90.9 / 90.9 / 100.0 | 4 | `{}` | `{}` | 53 / 31 | 90.9 / 81.8 |
| 2 | 0.6 | 93.9 / 93.9 / 100.0 | 4 | `{}` | `{}` | 113 / 12 | 93.9 / 72.7 |
| 2 | 0.65 | 97.0 / 100.0 / 97.0 | 5 | `{"3853":{"3":6,"4":1}}` | `{}` | 195 / 12 | 90.9 / 72.7 |
| 2 | 0.7 | 75.8 / 90.9 / 83.3 | 8 | `{"3853":{"3":2,"6":3,"7":1},"6313":{"2":1,"4":5,"5":1}}` | `{}` | 200 / 0 | 90.9 / 66.7 |
| 3 | 0.5 | 66.7 / 73.8 / 90.3 | 5 | `{"FIE038":{"1":2,"4":8},"MIE085":{"0":1,"3":8}}` | `{}` | 185 / 121 | 83.3 / 52.4 |
| 3 | 0.55 | 73.8 / 83.3 / 88.6 | 5 | `{"FIE038":{"1":3,"4":9},"MIE085":{"0":1,"3":8}}` | `{}` | 199 / 60 | 85.7 / 40.5 |
| 3 | 0.6 | 73.8 / 85.7 / 86.1 | 5 | `{"FIE038":{"1":3,"4":7},"MIE085":{"0":2,"3":8}}` | `{}` | 200 / 18 | 85.7 / 42.9 |
| 3 | 0.65 | 64.3 / 76.2 / 84.4 | 8 | `{"FIE038":{"1":1,"4":7,"7":1},"MIE085":{"0":2,"3":1,"5":1,"6":1}}` | `{}` | 200 / 1 | 76.2 / 47.6 |
| 3 | 0.7 | 71.4 / 85.7 / 83.3 | 8 | `{"FIE038":{"1":1,"4":10},"MIE085":{"0":2,"3":4,"5":1,"7":1},"MIO036":{"2":16,"6":1}}` | `{}` | 200 / 0 | 66.7 / 33.3 |
| 4 | 0.5 | 75.0 / 100.0 / 75.0 | 2 | `{}` | `{"1":{"1289":10,"28132":7}}` | 0 / 72 | 78.6 / 71.4 |
| 4 | 0.55 | 92.9 / 92.9 / 100.0 | 3 | `{}` | `{}` | 1 / 12 | 89.3 / 82.1 |
| 4 | 0.6 | 100.0 / 100.0 / 100.0 | 3 | `{}` | `{}` | 14 / 0 | 100.0 / 71.4 |
| 4 | 0.65 | 100.0 / 100.0 / 100.0 | 3 | `{}` | `{}` | 48 / 0 | 100.0 / 60.7 |
| 4 | 0.7 | 57.1 / 64.3 / 88.9 | 5 | `{"1289":{"2":2,"4":1},"28132":{"1":3,"3":1}}` | `{}` | 101 / 0 | 89.3 / 53.6 |

Clean pair-similarity results use all eligible clean clip pairs, unlike the device logs. `at_threshold` is 0.50 because it is the first supplied threshold; the 0.60 sweep row is shown as well.

| Conversation | AUC | At 0.50: same below / different at or above | At 0.60: same below / different at or above | Between-first speaker similarities |
| --- | ---: | --- | --- | --- |
| 1 | 1.0 | 0.0 / 0.0 | 0.124 / 0.0 | `{"6241/7850":0.341}` |
| 2 | 0.997 | 0.017 / 0.047 | 0.074 / 0.01 | `{"3081/3853":0.234,"3081/6313":0.37,"3081/652":0.348,"3853/6313":0.208,"3853/652":0.292,"6313/652":0.239}` |
| 3 | 0.974 | 0.166 / 0.035 | 0.401 / 0.003 | `{"FIE038/MIE085":0.381,"FIE038/MIO036":0.266,"MIE085/MIO036":0.407}` |
| 4 | 1.0 | 0.0 / 0.07 | 0.017 / 0.0 | `{"1289/28132":0.547,"1289/36208":0.271,"28132/36208":0.252}` |

Conversation 1 speaker 7850 anchor clip 0, to-first clip/similarity: `[{"id":2,"sim":0.606},{"id":4,"sim":0.651},{"id":6,"sim":0.579},{"id":8,"sim":0.618},{"id":10,"sim":0.595},{"id":12,"sim":0.6}]`. Conversation 2’s closest first-clip pair is 3081/6313 at 0.370; those two were merged in the device run.

Session replay uses the device phrase spans against clean audio and preserves the logged phrase sample lengths. Device/replay agreement compares literal cluster IDs and reasons, not a permutation-invariant speaker mapping. Device-minus-replay quantiles include only decisions while prior histories agree and the same best cluster exists. Conversation 3 sequence 2 had no analysis phrase and is not replayed; that omission changes the history and can shift cluster IDs.

| Session | Decisions / agree | First divergence seq | At first divergence: device / replay (label, reason, best, similarity) | Delta: n, min, p10, p25, median, p75, p90, max |
| --- | --- | ---: | --- | --- |
| 1 first | 41 / 33 | 13 | -1, ambiguous, 0, 0.75 / 0, match, 0, 0.6983 | 11, -0.026, -0.021, -0.007, 0.012, 0.051, 0.052, 0.078 |
| 1 repeat | 41 / 26 | 4 | 0, match, 0, 0.654 / 2, new, 0, 0.5885 | 2, 0.055, 0.055, 0.055, 0.066, 0.066, 0.066, 0.066 |
| 2 | 39 / 23 | 3 | 1, match, 1, 0.674 / 2, new, 1, 0.3723 | 2, -0.02, -0.02, -0.02, 0.302, 0.302, 0.302, 0.302 |
| 3 | 45 / 3 | 3 | 2, new, 0, 0.4 / 1, new, 0, 0.4544 | 1, -0.054, -0.054, -0.054, -0.054, -0.054, -0.054, -0.054 |
| 4 | 33 / 30 | 5 | -1, ambiguous, 2, 0.614 / 1, short_match, 1, 0.6912 | 3, 0.03, 0.03, 0.04, 0.04, 0.085, 0.085, 0.085 |

Correction: these quantiles were nearest-rank values rounded up, so with two observations the median column
shows the larger one. The two-observation deltas are 0.055 and 0.066 (Conversation 1 repeat) and −0.020 and
+0.302 (Conversation 2); interpolated medians are 0.061 and 0.141. `spkdiag.quantiles` now interpolates.
Larger samples above are affected only within one rank.

Conversation 1 first-run sequence 3: device similarity 0.558, clean session-span replay similarity 0.5648; both created cluster 2. The perfect-clip comparison 0.606 uses different audio boundaries.

The device and clean results both contain same/different overlap, with a substantial threshold tradeoff; the evidence does not establish one universally safe threshold. The clean 3081/6313 first-clip similarity is below 0.6 and the in-order clean replay separates them, but this does not establish that every phrase of the pair separates. Signed session-replay deltas vary and some have only 1–3 comparable observations, so they cannot establish a systematic device similarity reduction or isolate playback/microphone effects from segmentation and float-versus-quantized-model differences.

### Offline rule comparison

The offline comparison embedded four clean manifests, five session-span sets and 30 synthetic conversations of 24 turns from each of six stores. The manifests are `playlist-conv1`, `playlist-conv2`, `playlist-conv3`, `playlist-conv4`; the stores are `librispeech-dev-clean`, `librispeech-dev-clean-g2`, `ami-ihm-validation`, `ami-ihm-validation-g2`, `voxpopuli-dev`, and `voxpopuli-dev-g2`. Total: 189 sets, 4,654 phrases.

| Input group | Sets | Phrases |
| --- | ---: | ---: |
| clean | 4 | 135 |
| session | 5 | 199 |
| corpus:librispeech-dev-clean | 30 | 720 |
| corpus:librispeech-dev-clean-g2 | 30 | 720 |
| corpus:ami-ihm-validation | 30 | 720 |
| corpus:ami-ihm-validation-g2 | 30 | 720 |
| corpus:voxpopuli-dev | 30 | 720 |
| corpus:voxpopuli-dev-g2 | 30 | 720 |

The Mac model is float while the device trunk is quantized. Corpus conversations are synthetic, from clean or simulated `-g2` channel stores; shuffled orders measure sensitivity only. Session sets use clean source audio at device phrase spans, so they cannot reproduce Conversation 2’s actual on-device merge. Clean and session sets each use their in-order sequence and 200 seeded shuffles; corpus sets use their synthetic recorded order only. `all` pools all these runs and therefore reflects that unequal order count.

Coverage, labelled accuracy, and runs with split/merge are percentages. Split and merge are phrase counts per 100 scored phrases, with clusters assessed within each run; these are not counts of affected speakers. Rule deltas are versus production for the same group, in percentage points or phrases per 100 respectively. The criterion is lower split per 100 and no higher merge per 100, both over all orders; it does not require non-regression in coverage or accuracy. Hold/merge columns count decision reasons over all orders.

#### clean

| Rule | Coverage % | Labelled accuracy % | Split / 100 | Merge / 100 | Runs with split % | Runs with merge % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| production | 90.2 | 94.6 | 4.78 | 0.27 | 44.8 | 4.2 |
| production_0.55 | 90.2 | 95.3 | 3.25 | 1.35 | 33.6 | 12.9 |
| production_0.65 | 85.5 | 91.6 | 7.14 | 0.03 | 67.4 | 1.0 |
| hold_0.50 | 92.4 | 98.0 | 1.4 | 0.52 | 22.3 | 4.7 |
| hold_0.45 | 89.3 | 98.5 | 0.7 | 0.71 | 12.3 | 6.8 |
| hold_0.50_young4 | 93.7 | 96.8 | 2.71 | 0.4 | 31.5 | 4.6 |
| merge_young3 | 98.3 | 93.7 | 5.13 | 1.4 | 47.9 | 9.5 |
| merge_young3_sim0.45 | 98.2 | 94.0 | 5.05 | 1.21 | 47.5 | 8.2 |
| hold_0.50+merge_young3 | 93.5 | 97.0 | 1.68 | 1.45 | 26.7 | 10.1 |

| Rule | Δ coverage | Δ labelled accuracy | Δ split / 100 | Δ merge / 100 | Criterion | Hold reasons | Merge reasons |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| production | — | — | — | — | baseline | 0 | 0 |
| production_0.55 | 0.0 | 0.7 | -1.53 | 1.08 | false | 0 | 0 |
| production_0.65 | -4.7 | -3.0 | 2.36 | -0.24 | false | 0 | 0 |
| hold_0.50 | 2.2 | 3.4 | -3.38 | 0.25 | false | 1241 | 0 |
| hold_0.45 | -0.9 | 3.9 | -4.08 | 0.44 | false | 2327 | 0 |
| hold_0.50_young4 | 3.5 | 2.2 | -2.07 | 0.13 | false | 806 | 0 |
| merge_young3 | 8.1 | -0.9 | 0.35 | 1.13 | false | 0 | 686 |
| merge_young3_sim0.45 | 8.0 | -0.6 | 0.27 | 0.94 | false | 0 | 668 |
| hold_0.50+merge_young3 | 3.3 | 2.4 | -3.1 | 1.18 | false | 1297 | 204 |

#### session

| Rule | Coverage % | Labelled accuracy % | Split / 100 | Merge / 100 | Runs with split % | Runs with merge % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| production | 87.5 | 96.6 | 2.91 | 0.34 | 42.3 | 10.3 |
| production_0.55 | 88.8 | 96.5 | 2.18 | 1.6 | 37.3 | 23.6 |
| production_0.65 | 83.9 | 93.2 | 5.72 | 0.35 | 68.2 | 12.9 |
| hold_0.50 | 90.8 | 99.0 | 0.6 | 0.48 | 16.5 | 7.4 |
| hold_0.45 | 90.0 | 98.9 | 0.28 | 0.88 | 8.5 | 10.7 |
| hold_0.50_young4 | 91.3 | 98.4 | 1.34 | 0.35 | 25.5 | 7.0 |
| merge_young3 | 95.2 | 95.2 | 3.1 | 2.01 | 47.2 | 14.9 |
| merge_young3_sim0.45 | 95.1 | 95.4 | 3.06 | 1.82 | 46.6 | 13.9 |
| hold_0.50+merge_young3 | 92.2 | 97.3 | 0.92 | 1.98 | 24.3 | 14.8 |

| Rule | Δ coverage | Δ labelled accuracy | Δ split / 100 | Δ merge / 100 | Criterion | Hold reasons | Merge reasons |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| production | — | — | — | — | baseline | 0 | 0 |
| production_0.55 | 1.3 | -0.1 | -0.73 | 1.26 | false | 0 | 0 |
| production_0.65 | -3.6 | -3.4 | 2.81 | 0.01 | false | 0 | 0 |
| hold_0.50 | 3.3 | 2.4 | -2.31 | 0.14 | false | 1246 | 0 |
| hold_0.45 | 2.5 | 2.3 | -2.63 | 0.54 | false | 1998 | 0 |
| hold_0.50_young4 | 3.8 | 1.8 | -1.57 | 0.01 | false | 847 | 0 |
| merge_young3 | 7.7 | -1.4 | 0.19 | 1.67 | false | 0 | 777 |
| merge_young3_sim0.45 | 7.6 | -1.2 | 0.15 | 1.48 | false | 0 | 764 |
| hold_0.50+merge_young3 | 4.7 | 0.7 | -1.99 | 1.64 | false | 1292 | 220 |

#### corpus

| Rule | Coverage % | Labelled accuracy % | Split / 100 | Merge / 100 | Runs with split % | Runs with merge % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| production | 88.8 | 90.6 | 7.43 | 1.67 | 55.0 | 16.1 |
| production_0.55 | 90.0 | 91.6 | 5.19 | 3.29 | 41.1 | 22.8 |
| production_0.65 | 84.3 | 87.9 | 10.12 | 0.46 | 80.0 | 7.8 |
| hold_0.50 | 88.9 | 92.6 | 3.43 | 3.84 | 32.2 | 22.2 |
| hold_0.45 | 86.3 | 93.3 | 1.97 | 4.47 | 23.3 | 25.0 |
| hold_0.50_young4 | 89.4 | 92.7 | 4.51 | 3.03 | 41.7 | 21.1 |
| merge_young3 | 96.0 | 88.1 | 8.33 | 4.49 | 58.3 | 26.1 |
| merge_young3_sim0.45 | 95.9 | 88.1 | 8.29 | 4.44 | 58.3 | 25.6 |
| hold_0.50+merge_young3 | 90.2 | 91.5 | 3.75 | 4.86 | 35.6 | 27.2 |

| Rule | Δ coverage | Δ labelled accuracy | Δ split / 100 | Δ merge / 100 | Criterion | Hold reasons | Merge reasons |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| production | — | — | — | — | baseline | 0 | 0 |
| production_0.55 | 1.2 | 1.0 | -2.24 | 1.62 | false | 0 | 0 |
| production_0.65 | -4.5 | -2.7 | 2.69 | -1.21 | false | 0 | 0 |
| hold_0.50 | 0.1 | 2.0 | -4.0 | 2.17 | false | 291 | 0 |
| hold_0.45 | -2.5 | 2.7 | -5.46 | 2.8 | false | 449 | 0 |
| hold_0.50_young4 | 0.6 | 2.1 | -2.92 | 1.36 | false | 234 | 0 |
| merge_young3 | 7.2 | -2.5 | 0.9 | 2.82 | false | 0 | 120 |
| merge_young3_sim0.45 | 7.1 | -2.5 | 0.86 | 2.77 | false | 0 | 118 |
| hold_0.50+merge_young3 | 1.4 | 0.9 | -3.68 | 3.19 | false | 294 | 24 |

#### corpus:librispeech-dev-clean

| Rule | Coverage % | Labelled accuracy % | Split / 100 | Merge / 100 | Runs with split % | Runs with merge % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| production | 91.5 | 94.7 | 2.22 | 3.33 | 36.7 | 16.7 |
| production_0.55 | 91.4 | 95.3 | 0.69 | 3.89 | 10.0 | 20.0 |
| production_0.65 | 91.1 | 94.7 | 4.44 | 0.69 | 76.7 | 6.7 |
| hold_0.50 | 94.2 | 93.7 | 0.56 | 5.97 | 3.3 | 23.3 |
| hold_0.45 | 93.9 | 93.2 | 0.69 | 6.39 | 6.7 | 26.7 |
| hold_0.50_young4 | 94.4 | 94.0 | 0.97 | 5.42 | 13.3 | 23.3 |
| merge_young3 | 97.5 | 92.2 | 3.19 | 5.97 | 43.3 | 30.0 |
| merge_young3_sim0.45 | 97.5 | 92.2 | 3.19 | 5.97 | 43.3 | 30.0 |
| hold_0.50+merge_young3 | 95.7 | 91.6 | 1.39 | 7.64 | 13.3 | 33.3 |

| Rule | Δ coverage | Δ labelled accuracy | Δ split / 100 | Δ merge / 100 | Criterion | Hold reasons | Merge reasons |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| production | — | — | — | — | baseline | 0 | 0 |
| production_0.55 | -0.1 | 0.6 | -1.53 | 0.56 | false | 0 | 0 |
| production_0.65 | -0.4 | 0.0 | 2.22 | -2.64 | false | 0 | 0 |
| hold_0.50 | 2.7 | -1.0 | -1.66 | 2.64 | false | 26 | 0 |
| hold_0.45 | 2.4 | -1.5 | -1.53 | 3.06 | false | 33 | 0 |
| hold_0.50_young4 | 2.9 | -0.7 | -1.25 | 2.09 | false | 20 | 0 |
| merge_young3 | 6.0 | -2.5 | 0.97 | 2.64 | false | 0 | 14 |
| merge_young3_sim0.45 | 6.0 | -2.5 | 0.97 | 2.64 | false | 0 | 14 |
| hold_0.50+merge_young3 | 4.2 | -3.1 | -0.83 | 4.31 | false | 25 | 3 |

#### corpus:librispeech-dev-clean-g2

| Rule | Coverage % | Labelled accuracy % | Split / 100 | Merge / 100 | Runs with split % | Runs with merge % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| production | 90.6 | 95.9 | 2.22 | 1.94 | 40.0 | 16.7 |
| production_0.55 | 93.5 | 95.1 | 0.83 | 4.44 | 10.0 | 23.3 |
| production_0.65 | 87.5 | 93.2 | 5.97 | 0.56 | 73.3 | 10.0 |
| hold_0.50 | 93.6 | 94.8 | 0.69 | 4.86 | 6.7 | 23.3 |
| hold_0.45 | 93.6 | 94.1 | 0.42 | 5.56 | 3.3 | 23.3 |
| hold_0.50_young4 | 93.8 | 95.1 | 1.53 | 4.17 | 23.3 | 23.3 |
| merge_young3 | 98.2 | 91.8 | 3.47 | 6.11 | 46.7 | 26.7 |
| merge_young3_sim0.45 | 98.2 | 91.8 | 3.47 | 6.11 | 46.7 | 26.7 |
| hold_0.50+merge_young3 | 95.1 | 93.3 | 0.69 | 6.25 | 10.0 | 26.7 |

| Rule | Δ coverage | Δ labelled accuracy | Δ split / 100 | Δ merge / 100 | Criterion | Hold reasons | Merge reasons |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| production | — | — | — | — | baseline | 0 | 0 |
| production_0.55 | 2.9 | -0.8 | -1.39 | 2.5 | false | 0 | 0 |
| production_0.65 | -3.1 | -2.7 | 3.75 | -1.38 | false | 0 | 0 |
| hold_0.50 | 3.0 | -1.1 | -1.53 | 2.92 | false | 31 | 0 |
| hold_0.45 | 3.0 | -1.8 | -1.8 | 3.62 | false | 37 | 0 |
| hold_0.50_young4 | 3.2 | -0.8 | -0.69 | 2.23 | false | 24 | 0 |
| merge_young3 | 7.6 | -4.1 | 1.25 | 4.17 | false | 0 | 17 |
| merge_young3_sim0.45 | 7.6 | -4.1 | 1.25 | 4.17 | false | 0 | 17 |
| hold_0.50+merge_young3 | 4.5 | -2.6 | -1.53 | 4.31 | false | 31 | 2 |

#### corpus:ami-ihm-validation

| Rule | Coverage % | Labelled accuracy % | Split / 100 | Merge / 100 | Runs with split % | Runs with merge % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| production | 82.8 | 78.0 | 18.19 | 1.11 | 96.7 | 20.0 |
| production_0.55 | 84.7 | 80.8 | 14.44 | 3.75 | 93.3 | 33.3 |
| production_0.65 | 76.4 | 73.3 | 20.28 | 0.69 | 100.0 | 13.3 |
| hold_0.50 | 78.9 | 86.6 | 9.58 | 2.08 | 90.0 | 20.0 |
| hold_0.45 | 74.4 | 91.4 | 5.28 | 2.5 | 60.0 | 26.7 |
| hold_0.50_young4 | 79.7 | 85.9 | 11.11 | 1.25 | 93.3 | 16.7 |
| merge_young3 | 92.1 | 78.1 | 19.44 | 2.36 | 96.7 | 26.7 |
| merge_young3_sim0.45 | 91.9 | 78.4 | 19.17 | 2.08 | 96.7 | 23.3 |
| hold_0.50+merge_young3 | 80.8 | 86.1 | 10.28 | 2.78 | 90.0 | 26.7 |

| Rule | Δ coverage | Δ labelled accuracy | Δ split / 100 | Δ merge / 100 | Criterion | Hold reasons | Merge reasons |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| production | — | — | — | — | baseline | 0 | 0 |
| production_0.55 | 1.9 | 2.8 | -3.75 | 2.64 | false | 0 | 0 |
| production_0.65 | -6.4 | -4.7 | 2.09 | -0.42 | false | 0 | 0 |
| hold_0.50 | -3.9 | 8.6 | -8.61 | 0.97 | false | 91 | 0 |
| hold_0.45 | -8.4 | 13.4 | -12.91 | 1.39 | false | 134 | 0 |
| hold_0.50_young4 | -3.1 | 7.9 | -7.08 | 0.14 | false | 77 | 0 |
| merge_young3 | 9.3 | 0.1 | 1.25 | 1.25 | false | 0 | 32 |
| merge_young3_sim0.45 | 9.1 | 0.4 | 0.98 | 0.97 | false | 0 | 31 |
| hold_0.50+merge_young3 | -2.0 | 8.1 | -7.91 | 1.67 | false | 93 | 7 |

#### corpus:ami-ihm-validation-g2

| Rule | Coverage % | Labelled accuracy % | Split / 100 | Merge / 100 | Runs with split % | Runs with merge % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| production | 81.7 | 76.5 | 18.89 | 1.53 | 100.0 | 23.3 |
| production_0.55 | 85.7 | 82.3 | 13.47 | 3.61 | 96.7 | 30.0 |
| production_0.65 | 74.7 | 73.6 | 19.72 | 0.56 | 100.0 | 10.0 |
| hold_0.50 | 76.5 | 84.8 | 9.44 | 3.75 | 86.7 | 33.3 |
| hold_0.45 | 72.1 | 88.6 | 5.42 | 4.17 | 70.0 | 33.3 |
| hold_0.50_young4 | 78.9 | 82.9 | 12.08 | 3.06 | 93.3 | 30.0 |
| merge_young3 | 91.7 | 75.9 | 20.28 | 3.61 | 100.0 | 33.3 |
| merge_young3_sim0.45 | 91.1 | 75.8 | 20.28 | 3.61 | 100.0 | 33.3 |
| hold_0.50+merge_young3 | 79.0 | 84.7 | 9.58 | 4.31 | 86.7 | 36.7 |

| Rule | Δ coverage | Δ labelled accuracy | Δ split / 100 | Δ merge / 100 | Criterion | Hold reasons | Merge reasons |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| production | — | — | — | — | baseline | 0 | 0 |
| production_0.55 | 4.0 | 5.8 | -5.42 | 2.08 | false | 0 | 0 |
| production_0.65 | -7.0 | -2.9 | 0.83 | -0.97 | false | 0 | 0 |
| hold_0.50 | -5.2 | 8.3 | -9.45 | 2.22 | false | 103 | 0 |
| hold_0.45 | -9.6 | 12.1 | -13.47 | 2.64 | false | 146 | 0 |
| hold_0.50_young4 | -2.8 | 6.4 | -6.81 | 1.53 | false | 83 | 0 |
| merge_young3 | 10.0 | -0.6 | 1.39 | 2.08 | false | 0 | 32 |
| merge_young3_sim0.45 | 9.4 | -0.7 | 1.39 | 2.08 | false | 0 | 31 |
| hold_0.50+merge_young3 | -2.7 | 8.2 | -9.31 | 2.78 | false | 100 | 8 |

#### corpus:voxpopuli-dev

| Rule | Coverage % | Labelled accuracy % | Split / 100 | Merge / 100 | Runs with split % | Runs with merge % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| production | 92.9 | 97.3 | 1.53 | 1.39 | 30.0 | 10.0 |
| production_0.55 | 93.2 | 97.5 | 0.56 | 2.08 | 13.3 | 13.3 |
| production_0.65 | 88.9 | 95.3 | 4.17 | 0.28 | 60.0 | 6.7 |
| hold_0.50 | 95.1 | 96.6 | 0.14 | 3.19 | 3.3 | 16.7 |
| hold_0.45 | 93.2 | 95.5 | 0.0 | 4.17 | 0.0 | 20.0 |
| hold_0.50_young4 | 95.0 | 97.4 | 0.69 | 2.36 | 13.3 | 16.7 |
| merge_young3 | 98.6 | 93.5 | 2.22 | 5.14 | 33.3 | 23.3 |
| merge_young3_sim0.45 | 98.6 | 93.5 | 2.22 | 5.14 | 33.3 | 23.3 |
| hold_0.50+merge_young3 | 95.4 | 95.1 | 0.42 | 4.72 | 10.0 | 23.3 |

| Rule | Δ coverage | Δ labelled accuracy | Δ split / 100 | Δ merge / 100 | Criterion | Hold reasons | Merge reasons |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| production | — | — | — | — | baseline | 0 | 0 |
| production_0.55 | 0.3 | 0.2 | -0.97 | 0.69 | false | 0 | 0 |
| production_0.65 | -4.0 | -2.0 | 2.64 | -1.11 | false | 0 | 0 |
| hold_0.50 | 2.2 | -0.7 | -1.39 | 1.8 | false | 18 | 0 |
| hold_0.45 | 0.3 | -1.8 | -1.53 | 2.78 | false | 39 | 0 |
| hold_0.50_young4 | 2.1 | 0.1 | -0.84 | 0.97 | false | 14 | 0 |
| merge_young3 | 5.7 | -3.8 | 0.69 | 3.75 | false | 0 | 15 |
| merge_young3_sim0.45 | 5.7 | -3.8 | 0.69 | 3.75 | false | 0 | 15 |
| hold_0.50+merge_young3 | 2.5 | -2.2 | -1.11 | 3.33 | false | 23 | 3 |

#### corpus:voxpopuli-dev-g2

| Rule | Coverage % | Labelled accuracy % | Split / 100 | Merge / 100 | Runs with split % | Runs with merge % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| production | 93.5 | 98.4 | 1.53 | 0.69 | 26.7 | 10.0 |
| production_0.55 | 91.8 | 97.3 | 1.11 | 1.94 | 23.3 | 16.7 |
| production_0.65 | 87.4 | 93.0 | 6.11 | 0.0 | 70.0 | 0.0 |
| hold_0.50 | 94.9 | 96.6 | 0.14 | 3.19 | 3.3 | 16.7 |
| hold_0.45 | 90.4 | 95.5 | 0.0 | 4.03 | 0.0 | 20.0 |
| hold_0.50_young4 | 94.9 | 98.0 | 0.69 | 1.94 | 13.3 | 16.7 |
| merge_young3 | 97.9 | 95.5 | 1.39 | 3.75 | 30.0 | 16.7 |
| merge_young3_sim0.45 | 97.9 | 95.5 | 1.39 | 3.75 | 30.0 | 16.7 |
| hold_0.50+merge_young3 | 95.1 | 96.4 | 0.14 | 3.47 | 3.3 | 16.7 |

| Rule | Δ coverage | Δ labelled accuracy | Δ split / 100 | Δ merge / 100 | Criterion | Hold reasons | Merge reasons |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| production | — | — | — | — | baseline | 0 | 0 |
| production_0.55 | -1.7 | -1.1 | -0.42 | 1.25 | false | 0 | 0 |
| production_0.65 | -6.1 | -5.4 | 4.58 | -0.69 | false | 0 | 0 |
| hold_0.50 | 1.4 | -1.8 | -1.39 | 2.5 | false | 22 | 0 |
| hold_0.45 | -3.1 | -2.9 | -1.53 | 3.34 | false | 60 | 0 |
| hold_0.50_young4 | 1.4 | -0.4 | -0.84 | 1.25 | false | 16 | 0 |
| merge_young3 | 4.4 | -2.9 | -0.14 | 3.06 | false | 0 | 10 |
| merge_young3_sim0.45 | 4.4 | -2.9 | -0.14 | 3.06 | false | 0 | 10 |
| hold_0.50+merge_young3 | 1.6 | -2.0 | -1.39 | 2.78 | false | 22 | 1 |

#### all

| Rule | Coverage % | Labelled accuracy % | Split / 100 | Merge / 100 | Runs with split % | Runs with merge % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| production | 88.6 | 95.5 | 3.9 | 0.39 | 44.4 | 8.4 |
| production_0.55 | 89.4 | 95.7 | 2.77 | 1.61 | 36.1 | 19.2 |
| production_0.65 | 84.5 | 92.3 | 6.53 | 0.24 | 68.9 | 7.6 |
| hold_0.50 | 91.3 | 98.2 | 1.08 | 0.7 | 20.3 | 7.6 |
| hold_0.45 | 89.5 | 98.4 | 0.54 | 1.03 | 11.4 | 10.5 |
| hold_0.50_young4 | 92.1 | 97.4 | 2.05 | 0.53 | 29.4 | 7.3 |
| merge_young3 | 96.4 | 94.2 | 4.19 | 1.93 | 48.5 | 13.7 |
| merge_young3_sim0.45 | 96.3 | 94.4 | 4.13 | 1.75 | 48.0 | 12.7 |
| hold_0.50+merge_young3 | 92.6 | 96.9 | 1.38 | 1.95 | 26.3 | 14.0 |

| Rule | Δ coverage | Δ labelled accuracy | Δ split / 100 | Δ merge / 100 | Criterion | Hold reasons | Merge reasons |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| production | — | — | — | — | baseline | 0 | 0 |
| production_0.55 | 0.8 | 0.2 | -1.13 | 1.22 | false | 0 | 0 |
| production_0.65 | -4.1 | -3.2 | 2.63 | -0.15 | false | 0 | 0 |
| hold_0.50 | 2.7 | 2.7 | -2.82 | 0.31 | false | 2778 | 0 |
| hold_0.45 | 0.9 | 2.9 | -3.36 | 0.64 | false | 4774 | 0 |
| hold_0.50_young4 | 3.5 | 1.9 | -1.85 | 0.14 | false | 1887 | 0 |
| merge_young3 | 7.8 | -1.3 | 0.29 | 1.54 | false | 0 | 1583 |
| merge_young3_sim0.45 | 7.7 | -1.1 | 0.23 | 1.36 | false | 0 | 1550 |
| hold_0.50+merge_young3 | 4.0 | 1.4 | -2.52 | 1.56 | false | 2883 | 448 |

#### In-order clean and session totals

| Group | Rule | Coverage % | Labelled accuracy % | Split / 100 | Merge / 100 | Runs with split % | Runs with merge % |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| clean | production | 94.1 | 96.1 | 3.7 | 0.0 | 25.0 | 0.0 |
| clean | production_0.55 | 91.1 | 96.7 | 2.96 | 0.0 | 25.0 | 0.0 |
| clean | production_0.65 | 88.9 | 94.2 | 5.19 | 0.0 | 75.0 | 0.0 |
| clean | hold_0.50 | 92.6 | 96.0 | 3.7 | 0.0 | 25.0 | 0.0 |
| clean | hold_0.45 | 91.9 | 96.0 | 3.7 | 0.0 | 25.0 | 0.0 |
| clean | hold_0.50_young4 | 92.6 | 96.0 | 3.7 | 0.0 | 25.0 | 0.0 |
| clean | merge_young3 | 94.8 | 96.1 | 3.7 | 0.0 | 25.0 | 0.0 |
| clean | merge_young3_sim0.45 | 94.8 | 96.1 | 3.7 | 0.0 | 25.0 | 0.0 |
| clean | hold_0.50+merge_young3 | 93.3 | 96.0 | 3.7 | 0.0 | 25.0 | 0.0 |
| session | production | 82.3 | 96.9 | 2.53 | 0.51 | 60.0 | 20.0 |
| session | production_0.55 | 91.9 | 98.9 | 1.01 | 0.0 | 20.0 | 0.0 |
| session | production_0.65 | 91.4 | 95.0 | 4.55 | 0.51 | 80.0 | 20.0 |
| session | hold_0.50 | 92.9 | 98.9 | 1.01 | 0.51 | 20.0 | 20.0 |
| session | hold_0.45 | 90.9 | 98.9 | 1.01 | 0.51 | 20.0 | 20.0 |
| session | hold_0.50_young4 | 92.9 | 98.9 | 1.01 | 0.51 | 20.0 | 20.0 |
| session | merge_young3 | 96.5 | 97.4 | 2.53 | 0.0 | 60.0 | 0.0 |
| session | merge_young3_sim0.45 | 96.5 | 97.4 | 2.53 | 0.0 | 60.0 | 0.0 |
| session | hold_0.50+merge_young3 | 94.4 | 99.5 | 0.51 | 0.0 | 20.0 | 0.0 |

#### Selected in-order sets

Values are `scored / labelled / right / split / merge` phrase counts.

| Set | Rule | Counts |
| --- | --- | --- |
| Conversation 1 clean | production | 32 / 32 / 32 / 0 / 0 |
| Conversation 1 clean | hold_0.50 | 32 / 32 / 32 / 0 / 0 |
| Conversation 1 clean | merge_young3 | 32 / 32 / 32 / 0 / 0 |
| Conversation 1 clean | hold_0.50+merge_young3 | 32 / 32 / 32 / 0 / 0 |
| Conversation 1 first | production | 41 / 31 / 30 / 1 / 0 |
| Conversation 1 first | hold_0.50 | 41 / 39 / 39 / 0 / 0 |
| Conversation 1 first | merge_young3 | 41 / 40 / 39 / 1 / 0 |
| Conversation 1 first | hold_0.50+merge_young3 | 41 / 39 / 39 / 0 / 0 |
| Conversation 1 repeat | production | 41 / 25 / 24 / 1 / 0 |
| Conversation 1 repeat | hold_0.50 | 41 / 39 / 39 / 0 / 0 |
| Conversation 1 repeat | merge_young3 | 41 / 40 / 39 / 1 / 0 |
| Conversation 1 repeat | hold_0.50+merge_young3 | 41 / 39 / 39 / 0 / 0 |

Conversation 2 session merge phrase counts by rule: production: 0, production_0.55: 0, production_0.65: 0, hold_0.50: 0, hold_0.45: 0, hold_0.50_young4: 0, merge_young3: 0, merge_young3_sim0.45: 0, hold_0.50+merge_young3: 0.

No candidate meets the specified criterion in all three of clean, session and pooled corpus.
All comparisons are offline research results, not changes to device policy. The embedding and comparison artifacts are private and are not committed.

### Deferred speaker confirmation experiment

A new offline prototype holds unmatched phrases pending, confirms a speaker only after two or three mutually similar long phrases, and revisits pending labels after further evidence. Emitted labels never change. Both variants keep threshold 0.6, minimum 32,000 samples and eight speakers; pending state expires after eight further phrase arrivals and retains at most eight pending phrases between calls. Supporting phrases must match no confirmed speaker, and delayed resolved labels do not train the centroid. These choices were fixed before inspecting the experiment results; no additional rule or threshold tuning followed. See [SPEAKER_PROVISIONAL_EXPERIMENT.md](SPEAKER_PROVISIONAL_EXPERIMENT.md) for the exact policy, limits and reproduction command.

The existing 189 sets / 4,654 phrases were reused: four clean sets, five clean-audio-at-device-span sets and 180 synthetic corpus conversations. Production and candidates see identical input orders. Clean/session results include original order plus 200 shared shuffles. Corpus results use synthetic recorded order only. Even/odd corpus indices form development/reserved subsets of 90 conversations each; these are not speaker-disjoint, and the corpus has been used in earlier experiments. Reserved results therefore do not establish unseen-speaker generalization.

Values below use final labels after causal delayed resolution. Coverage at arrival is reported separately. Delay is subsequent phrase arrivals, not seconds; no wall-clock label latency was measured. Runs with a split/merge are percentages; split/merge rates count phrases per 100 scored phrases.

| Group | Rule | Final coverage % | Labelled accuracy % | Split / 100 | Merge / 100 | Coverage at arrival % | Label delay p50 / p90 / max arrivals | Runs with split / merge % |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| clean | production | 90.2 | 94.6 | 4.78 | 0.27 | 90.2 | 0 / 0 / 0 | 44.8 / 4.2 |
| clean | deferred2 | 94.0 | 98.8 | 0.7 | 0.66 | 83.7 | 0 / 1 / 7 | 12.4 / 7.5 |
| clean | deferred3 | 85.8 | 98.9 | 0.24 | 0.94 | 67.3 | 0 / 3 / 7 | 6.8 / 11.7 |
| session | production | 87.5 | 96.6 | 2.91 | 0.34 | 87.5 | 0 / 0 / 0 | 42.3 / 10.3 |
| session | deferred2 | 92.9 | 98.9 | 0.52 | 0.86 | 84.0 | 0 / 0 / 7 | 10.0 / 11.8 |
| session | deferred3 | 86.2 | 98.3 | 0.36 | 1.44 | 70.7 | 0 / 3 / 7 | 10.1 / 16.3 |
| corpus | production | 88.8 | 90.6 | 7.43 | 1.67 | 88.8 | 0 / 0 / 0 | 55.0 / 16.1 |
| corpus | deferred2 | 89.6 | 94.6 | 1.11 | 4.35 | 75.3 | 0 / 2 / 7 | 12.2 / 25.0 |
| corpus | deferred3 | 75.9 | 94.8 | 0.19 | 3.94 | 54.9 | 0 / 4 / 7 | 4.4 / 23.9 |
| corpus_development | production | 89.2 | 90.6 | 7.22 | 2.22 | 89.2 | 0 / 0 / 0 | 57.8 / 21.1 |
| corpus_development | deferred2 | 90.5 | 93.6 | 1.25 | 5.23 | 76.0 | 0 / 2 / 7 | 13.3 / 30.0 |
| corpus_development | deferred3 | 77.4 | 95.3 | 0.28 | 3.66 | 55.1 | 0 / 5 / 7 | 6.7 / 22.2 |
| corpus_heldout | production | 88.4 | 90.6 | 7.64 | 1.11 | 88.4 | 0 / 0 / 0 | 52.2 / 11.1 |
| corpus_heldout | deferred2 | 88.6 | 95.6 | 0.97 | 3.47 | 74.7 | 0 / 2 / 7 | 11.1 / 20.0 |
| corpus_heldout | deferred3 | 74.4 | 94.3 | 0.09 | 4.21 | 54.7 | 0 / 4 / 7 | 2.2 / 25.6 |
| corpus:librispeech-dev-clean | production | 91.5 | 94.7 | 2.22 | 3.33 | 91.5 | 0 / 0 / 0 | 36.7 / 16.7 |
| corpus:librispeech-dev-clean | deferred2 | 97.2 | 93.4 | 0.56 | 6.39 | 84.2 | 0 / 2 / 7 | 3.3 / 23.3 |
| corpus:librispeech-dev-clean | deferred3 | 87.4 | 92.7 | 0.14 | 6.39 | 65.7 | 0 / 4 / 7 | 3.3 / 30.0 |
| corpus:librispeech-dev-clean-g2 | production | 90.6 | 95.9 | 2.22 | 1.94 | 90.6 | 0 / 0 / 0 | 40.0 / 16.7 |
| corpus:librispeech-dev-clean-g2 | deferred2 | 96.1 | 94.4 | 0.42 | 5.42 | 82.6 | 0 / 2 / 7 | 6.7 / 23.3 |
| corpus:librispeech-dev-clean-g2 | deferred3 | 89.9 | 92.0 | 0.0 | 7.22 | 67.2 | 0 / 4 / 7 | 0.0 / 30.0 |
| corpus:ami-ihm-validation | production | 82.8 | 78.0 | 18.19 | 1.11 | 82.8 | 0 / 0 / 0 | 96.7 / 20.0 |
| corpus:ami-ihm-validation | deferred2 | 75.1 | 95.4 | 2.5 | 1.94 | 59.2 | 0 / 4 / 7 | 23.3 / 26.7 |
| corpus:ami-ihm-validation | deferred3 | 51.0 | 95.4 | 0.14 | 2.36 | 34.3 | 0 / 5 / 7 | 3.3 / 20.0 |
| corpus:ami-ihm-validation-g2 | production | 81.7 | 76.5 | 18.89 | 1.53 | 81.7 | 0 / 0 / 0 | 100.0 / 23.3 |
| corpus:ami-ihm-validation-g2 | deferred2 | 74.4 | 92.2 | 2.64 | 4.31 | 58.3 | 0 / 4 / 7 | 30.0 / 36.7 |
| corpus:ami-ihm-validation-g2 | deferred3 | 48.8 | 95.2 | 0.14 | 2.36 | 32.2 | 0 / 5 / 7 | 3.3 / 20.0 |
| corpus:voxpopuli-dev | production | 92.9 | 97.3 | 1.53 | 1.39 | 92.9 | 0 / 0 / 0 | 30.0 / 10.0 |
| corpus:voxpopuli-dev | deferred2 | 97.5 | 95.7 | 0.28 | 4.17 | 84.0 | 0 / 2 / 7 | 6.7 / 23.3 |
| corpus:voxpopuli-dev | deferred3 | 90.3 | 97.1 | 0.56 | 2.64 | 65.4 | 0 / 4 / 7 | 13.3 / 26.7 |
| corpus:voxpopuli-dev-g2 | production | 93.5 | 98.4 | 1.53 | 0.69 | 93.5 | 0 / 0 / 0 | 26.7 / 10.0 |
| corpus:voxpopuli-dev-g2 | deferred2 | 96.9 | 96.0 | 0.28 | 3.89 | 83.8 | 0 / 2 / 7 | 3.3 / 16.7 |
| corpus:voxpopuli-dev-g2 | deferred3 | 88.1 | 97.0 | 0.14 | 2.64 | 64.6 | 0 / 4 / 7 | 3.3 / 16.7 |
| all | production | 88.6 | 95.5 | 3.9 | 0.39 | 88.6 | 0 / 0 / 0 | 44.4 / 8.4 |
| all | deferred2 | 93.1 | 98.6 | 0.62 | 1.0 | 83.4 | 0 / 1 / 7 | 11.2 / 11.3 |
| all | deferred3 | 85.4 | 98.4 | 0.31 | 1.4 | 68.4 | 0 / 3 / 7 | 8.3 / 15.1 |

Both variants fail the lower-split/no-higher-merge gate in clean, session and pooled corpus. Neither qualifies as a firmware replacement. On reserved corpus indices, the two-phrase variant changes split/merge rates from 7.64/1.11 to 0.97/3.47; three-phrase confirmation changes them to 0.09/4.21 while reducing coverage from 88.4% to 74.4%. Increased labelled accuracy does not negate the additional wrong-speaker merges.

| Corpus subset | Rule | Δ coverage pp, 95% CI | Δ labelled accuracy pp, 95% CI | Δ split / 100, 95% CI | Δ merge / 100, 95% CI |
| --- | --- | --- | --- | --- | --- |
| corpus_development | deferred2 | +1.30 [-1.574, +4.676] | +3.00 [+0.614, +5.097] | -5.97 [-7.222, -4.676] | +3.01 [+1.111, +5.417] |
| corpus_development | deferred3 | -11.80 [-16.667, -7.037] | +4.70 [+2.181, +6.969] | -6.94 [-8.565, -5.324] | +1.44 [-0.185, +3.333] |
| corpus_heldout | deferred2 | +0.20 [-2.037, +2.593] | +5.00 [+2.664, +7.185] | -6.67 [-7.917, -5.417] | +2.36 [+0.926, +4.028] |
| corpus_heldout | deferred3 | -14.00 [-19.352, -8.750] | +3.70 [+0.664, +6.575] | -7.55 [-8.843, -6.343] | +3.10 [+1.389, +5.000] |

Intervals use 10,000 paired bootstrap replicates, stratified by source family and resampling conversation indices while keeping clean/g2 pairs together (45 blocks per subset). Speakers can recur across conversations. These are conditional intervals on reused data, not independent speaker-generalization bounds. Shuffles are sensitivity trials, not additional independent recordings.

| Conversation 1 replay set | Rule | Final coverage % | Labelled accuracy % | Split / merge phrases | Label delay p90 / max arrivals |
| --- | --- | ---: | ---: | --- | --- |
| Clean clips | production | 100.0 | 100.0 | 0 / 0 | 0 / 0 |
| Clean clips | deferred2 | 100.0 | 100.0 | 0 / 0 | 0 / 2 |
| Clean clips | deferred3 | 93.8 | 100.0 | 0 / 0 | 2 / 6 |
| First session spans | production | 75.6 | 96.8 | 1 / 0 | 0 / 0 |
| First session spans | deferred2 | 97.6 | 100.0 | 0 / 0 | 0 / 4 |
| First session spans | deferred3 | 97.6 | 100.0 | 0 / 0 | 2 / 7 |
| Repeat session spans | production | 61.0 | 96.0 | 1 / 0 | 0 / 0 |
| Repeat session spans | deferred2 | 97.6 | 100.0 | 0 / 0 | 0 / 4 |
| Repeat session spans | deferred3 | 97.6 | 100.0 | 0 / 0 | 2 / 7 |

The original duplicate-speaker clean-span replay is recovered: two-phrase confirmation labels 40/41 phrases correctly in both Conversation 1 span sets, without a split or merge. These are float clean-span results, not the original microphone results. The same mechanism merges other voices more often in the broader corpus. Three-phrase confirmation adds delay and abstentions without fixing that issue.

The unchanged Mac model is float and the device trunk quantized. Session sets use clean audio at estimated device spans and do not reproduce Conversation 2's actual device merge. Corpus conversations are synthetic clean/simulated-channel turns; shuffled orders only measure sensitivity. No firmware, model, production clusterer or device policy was changed, and no device was flashed.

`tests/test_spkprovisional.py` checks synthetic recovery, distinguishable nearby speakers, ambiguous bridges, short-phrase exclusion, expiry, immutable emitted labels, invalid embeddings and score/CLI behavior. The actual C++ class passes AddressSanitizer and UndefinedBehaviorSanitizer invariants. Retained pending embedding state is bounded, but the offline output archive is not; P4 runtime, allocation behavior, wall-clock delay and real-world accuracy remain unqualified. Private voiceprints and detailed result artifacts are not committed.

### Standalone audio path and window-selection experiment

The first standalone round audited the actual C++ frontend and two fixed, opt-in window selectors. The production frontend, model weights and clustering rule remain unchanged; no production caller enables the new selector. The frontend header comment was corrected to describe the existing PCM-crop-before-feature-extraction order. See [SPEAKER_AUDIO_EXPERIMENT.md](SPEAKER_AUDIO_EXPERIMENT.md) for code, configuration, reproduction and transfer requirements.

The audit used 40 cases: ten synthetic edge cases and 30 speech cases from 15 development speaker IDs (paired channels). On speech, maximum absolute feature error was 4.93526459e-05, maximum RMS feature error 2.08444908e-06, and minimum native/Python float-embedding cosine 0.999999404. This supports close implementation parity on those inputs, not a claim that the representation loses no identity information. Silence/DC embeddings are not meaningful voice-identification evidence. Full quantized-model and actual microphone-input comparisons remain unperformed.

A new frozen partition excludes all 64 reference IDs from prior voiceprint sets. Dataset speaker IDs are globally disjoint between development (37 IDs) and final (36), and paired clean/simulated-channel versions remain together. This does not certify identities across unrelated datasets or pretraining. Final-partition audio has not been embedded or scored.

| Store pair | Development IDs | Final IDs |
| --- | ---: | ---: |
| librispeech-test-clean / g2 | 23 | 15 |
| ami-ihm-test / g2 | 5 | 11 |
| voxpopuli-validation / g2 | 9 | 10 |

Plan SHA-256: `bcefd8bf917d9b70d4e01a443326c358324da84ba6f259e643125bfc03cbda07`. The development comparison has 189 sets / 4,654 phrases: 180 new synthetic corpus conversations (30 per store, 24 turns), plus the four old clean playlists and five old session-span diagnostics. Clean/session order sensitivity uses 200 shared shuffles; corpus uses its synthetic original order. All nine diagnostic baseline in-order count blocks reproduce the prior production replay exactly.

Policies: `center` is the existing crop; `activity` selects the densest energy-active contiguous window; `trim_activity` additionally trims ends with 100 ms context. Fixed parameters are 20 ms RMS frames/10 ms hop, threshold max(32 int16 RMS units, 0.1*p90), and a 47,840-sample maximum. This is an energy heuristic, not validated speech/turn detection. Original reference IDs, mixed-phrase flags and supplied clustering durations are preserved for all policies, isolating embedding selection.

| Development group | Policy | Coverage % | Labelled accuracy % | Split / 100 | Merge / 100 |
| --- | --- | ---: | ---: | ---: | ---: |
| clean | center | 90.2 | 94.6 | 4.78 | 0.27 |
| clean | activity | 90.8 | 94.8 | 4.74 | 0.15 |
| clean | trim_activity | 92.4 | 94.9 | 4.73 | 0.0 |
| session | center | 87.5 | 96.6 | 2.91 | 0.34 |
| session | activity | 88.5 | 96.6 | 2.92 | 0.23 |
| session | trim_activity | 88.4 | 96.5 | 3.13 | 0.07 |
| corpus | center | 88.9 | 90.8 | 7.78 | 0.56 |
| corpus | activity | 90.0 | 91.4 | 7.57 | 0.44 |
| corpus | trim_activity | 89.5 | 91.2 | 7.71 | 0.37 |
| corpus:librispeech-test-clean | center | 96.0 | 96.7 | 2.36 | 0.83 |
| corpus:librispeech-test-clean | activity | 94.4 | 96.3 | 3.47 | 0.28 |
| corpus:librispeech-test-clean | trim_activity | 93.9 | 96.2 | 3.61 | 0.14 |
| corpus:librispeech-test-clean-g2 | center | 94.2 | 96.2 | 2.92 | 0.69 |
| corpus:librispeech-test-clean-g2 | activity | 93.3 | 96.6 | 3.19 | 0.28 |
| corpus:librispeech-test-clean-g2 | trim_activity | 92.1 | 96.5 | 3.19 | 0.14 |
| corpus:ami-ihm-test | center | 76.2 | 75.8 | 18.19 | 0.56 |
| corpus:ami-ihm-test | activity | 78.6 | 77.6 | 17.36 | 0.83 |
| corpus:ami-ihm-test | trim_activity | 78.5 | 77.7 | 17.22 | 0.69 |
| corpus:ami-ihm-test-g2 | center | 78.9 | 76.4 | 18.61 | 0.14 |
| corpus:ami-ihm-test-g2 | activity | 78.6 | 76.7 | 18.33 | 0.14 |
| corpus:ami-ihm-test-g2 | trim_activity | 77.5 | 75.4 | 19.03 | 0.14 |
| corpus:voxpopuli-validation | center | 94.6 | 97.1 | 2.36 | 0.56 |
| corpus:voxpopuli-validation | activity | 97.8 | 98.2 | 1.39 | 0.56 |
| corpus:voxpopuli-validation | trim_activity | 98.3 | 98.2 | 1.39 | 0.56 |
| corpus:voxpopuli-validation-g2 | center | 93.3 | 97.2 | 2.22 | 0.56 |
| corpus:voxpopuli-validation-g2 | activity | 97.1 | 97.9 | 1.67 | 0.56 |
| corpus:voxpopuli-validation-g2 | trim_activity | 96.8 | 97.7 | 1.81 | 0.56 |

| Policy vs center, pooled development corpus | Δ coverage pp, CI95 | Δ labelled accuracy pp, CI95 | Δ split / 100, CI95 | Δ merge / 100, CI95 |
| --- | --- | --- | --- | --- |
| activity | +1.10 [-0.162, +2.384] | +0.60 [-0.219, +1.595] | -0.21 [-0.741, +0.324] | -0.12 [-0.718, +0.255] |
| trim_activity | +0.60 [-0.833, +2.153] | +0.40 [-0.497, +1.430] | -0.07 [-0.671, +0.532] | -0.19 [-0.764, +0.139] |

The intervals use 10,000 paired bootstrap replicates, stratified by source family and resampling 90 conversation-index blocks while keeping channel pairs together. Speakers recur among dialogues, so these are conditional reused-development intervals, not independent speaker-generalization bounds. All four intervals include zero for both policies. Pooled direction does not remove per-store regressions: activity selection increases LibriSpeech clean split phrases per 100 from 2.36 to 3.47, for example.

| Conversation 1 original-order diagnostic | Policy | Coverage % | Labelled accuracy % | Split / 100 | Merge / 100 |
| --- | --- | ---: | ---: | ---: | ---: |
| Clean clips | center | 100.0 | 100.0 | 0.0 | 0.0 |
| Clean clips | activity | 100.0 | 100.0 | 0.0 | 0.0 |
| Clean clips | trim_activity | 68.8 | 86.4 | 9.38 | 0.0 |
| First session spans | center | 75.6 | 96.8 | 2.44 | 0.0 |
| First session spans | activity | 73.2 | 96.7 | 2.44 | 0.0 |
| First session spans | trim_activity | 63.4 | 88.5 | 7.32 | 0.0 |
| Repeat session spans | center | 61.0 | 96.0 | 2.44 | 0.0 |
| Repeat session spans | activity | 63.4 | 96.2 | 2.44 | 0.0 |
| Repeat session spans | trim_activity | 63.4 | 88.5 | 7.32 | 0.0 |

In the clean Conversation 1 clip comparison, first/third-clip similarity is 0.6060 for center/activity and 0.5706 after trimming. The first session-span pair is approximately 0.5649 for center/activity and 0.5337 after trimming; the repeat pair is 0.5885 and 0.5230. These are dot products of rounded saved vectors; the prior unrounded C++ best similarity at sequence 3 was 0.5648. Trimming harms these cases and is not a qualified input change.

The final-test speaker partition is being preserved because neither development candidate passes the integration gate. No HardwareOne source, model file, device policy or device flash was changed. The portable selector remains opt-in only. The current evidence favors checking actual speech quality/consistency over blindly removing normalization or silence. Its next comparison should use the frozen partition protocol and must show merge, split, coverage and labelled-accuracy behavior as well as P4 timing/memory before deployment.

Verification: the actual native selector and frontend passed AddressSanitizer/UndefinedBehaviorSanitizer bounds and finite-output cases; synthetic tests cover silence fallback, activity selection, trimming, deterministic disjoint partitions, exact store roots and bootstrap direction. Numerical float parity was measured separately. No real-time P4 or quantized-path qualification is implied. Raw audio, voiceprints, partitions and detailed numeric artifacts remain in ignored private storage.

### Known-PCM P4 speaker parity and fresh baseline

Following the offline window experiment, the original P4 app was verified over
its complete 7,426,048-byte slot before additional testing. Its SHA-256 is
`bc86107c5483d93225fef821c306686849786b1518f287ae5e2fafc8ba2231a8`.
The actual SD model is 1,994,544 bytes (w8a16 trunk plus float projection head);
its header reports threshold
0.6000000238418579 and minimum new-speaker duration 2,000 ms. Header/footer
bytes match the local export. No model file was written.

A fresh original-firmware Conversation 1 run, session `20261031-192829_s1`,
completed on onboard PDM at Mac volume 75%. The final analyser has 41 scored
phrases: 41/41 correct and labelled, two clusters, zero unknowns, zero lost
results; firmware submitted/labelled/skipped = 41/41/0. Median/maximum
submit-to-label lag is 1,919/9,951 ms and median capture-end-to-label delay is
3,057 ms. Alignment delta is 0 ms and median text similarity 0.91. There were
zero reported overruns, watchdog warnings or fatal markers, and normal drain
completed with zero pending results. This is one additional baseline run, not
an improvement comparison or an ordinary-use reliability estimate.

The analyser initially missed two complete segment log lines after a pending
CLI prompt. `tl_parse.py` now removes that specific prompt only when a complete
ESP log follows; a synthetic test also rejects ordinary prompts and JSON text.
After re-analysis, the scored denominator is 41 rather than 39. Historical
sessions and published historical scores were not regenerated.

For the identical-PCM test, local HardwareOne diagnostic commits f91cd415 and
0637d23f derive from aa6508fd. They enable existing probes, use a separately owned
SD fixture and emit normalized embeddings; the model, speaker policy and audio
algorithms are unchanged. The final diagnostic app is 6,029,744 bytes, SHA-256
`d9fb82cdf20bc4e77e3f016956ff3e5da00ef6fa02e727e015a9cfbfebe312af`.
Only the verified app partition at 0x10000 was flashed. This diagnostic has extra
work and is not a performance candidate. Source patches and reproduction are
in [SPEAKER_P4_PARITY.md](SPEAKER_P4_PARITY.md); source bundles, app images,
PCM, vectors and logs remain private. No HardwareOne branch is pushed.

The reference fixture contains 44,560 PCM samples and 512-dimensional vectors.
Its original exported expected vector is host-simulated quantized, not float.
The experiment recomputes the float reference using the unchanged checkpoint
and verifies that its projection head equals the shipped model's head. Float
versus simulated-quantized cosine is 0.996255194. Across five successful P4
reboot trials, P4 versus float cosine is 0.992834856 and P4 versus simulated
quantized is 0.996645133; all five emitted vectors agree exactly at logged
precision (all ten pairwise reboot cosines = 1.0). These are same-input vector
comparisons, not speaker accuracy. The P4/float comparison combines quantization
with target frontend, pooling and kernel arithmetic; it does not isolate every
source of numerical difference. The simulated-quantized reference is not a
bit-exact P4 oracle.

Two harness issues were corrected and excluded from successful-trial counts:
requesting stop before normal warm/capture readiness caused one stop timeout;
long vector log lines were truncated, sometimes leaving a parseable final
number. The final format uses eight-value chunks with an explicit end marker,
unit-norm validation, complete indices and agreement with the firmware cosine.
The harness also awaits the load-summary line after the vector; that line can
arrive later. Synthetic cases cover truncation, ANSI wrapping, missing chunks
and delayed summary readiness. Two initial long-line runs stopped cleanly but
their vectors are excluded; an interrupted next boot and the summary-race
attempt are also excluded. Each recovery preserved the original rollback.

Source inspection at aa6508fd shows continuous STT reads `audioReadPcm` directly.
The normal microphone recording path additionally calls `micProcessForSource`
and `applyMicAudioProcessing` (filtering, pre-emphasis, software gain/clipping).
A recording from that path would therefore not be an identical STT-PCM capture.
This source finding does not exclude lower-level PDM processing or quantify
physical microphone/channel effects.

The float checkpoint contains 1,437,078 parameters: 5,748,312 parameter bytes,
plus 17,312 buffer bytes. These are tensor payloads, not a P4 runtime allocation
measurement. The shipped mixed-precision file is 1,994,544 bytes. Existing normal
P4 tests measured approximately 3.3 MB additional PSRAM with speaker support and
1.7–2.1 s median speaker-label delay across standard-playlist sessions. There is
no same-P4 float runtime/RAM benchmark; Mac timing cannot supply that comparison.

| Fixed PCM input | Samples | Trials | P4 vs float cosine, min = median = max |
| --- | ---: | ---: | ---: |
| export_reference | 44560 | 5 | 0.992834856 |
| session_seq1 | 56000 | 5 | 0.992231570 |
| session_seq3 | 43840 | 5 | 0.988928869 |
| clip0 | 64080 | 5 | 0.988936040 |
| clip2 | 58400 | 5 | 0.990130057 |

All 25 corrected trials completed with zero reported audio overruns, watchdog
warnings and fatal markers. For each input all five emitted vectors match at
logged precision (ten pairwise reboot cosines per input = 1.0). Five reboots of
one input are repeatability trials, not five independent voices.

| Speaker 7850 input pair | Mac float | P4, all five pairs | P4 minus float | P4 at/above 0.600 |
| --- | ---: | ---: | ---: | ---: |
| First-session captured-span excerpts, seq 1/3 | 0.564850450 | 0.574662089 | +0.009811639 | 0/5 |
| Clean clips 0/2 | 0.605987318 | 0.595827872 | -0.010159446 | 0/5 |

Findings: the captured-span pair stays below threshold on both paths; the P4
increases its similarity. The clean-clip pair moves from just above threshold
on Mac to just below it on P4. Thus the target path can flip a borderline
single-anchor match, and signed similarity changes are not uniformly negative.
This does not measure different-speaker overlap or establish a new threshold.
The earlier corpus threshold/rule tradeoffs still prohibit declaring a lower
threshold a qualified fix.

The session diagnostic fixtures used 56,000/43,840 samples cut from captured
spans; original firmware speaker inputs were 52,000/39,200 samples. They are
identical-input Mac/P4 tests of those clean excerpts, not a reconstruction of
original microphone PCM or its trimmed speaker input. The following boundary
audit corrects that replay mismatch. The original device sequence 3 similarity
was 0.558; the comparisons above cannot assign its remaining difference to the
microphone, timing or numerical path individually.

Each temporary SD fixture was owned, read-back verified and removed. LittleFS
remained above 6,582,272 B during the successful trial measurements; final probe
reported 6,569,984 B free, system file logging inactive and PDM preferred. The
original complete app slot was restored and digest-verified again. Final model
header/footer still matched the local export. No firmware improvement or
window selector was left enabled.



### Speaker boundary and exact-PCM audit

The boundary audit found a replay reconstruction error: `TL seg` spans describe
captured audio, but `sttSpeakerSubmit` receives `retainedSamples`, after optional
tail trimming and before its center crop. Historical session replay embedded
the longer captured span while using the shorter logged sample count only for
clustering. `spkreplay.py` now embeds the retained prefix; synthetic cases cover
that difference and reject lengths exceeding capture. `spkcuts.py` separately
reports captured, retained and model-selected spans, including manifest-speaker
mixing and coverage. Its speech envelopes are energy estimates, not phonetic
annotations, and timestamps alone cannot prove a cut removed a phoneme.

Six sessions were re-analysed/replayed in a separate private audit tree; original
historical records were preserved. Conversation 3 recovers a previously missed
segment (46 replayed phrases rather than 45). These corrected inputs supersede
the interpretation of historical session replay as exact speaker-span replay;
old numeric tables remain historical results for their actual longer inputs.
Historical clean/corpus rule comparisons and their no-qualified-candidate
conclusion are not changed by this session-only reconstruction fix.

| Session | Corrected phrases | Trimmed captured tails | Accuracy / coverage % | Labelled accuracy % | Device decisions agreeing | First divergence seq | Mixed selected model windows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20261031-162708_s1 | 41 | 21 | 65.9 / 68.3 | 96.4 | 38 | 13 | 0 |
| 20261031-164427_s1 | 41 | 21 | 65.9 / 68.3 | 96.4 | 29 | 4 | 0 |
| 20261031-163129_s1 | 39 | 17 | 94.9 / 94.9 | 100.0 | 23 | 3 | 0 |
| 20261031-163552_s1 | 46 | 27 | 84.4 / 93.3 | 90.5 | 41 | 9 | 1 |
| 20261031-164012_s1 | 33 | 14 | 97.0 / 97.0 | 100.0 | 30 | 5 | 0 |
| 20261031-192829_s1 | 41 | 21 | 58.5 / 61.0 | 96.0 | 24 | 3 | 0 |

The original Conversation 1 sequence 3 mapped model span is 20.399–22.849 s
(39,200 samples), one manifest speaker, with no cross-turn mixing. The estimated
speech envelope is 20.285–22.325 s, so the timestamp projection starts 114 ms
after its estimated onset. The source interval is an energy envelope and the
mapping has timing uncertainty; this does not establish a defective cut.
Corrected clean float similarity to sequence 1 is about 0.552, versus the
original device's 0.558. The fresh sequence 3 retained span is 20.034–22.744 s
(43,360 samples); it contains the complete estimated envelope and correct clean
float replay gives about 0.599, while the original-firmware device scored 0.656.
These differences motivated capturing actual input rather than relying on
projected clean spans.

#### Bounded exact microphone-input capture

Local diagnostic source 8692ce8d (based on aa6508fd plus the parity probes)
writes only explicitly host-created, nonce-armed files for selected sequences.
It captures the exact model-input PCM and raw FC vector after label publication,
adds SHA-256, uses the guarded SD captures scope and filesystem lock, and never
writes model assets or enables system file logging. The four writes took
28,086 / 28,039 / 26,854 / 28,428 microseconds. This instrumentation is not a
performance candidate. App size is 6,031,008 B, SHA-256
`dfc9ca8cc825f18f3cebaa3d5486dbf094ded03e57143aa36bf723c12197350e`.
Source is preserved in the private bundle and the reproducible source patch.

Session `20261031-203539_s1` completed at 75% Mac volume on onboard PDM: 40/40
scored phrases correctly labelled, two clusters, zero unknowns, zero reported
overruns/watchdogs/fatal markers; submitted/labelled/skipped = 40/40/0, complete
drain and zero pending results. All four packet checksums passed. The initial
reader incorrectly expected unit vectors; the raw FC norms were 7.824417,
7.389736, 7.887817 and 7.755696. The reader now accepts finite nonzero vectors;
cosine consumers normalize. A synthetic case covers unnormalized vectors.
Cleanup preserved the packets before removing every owned SD file, so no second
playback was required to recover this reader error.

Waveform alignment uses 100–3,500 Hz filtering and normalized correlation over
a fixed ±1 s search, trimming 40 ms edges. The preselected confidence cutoff is
0.25 and excludes search-edge peaks. Synthetic tests cover known delay, gain,
polarity and silence. Sequences 1/2/3 match with correlations
0.312668 / 0.339142 / 0.385382, and runner-up peaks outside ±50 ms are
0.030976 / 0.028071 / 0.049577. All indicate polarity -1. Sequence 4's 0.215490
peak is below the fixed cutoff; no aligned-clean embedding is reported for it.
The four captured PCM inputs have zero clipped samples.

For sequence 3, the waveform-matched model span is 19.9860625–22.8060625 s.
Its estimated speech envelope is 20.285–22.325 s: approximately 299 ms before
onset and 481 ms after the end, with no other manifest speaker. Sequence 1's
matched span is 6.1984375–9.1884375 s, covering its 6.36–8.78 s envelope. This
successful recording has no onset/end loss for either short reference clip.
It cannot establish that the original unsuccessful recording had correct cuts,
because that earlier microphone PCM was not saved. Console/alignment projections
are measurably different from direct waveform alignment and must not be treated
as exact audio timing.

| Sequence | P4 vs Mac float, identical microphone PCM | Mac float microphone vs aligned-clean embedding |
| --- | ---: | ---: |
| 1 | 0.991661740 | 0.784096972 |
| 2 | 0.994556282 | 0.861571972 |
| 3 | 0.992436686 | 0.801331974 |
| 4 | 0.996272265 | not reported: alignment below cutoff |

| Pair seqs, reference IDs | P4 microphone similarity | Mac float microphone | Mac float aligned clean |
| --- | ---: | ---: | ---: |
| 1/2, 7850/6241 | 0.324255997 | 0.331406286 | 0.355396948 |
| 1/3, 7850/7850 | 0.642508423 | 0.632405133 | 0.585196339 |
| 1/4, 7850/6241 | 0.356948406 | 0.349950865 | not reported |
| 2/3, 6241/7850 | 0.371403994 | 0.348822583 | 0.297536528 |
| 2/4, 6241/6241 | 0.778283005 | 0.787568298 | not reported |
| 3/4, 7850/6241 | 0.348380124 | 0.347769549 | not reported |

Findings: the critical 7850 pair matches on P4 (0.642508) and Mac using identical
microphone PCM (0.632405), but falls below 0.6 on the waveform-aligned clean
reference (0.585196). The physical signal path substantially changes embeddings
without uniformly reducing same-speaker similarity. P4/float numerical changes
and signal-path changes must be measured separately. These four inputs/two
reference IDs do not establish corpus-wide separation or a qualified fix.
No captured evidence here supports the original sequence 3 spanning two turns;
actual failure-case PCM remains necessary to establish missing-onset causation.

All four owned files and the newly created empty capture directory were removed.
The original entire app slot was restored and digest-verified. Final probe:
6,520,832 B LittleFS free, logging inactive, PDM preferred, original model
header/footer unchanged and no watchdog/fatal markers. The user subsequently
requested 50% playback; Mac output was set and verified at 50%, unmuted. Future
50% runs are a separate condition; they are not pooled with these 75% recordings.
Overnight work continues silently under [SPEAKER_OVERNIGHT_PLAN.md](SPEAKER_OVERNIGHT_PLAN.md).

### First code-only frontend candidate (host checkpoint)

The standalone frontend now has a candidate that clears its frame buffer once
per computation rather than once per frame. FFT reads do not modify that buffer,
and every window sample is replaced each frame. The model, arithmetic order,
output shape, workspace size and settings are unchanged. A frozen 92b028c
reference validates 150 cases across three feature specifications and silence,
DC, full-scale alternation, seeded noise and sine inputs, including repeated
long/short calls. Features are byte-identical in normal and ASan/UBSan builds.

On Mac, after 60 warm-up calls per implementation, ten alternating matched
pairs of 30 computations each gave median 593.3105 µs reference and 587.0875 µs
candidate. Mean paired difference is -5.8042 µs, bootstrap 95% interval
[-6.8480, -4.6905] µs (10,000 resamples, seed 17). This is a small host frontend
result on one fixed synthetic input, not target embedding speed or end-to-end
caption latency. The subsequent target comparison is reported below; the
candidate has not replaced the normal HardwareOne frontend or been left installed.

### Silent P4 frontend comparison

HardwareOne diagnostic source d6029017 compiles the original frontend and the
standalone 64ec0e2 clear-once candidate separately, without replacing the normal
model's frontend. The compiler options match (`-O2` last in both), and no model,
settings, tile sizes, CPU or RAM clocks change. The app is 6,036,816 B, SHA-256
4ef84490b5f31fdbdd01559e102274247944d1b920d2febf88ab41be0e9ebae6.
Selected app, matching ELF/map/build metadata and a source bundle stay private;
only the diagnostic source patch and numeric report are committed here.

Five independent boots used one fixed 44,560-sample input. Each boot checked
six lengths (1, 2, 257, 400, 16,000 and 44,560) with byte-identical features:
30/30 target cases passed. Eight warm-up calls per implementation preceded ten
alternating timing pairs of three computations each. Scratch/output addresses
are shared; allocations, comparisons, logging and task delays are untimed.
The bootstrap resamples whole boots (10,000 draws, seed 17), rather than treating
50 within-boot pairs as independent reboot trials.

| Frontend computation | Original | Clear once |
|---|---:|---:|
| Mean (ms) | 55.381373 | 54.709907 |
| Median of pair averages (ms) | 55.410000 | 54.724167 |
| p05–p95 (ms) | 54.982183–55.947000 | 54.340233–55.046183 |
| Min–max (ms) | 54.893000–56.098000 | 54.273000–55.667667 |
| Workspace (B) | 97,892 | 97,892 |
| Output (B) | 48,000 | 48,000 |

Mean paired candidate-minus-original difference is -0.671467 ms, bootstrap 95%
[-0.743473, -0.599460] ms; relative change -1.212441%, interval
[-1.341257%, -1.083394%]. Per-boot differences are -0.566400, -0.576667,
-0.784633, -0.711167 and -0.718467 ms. All five normal STT lifecycle controls
stopped/drained with zero reported overruns, watchdog warnings or fatal markers;
the original-path fixture cosine repeated at 0.9928348557423828.

This establishes a small isolated target frontend saving, not an end-to-end
caption/embedding speed or accuracy improvement. The diagnostic temporarily
allocates additional comparison state; its app RAM/load time is not a production
memory benchmark. Candidate features match, but the normal model in this image
continues to consume original frontend output. Live WER/labels, delivery delays,
peak headroom and a production-style candidate app remain qualification gaps.

The cleanup reader initially rejected debug output interleaved inside one
otherwise valid JSON base64 string. It now retries the identical read up to
three times with strict base64, offset, size and length checks; it never strips
foreign characters or repairs data. A synthetic regression covers successful
retry, persistent corruption and mismatched byte counts. The first orchestration
process exited with a cleanup error after its `finally` path successfully
restored and full-slot-verified the original app. Retrying with the fixed reader
verified and deleted the owned SD fixture. Final LittleFS free is 6,504,448 B;
logging remained inactive, PDM preferred, model header/footer unchanged and no
watchdog/fatal markers in the restored-app probe. This was a host read-framing
failure after valid timing trials, not a device crash or benchmark failure.

### Portable sample-boundary audit

`tests/test_segmenter_boundaries.py` compiles the actual portable segmenter
under ASan/UBSan. Six synthetic configurations and 20 seeded streams each were
compared against the same stream pushed on its 160-sample analysis grid. Chunk
sizes 1, 159, 161, 257 and 4,096 plus seeded random chunks yielded 720 matching
comparisons and 1,076 reference segments. Every emitted PCM sample equals its
absolute source sample; offsets and boundary metadata are invariant to chunking.
Continuous qualified speech survives repeated hard cuts and a 79-sample partial
session end without gaps or unrequested overlap. Stopping while a quiet-point
cut is ready preserves the otherwise pending suffix. No sanitizer fault or
boundary error was found; no segmenter change was made.

This covers fixed/adaptive endpointing, percentile noise, blip tolerance,
forced overlap, quiet-point hard cuts and short closes on synthetic audio.
Intentional idle gaps and rejected short candidates are permitted. It does not
prove microphone transport continuity, timestamp alignment, phonetic correctness
or transport/ownership behavior of the HardwareOne capture loop. The tested
segmenter header is byte-identical to the current HardwareOne diagnostic source
(SHA-256 2b3e4a5c48fec27b3c82770e9fbed51075e098e85431b23ba6e0c984d8d59151). The existing
portable streaming suite also passed its feature equality, preemption, exact
promotion, resumed speech, finish/cancel, queue overflow, stale generation and
concurrent ownership checks, including a separate ThreadSanitizer run.

The unchanged production LM decoder's existing ASan/UBSan oracle suite also
passed: 2,612 comparisons at factor 1.00 and 2,626 at synthetic factor 0.75;
388 and 374 cases respectively were skipped because a nonstructural rank
decision lay within 1e-6 nats. Context reset, within-call history, unavailable
stages, immutable LM and validation cases passed. These are synthetic
correctness checks, not a production setting change or measured WER gain.

### Offline boundary sensitivity

All four known conversation playlists were replayed with the unchanged float
model and production C++ clusterer at threshold 0.6 and minimum new-speaker
length 2,000 ms. Eleven extraction conditions change one boundary at a time:
pre-roll -300, -100, 0, 150, 300 (control), 450 or 600 ms with tail 500 ms;
tail 0, 250, 500 (control), 750 or 1,000 ms with pre-roll 300 ms. Negative
pre-roll starts inside the source clip. These are offline input perturbations,
not production configuration changes or selected optimization gains.

135 source phrases × 11 conditions produced 1,485 embeddings and 44 in-order
replays. Each condition also replayed the same 200 seeded shuffles (seed 1):
8,800 order simulations. No manifest energy envelope from a different reference
speaker intruded into these extracted spans (0/1,485). Energy envelopes are
not phonetic annotations; this does not establish that every cut retains speech.

Pooled in-order counts below are over the same 135 phrases. S/M conversations
count conversations containing any split/merge, out of four; shuffled S/M
counts orders with any split/merge, out of 800 per condition. These are
descriptive sensitivity results, not independent accuracy trials or confidence
intervals. No final-test speakers were opened.

| Pre / tail (ms) | Correct / labelled | Accuracy % | Coverage % | Labelled accuracy % | S/M conversations | Shuffled S/M |
|---|---:|---:|---:|---:|---:|---:|
| 300 / 500 | 122 / 127 | 90.370 | 94.074 | 96.063 | 1/0 | 372/30 |
| -300 / 500 | 125 / 129 | 92.593 | 95.556 | 96.899 | 1/1 | 390/147 |
| -100 / 500 | 119 / 124 | 88.148 | 91.852 | 95.968 | 1/0 | 407/51 |
| 0 / 500 | 116 / 120 | 85.926 | 88.889 | 96.667 | 2/0 | 363/8 |
| 150 / 500 | 113 / 119 | 83.704 | 88.148 | 94.958 | 2/0 | 386/5 |
| 450 / 500 | 116 / 124 | 85.926 | 91.852 | 93.548 | 3/0 | 468/36 |
| 600 / 500 | 125 / 130 | 92.593 | 96.296 | 96.154 | 1/0 | 376/112 |
| 300 / 0 | 128 / 130 | 94.815 | 96.296 | 98.462 | 1/0 | 370/6 |
| 300 / 250 | 115 / 120 | 85.185 | 88.889 | 95.833 | 2/0 | 374/8 |
| 300 / 750 | 115 / 122 | 85.185 | 90.370 | 94.262 | 3/0 | 468/25 |
| 300 / 1000 | 124 / 129 | 91.852 | 95.556 | 96.124 | 1/0 | 387/87 |

Per-conversation results for all conditions:

| Conversation | Pre / tail (ms) | Accuracy / coverage / labelled accuracy % | Clusters | Split IDs / merged clusters | Shuffled S/M (of 200) |
|---|---|---|---:|---:|---:|
| 1 | 300 / 500 | 100.0 / 100.0 / 100.0 | 2 | 0/0 | 45/0 |
| 1 | -300 / 500 | 100.0 / 100.0 / 100.0 | 2 | 0/0 | 72/0 |
| 1 | -100 / 500 | 100.0 / 100.0 / 100.0 | 2 | 0/0 | 59/0 |
| 1 | 0 / 500 | 65.6 / 68.8 / 95.5 | 3 | 1/0 | 80/0 |
| 1 | 150 / 500 | 68.8 / 71.9 / 95.7 | 3 | 1/0 | 80/0 |
| 1 | 450 / 500 | 78.1 / 81.2 / 96.2 | 3 | 1/0 | 68/0 |
| 1 | 600 / 500 | 100.0 / 100.0 / 100.0 | 2 | 0/0 | 61/0 |
| 1 | 300 / 0 | 100.0 / 100.0 / 100.0 | 2 | 0/0 | 80/0 |
| 1 | 300 / 250 | 75.0 / 78.1 / 96.0 | 3 | 1/0 | 77/0 |
| 1 | 300 / 750 | 75.0 / 78.1 / 96.0 | 3 | 1/0 | 66/0 |
| 1 | 300 / 1000 | 100.0 / 100.0 / 100.0 | 2 | 0/0 | 68/0 |
| 2 | 300 / 500 | 93.9 / 93.9 / 100.0 | 4 | 0/0 | 113/12 |
| 2 | -300 / 500 | 100.0 / 100.0 / 100.0 | 4 | 0/0 | 86/0 |
| 2 | -100 / 500 | 97.0 / 97.0 / 100.0 | 4 | 0/0 | 128/3 |
| 2 | 0 / 500 | 93.9 / 93.9 / 100.0 | 4 | 0/0 | 54/5 |
| 2 | 150 / 500 | 97.0 / 97.0 / 100.0 | 4 | 0/0 | 83/3 |
| 2 | 450 / 500 | 93.9 / 97.0 / 96.9 | 5 | 1/0 | 183/14 |
| 2 | 600 / 500 | 93.9 / 93.9 / 100.0 | 4 | 0/0 | 98/13 |
| 2 | 300 / 0 | 97.0 / 97.0 / 100.0 | 4 | 0/0 | 73/6 |
| 2 | 300 / 250 | 97.0 / 97.0 / 100.0 | 4 | 0/0 | 74/8 |
| 2 | 300 / 750 | 90.9 / 93.9 / 96.8 | 5 | 1/0 | 184/12 |
| 2 | 300 / 1000 | 97.0 / 97.0 / 100.0 | 4 | 0/0 | 95/16 |
| 3 | 300 / 500 | 73.8 / 85.7 / 86.1 | 5 | 2/0 | 200/18 |
| 3 | -300 / 500 | 78.6 / 88.1 / 89.2 | 5 | 2/1 | 200/144 |
| 3 | -100 / 500 | 66.7 / 78.6 / 84.8 | 7 | 2/0 | 200/38 |
| 3 | 0 / 500 | 88.1 / 95.2 / 92.5 | 5 | 2/0 | 200/2 |
| 3 | 150 / 500 | 73.8 / 85.7 / 86.1 | 7 | 2/0 | 200/2 |
| 3 | 450 / 500 | 76.2 / 90.5 / 84.2 | 5 | 2/0 | 200/22 |
| 3 | 600 / 500 | 81.0 / 92.9 / 87.2 | 5 | 2/0 | 200/98 |
| 3 | 300 / 0 | 88.1 / 92.9 / 94.9 | 5 | 1/0 | 200/0 |
| 3 | 300 / 250 | 73.8 / 83.3 / 88.6 | 5 | 2/0 | 200/0 |
| 3 | 300 / 750 | 81.0 / 92.9 / 87.2 | 5 | 2/0 | 200/10 |
| 3 | 300 / 1000 | 81.0 / 92.9 / 87.2 | 5 | 2/0 | 200/61 |
| 4 | 300 / 500 | 100.0 / 100.0 / 100.0 | 3 | 0/0 | 14/0 |
| 4 | -300 / 500 | 96.4 / 96.4 / 100.0 | 3 | 0/0 | 32/3 |
| 4 | -100 / 500 | 96.4 / 96.4 / 100.0 | 3 | 0/0 | 20/10 |
| 4 | 0 / 500 | 96.4 / 96.4 / 100.0 | 3 | 0/0 | 29/1 |
| 4 | 150 / 500 | 100.0 / 100.0 / 100.0 | 3 | 0/0 | 23/0 |
| 4 | 450 / 500 | 100.0 / 100.0 / 100.0 | 3 | 0/0 | 17/0 |
| 4 | 600 / 500 | 100.0 / 100.0 / 100.0 | 3 | 0/0 | 17/1 |
| 4 | 300 / 0 | 96.4 / 96.4 / 100.0 | 3 | 0/0 | 17/0 |
| 4 | 300 / 250 | 100.0 / 100.0 / 100.0 | 3 | 0/0 | 23/0 |
| 4 | 300 / 750 | 96.4 / 96.4 / 100.0 | 3 | 0/0 | 18/3 |
| 4 | 300 / 1000 | 92.9 / 92.9 / 100.0 | 3 | 0/0 | 24/10 |

For Conversation 1 speaker 7850, clip 2 against anchor clip 0 ranges from
0.538 to 0.629 across these conditions (float model, three-decimal reporting).
At pre/tail 300/500 ms it is 0.606; 150/500 gives 0.548, 450/500 gives
0.544, 300/250 gives 0.566 and 300/750 gives 0.538. The relation is not
monotonic in added padding; the existing center crop changes which speech and
context contribute to the fixed model window.

Interpretation: boundaries can materially alter labels without crossing a known
speaker turn. Removing the clip-mode tail raises pooled in-order accuracy from
90.370% to 94.815%, but Conversation 4 falls from 100% to 96.4% and
Conversation 1 shuffled orders with a split rise from 45/200 to 80/200.
This does not support a universal tail-removal change. Some extra-padding arms
also improve selected in-order results while sharply increasing shuffled merges.
None establishes a corrected cut for the original failed microphone session.

Caveats: the Mac model is float and the device trunk quantized; clip mode uses
perfect manifest segmentation, perturbed here around the usual 300 ms pre-roll
and 500 ms tail. Duration changes can affect the unchanged 2 s new-speaker
admission as well as the model window. Shuffles measure order sensitivity, not
realistic turn order. These known conversations are diagnostic/development data,
not held-out generalization evidence. No firmware, acoustic model or production
label policy was changed by this experiment.

Reproduction: run `spkreplay.py` on each of the four manifests at
`--thresholds 0.6 --min-new-ms 2000 --shuffles 200 --seed 1`, adding the
`--pre-ms` / `--tail-ms` pairs above. Numeric per-condition artifacts, the frozen
grid, private runner and model/environment identities remain private;
no audio, vectors, transcripts or session logs are committed.

## Silent pointwise address-walk comparison

Local HardwareOne diagnostic c6252b6e tests a one-column pointer walk in the
existing tiled 1×1 loop. Each kernel call, channel tile and full input-channel
reduction stays in the original order. Filter/spatial tiles remain 16 KiB/64
pixels, with unchanged weights, frontend, speaker policy, compiler and clock
configuration. The prior frontend-clear candidate is excluded. The diagnostic
selector is reset to the original path afterward; it is not a runtime setting.

App size 6,032,320 B; SHA-256
2381da9d1d4f01943a4f554ede67a9480c92ca9c270a8537c80b1f7bd72fda3d.
The selected app, matching ELF/map/build data and source bundle remain private.
The incremental probe patch and MIT-licensed extracted loops are preserved in
`tools/device_tests/kernels/`; no production integration is made.

Host ASan/UBSan testing of the real extracted loop covered 600 rectangles:
311 accepted, 145 one-column, and 554,628 identical ordered body calls per
implementation. Cases include byte widths, strides, aligned body origins,
misalignment, remainders, unsupported activation, null body and empty shapes.
The host substitutes the argument container/body and does not emulate PIE.

Five independently rebooted P4 trials replayed the same 44,560-sample input
with the resident fixed gen2-25397 acoustic model. Four warm-up calls preceded
patterns original/candidate, candidate/original, original/candidate: 15 timed
pairs, 30 timed model calls and 20 warm-ups. Feature, logit and greedy-text
hashes match across both modes and all five boots (50/50 calls). Each inference
exercised 184 tiled calls, all one-column, including 106 calls for 512→512
(the 53 relevant layers split across two workers). No hash identities, tensor
contents, captions or audio are printed in this report.

Paired differences are candidate minus original. Intervals bootstrap whole
boot means (10,000 draws, seed 17); within-boot pairs are not treated as
independent reboot trials. Times are wall measurements; stage sums are not
exclusive CPU time.

| Measure (ms) | Original mean | Candidate mean | Paired difference | Bootstrap 95% interval |
|---|---:|---:|---:|---|
| Transcribe call | 861.077667 | 862.633733 | +1.556067 | [-3.392933, +5.596400] |
| Inference | 788.077733 | 789.235400 | +1.157667 | [-3.437533, +5.275533] |
| Summed model stages | 771.448600 | 772.644800 | +1.196200 | [-3.181400, +5.381133] |
| Inference yields | 3.164200 | 3.360200 | +0.196000 | [-0.114933, +0.506933] |

| Distribution (ms) | Original min / median / max | Candidate min / median / max |
|---|---|---|
| Transcribe call | 849.235 / 860.401 / 875.541 | 852.544 / 862.905 / 872.752 |
| Inference | 777.343 / 787.947 / 802.770 | 778.991 / 790.117 / 800.001 |
| Summed model stages | 760.891 / 771.200 / 788.124 | 762.796 / 773.465 / 781.554 |
| Inference yields | 2.368 / 3.111 / 4.178 | 2.390 / 3.228 / 4.631 |

Per-boot inference differences (ms): -7.467667, +5.857000, -0.641667, +6.623000, +1.417667.

| Memory observation (B) | Original minimum / median | Candidate minimum / median |
|---|---:|---:|
| Scoped minimum internal free | 243,123 / 243,143 | 243,123 / 243,143 |
| Scoped minimum PSRAM free | 3,529,532 / 3,529,600 | 3,529,532 / 3,529,600 |
| Internal free at inference | 247,223 / 247,243 | 247,223 / 247,243 |
| PSRAM free at inference | 3,609,164 / 3,609,232 | 3,609,164 / 3,609,232 |
| Largest internal block after call | 147,456 / 147,456 | 147,456 / 147,456 |
| Largest PSRAM block after call | 3,538,944 / 3,538,944 | 3,538,944 / 3,538,944 |

**Finding:** no measurable improvement. Mean inference change is +0.146898%,
95% interval [-0.435127%, +0.671763%]. The interval includes zero; summed stage
and full transcribe-call intervals also include zero. Measured headroom is
unchanged, and all five lifecycle controls report zero overruns, watchdogs or
fatal markers. The first reboot improved and later reboots moved in both
directions; selecting the first result would have produced a false speed claim.
The candidate is rejected for promotion on the current evidence.

**Limits:** this is one input/shape with full-model equality against the original
kernel path, not the complete export-fixture/length suite or live WER testing.
The acoustic replay uses greedy decoding without the LM and runs with background PDM capture already active, before the normal
capture-feature pool and speaker worker start. End-to-end delivery and ordinary-use fault
rates are not measured. Both modes share hashes, counters, heap monitoring and
extra probe code; code placement/instrumentation may affect cache behavior.
Scoped heap minima include other firmware tasks and are not exclusive allocation
attribution. No PSRAM bandwidth, cache misses or bus transactions were measured.

The owned SD fixture was verified and removed; the original 7,426,048-byte app
slot was restored and fully verified. Final probe: 6,422,528 B LittleFS free,
logging inactive, PDM preferred, speaker model header/footer unchanged, zero
watchdog/fatal markers. Only the app at the verified 0x10000 address was flashed.

Interpretation: this address-calculation shortcut is not a useful demonstrated
gain. Further kernel work should measure cache/bus behavior and attack larger
work or data movement, rather than extrapolating from simpler source code.

## Feature-cache ownership repair and shutdown faults

**Confirmed bounded correctness defect; application qualification incomplete.**
The HardwareOne feature task computes an eight-row batch directly into cache
storage outside `gSTTMux`. Orphan retirement and attached-cache release can wipe
that same uncommitted region. A late DSP completion writes it again after the
cache is marked `FeState::Free` for reuse (its storage remains allocated); the
later generation/state check rejects publication but
cannot undo those writes. This establishes an ownership/data-race defect, not
that a wrong committed prefix was delivered or that it caused earlier crashes.
The forced retirement schedules do not deallocate storage before the worker
joins; no out-of-bounds access or heap use-after-free is demonstrated here.

### Host reproduction and narrow repair

The tests compile the real extracted HardwareOne worker, wipe and retirement
functions with host lock/task adapters and the actual shared acoustic frontend.
Source binding verifies the aa6508fd reference and current candidate; the DSP
implementation is byte-identical in both repositories (SHA-256
09073499b5b7a6af556c90afbde9bec60c1e46030f512c2f665ef904e1fb649a).
The fixed ring, 1,024-sample capture-block margin and controlled preemption
isolate cache ownership from the separate ring-overwrite question.

| Host schedule | Original | Candidate |
|---|---|---|
| Late orphan retirement | 512 nonzero values after wipe; 0 committed rows | 0 nonzero values; 0 committed rows |
| Late attached release | 512 nonzero values after wipe; 0 committed rows | 0 nonzero values; 0 committed rows |
| Overlap under ThreadSanitizer | Data race detected in both retirement paths | Both paths pass |
| Normal live capture | 10 committed, byte-identical reference rows | Same 10 rows, byte-identical |
| Injected invalid first DSP row | 10 rows committed, 1 wrong row; error ignored | 0 rows committed; overrun/fallback flagged |

Local HardwareOne fix 3fff3013 changes only the worker and a shared API comment:
21 added / 3 removed lines in two files. It stages rows in the existing,
worker-owned `FrontendWorkspace::conditioned[512]`, then under the lock checks
the original live generation, copies the batch and publishes its count together.
A failed DSP call cannot publish uninitialized staging data. Batch size and
publication granularity stay unchanged. No extra row-buffer allocation or stack
buffer is added; the configured 3,072-byte task stack, priority/core, model,
feature arithmetic, thresholds, cadence and clocks are unchanged. The normal
patch applies directly to aa6508fd without enabling diagnostics.

The explicit scratch-alias contract first passed 15 standalone ASan/UBSan cases,
1,251 rows, including short/partial lengths and physical ring wrap. Direct,
ring and privately staged outputs are byte-identical. The portable standalone
`StreamPipeline` already stages private rows and commits under its lock; the
older HardwareOne path needed the repair. No whole-app synchronization is made.

### Real P4 tasks: all observations, including failed lifecycles

Temporary diagnostic ebe29cdf adds the original worker as positive control and
a keyed before-DSP scheduling gate. App: 6,032,832 B, SHA-256
2037418536e564af428225eb65c8b3f7b94f21f7593830efb6ccfed2d625687c.
Normal fix source, diagnostic source, matching app/ELF/map/build metadata and raw
results stay private; reproducible patches/tests are in
`tools/device_tests/feature_cache/`.

A startup/source audit clarified placement: PDM capture is already active, while
the normal capture-feature pool and speaker worker have not started. Earlier
notes described fixture diagnostics as before capture; wording is corrected,
not the numerical measurements. The synthetic feature tasks use the real
core 0 / priority 1 / 3,072-byte stack, the same 44,560-sample owned input and a
ring start at absolute sample 65,520. No audible playback is involved.

One smoke reboot and six matrix/replacement attempts ran: seven boots, 42 forced
cases. **All 42 ownership checks passed before shutdown; five lifecycles
completed and two failed.** The planned matrix has four complete lifecycles
and two failed attempts, so it is not presented as five clean matrix runs.
After the replacement failed, unchanged retries stopped; no five-clean-matrix
subset is reported.

| P4 case | Runs per version | Committed rows per run | Original post-retirement nonzero | Candidate post-retirement nonzero | Normal rows equal per version, total |
|---|---:|---:|---:|---:|---:|
| Normal | 7 | 278 | n/a | n/a | 1,946 |
| Forced late orphan | 7 | 0 | 512 each | 0 each | n/a |
| Forced late attached release | 7 | 0 | 512 each | 0 each | n/a |

All 3,892 normal row comparisons across both versions match the unchanged DSP.
Normal-case stack headroom is 2,624–2,628 B in both versions; paused late cases
report 2,720–2,724 B in both. ESP-IDF's high-water API reports bytes. The observed
normal-case stack usage is therefore 444–448 B of the same 3,072-byte allocation;
there is no measured stack-headroom difference in this probe. This is not a
whole-application RAM peak or performance comparison. The speaker fixture
cosine repeats at 0.9928348557423828; no speaker rule/model change is involved.

### Shutdown failures retained

| Attempt | Ownership cases | Normal capture feature rows / speaker jobs | Failure |
|---|---:|---:|---|
| Matrix fifth | 6/6 passed | 0 / 0 | Reset reason 0x7, HP_SYS_HP_WDT_RESET, about 4,654 ms after stop |
| Replacement | 6/6 passed | 0 / 0 | Core 0 load-access fault; MCAUSE 0x5, MTVAL 0x0029607c; software reset 0xc |

The first failure has no panic record or preceding task-watchdog warning line.
The replacement panic occurs about 257 ms after stop and 202 ms after the
speaker-worker completion summary. Matching-ELF symbolication maps MEPC
0x4ff37390 to `tlsf_block_size_max` / `adjust_request_size` / `tlsf_malloc`
(`tlsf_control_functions.h:277,292`, `tlsf.c:437`), RA 0x4ff36df6 to
`multi_heap_malloc_impl` (`multi_heap.c:216`). These identify the observed heap
allocation fault, not its cause. Raw registers/stacks/logs stay
private. No assertion identifier was emitted for this load-access fault.

Both failures occur after the feature and speaker workers' completion summaries,
before terminal STT completion was observed. The speaker summary precedes
destruction of its model and buffers; no later teardown-phase markers exist.
Model release, backend teardown, buffer freeing, completion publication and task
reclamation need instrumentation. The observed allocation fault does not identify
where the invalid state originated. No causal link is established between this fault, the fixed
cache race, extra diagnostic tasks or earlier campaign assertions. The real
capture cache computed zero rows in these two stop failures. This diagnostic
stress sample does not establish ordinary-use crash frequency.

The known-PCM harness now checks reader/fatal/reset state throughout command,
next/ack and stop/status polling, invalidates old run tokens on reset and retains
`failure.json`. Success is persisted only after context/reader shutdown checks.
Synthetic cases cover rebooted replies/acks and context cleanup. The replacement
fault was detected immediately instead of timing out and retrying a stale stop.
The numeric ownership loader rejects a failed-lifecycle marker even if case
records passed. Faulted boots are retained separately from completed lifecycles.

**Status:** the forced-schedule repair is supported by host and P4 evidence;
no WER improvement, ordinary-use reliability gain or fully qualified firmware
replacement is claimed. Application qualification remains incomplete. The next
step is numeric teardown-phase/heap-integrity instrumentation, not more unchanged
retries or promotion of this image. Direct-ring overwrite concurrency is a
separate remaining audit.

After both interrupted blocks, the owned SD fixture was removed and the original
7,426,048-byte app slot restored/full-slot-verified. Final healthy original-app
probe: 6,230,016 B LittleFS free, logging inactive, PDM preferred, speaker model
header/footer unchanged, zero new watchdog/fatal markers. No unqualified image
is left installed. Future playback remains 50%; these tests were silent.

## Technical recordings and pending work

The five vocabulary-heavy recordings each ran once on the restored original
app, with 36 of 36 reference clips retained per recording. Full-recording WER
was 192/443 (43.34%), 183/416 (43.99%), 173/426 (40.61%), 226/470 (48.09%),
and 185/403 (45.91%), respectively. These are full-reference word errors, not
isolated technical-term accuracy; there is no controlled LM-strength comparison.
All five runs completed with zero reported audio overruns, watchdog warnings,
or fatal markers. The five conversation runs also reported zero audio overruns.
Each playback used the Mac speaker at 75% and the onboard PDM mic.

All ten additional sessions checked LittleFS before and after and kept system
file logging inactive. The last recorded free space was 7,016,448 B. Free space
varied over the block and the final reading was lower than the first; the cause
was not established. No filesystem cleanup was attempted. STT was stopped at
the end of each complete session. The saved original app-slot image was restored
and verified over all 7,426,048 B; no other partition was flashed.

The initial campaign had no accessible production runtime strength control or
logit replay, so no controlled LM-strength result is claimed. The subsequent
code-only queue keeps production settings fixed by user direction; it does not
substitute configuration tuning for a code improvement. Standalone runtime
controls described elsewhere are not a matched control for those historical runs.
The first pointwise address-walk candidate is now measured above and rejected
for promotion. Cache/PSRAM traffic, the complete target export-fixture suite and
broader kernel/layout candidates remain open. Memory attribution is partial;
no right-sizing is qualified. Candidate sources/recovery inputs remain private,
and no unqualified change has been integrated into another checkout.

## Teardown phase and heap-integrity diagnostics

Diagnostic-only HardwareOne 5e07c4d9 adds 19 numbered cleanup boundaries:
worker join; speaker trunk/workspace and state buffers; backend park/reset;
audio-buffer release; completion publication; worker self-delete. Each boundary
emits an entry marker and a completed full-heap scan. The app is 6,034,608 B
(SHA-256 0f8cd832535b0287424caab5126026377bd822717ffcce38e1704e0f842ab5c8).
Matching source/app/ELF/map/configuration are retained privately. Model,
algorithms, production settings, task stacks and CPU/RAM clocks are unchanged.
No playback, flashing outside the app slot or system file logging was used.

**Findings:** four silent PDM start/stop lifecycles completed on separate boots:
two without the owned fixture and two with it. Load-time speaker self-test
remained enabled in both conditions. All runs had zero normal capture-feature
rows and zero submitted/labelled/skipped speaker jobs. The fixture condition
also executed all six forced ownership cases, with all 12 checks passing.
These are idle-capture cleanup diagnostics, not transcription accuracy tests.

| Trial ID | Owned fixture | Complete cleanup marker pairs | Logged heap failures | Sum of logged heap scans (us) | First-to-last marker (ms) | Watchdog warnings / fatal markers / audio overruns |
|---|---|---:|---:|---:|---:|---|
| 0 | 0 | 19/19 | 0 | 37427 | 224 | 0 / 0 / 0 |
| 1 | 0 | 19/19 | 0 | 37264 | 208 | 0 / 0 / 0 |
| 2 | 1 | 19/19 | 0 | 35726 | 173 | 0 / 0 / 0 |
| 3 | 1 | 18/19 | 0 | 55864 | 170 | 0 / 0 / 0 |

All 75 fully parsed heap checks passed. Trials 0–2 have all 38 expected entry
and completion markers. Trial 3 has 37: the completed phase-301 marker was
interleaved with a CLI JSON reply and does not satisfy the full marker grammar.
The later phases through 321 completed, and the normal status confirmed terminal
completion. Count that run as a completed device lifecycle but an **incomplete
heap diagnostic**, not 19/19 verified scans. No bytes or fields were reconstructed.
The strict collector stopped on the missing marker and restored the original
app; retrospective `--partial` output retains all four attempts and explicitly
lists missing event [301,1]. Synthetic cases cover this exact omission pattern,
missing model phases, duplicate/out-of-order events and failed heap checks.

The first instrumentation build 7c8736d0 completed one separate no-fixture
lifecycle with 16 passing scans and zero watchdog/fatal markers, but omitted
model phases 200–202 because that source did not inherit the diagnostics policy.
It was rejected as a full diagnostic. The corrected model source includes the
existing policy owner; an undefined policy now fails compilation. Host tests
compile the actual probe with enabled, disabled and missing policies, and the
corrected target object contains the marker format. This was an instrumentation
fix, not a firmware algorithm or model change.

**Interpretation:** cleanup can complete with no detected heap damage both with
and without the fixture in this small instrumented sample. The two earlier
shutdown faults remain unexplained and remain in the report. Full heap scans
and additional output perturb scheduling; these four runs cannot qualify the
uninstrumented repair, measure a speedup or isolate load-time self-test effects.
Heap integrity also does not prove every live object's contents correct. No
WER benefit or ordinary-use reliability improvement is claimed.

A separate host ring-wrap attempt used the actual producer and DSP paths with
192 blocks of 1,024 samples against a 65,536-sample ring. Under ASan/UBSan both
reference and ownership repair rejected the stale batch: zero committed rows,
one overrun. The tested reference schedule did not elicit a ThreadSanitizer
race, so it is **not an accepted race reproducer**; the candidate TSAN stage
was not reached. Attempt source/results remain private. Production ring code
is unchanged; further validation must establish an actual overlap before
claiming a race or its connection to a device fault.

After both diagnostic blocks the original 7,426,048-byte app slot was
restored/full-slot-verified, and the owned fixture was removed. The last healthy
original-app probe found 6,135,808 B LittleFS free, logging inactive, PDM preferred,
speaker model header/footer unchanged, and zero new watchdog/fatal markers.
Every measured block remained above the 2 MiB free-space floor. Small persistent
filesystem changes were retained, not deleted speculatively. Future playback
remains 50%; this entire diagnostic was silent.

Next controlled step: reduce instrumentation perturbation with phase markers
without repeated heap scans, retain all failures, and avoid interleaving CLI
polling with the diagnostic marker stream. Compare the same fixture workloads;
then isolate load-time self-test separately. Neither continued testing nor a
clean selected subset is evidence that the earlier faults are fixed.

## Marker-only cleanup, command-allocation fault and live-ring audit

### Marker collection and retained attempts

HardwareOne 853b2ed8 removed heap scans, emitting one event-2 marker per
boundary. Three no-fixture lifecycles completed with all 19 markers. A fourth
reached phase 321 but a phase-200 marker was interrupted by asynchronous output;
the collector rejected it before obtaining a terminal-status reply. This is a
marker/data-quality failure, not evidence of a new device panic. All four had
zero observed watchdog/fatal markers. The fixture arm was not reached.
The original app was restored/full-slot-verified.

Source inspection identified why passive CLI collection alone did not solve
interleaving: ROM printf bypassed HardwareOne's existing `loglink` single-writer
queue. Diagnostic 002e3a0c uses ESP_LOGI through that queue. Logging remains
enabled, and the normal algorithms, models, stacks and clocks are unchanged.
The app is 6,033,328 B, SHA-256
2211f7e8881d6a2538368296a2eab0315ac1f7a13c99400cf6936375fa5bf6cb.
Matching source/ELF/map/configuration are retained privately.

The planned comparison was five no-fixture and five fixture boots. It stopped
at the first device fault, on the third fixture attempt; two planned fixture
runs were not attempted. Every attempted run produced all 19 markers, including
the faulted run. Event 2 records a boundary only: **zero heap scans were run**.

| Trial IDs | Fixture | Attempts | Completed lifecycles | Faulted | Complete marker sequences | Watchdog warnings | Fatal markers |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0–4 | 0 | 5 | 5 | 0 | 5 | 0 | 0 |
| 5–7 | 1 | 3 | 2 | 1 | 3 | 0 | 1 |

All runs had zero normal capture-feature rows, feature overruns, and submitted /
labelled / skipped speaker jobs. All 18 forced ownership checks in the three
fixture attempts passed before the later fault. There was no playback. Load-time
speaker self-test remained enabled in both conditions. These idle-capture
samples do not measure WER or ordinary-use crash frequency. Three complete
marker sequences in the fixture arm do not substitute for five clean lifecycles.

The passive collector now waits for phase 321 before issuing status; it does
not send status/next/ack while collecting the stream. It separately validates
terminal state and reader health. A complete marker sequence cannot override
a subsequent panic. Synthetic cases cover reset, timeout, missing/corrupted
markers, mixed protocols and terminal-state evidence after a data-quality error.
No damaged marker fields are reconstructed.

### Heap fault after the marked cleanup

Trial 7 logged phase 321 at device ms 43,769, after the model/workspace/buffers
were released and terminal state was published, immediately before worker
self-delete. The panic arrived 81.316 ms after that marker in host receive
timestamps; USB batching means this is not an exact hardware fault latency.
The status request did not return a verified terminal reply.

| Field | Value |
|---|---|
| Core | 0 |
| MCAUSE | 0x5 |
| MEPC | 0x4ff37390 |
| RA | 0x4ff36df6 |
| MTVAL | 0x002960d4 |
| TLSF control pointer, A0 / S5 | 0x002960c4 |
| Requested allocation, A1 / S0 | 6,384 B |
| Saved multi-heap handle | 0x4809e424 |
| Current ELF external-BSS end | 0x4809e424 |

The matching ELF resolves MEPC to the load of `control->fl_index_max` at offset
16, inside `tlsf_malloc`; MTVAL equals A0 + 16. The caller loads the control
pointer from the heap header's `heap_data` field. This identifies an invalid
control pointer for the PSRAM heap, not the writer that damaged it.

The RISC-V stack dump uses bare hexadecimal line addresses. Six saved return
addresses were checked against actual prologue frame sizes and RA offsets in
the matching ELF, rather than treating every code-looking stack word as a
backtrace:

| Frame ID | Stack frame (B) | Saved RA offset (B) | Saved RA / next function ID |
|---|---:|---:|---|
| tlsf_malloc | 48 | 44 | 0x4ff36df6 / multi_heap_malloc_impl |
| multi_heap_malloc | 32 | 28 | 0x4ff20c84 / heap_caps_aligned_alloc_base |
| heap_caps_aligned_alloc_base | 48 | 44 | 0x4ff2096a / heap_caps_malloc_prefer |
| heap_caps_malloc_prefer | 80 | 44 | 0x401059dc / ps_alloc |
| ps_alloc | 32 | 28 | 0x40122d3c / submitAndExecuteSync |
| submitAndExecuteSync | 176 | 172 | 0x40029b06 / hardwareone_loop |

At 0x40122d38, the command dispatcher calls `ps_alloc(sizeof(ExecReq))` with
immediate size 0x18f0 (6,384). The serial loop calls that dispatcher. This places
the observed allocation fault in a new synchronous serial command request,
after the marked STT cleanup, rather than directly in model destruction.
It does not prove the command system caused the heap damage.

The earlier ebe29cdf load-access fault was rechecked using its separately
archived matching ELF. Its six prologue/RA checks and allocation size are
identical. Its MTVAL was 0x0029607c. Both faults expose the same command-request
allocation path. The earlier hardware-watchdog reset still has no corresponding
panic stack. No common corruption origin has been established.

**Interpretation:** the new trace narrows the immediate failure location beyond
`spk_end`: all marked cleanup boundaries had been reached when the later
allocation exposed an invalid heap-control pointer. Deferred task reclamation,
other concurrent work, previous writes and hardware/cache effects are not
excluded. Neither a clean scan sample nor a command-stack location proves a
cause. The original faults remain in the qualification history.

### Live-ring race and sanitizer calibration

Apple clang 21.0.0's runtime help on this Mac reports
`ignore_interceptors_accesses=true`. That setting hides accesses inside
`memcpy`, despite instrumented scalar PCM reads. It explains why the earlier
ring schedule did not produce a warning; its negative result is superseded.
The host tests now explicitly set `ignore_interceptors_accesses=0`.

| Synthetic copy control | Ignore interceptor accesses | Locked | Race detected / exit |
|---|---:|---:|---|
| memcpy / scalar read | 1 | 0 | 0 / 0 |
| Same workload | 0 | 0 | 1 / 66 |
| Same workload | 0 | 1 | 0 / 0 |

With that calibrated setting, the unchanged production ring writer and actual
DSP reproduce a separate race in both aa6508fd's worker and 3fff3013's cache-row
repair. Source binding verifies the producer is identical in both versions.
The host gate forces preemption across 192 producer blocks of 1,024 samples
against the 65,536-sample ring. No copy adapter or DSP replacement was needed.
The production worker reads PCM outside the producer's lock; the producer
copies PCM outside it too. A later head check can reject results but cannot
serialize those memory accesses.

| Worker | TSAN ring race / exit | Separate ASan/UBSan committed rows | Separate overrun count |
|---|---|---:|---:|
| aa6508fd | 1 / 66 | 0 | 1 |
| 3fff3013 cache-row repair | 1 / 66 | 0 | 1 |

This is a host forced-preemption correctness finding, not evidence of delivered
wrong features, a heap use-after-free, a measured WER loss or ordinary-use
frequency. It does not establish a link to the idle-capture command-allocation
faults. The cache-row retirement repair still passes its original suite under
the stricter setting, including its positive controls. The actual portable
StreamPipeline also passes TSAN with interceptor access checking enabled; it
already snapshots private PCM under its lock. No production ring code changed.

Next bounded repair: serialize producer writes and copy a stable row window
under the same lock, then run DSP on private PCM. Reuse the portable pattern;
retain the existing stack configuration and measure actual headroom/critical
copy cost on P4. Byte parity and matched regression gates remain mandatory.

Next fault-location diagnostic: verify ownership of hardware watchpoints on
both cores, then consider a write watchpoint on the PSRAM heap header's control
pointer. The current SDK/profile has three CPU watchpoints and end-of-stack
watchpoint checking disabled. These source checks do not prove a slot is free;
inspect existing per-core trigger state before arming anything. No watchpoint
has been changed on the board yet.

The separate cache-counter semantics audit is recorded in
[P4_CACHE_COUNTER_PLAN.md](P4_CACHE_COUNTER_PLAN.md); target counters remain
unmeasured. No cache geometry or clock change is proposed.

After both marker-only blocks, the original full app slot was restored and
verified. The owned fixture was removed. Latest healthy original-app probe:
6,021,120 B LittleFS free, logging inactive, onboard PDM preferred, model
header/footer unchanged, zero new watchdog/fatal markers. Every measured block
remained above 2 MiB. Future playback stays 50%; all these tests were silent.

## Stable-PCM-window repair and target cost

**Status:** prepared correctness repair, not a speed/accuracy win or a fully
qualified application update. HardwareOne normal candidate b7598680 is on the
local `codex/stt-ab-feature-ring` branch off aa6508fd, with the prior cache-row
repair carried separately as 0e4a59e2 (same source as 3fff3013). No HardwareOne
branch was pushed. The normal candidate was built but not flashed; target
checks used the explicitly labelled cc6a256d diagnostic. Original firmware is
restored. The earlier command-allocation faults remain unresolved.

### Change and host findings

The producer now copies PCM and publishes its head under `gSTTMux`. The feature
worker uses that same lock to snapshot only the sample indices needed by one
stable row into a private 512-sample ring, then performs the unchanged DSP after
unlocking. Frame 0 includes reflected sample 160; other stable rows need at
most 321 samples. Two bounded copies handle private/source ring wrap. Generation,
state and the existing conservative overwrite guard remain checked. Cache-row
staging/publication is retained. No segmentation, speaker policy, acoustic
math, model, preview cadence, stack configuration or clock setting changed.

The private PCM array occupies 1,024 B of the existing worker stack; it is not
a new heap buffer or a larger configured task allocation. The actual portable
StreamPipeline already uses a stable private window and was not rewritten.

| Host worker ID | TSAN forced-wrap race | ASan/UBSan stale committed rows / overruns | Parity cases | Exact checked rows |
|---|---:|---|---:|---:|
| aa6508fd | 1 | 0 / 1 | 104 | 12,904 |
| 3fff3013 cache-row repair | 1 | 0 / 1 | 104 | 12,904 |
| b7598680 stable-window repair | 0 | 0 / 1 | 104 | 12,904 |

The 104 cases combine 13 lengths (320–160,000 samples) and eight starts,
including physical/private wraps and cached tails of long phrases. All three
variants match the actual shared DSP byte for byte for checked stable rows.
ASan/UBSan and strict TSAN both pass the final repair's normal, retirement,
failed-DSP and parity checks; the original race schedules remain positive
controls. Copy-interceptor calibration and the production portable pipeline
also pass. Source binding checks actual producer/snapshot/worker bodies; DSP
entry gating is a host scheduling adapter, not a replacement calculation.

### P4 findings

Five separate boots completed all 50 normal feature-worker cases (25 matched
pairs). Every repaired and reference case matched 278 stable rows from the
same 44,560-sample input: 6,950 exact rows per arm, zero mismatches. The control
is the actual cache-row-only 3fff3013 worker, with only its function renamed.
Pair order alternates and a logged random flip selects each boot's first arm.

Both workers use the original core 0 / priority 1 / 3,072-byte task allocation.
Timing uses the unchanged profile's existing microsecond FreeRTOS runtime
counter, read after each task blocks. No timer hook was added inside either
worker. Wall time includes task creation/readiness polling and scheduling.

| Metric | Cache-row-only control | Stable-window repair | Candidate minus control / bootstrap 95% CI |
|---|---:|---:|---|
| Mean task CPU (us) | 56,302.84 | 56,907.24 | +604.40 [557.56, 653.32] |
| CPU min / median / max (us) | 56,171 / 56,277 / 56,645 | 56,730 / 56,901 / 57,059 | — |
| CPU cost (%) | — | — | +1.07348 [0.98979, 1.16046] |
| Mean creation-to-ready wall (us) | 62,889.96 | 63,412.52 | +522.56 [78.60, 1,099.84] |
| Stack high-water free range (B) | 2,608–2,624 | 1,600–1,612 | Same 3,072-B allocation |

Intervals resample **five boots**, preserving the five matched pairs within
each selected boot: 20,000 percentile resamples, seed 20261101, linear 2.5/97.5
percentiles. The 25 pairs are not treated as 25 independent boots.

| Boot ID | Flip | Control mean CPU (us) | Repair mean CPU (us) | Paired CPU delta (us) | Paired wall delta (us) |
|---|---:|---:|---:|---:|---:|
| 0 | 1 | 56290.20 | 56888.40 | 598.20 | 203.80 |
| 1 | 1 | 56246.40 | 56880.60 | 634.20 | 732.80 |
| 2 | 0 | 56324.00 | 56870.80 | 546.80 | 73.00 |
| 3 | 1 | 56358.20 | 56906.20 | 548.00 | 21.60 |
| 4 | 1 | 56295.40 | 56990.20 | 694.80 | 1581.60 |

The direct snapshot check verified all required PCM values in 12,500/12,500
calls. Whole snapshot-call mean was 5.82304 us (boot bootstrap 95%
[5.54648, 6.20664]); per-case means ranged 4.526–8.026 us, largest observed
whole call 923 us. These calls include guards, lock acquisition, copy and timer
overhead, with possible preemption outside the lock. They are **not isolated
critical-section duration or a worst-case interrupt-latency bound**.

The separate producer microbenchmark repeats 500 maximum contiguous
1,024-sample writes to the same hot location per case: 12,500 calls per arm.
Control / repair means were 4.69304 / 4.67392 us; paired difference -0.01912 us,
boot bootstrap 95% [-0.23184, 0.19624]. Per-case mean ranges were
4.530–6.360 / 4.532–6.202 us; largest whole calls 896 / 828 us. This does not
establish a speedup or bound cold/streaming capture-copy latency. Microbenchmarks
are separate workloads, not additive components of the measured worker cost.

All five complete lifecycles had zero watchdog warnings, fatal markers and
audio overruns. Normal idle capture computed zero feature rows and submitted /
labelled / skipped zero speaker jobs. Target feature checks used known private
PCM while onboard PDM capture was active; they did not send audio through the
microphone. No playback or live-speech WER/latency comparison was performed.
This patch concerns recognition feature caching, not speaker similarity.

**Interpretation:** the repair removes the demonstrated live-ring read/write
race in the tested source paths and preserves checked feature values, with
about 0.604 ms additional feature-task CPU per input in this scope. The positive
cost interval means this is not a performance winner. The fixed stack retains
at least 1,600 B measured headroom. No new heap buffer is requested, but full-app
RAM, speech latency, recognition accuracy and long-run reliability still require
qualification. Five clean diagnostic boots do not resolve the earlier heap
faults or prove an ordinary-use crash reduction.

### Reproducibility and remaining work

Normal app b7598680: 6,026,048 B, SHA-256
8f6827a1227dc5f44dd16857cd04bafd0c8776307b4eac4204626f24b85508ea.
Diagnostic cc6a256d: 6,033,776 B, SHA-256
2defc425174cef479bddfeec5c0ee903c73870a84cfa3135d5ed6c3402d09e5d.
Matching source/app/ELF/map/profile inputs are private. The normal and diagnostic
sdkconfig files are byte-identical; the original reviewed ESP-DL override is
still active. No CPU/PSRAM/cache setting was changed.

`feature-ring-aa6508fd.patch` contains the normal row and ring repairs;
`feature-ring-3fff3013.patch` adds only the ring repair to the existing row fix.
The separate `p4-feature-ring-probe-b7598680.patch` includes diagnostic enablement
and measurement code; it is not part of the normal candidate. The numeric parser
checks pairing order, exact rows, stack/timing fields and lifecycle gates;
synthetic tests reject corrupted, failed and incomplete records. It retains all
attempts when summarizing costs and cannot count a failed boot as clean.

The next fault-origin investigation is described in
[P4_HEAP_WATCH_PLAN.md](P4_HEAP_WATCH_PLAN.md): SDK watchpoint setters do not check
ownership, and RISC-V breakpoints/watchpoints share the same trigger slots.
Readback and expected-trap calibration on both cores are still pending. No board
watchpoint has been armed. Cache traffic remains a separate unmeasured gap.

The owned SD fixture was removed and the original full 7,426,048-byte app slot
restored/full-slot-verified. Final healthy original-app probe: 5,943,296 B
LittleFS free, logging inactive, PDM preferred, model header/footer unchanged,
zero new watchdog/fatal markers. All blocks stayed above 2 MiB. Future playback
remains 50%; this entire test block was silent.

## Heap-header and trigger readback before calibration

The read-only discovery gate completed on two separate diagnostic images:
16bfb713 (TDATA1/2 only) and 647e4858 (adds TDATA3 context filters), one boot each.
Both derive from archived fault-reproduction image 002e3a0c on the local
`codex/stt-ab-heap-watch` branch. They retain that known-input workload and
cache-row-only repair; they do not incorporate the separate b7598680 ring
candidate. No HardwareOne branch is pushed or normal firmware promoted.

### Findings

| Source ID | Completed lifecycles | Readback checkpoints | Core/slot observations | TDATA3 reads | Configurable trigger bits nonzero | Heap-pointer mismatches | Watchdog / fatal / audio overrun |
|---|---:|---:|---:|---:|---:|---:|---|
| 16bfb713 | 1 | 4 | 24 | 0 | 0 | 0 | 0 / 0 / 0 |
| 647e4858 | 1 | 4 | 24 | 24 | 0 | 0 | 0 / 0 / 0 |

Each checkpoint queries both cores and all three trigger indices. The stage IDs
are 0 before speaker-model loading, 1 after speaker-worker join/queue release,
2 after speaker-state destruction, and 3 after backend/audio-buffer cleanup and
transcript completion publication, before terminal-state publication. The
six existing forced ownership checks passed in each run. Normal capture had
zero feature rows and zero submitted / labelled / skipped speaker jobs.
Known-PCM diagnostic work ran while onboard PDM capture was active; no playback
or speech accuracy comparison was performed.

All six physical slots had the same values at every checkpoint:

| Field | Value |
|---|---|
| Cores | 0, 1 |
| Trigger indices per core | 0, 1, 2 |
| Debugger attached | 0 |
| TSELECT before / after | 0 / 0 |
| TCONTROL before / after | 0 / 0 |
| TDATA1 | 0x21000000 |
| Type / maskmax | 2 / 8 |
| Configurable bits (mask 0x081fffff) | 0 |
| TDATA2 | 0 |
| TDATA3 in 647e4858 | 0 |
| IPC errors / selector-restore failures | 0 / 0 |

The manual identifies type and maskmax as read-only capability fields; maskmax
8 describes a 256-byte maximum NAPOT range. Those bits explain the nonzero
TDATA1 value. TDATA3 controls optional context filtering. The decoder now
separates capability/configuration bits and records context coverage rather
than treating every nonzero low bit as an occupied trigger. The first image's
context remained unobserved; the second supplied the missing reads.
[Espressif TRM, pp. 164–166](https://documentation.espressif.com/esp32-p4_technical_reference_manual_en.pdf#page=164).

In both images the heap observations were identical at all four checkpoints:

| Heap field | Value |
|---|---|
| Heap start / matching ELF external-BSS end | 0x4809e424 |
| heap_data field address | 0x4809e434 |
| Read control pointer | 0x4809e438 |
| Expected control pointer | 0x4809e438 |
| First mismatching stage | none |

The installed SDK's non-ROM heap descriptor is five 32-bit fields. Its
registration initializes the control immediately after that descriptor; the
runtime observations match the pinned layout. This verifies the target field
and expected pointer for these images. Future images must derive/verify their
own addresses instead of copying this numeric address blindly.

### Interpretation and next gate

The observed trigger state matches the inactive reset shape on both cores;
there is no observed attached debugger or context qualifier. This is point-in-time
discovery, not a permanent lease. Recheck immediately before arming and preserve
unexpected owner state. The readback helper exposes only slot-selector writes,
restores the saved selector and interrupt mask, and compares global control
before/after. It never writes trigger configuration/address/context or arms /
clears a watchpoint. No watchpoint was armed in either run.

The expected heap pointer in these samples does not explain or cure the earlier
corruption. This is not a heap-wide integrity proof, a crash-rate estimate or a
qualified application update. The next gate is a labelled expected-trap
calibration on a synthetic four-byte word, separately for each core, followed by
post-trap state/owned-cleanup verification. Only then monitor the real heap
field. No corruption writer has been identified.

The manual notes that TINFO can be absent and trap on read. Its support was not
probed; the already observed type field supplies the needed trigger type.
The register default tables also do not alone establish recovery through this
specific panic/USB reset sequence. Capture actual post-trap state during
calibration. See P4_HEAP_WATCH_PLAN.md for ownership and panic-context limits.

### Reproducibility and recovery

16bfb713 app: 6,035,008 B, SHA-256
229e7ad9efeb6adc6c8d4f03f836da176534e10d90be812a1bd142edbd17c2b8.
647e4858 app: 6,035,232 B, SHA-256
1da2c6509b94b27f8e586ac7d098221da18261bce54b71bf79c9fa17185d4891.
Matching source/app/ELF/map/profile artifacts are private. The sdkconfig matches
002e3a0c byte for byte; CPU/PSRAM/cache settings, models and labelling policy
are unchanged. `p4-heap-readback-002e3a0c.patch` contains only the diagnostic
addition. Source-template host tests check selector/IRQ restoration, all slot
values, unsupported selection and changed global state. Numeric parser cases
cover real capability defaults, missing context, mixed formats, corruption and
heap mismatch; complete tables do not override lifecycle health checks.

Both blocks removed their owned SD fixture and restored/full-slot-verified the
original app. Healthy post-restore LittleFS free was 5,967,872 / 5,935,104 B;
logging inactive, PDM preferred, model header/footer unchanged, zero new
watchdog/fatal markers. All measurements stayed above 2 MiB. All tests were
silent; future playback remains 50%.


## Synthetic store-watchpoint calibration

### Findings

| Source / core | Expected traps | Expected / observed PC | MCAUSE | Read + adjacent store | Watched word after reset | Serial reopened before recovery |
|---|---:|---|---:|---|---|---|
| 18da8a44 / 0 | 1 | 0x4ff22cd0 / 0x4ff22cd0 | 3 | pass | 0x13579bdf | yes |
| f8a2a5bc / 1 | 1 | 0x4ff22cd0 / 0x4ff22cd0 | 3 | pass | 0x13579bdf | no |

Each run armed only slot 0 of its named core. Both cores' three slots were
checked inactive before arming; a fresh local check occurred under the saved
interrupt mask immediately before the SDK arm call. The naturally aligned RTC
no-init target was 0x50108234, four bytes. Armed TDATA1 / TDATA2 / TCONTROL were
0x210000ca / 0x50108235 / 0x88. The matching ELFs identify the compressed
`sw a5,0(a0)` at 0x4ff22cd0 as the sole deliberate faulting store. Reads and a
store to the following word returned normally before the watched store.

The retained phase was 2 in both recoveries. The watched value was unchanged
from initialization (0x13579bdf), and the adjacent word held 0x2468ace0. The
attempted watched replacement was 0x51a7cafe. These observations are consistent
with a trap before the matching instruction takes effect. The trigger hit bit
was not captured before reset and is not claimed as observed evidence.

Both recovery reads found slot 0 TDATA1=0x21000000, TDATA2=0, TCONTROL=0. All
three slots on both cores, including TDATA3 context qualifiers, had the inactive
shape at all four subsequent lifecycle checkpoints. Thus recovery required no
trigger-data/control writes in these actual runs. The release helper accepts
only the exact owned diagnostic address/configuration (allowing the hit bit),
refuses unexpected owners, and restores local selector/interrupt state. It can
clear an owned trigger if retained; that branch is host-tested, not target-hit
in these runs.

Both recovery STT lifecycles reached done with zero audio overruns and no new
watchdog/fatal markers. Each deliberate MCAUSE=3 trap is retained separately;
neither is counted as a clean STT lifecycle or an unexpected ordinary-use
crash. No fixture was uploaded for this block. No audio was played; PDM was
verified and future playback remains 50%.

### Interpretation and limits

The store-watchpoint path catches the intended CPU store on each core. This
establishes a positive control for a later heap-field watch, not a corruption
origin, an accuracy gain, a crash-rate estimate or an application qualification.
The synthetic target is RTC memory, not the PSRAM heap. It does not establish
coverage of DMA, all address aliases, cache behavior or unarmed intervals.

Core 0's first controller closed/reopened serial before recovery; opening the
port can reset this board. Its inactive recovery state therefore covers the
combined panic/reopen sequence and does not isolate panic-reset behavior. Core
1 kept the same serial handle, including through the post-panic readback and
cleanup, with no further reset/fault during that recovery. Only one core's
trigger was armed in each experiment. Before arming both cores on the actual
heap field, perform the bounded follow-up with both cores armed on the
synthetic word, a deliberate core-0 store, continuous serial and verification
of the non-firing peer's post-reset state. This also removes core 0's reopening
confound. Then watch the real heap field using addresses derived from the new
matching ELF/runtime layout and retain any writer trap or workload failure.

The earlier two heap-control-pointer faults remain unresolved. The diagnostic
uses the earlier cache-only fault workload base 647e4858; it does not combine
the ring correctness candidate with this investigation. Configuration is
byte-identical to the prior readback build. Models, recognition math, speaker
policy, clocks, cache settings and configured task stacks are unchanged. No
panic-hook or system-file-logging change is included.

### Reproducibility

18da8a44 app: 6,037,696 B, SHA-256
267b301b26fc94aa203abf465d6a000d2f0f5badea29564a61ed073d999d1f3f.
f8a2a5bc app: 6,037,712 B, SHA-256
cb8fc8478bc8a2505b97064dac903d82f3149f707dfbb9a62e04c95a07131a18.
Selected matching ELF/map/configuration and bounded source bundles are private.
The public incremental patch applies to 647e4858 and reproduces f8a2a5bc's
three touched file endpoints; selecting core 0 reproduces the earlier source.
Source-bound lease/release host tests pass under ASan/UBSan. Numeric parser
tests include both cores, exact PC/cause matching, owned and reset post-states,
refusal, truncated/duplicate markers, changed words and extra traps. Raw logs,
registers, private evidence and binaries are not committed. HardwareOne branches
remain local; only the STT diagnostics branch receives the public report/tools.

Both blocks restored the original 7,426,048-byte app slot and verified it
against the saved baseline. Final healthy baseline LittleFS free was
5,906,432 B after core 0 and 5,869,568 B after core 1; logging inactive, PDM
preferred, model header/footer unchanged, zero new fatal/watchdog markers. All
readings were above 2 MiB. No SD fixture was created. The existing owned build
is retained for the bounded simultaneous-arming follow-up; selected compact
recovery/debug inputs remain private before that build is reused.


## Both-core synthetic recovery and heap-field watch

### Both-core calibration findings

06b04fbe armed slot 0 on cores 0 and 1 against the same four-byte RTC word
0x50108234. Both read/adjacent-store controls passed; both configurations were
rechecked before the deliberate core-0 store. One expected trap occurred at
0x4ff22cd0, matching the ELF's store instruction; MCAUSE 3. The word remained
0x13579bdf and its neighbour held 0x2468ace0. Serial stayed open through panic
and recovery. Neither core showed an active trigger on the recovery read:
TDATA1=0x21000000, TDATA2=0, TCONTROL=0 for both the firing core and non-firing
peer. Both cores' three slots and context qualifiers retained inactive state
at all four subsequent readback checkpoints. No trigger-data/control clear was
needed in this run. Recovery STT reached done with zero new fatal/watchdog/
overrun markers, and the original app was restored/full-slot-verified. Final
healthy baseline: 5,844,992 B LittleFS free, logging inactive, PDM preferred,
model header/footer unchanged. The expected trap is separate from ordinary
failures. No PSRAM/DMA or pre-reset hit-bit coverage follows from the RTC test.

06b04fbe app: 6,037,968 B, SHA-256
1fe97d6b2be4f05d05dbf9312a7a665a6442138f9ff2d7151bf8cdb3c64dceed.
The sdkconfig is byte-identical to 647e4858; matching debug/source inputs stay
private. The incremental patch reproduces the single touched file endpoint.
The dual parser requires both arm/probe pairs, the final two-lease verification
and both recovery rows. Missing/changed peer evidence is rejected.

### Actual heap-watch design and timing qualification

e1044e86 replaces automatic calibration with explicit diagnostic-only
`sttperf heapwatch arm|off` commands, accepted with the STT worker inactive.
The field is derived from this matching ELF/runtime heap start, and its pointer
must match the pinned SDK layout before arming. A fresh per-core ownership
check occurs under the saved local IRQ mask. The watch remains armed through
all STT teardown markers, terminal publication and the following terminal
status-command allocation. Release is a later command; only a recorded, exact
owned configuration may clear. With no lease, occupied slots are preserved.
IPC callbacks do not log, allocate or hold cross-core locks. Neither path
writes the heap header. The diagnostic is based on the earlier cache-only
fault workload, not the separately prepared ring candidate.

The first five-boot batch completed but released shortly after the terminal
reply. Same-clock log prefixes show only 2,378–3,982 ms of watch time after
phase 321. This does not cover the earlier approximately 4,654-ms-after-stop
watchdog window in every trial. A separate follow-up holds the watch for six
seconds after the terminal reply; retain these timing cohorts separately.

An initial cross-clock subtraction overstated the post-cleanup intervals by
approximately 1.5 s. Installed `log/src/os/log_timestamp.c` uses a scheduler
clock/base, while teardown's explicit `ms=` uses esp_timer. The parser now
compares log prefixes with each other for intervals. Same-clock arm/release
watch durations were unaffected. Synthetic tests explicitly exercise this
clock distinction; raw logs are not altered or reconstructed.

### Heap-watch numeric findings

Matching ELF heap start / watched field / expected control pointer:
0x4809e424 / 0x4809e434 / 0x4809e438. Each trial armed slot 0 on both cores
with TDATA1=0x210000ca, TDATA2=0x4809e435, TCONTROL=0x88. All four readbacks
per trial found both watches present, other slots inactive, zero context
qualifiers, no debugger, restored selectors and the expected heap pointer.
The installed SDK assigns heap_data at registration; no later write was caught.

| Cohort | Fresh-boot trials | Watch duration ms, min / median / max | Sum of watched ms | After phase 321 ms, min / median / max |
|---|---:|---|---:|---|
| e1044e86 initial | 5 | 12,294 / 12,343 / 13,964 | 64,668 | 2,378 / 2,435 / 3,982 |
| e1044e86 dwell6 | 5 | 18,334 / 20,107 / 21,491 | 98,567 | 8,478 / 10,118 / 10,847 |

The added host wait measured 6,009 / 6,021 / 6,037 ms (min / median / max).
The combined 163,235 ms is the sum of separate armed intervals across ten
trials; startup and between-run unarmed gaps are excluded. These are descriptive
fault-tracing durations, not a baseline/candidate speed comparison.

| Cohort / trial | Watch ms | Watch after phase 321 ms | Added terminal hold ms |
|---|---:|---:|---:|
| initial / 0 | 12,343 | 2,435 | 0 |
| initial / 1 | 12,294 | 2,420 | 0 |
| initial / 2 | 13,964 | 3,982 | 0 |
| initial / 3 | 13,730 | 3,849 | 0 |
| initial / 4 | 12,337 | 2,378 | 0 |
| dwell6 / 0 | 20,107 | 10,118 | 6,022 |
| dwell6 / 1 | 20,109 | 10,281 | 6,009 |
| dwell6 / 2 | 18,334 | 8,559 | 6,037 |
| dwell6 / 3 | 21,491 | 10,847 | 6,016 |
| dwell6 / 4 | 18,526 | 8,478 | 6,021 |

Across ten completed trials: zero caught heap-field writes, zero fatal markers,
zero watchdog warnings and zero audio overruns. All 60 forced ownership checks,
80 active trigger observations, 40 heap-pointer observations and 190 teardown
markers passed. Both cores were released to inactive state after each covered
terminal reply. Normal capture had zero feature rows, feature overruns, finals,
cached/draft rows and submitted/labelled/skipped speaker jobs in all ten runs.
Known-input fixture work was performed while onboard PDM capture was active;
this was not a microphone speech-accuracy or long-run application qualification.

### Interpretation and next experiment

The earlier faults did not reproduce in these bounded watched intervals. The
writer remains unknown. Trigger visibility is verified at four checkpoints per
run; the samples do not prove permanent ownership between reads or rule out
DMA, aliases, different timing, register/argument corruption or events outside
the interval. Instrumentation and additional command allocations can perturb
a timing-dependent failure. Neither the earlier faults nor this negative
batch establishes an ordinary-use crash rate. No WER, speaker-accuracy, RAM
speed or performance gain is claimed.

The positive store controls used RTC memory. The next bounded check should
watch a separate allocated PSRAM word and catch its deliberate store without
writing the heap descriptor. That directly tests the memory path relevant to
this negative heap-watch result. Preserve both-core ownership/recovery guards,
exact ELF PC verification and the original-app rollback. The PSRAM-path
positive control is not yet performed; do not count it as completed coverage.

e1044e86 app: 6,037,952 B, SHA-256
2652cbcbed0da343a8f2f4ba1b5def1ef03af74e908b8a12f14904ca9138d9f9.
The public patch reproduces its four touched file endpoints after 06b04fbe.
The matching app/ELF/map/configuration and bounded source bundle are private.
SDK configuration remains byte-identical to 647e4858 and ESP-DL override checks
match the restored original override. No production algorithm/model, clock,
cache geometry, configured stack or file-logging policy was changed. Host
ASan/UBSan tests cover fresh arming, occupied slots, SDK failures/readback
mismatch and exact owned release; parsers cover both-core/interval/cleanup
requirements, historical versus live faults and damaged/missing evidence.

Both five-trial blocks removed their separately owned/content-verified fixture
and restored/full-slot-verified the original 7,426,048-byte app. Healthy final
baseline LittleFS free: 5,767,168 / 5,689,344 B. Logging inactive, PDM preferred,
speaker model header/footer unchanged, zero new fatal/watchdog markers. All
observed free-space readings remained above 2 MiB. No audible playback occurred;
future playback remains 50%. No HardwareOne branch is pushed or promoted.
The one owned build remains needed for the next PSRAM-path diagnostic; selected
matching app/debug/source inputs are archived before it is reused.


## PSRAM scalar-store watchpoint controls

### Findings

| Source / firing core | Allocated target | Payload bytes | Both cores armed | Expected / observed store PC | MCAUSE |
|---|---|---:|---:|---|---:|
| fcdc25dd / 0 | 0x49625bf8 | 8 | 2 | 0x4ff22cd0 / 0x4ff22cd0 | 3 |
| 4404da4e / 1 | 0x4826ac8c | 8 | 2 | 0x4ff22cd0 / 0x4ff22cd0 | 3 |

Each trial allocated a word and neighbour with SPIRAM/8-bit capabilities and
checked both allocation endpoints using the installed SDK's external-RAM
classifier. Both cores' three shared trigger slots were checked inactive first;
arming was rechecked locally under the saved interrupt mask. Slot 0 on both
cores used TDATA1=0x210000ca, TDATA2=target|1 and TCONTROL=0x88. Reads of the
watched word and stores to its neighbour returned on both cores before the
intended store. Both leases were rechecked before the expected trap.

Both matching ELFs identify the faulting instruction as the compressed scalar
`sw a5,0(a0)` at 0x4ff22cd0. Each produced exactly one expected breakpoint
trap, on its selected core. There were zero watchdog warnings in these trap
records. These deliberate traps are counted separately from unexpected
ordinary-use failures and from the subsequent successful STT lifecycles.

Pre-trap probe values retained in RTC: word=0x13579bdf, neighbour=0x2468ace0.
The attempted store value was 0x51a7cafe. The retained values are snapshots
from before the store, not reads of PSRAM after reboot. The old allocation was
not dereferenced or freed after reset; the new boot's allocator owns PSRAM
again. The ordinary target pointer resets to null. Distinct PSRAM recovery
markers and parser fields preserve this provenance and omit word_unchanged.

Serial remained open through each panic and recovery. Both cores read
TDATA1=0x21000000, TDATA2=0, TCONTROL=0 on recovery; no trigger-data/control
clear was needed. The six physical slots, including context qualifiers, were
inactive at all four later lifecycle checkpoints in both runs: 48 context/slot
observations and eight expected heap-pointer observations in total. Both
recovery STT sessions reached done with zero new fatal/watchdog/overrun markers.
No SD fixture or audio playback was used.

Both original app slots were restored/full-slot-verified. Healthy baseline
LittleFS free after core 0 / core 1: 5,652,480 / 5,615,616 B; logging inactive,
onboard PDM preferred, speaker-model header/footer unchanged, zero new
fatal/watchdog markers. All readings stayed above 2 MiB. Future playback is 50%.

### Interpretation and remaining coverage

Direct aligned 32-bit CPU stores to two selected cached-PSRAM addresses are
observable with this watchpoint setup on both cores. The earlier ten negative
heap-field watches remain bounded negative results; no corrupting writer,
accuracy improvement or application-reliability qualification has been found.
The controls do not prove coverage of every address, alias, access width, DMA
write or instruction path. No pre-reset trigger hit-bit observation is claimed.

The next bounded control should use an aligned owned PSRAM block and an actual
128-bit store, comparing a watch at the store's base with a watch four bytes
inside its span. The latter matches the heap field's offset within a 16-byte
alignment block. The installed ESP-DL copy assembly contains
`esp.vst.128.ip`; scalar coverage alone does not measure that vendor instruction.
Retain either outcome: an exact-PC trap or a returned store with an observed
changed target and verified owned release. Do not broaden the real heap watch
until legitimate neighbouring heap-metadata writes and the new coverage are
understood. Aliases, DMA, timing and register/argument corruption remain open.

The generic RISC-V trigger specification requires a compare value for the
lowest accessed address and recommends additional values for other accessed
addresses. This motivates the overlap test; P4 vendor-instruction behavior
requires measurement. [RISC-V mcontrol address selection](https://github.com/riscv/riscv-debug-spec/blob/main/xml/hwbp_registers.xml#L335-L342).

### Reproducibility

fcdc25dd app: 6,040,560 B, SHA-256
9c8e6af24de59a03bb82217fcb8cebf2753f0df706e9bc465ee0e7ca9c31bf3c.
4404da4e app: 6,040,560 B, SHA-256
3e6df43710a4de533c340c5773d4ff41c8193fd7cb05c52af19d1167abc03aad.
The public incremental patch reproduces 4404da4e's two touched file endpoints
after e1044e86; selecting firing core 0 reproduces fcdc25dd source. Matching
app/ELF/map/configuration and bounded source bundles are private. SDK config
is byte-identical to 647e4858 and the ESP-DL override check matches the restored
original override. Models, production speaker policy, clocks, cache geometry
and configured task stacks are unchanged; the heap descriptor is never written.

The parser adds a PSRAM mode requiring target kind/size/external classification,
a cached-address-window check from the pinned P4 soc.h, both arm/probe pairs,
exact trap and both recovery records. Synthetic tests reject mixed RTC/PSRAM
formats, invalid classification/addresses, missing peers, changed probe values
and damaged evidence. Prior RTC modes remain tested. No real-line parse fix
was required. Raw logs, registers, audio and private data are not committed.


## 128-bit PSRAM store overlap controls

### Findings

570be9f8 used one labelled image and three explicit conditions. Each allocated
a 16-byte-aligned, 32-byte payload and watched four bytes on both cores.
Before arming, each CPU separately observed the old four-word pattern, executed
an unwatched 128-bit store and verified the changed four-word pattern. Values
were reset between CPUs. Both read/adjacent-store probes and lease checks then
passed. The matching ELF identifies `esp.vst.128.ip q0,a0,16` at 0x4ff22ccc.

| Condition | Firing core | Watch offset bytes | Store base | Watched address | Trap PC | MCAUSE |
|---:|---:|---:|---|---|---|---:|
| 0 | 0 | 0 | 0x480d4a40 | 0x480d4a40 | 0x4ff22ccc | 3 |
| 1 | 0 | 4 | 0x480d4a40 | 0x480d4a44 | 0x4ff22ccc | 3 |
| 2 | 1 | 4 | 0x480d4a40 | 0x480d4a44 | 0x4ff22ccc | 3 |

All three conditions produced exactly the intended trap: six unwatched vector
execution checks and six read/adjacent checks passed; both watches were
verified before each store. Zero returned-store outcomes occurred. Serial was
not reopened across any panic/recovery pair. Both cores read inactive slot 0
state after every panic (TDATA1=0x21000000, TDATA2=0, TCONTROL=0), and the
firmware's fresh full-slot/context checks reported both cores idle. No old
PSRAM allocation was read or freed after reset. No pre-reset hit-bit or
post-reset target-content observation is claimed.

A final quiet STT smoke lifecycle reached done, zero fatal/watchdog/overrun
markers, with all four trigger-readback checkpoints inactive and expected heap
pointers. No SD fixture or playback was used. The original 7,426,048-byte app
slot was restored/full-slot-verified. Final healthy baseline: 5,562,368 B
LittleFS free, logging inactive, onboard PDM preferred, model header/footer
unchanged, zero new fatal/watchdog markers. Future playback remains 50%.

### Interpretation and reproducibility

The four-byte watch catches this 128-bit instruction both at the store base
and four bytes inside its span on the tested cores. This closes the tested
overlap case; it does not explain the ten negative heap-watch trials or identify
a corrupting writer. Other instructions, aliases, DMA, different timing and
register/argument corruption remain unproven. No crash-rate, speech accuracy
or performance improvement follows from these deliberate memory controls.

App: 6,041,840 B, SHA-256
2579717e59ea589c3f10c7a2d1efa7e4cf694b71e37c8c3d817bf715a4d14795.
The incremental patch reproduces three touched file endpoints after 4404da4e.
SDK configuration matches 647e4858 byte for byte; the restored ESP-DL override
check passes. Models, production labelling, clocks/cache geometry and configured
stacks are unchanged. Matching app/debug/configuration/source inputs remain
private. The strict parser requires both execution controls, arm/probe pairs,
lease verification, exact trap/core and owned recovery. It also validates a
returned store only with changed target data, watch readback and both releases;
that branch has synthetic coverage, not a target observation in this block.

## Allocator argument recheck and independent I2C bounds candidate

### Findings

The archived 002e3a0c ELF was rechecked against the saved fault registers/stack:

| Field | Value |
|---|---|
| Caller argument load | 0x4ff36df2: load from heap + 16 |
| TLSF call / saved return | 0x4ff36df4 / 0x4ff36df6 |
| Saved caller heap slot | 0x4ff5f4a8 |
| Saved caller heap value | 0x4809e424 |
| Derived heap_data address | 0x4809e434 |
| Observed TLSF argument / matching S5 | 0x002960c4 / 0x002960c4 |
| Fault address | 0x002960d4 |
| Explicit heap-field snapshots in that log | 0 |

The argument load is immediately before the call. The saved caller heap value
is from the callee's ABI-verified saved-S0 slot, not an arbitrary code-looking
stack word. This supports the watched-field choice. The old log does not
directly dump that field's contents at the fault, so a bad argument is observed
while a memory overwrite's timing/writer remains inferred.

The same ELF/map places a 1,596-byte Arduino I2C bus array at 0x4809dde8,
ending exactly at 0x4809e424. Its attribution is esp32-hal-i2c-ng.c. This
proximity prompted a separate source audit, which found that the pinned
`i2cRead` and `i2cWriteReadNonStop` paths pass a uint16 address to the common
cache helper without the 7-bit guard already present in `i2cWrite`. The helper
indexes dev_handles[128] before any range check.

A source-bound host test compiled the actual helper and bus type. Address 128
reproduced an out-of-bounds read under ASan/UBSan with strict trailing-array
bounds. The guard candidate returns invalid-argument before indexing. Five
invalid cases (128,129,255,256,65535), two in-range boundaries (0,127) and one
existing-handle reuse case passed with stub hardware APIs. No SDK hardware
call occurred in the invalid cases. No physical I2C transaction was performed.

Apple clang 21.0.0's default sanitizer compilation did not produce the bounds
diagnostic for this trailing array. The calibrated strict build uses
fstrict-flex-arrays=3 and reproduces it; both build outcomes are retained
privately. This is host instrumentation, with no device configuration change.
The prepared patch adds the missing guard in the common helper. The installed
Arduino file remains byte-identical, SHA-256
d05cf90b96b6023061be5993959bb3fd6d802b9c43e2e31d71b72b5c4643ee53.

### Interpretation and next work

The bounds read is a reproducible independent correctness flaw in the pinned
dependency. Invalid I2C input during the STT failures has not been established.
The array's adjacency does not prove a write into the heap or make this driver
the corrupting writer. The candidate is host-tested only, not applied, flashed
or promoted. Keep it separate for review and eventual public-wrapper/target
qualification; valid address behavior must remain unchanged.

Next inspect actual caller/alias paths and plan a minimal fault-time capture
of the heap field alongside the allocator argument. The SDK exposes a
non-cached alias via a +0x40000000 offset; 0x8809e434 is the macro-derived
candidate alias of the earlier field, not a measured fault-time value. Do not
infer coverage of that alias from the cached scalar/vector controls. Any
additional instrumentation must preserve panic-context restrictions, ownership,
models, clocks, logging and rollback. No writer or corruption cure is claimed.
