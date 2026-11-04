# Quiet-speech admission threshold A/B

The question is whether lowering the speech-admission threshold recovers quiet words without degrading ordinary recognition or producing extra background captions.

## Fixed experiment

Replay the actual portable C++ StreamPipeline with identical samples at speech floors 45 (current), 32, 24 and 16. The silence floor stays 16. Background-relative gating, 25th-percentile noise estimation, phrase timing, maximum duration and full-tail mode are fixed. The worker drains each final synchronously. All arms use the same deployed int8 model, no-dither portable C++ frontend and meeting language model. This comparison excludes inference backlog and live task timing.

The cases consist of 32 six-second physical P4 captures (eight phrases at ordinary and quiet playback levels in each of two orientations), 45 speech cases from the existing development release suite, and six one-minute background conditions. Recorded audio and all hypotheses are private. Both orientations contain the same phrases, so they are repeated physical recordings rather than independent language samples.

Background conditions are digital silence, synthetic room tone, cycling synthetic fan, synthetic taps and two recorded DEMAND ambience windows from the designated training partition. Recorded ambience can contain incidental speech. Output on those recordings must be interpreted as background-triggered captions rather than proven hallucinations.

The suite is frozen under `private/admission-ab/manifest.json`. It identifies each PCM, the model, language model and frontend sources. Per-case cuts, raw hypotheses, word edits and cached recognition outputs are preserved there. The shared model and firmware settings have not been modified.

## Acceptance

Compare quiet deletions and total edits. Separately inspect ordinary per-phrase regressions, loud or noisy speech, meeting speech with overlap, caption joins and hard cuts. Count words and recognition segments on backgrounds. Extra segments cost inference time even when the model returns an empty caption. Any promising setting requires continuous listening and a device timing check before adoption. A failed screen is sufficient to retain the current floor.

## Findings

| Condition | Words | Floor 45 | Floor 32 | Floor 24 | Floor 16 |
|---|---:|---:|---:|---:|---:|
| Facing speaker, quiet | 73 | 73 | 73 | 73 | 73 |
| Facing speaker, ordinary | 73 | 41 | 40 | 39 | 39 |
| Facing away, quiet | 73 | 60 | 61 | 61 | 61 |
| Facing away, ordinary | 73 | 25 | 25 | 25 | 25 |
| Release speech with endpoint replay | 687 | 187 | 184 | 179 | 178 |
| Words emitted across six background minutes | 0 | 4 | 8 | 8 | 8 |

Speech cells are word edit counts. The release score here recomputes the segmenter’s final sample ranges for each input. The earlier 146-error release baseline used frozen segment ranges, so it is a different measurement.

All lower thresholds recovered some ordinary words but changed other ordinary captions for the worse. In the facing-speaker group, floors 32 and 24 improved two phrases, tied four and worsened two. Floor 16 improved two, tied five and worsened one. On facing-speaker quiet speech, floor 16 replaced seven deletions with five substitutions and two insertions, leaving total errors unchanged. No lower floor improved the facing-away quiet aggregate.

Synthetic silence, room tone, fan and taps produced zero words in all arms. Recorded living-room ambience increased from three words and five recognition jobs to seven words and seven jobs at every lower floor. Recorded office ambience stayed at one word and 15 jobs. Across all backgrounds, recognition jobs increased from 30 to 32. Incidental voices may account for some words in recorded ambience, but the additional background output is still a regression for a caption experience intended to suppress that audio.

## Decision and limits

Retain floor 45. The tested settings do not meet the combined requirement of better quiet recall and preserved ordinary/background behavior. A live flash is unwarranted for these rejected candidates. No production setting was changed. Reducing the separate background-relative gate or introducing a more discriminating speech detector would require another experiment with the same false-caption controls.

Each physical recording restarts the segmenter, including its ambient calibration. Some background and release cases run longer. These replay results do not establish behavior under concurrent P4 workloads or sustained live listening. The synchronous worker does not model queue pressure, latency or speaker-label accuracy. A candidate that passes the replay gates would still require those device checks.

All 83 cases completed at all four settings. All 16 current-floor facing-speaker hypotheses and sample cuts matched the earlier baseline replay. The audit checked all 332 arm records, reference lengths, edit arithmetic and cut bounds.

Manifest SHA-256 is `52125f96fe80a3c5d784323859c03e709ee3c6f5576ec7348f4de2951cd185fd`. Private scripts `run.py`, `summarize.py` and `compare.py` regenerate the evidence and comparisons.
