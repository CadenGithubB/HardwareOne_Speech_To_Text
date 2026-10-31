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
- In the measured debug block, four sessions completed without fault markers or
  reported overruns. The fifth and its first replacement asserted in the TLSF allocator during
  shutdown and rebooted. A subsequent replacement reported a task-watchdog
  warning but drained with zero overruns. These three attempts are excluded
  from clean-session statistics and retained in the fault count.

## Comparisons

| Comparison | Valid sessions per arm | Outcome |
| --- | ---: | --- |
| Debug vs lean logging | 4 / 0 | Lean control in progress; confidence intervals pending |
| Preview cadence | 0 / 0 | Pending |
| Speaker labels and conversation accuracy | 0 / 0 | Pending |
| Pointwise kernels and traffic | 0 / 0 | Pending |
| RAM attribution and right-sizing | 0 / 0 | Pending |
| LM strength and technical vocabulary | 0 / 0 | Pending |

No win is claimed without the requested matched runs and confidence intervals.
