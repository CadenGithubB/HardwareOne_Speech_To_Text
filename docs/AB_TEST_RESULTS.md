# P4 STT A/B results

31 October 2026. **In progress; no optimization has been qualified.** The
fixed gen2-25397 model, onboard PDM microphone and Mac speaker are used. The
speaker output is fixed at 75%. Raw audio, captions, logs and flash images are
private and are not included here.

## Qualification and safety

- USB MAC matched the designated P4. The read-back partition table places the
  app at `0x10000`, length `0x715000`, and LittleFS at `0x725000`.
- A complete 7,426,048-byte app-slot rollback image was saved privately before
  testing. No firmware has been flashed.
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
| Preview cadence | 0 / 0 | Pending |
| Speaker labels and conversation accuracy | 0 / 0 | Pending |
| Pointwise kernels and traffic | 0 / 0 | Pending |
| RAM attribution and right-sizing | 0 / 0 | Pending |
| LM strength and technical vocabulary | 0 / 0 | Pending |

No win is claimed without the requested matched runs and confidence intervals.

These are stress-test outcomes under serial polling, periodic memory reports and
repeated start/stop cycles. The user reports that crashes are uncommon in their
ordinary STT/transcription use. These experiments do not establish real-world
crash frequency or isolate the cause of an assertion.

## Logging control

Five complete standard-playlist sessions per arm at 75%; debug and control
runs were collected in blocks, not randomized. The control disabled the
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
