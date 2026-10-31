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
of two runs; it has been checked only on synthetic logs
(`tests/test_spkdiag.py`), not yet on these private sessions.

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
