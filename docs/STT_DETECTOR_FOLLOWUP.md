# STT detector mechanism follow-up

4 November 2026.

**No candidate passed the frozen development gates.** Production settings and model remain unchanged. This report tests detector changes with recognition audio kept raw.

## Measured causes

The original percentile histogram represents levels up to 190 RMS; higher frames accumulate in its last bin. High-pass/bounded processing put 94.5% of synthetic room-tone frames above 192 RMS, with a 25th percentile of 336.6. The experiment's overflow-safe arm retains the original low-range histogram and computes the actual percentile when the selected rank falls in the overflow bin. This is a private experimental implementation, not a production change.

A separate startup mismatch was measured. The previous gain starts at1× and increases 5% per 1,024-sample block, taking roughly 4.2 seconds to reach24×. Calibration lasts 500 ms. With steady room tone the trace showed RMS 21 / floor 16 at 0.5 s, speech latched at 1.4 s with RMS 46 / floor 18, and RMS 315 / floor 18 at 4 s. The detector mistakes its own gain ramp for a changed acoustic scene. Correcting the percentile alone did not remove the seven room-tone jobs. Initializing gain immediately from the first causal block removed them in diagnostic replay; speech retention still requires the scores below.

The combined correction lowered background jobs from 30 to 20 and background output from four words to zero, but ordinary P4 errors increased from 41 to 49 and the P4 quiet gain disappeared (73 errors before and after). Constructed P4 continuous errors increased from 88 to 120. The actual continuous G2 score improved from 97 to 74. These source differences prevent recommending the combination. A quieter detector is not sufficient evidence of better captions.

## Frozen comparisons

Six single-setting changes start from the prior high-pass/bounded detector: noise percentile 25→50, freezing noise during speech, blip tolerance 30→0 ms, pause 600→400 ms, minimum voice 200→400 ms, and pause 600→800 ms. Mechanism arms separately test overflow-safe percentile, immediate gain initialization, their combination, and the percentile change on raw detector audio. First-block gain uses only that 64 ms block; later bounded gain behavior is unchanged. All recognition calls use original PCM at the detector's selected endpoints. There is no source-specific tuning.

The same prior panel is reused: 32 physical microphone clips and 131 validation cases. These are development/regression data, not a new holdout. Selection excludes read, loud and overlap confirmation conditions. It requires per-development-group nonincreasing errors/deletions, strict quiet recovery for both microphones, and no extra background words/jobs. Extra jobs are a conservative guard rather than a measured P4 realtime failure. Recorded ambience can contain real voices, so extra words there are not proof of hallucination.

## Physical clips

Word errors; 73 reference words per column. G2 isolated clips have 150 ms lead-in versus 500 ms fresh calibration, so they are interpreted alongside continuous replay.

| Detector | P4 quiet | P4 ordinary | G2 quiet | G2 ordinary |
|---|---|---|---|---|
| Current raw detector | 73 | 41 | 73 | 40 |
| Prior high-pass/gain detector | 45 | 25 | 54 | 36 |
| Noise percentile 50 | 45 | 25 | 54 | 42 |
| Freeze active noise | 45 | 25 | 54 | 42 |
| No blip tolerance | 45 | 25 | 54 | 36 |
| 400 ms pause | 45 | 25 | 54 | 36 |
| 400 ms minimum voice | 45 | 25 | 54 | 36 |
| 800 ms pause | 45 | 25 | 54 | 36 |
| Overflow-safe percentile | 45 | 25 | 64 | 39 |
| Immediate gain initialization | 48 | 28 | 54 | 36 |
| Initialization + percentile | 73 | 49 | 64 | 39 |
| Raw + overflow-safe percentile | 73 | 41 | 73 | 40 |

## Regression and confirmation

Word errors; backgrounds total six minutes. Loud speech is digitally scaled input rather than louder acoustic capture. Overlap labels describe an annotated turn and may omit competing speech.

