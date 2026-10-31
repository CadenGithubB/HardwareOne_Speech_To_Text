# P4 STT A/B results

31 October 2026. **In progress; no optimization has been qualified.** The
fixed gen2-25397 model, onboard PDM microphone and Mac speaker are used. The
speaker output is fixed at 75%. Raw audio, captions, logs and flash images are
private and are not included here.

## Qualification and safety

- USB MAC matched the designated P4. The read-back partition table places the
  app at `0x10000`, length `0x715000`, and LittleFS at `0x725000`.
- A complete 7,426,048-byte app-slot rollback image was saved privately before
  testing and verified against the device. The matching rebuilt baseline was
  subsequently flashed at `0x10000` only. The preview-cadence candidate is
  was tested at the same app address. The speaker-off candidate is now
  installed there. All writes verified; the original image is reserved for
  restoration. No other partition was flashed.
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

| Comparison | Valid sessions per arm | Outcome |
| --- | ---: | --- |
| Debug vs lean logging | 5 / 5 | No clear difference; fault-affected attempts retained separately |
| Preview cadence | 5 / 5 | Fewer previews, later first preview; not a qualified win |
| Speaker labels and conversation accuracy | 0 / 0 | Pending |
| Pointwise kernels and traffic | 1 profile | Profile captured; traffic and kernel comparison pending |
| RAM attribution and right-sizing | 1 phase sample | Partial attribution; transient peaks and resizing pending |
| LM strength and technical vocabulary | 0 / 0 | Pending |

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

An LM-strength sweep remains blocked: the available production firmware lacks
an accessible runtime strength control and logit export/replay path, and the
user reserved further firmware development for another agent. The profile
identified the pointwise stage as a candidate for investigation, but no kernel
or layout candidate was prepared or tested against the export fixtures. Memory
attribution is incomplete and no right-sizing has been qualified. Candidate
sources are preserved in a private Git bundle based on `aa6508fd`; no candidate
has been integrated into another checkout. These are follow-up work, not wins.