| Detector | Release /687 | Read /362 | Quiet read /362 | Loud /362 | Overlap /103 | Background words | Background jobs |
|---|---|---|---|---|---|---|---|
| Current raw detector | 187 | 41 | 43 | 41 | 66 | 4 | 30 |
| Prior high-pass/gain detector | 176 | 41 | 43 | 41 | 67 | 7 | 35 |
| Noise percentile 50 | 175 | 41 | 43 | 41 | 67 | 7 | 35 |
| Freeze active noise | 176 | 41 | 43 | 41 | 68 | 7 | 35 |
| No blip tolerance | 174 | 41 | 43 | 41 | 67 | 7 | 42 |
| 400 ms pause | 177 | 42 | 42 | 41 | 66 | 7 | 35 |
| 400 ms minimum voice | 176 | 41 | 43 | 41 | 67 | 7 | 33 |
| 800 ms pause | 175 | 41 | 42 | 42 | 68 | 7 | 35 |
| Overflow-safe percentile | 172 | 41 | 43 | 41 | 68 | 7 | 35 |
| Immediate gain initialization | 178 | 41 | 43 | 41 | 67 | 13 | 29 |
| Initialization + percentile | 172 | 41 | 45 | 41 | 72 | 0 | 20 |
| Raw + overflow-safe percentile | 186 | 41 | 43 | 41 | 68 | 4 | 30 |

## Continuous replay

Each source contains 146 reference words. The G2 sequence is an actual saved continuous recording. P4 continuity is constructed by concatenating 16 recordings. Each policy starts once per sequence. Recognition still receives raw samples.

| Detector | Constructed P4 /146 | Actual G2 /146 |
|---|---|---|
| Current raw detector | 88 | 97 |
| Prior high-pass/gain detector | 65 | 74 |
| Noise percentile 50 | 65 | 74 |
| Freeze active noise | 65 | 74 |
| No blip tolerance | 65 | 74 |
| 400 ms pause | 65 | 74 |
| 400 ms minimum voice | 65 | 74 |
| 800 ms pause | 65 | 74 |
| Overflow-safe percentile | 65 | 74 |
| Immediate gain initialization | 79 | 74 |
| Initialization + percentile | 120 | 74 |
| Raw + overflow-safe percentile | 88 | 97 |

## Selection

| Detector | Failed selection gates |
|---|---|
| Prior high-pass/gain detector | release-noise10 increases errors; release-noise10 increases deletions; release-ami_sdm increases deletions; background increases errors; background more jobs |
| Noise percentile 50 | g2-ordinary increases errors; release-noise10 increases errors; release-noise10 increases deletions; background increases errors; background more jobs |
| Freeze active noise | g2-ordinary increases errors; release-noise10 increases errors; release-noise10 increases deletions; release-ami_sdm increases deletions; background increases errors; background more jobs |
| No blip tolerance | release-natural increases errors; release-noise10 increases deletions; release-ami_sdm increases deletions; background increases errors; background more jobs |
| 400 ms pause | release-natural increases errors; release-noise10 increases errors; release-noise10 increases deletions; release-ami_sdm increases errors; release-ami_sdm increases deletions; release-forced_cuts increases deletions; background increases errors; background more jobs |
| 400 ms minimum voice | release-noise10 increases errors; release-noise10 increases deletions; release-ami_sdm increases deletions; background increases errors; background more jobs |
| 800 ms pause | release-natural increases deletions; release-noise10 increases errors; release-noise10 increases deletions; release-ami_sdm increases deletions; release-forced_cuts increases deletions; background increases errors; background more jobs |
| Overflow-safe percentile | release-ami_sdm increases deletions; background increases errors; background more jobs |
| Immediate gain initialization | release-natural increases errors; release-noise10 increases errors; release-noise10 increases deletions; release-ami_sdm increases deletions; background increases errors |
| Initialization + percentile | p4-quiet no quiet gain; p4-ordinary increases errors; p4-ordinary increases deletions |
| Raw + overflow-safe percentile | p4-quiet no quiet gain; g2-quiet no quiet gain |

## Verification and remaining limits

The overflow calculation passed 10,800 rolling-window checks against a sorted exact percentile. The initialization processor passed 48 signed-limit, identity, short-tail, bounded-headroom and deterministic-reset checks. The result audit checked 1,815 arm records: 1,793 physical/validation records and 22 continuous records. It verified frozen policies, raw PCM cache identities, cut bounds, edit counts and original-control parity. The fixed model and LM are the same as the [prior conditioning experiment](STT_SHARED_CONDITIONING_AB.md).

No production firmware or processing default was changed. Live capture integrity, latency, peak memory, draft-caption behavior and speaker-label effects remain unqualified. Live G2 access was unavailable while the user had the glasses. The separate training chat is actively training its matched compact 16 kHz separator arms. An early exported checkpoint exists, but has not been selected and qualified; a new-model comparison remains pending that decision. The experiment recipe is recorded in STT_NEXT_TRAINING_EXPERIMENT.md.

Private reproduction evidence: `private/stt-detector-followup/`, including the three protocols, frozen hashes, run.py, startup_run.py, continuous.py, select.py, audit.py, all per-case results and isolated decoder cache.
