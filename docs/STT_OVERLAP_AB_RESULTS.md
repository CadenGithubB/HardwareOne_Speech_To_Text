# Sequential overlap A/B results

The subsequent 16 kHz compact-separator A/B has completed both 8,192-update training arms and all six development checkpoint comparisons. Development selected supervised A4096 and teacher-assisted B8192; their qualification is running. Its recipe, interim evidence and remaining requirements are tracked in [STT_NEXT_TRAINING_EXPERIMENT.md](STT_NEXT_TRAINING_EXPERIMENT.md). The seven comparisons below describe the earlier completed host program; they do not conclude that new run.

All seven bounded host comparisons have been scored; no new model qualifies for promotion. Primary dual-output decisions use per-speaker word errors. Joined-word scores remain diagnostics. The total application peak target is30,000,000 bytes, and integrated P4 memory remains unmeasured. The reference-separation table below preserves the host comparison with the deployed int8 recognizer. Both speaker transcripts are scored. Speaker assignment is fixed over each six-condition source pair by minimum total word errors. This is an oracle evaluation assignment and does not implement stable person labels.

| Idea | Evidence from the bounded A/B tests |
| --- | --- |
| Separate voices before recognition | Strong synthetic recovery; real-room overlap remains poor. Both float reference pipelines exceed the memory budget. |
| Two resident recognizers versus reuse | Same words in the serial host comparison. Two independently loaded model images alone exceed the budget. Shared-weight contexts were not tested. |
| Train a compact separator | This small training screen failed word recovery in both float and exported scoring. It does not rule out compact separators with more training. |
| Shared encoder with two output paths | Linear, balanced-loss and nonlinear paths completed host checks; ordinary-speech retention and real overlap remain poor. Oracle output assignment still supplies the speaker correspondence. |
| Simulate quantization during training | Later matched-update development score improved, but the selected procedure did worse on synthetic qualification; real-room errors tied its control. |
| Add microphone spatial information | Blind two-channel processing worsened transcription in the small synchronized pilot. Privileged timing/steering is not a deployable result. |
| Widen block 3 | Both initializations have completed the frozen host panels; see selected-checkpoint counts below. |

Host comparisons and candidate qualification are separate: real-overlap speaker continuity, device numerical parity, realtime operation and total application peak memory remain unqualified.


| Panel | Overlap requested | Words | Mixture errors / deletions | Clean-source errors / deletions | Separated errors / deletions |
| --- | --- | --- | --- | --- | --- |
| development | 0 | 176 | 170 / 84 | 4 / 0 | 6 / 0 |
| development | 0.5 | 176 | 159 / 84 | 2 / 0 | 16 / 1 |
| development | 1 | 176 | 124 / 88 | 4 / 0 | 18 / 3 |
| qualification | 0 | 168 | 166 / 82 | 5 / 0 | 10 / 0 |
| qualification | 0.5 | 168 | 164 / 82 | 7 / 0 | 11 / 0 |
| qualification | 1 | 168 | 137 / 86 | 6 / 0 | 16 / 0 |

Separator has 5,050,545 parameters, 20,202,180 float parameter bytes. 292.600 seconds of mixtures took 40.585 seconds on one host CPU thread. Host timing and RSS do not establish P4 runtime or memory.

The mixture arm has one hypothesis stream plus an empty second stream. It exposes the current single-output limitation. Source words repeat across overlap/level conditions. The nominal qualification pairs were held from this experiment, but their LibriSpeech dev-clean sources can overlap separator pretraining validation. Independent test-clean and real-meeting confirmation remain required.

The pretrained model is a whole-window, global-layer-normalized separator with 8 kHz input/output. Polyphase resampling to/from the recognizer’s 16 kHz interface is part of B. Float separator weights plus the 20,112,128-byte recognizer exceed the P4 ceiling before activations or app work. No int8 separator or P4 kernel/runtime compatibility has been established.

Private provenance includes suite.json, model8-info.json, separation.json and recognition/results.json. Model weights were loaded with the restricted torch weights-only loader and narrowly allowlisted NumPy scalar metadata. Audio and hypotheses remain private.

1 resident recognizer instance(s), serial calls: host peak RSS 797,933,568 bytes, measured rounds [13.063, 12.813] seconds. P4 serialized recognizer storage alone 20,112,128 bytes.

2 resident recognizer instance(s), serial calls: host peak RSS 1,188,790,272 bytes, measured rounds [13.451, 12.892] seconds. P4 serialized recognizer storage alone 40,224,256 bytes.

One reused and two separately loaded resident instances produced identical hypotheses on the matched probe. The tested two-copy implementation exceeds both the30,000,000-byte budget and the physical32MiB ceiling in model images alone. This does not establish RAM use or thread safety for two contexts sharing a single read-only weight image. Serial host measurements do not predict concurrentP4speed.

Current completed dual-output selected-checkpoint checks: dual, dual-balanced, dual-nonlinear, qat-control, qat-qat, qat-wide, qat-wide-distinct. Completion here means the frozen host panels were scored, not that a candidate passed. Reference separation has independent-source ASR corroboration and real-meeting scoring; functional stable labels in real overlap and full-app P4 gates remain open. See private/training-track/overlap-ab/PLAN.md.

## Mixed audio with oracle timing

This control knows each source speaker’s exact active span and identity and recognizes the mixture inside each span. It supplies timing and labels, but does not separate concurrent voices. It is a stronger privileged control than the whole-clip single-output diagnostic.

| Panel | Overlap | Errors | Deletions | Words |
| --- | --- | --- | --- | --- |
| development | 0 | 4 | 0 | 176 |
| development | 0.5 | 65 | 8 | 176 |
| development | 1 | 124 | 11 | 176 |
| qualification | 0 | 5 | 0 | 168 |
| qualification | 0.5 | 73 | 0 | 168 |
| qualification | 1 | 130 | 28 | 168 |

Current working budget is **30,000,000 bytes total peak application memory**, superseding 28 MB. This includes model loading, activations, audio, decoder and speaker work. P4 PSRAM and internal memory must be measured and reported separately and together.

## Compact separator word scores

| Panel | Words | Reference separator errors / deletions | Compact float errors / deletions | Compact export errors / deletions |
| --- | --- | --- | --- | --- |
| development | 528 | 40 / 4 | 427 / 30 | 411 / 46 |
| qualification | 504 | 37 / 0 | 432 / 22 | 445 / 36 |

## Real two-speaker meeting overlap

| Path | Words | Errors | Deletions | Insertions |
| --- | --- | --- | --- | --- |
| mixture | 313 | 243 | 142 | 48 |
| headsets | 313 | 78 | 22 | 7 |
| oracle_time_windows | 313 | 157 | 79 | 10 |
| separated | 313 | 229 | 105 | 34 |

These 15 windows come from four AMI test series. The mixed single-output and separated paths use per-clip best two-speaker assignment. Headsets and oracle timing know source identity. This is a transcription lower bound, not a stable-label or integrated P4 score. The pretrained separator does not outperform oracle timing on real room audio.

## Two-microphone spatial pilot

Four exactly aligned clips from one meeting, 80 words, array channels 1/3; exact pair spacing unverified, delay bound covers the full 20 cm array diameter. Four other fixed-roster clips were unavailable. DSP constants were frozen before recognition.

| Path | Errors | Deletions | Insertions |
| --- | --- | --- | --- |
| single_channel | 58 | 35 | 6 |
| delay_sum | 76 | 11 | 38 |
| null_steering | 67 | 15 | 28 |
| oracle steering/time crop delay_sum | 36 | 20 | 0 |
| oracle steering/time crop null_steering | 42 | 24 | 2 |

Mono with oracle timing on these same clips made 39 errors, 24 deletions and zero insertions. Headsets made 21 errors. Direction estimates and counts correspond to the current geometry-bounded run. Timing-assisted results depend on privileged activity intervals and do not establish a deployable spatial benefit. Blind outputs contain many extra words. These are host corpus tests, not P4 microphones.

At its 3-second serialized shape, the compact separator's distinct static activation peak is 3,453,952 bytes. All activation metadata were present. This excludes allocator reuse, scratch, weights and other app state. Small weight size alone does not establish compliance with the 30 MB total peak budget.

## Shared encoder development diagnostics

Float + fixed LM, 528 repeated reference-word occurrences. Single control scores both transcripts in onset order and allows either order at simultaneous onset. Dual outputs use pair-global oracle assignment for the speaker score. Per-speaker errors are the stricter metric; joined all-word counts remain diagnostics. These provisional float scores do not choose the deployed checkpoint or establish functional person tracking or P4 qualification.

| Arm | Update | All-word errors | All-word deletions | Per-speaker errors | Per-speaker deletions |
| --- | --- | --- | --- | --- | --- |
| dual | 256 | 521 | 481 | 522 | 481 |
| dual | 1024 | 425 | 365 | 428 | 364 |
| dual-balanced | 256 | 450 | 399 | 452 | 399 |
| dual-balanced | 1024 | 390 | 326 | 412 | 335 |
| dual-nonlinear | 256 | 323 | 259 | 417 | 300 |
| dual-nonlinear | 1024 | 305 | 234 | 403 | 277 |
| qat-control | 256 | 367 | 293 | 415 | 315 |
| qat-control | 1024 | 319 | 247 | 396 | 279 |
| qat-qat | 256 | 401 | 338 | 403 | 338 |
| qat-qat | 1024 | 392 | 331 | 396 | 332 |
| qat-wide | 256 | 361 | 286 | 406 | 307 |
| qat-wide | 1024 | 323 | 252 | 386 | 279 |
| qat-wide-distinct | 256 | 366 | 296 | 412 | 315 |
| qat-wide-distinct | 1024 | 338 | 266 | 394 | 291 |

The earlier single-output arbitrary-order pilot is retained privately but excluded from this table. The initial per-head dual loss is a diagnostic arm; the combined-character-normalized follow-up tests its blank-output failure. Actual exported-model and locked qualification scores follow where completed.

## Actual exported shared-model scores

Ordered all-word errors / deletions. Single-output ordering and dual oracle assignment differ; these are word-recovery diagnostics, not equivalent person-attributed scores. Development has 528 repeated words; qualification has 504. Selection uses development only.

| Arm | Update | Development errors / deletions | Locked qualification errors / deletions |
| --- | --- | --- | --- |
| single-order | 256 | 202 / 124 | 215 / 88 |
| single-order | 1024 | 212 / 75 | pending |
| dual | 256 | 516 / 466 | pending |
| dual | 1024 | 383 / 305 | 375 / 262 |
| dual-balanced | 256 | 444 / 375 | pending |
| dual-balanced | 1024 | 406 / 339 | 372 / 285 |
| dual-nonlinear | 256 | 329 / 259 | pending |
| dual-nonlinear | 1024 | 314 / 229 | 364 / 262 |
| qat-control | 256 | 410 / 334 | 361 / 277 |
| qat-control | 1024 | 412 / 327 | pending |
| qat-qat | 256 | 413 / 347 | pending |
| qat-qat | 1024 | 387 / 318 | 350 / 265 |
| qat-wide | 256 | 422 / 356 | pending |
| qat-wide | 1024 | 397 / 315 | 383 / 287 |
| qat-wide-distinct | 256 | 418 / 341 | pending |
| qat-wide-distinct | 1024 | 406 / 332 | 381 / 287 |

## Locked candidate regression checks

Historical all-word-selected candidates: both output streams count in ordinary-speech checks, including duplicate words. See the stricter separate-speaker selections below for the primary dual-output decision. Real-overlap dual outputs use per-clip oracle assignment; this does not supply stable speaker identities. The 724-word read panel contains ordinary and attenuated versions of the same 24-speaker material.

| Arm | Panel | Words | Errors | Deletions | Insertions |
| --- | --- | --- | --- | --- | --- |
| single-order | real | 313 | 169 | 74 | 3 |
| single-order | release | 687 | 169 | 40 | 12 |
| single-order | independent | 724 | 53 | 3 | 9 |
| dual | real | 313 | 223 | 124 | 2 |
| dual | release | 687 | 437 | 303 | 9 |
| dual | independent | 724 | 439 | 335 | 12 |
| dual-balanced | real | 313 | 254 | 189 | 0 |
| dual-balanced | release | 687 | 444 | 295 | 11 |
| dual-balanced | independent | 724 | 313 | 205 | 29 |
| dual-nonlinear | real | 313 | 272 | 203 | 0 |
| dual-nonlinear | release | 687 | 397 | 238 | 9 |
| dual-nonlinear | independent | 724 | 222 | 118 | 29 |
| qat-control | real | 313 | 240 | 175 | 1 |
| qat-control | release | 687 | 437 | 288 | 8 |
| qat-control | independent | 724 | 312 | 204 | 21 |
| qat-qat | real | 313 | 240 | 178 | 1 |
| qat-qat | release | 687 | 412 | 282 | 7 |
| qat-qat | independent | 724 | 234 | 155 | 17 |
| qat-wide | real | 313 | 251 | 183 | 0 |
| qat-wide | release | 687 | 427 | 270 | 10 |
| qat-wide | independent | 724 | 282 | 178 | 22 |
| qat-wide-distinct | real | 313 | 257 | 184 | 2 |
| qat-wide-distinct | release | 687 | 458 | 305 | 10 |
| qat-wide-distinct | independent | 724 | 290 | 190 | 21 |

The balanced linear two-output model fails retention: its selected export has 444 errors on 687 release words and 313 on 724 ordinary/attenuated read words. The corrected single-output control has 169 and 53 respectively, but cannot provide both labeled transcript streams. These recipes do not qualify for promotion. Nonlinear heads, QAT and additional capacity are separate bounded tests; poor linear-head results do not establish that all shared encoders fail.

## Speaker bandwidth control

Same corrected speaker model, portable production clusterer, threshold 0.6 and energy-crop rule. No forced two-person assignment during clustering. The final score uses one oracle profile-to-source mapping per pair.

| Audio input | Correct labeled turns | Speaker pairs merged into one profile |
| --- | --- | --- |
| clean-16k | 96 / 96 | 0 |
| clean-8k-resampled | 84 / 96 | 2 |
| separated-8k | 83 / 96 | 2 |

Down/up-sampling the clean signals through 8 kHz reproduces both merged speaker pairs seen after separation. On these repeated synthetic sources, bandwidth reduction accounts for most of the observed label loss; the separator adds one further incorrect turn. This is a controlled diagnostic on 16 voices, not independent stable-label or P4 qualification. Preserving voice information above 4 kHz is a concrete follow-up hypothesis.

## Independent-source separator corroboration

Frozen 48 conditions, 16 LibriSpeech test-clean voices, 1,038 repeated word occurrences. No fitting or setting selection uses this panel. Sources are outside the audited continuation training stores; the external separator author has previously evaluated LibriMix test data, so this is independent of train/dev sources, not an untouched external corpus. Original ASR/speaker pretraining exposure is not fully audited. Six panel identities overlap another track’s speaker-final roster; this panel supplies frozen ASR/separator scores only, not speaker-policy development evidence.

| Requested overlap | Words | Clean-source errors / deletions | Reference separator errors / deletions | Oracle mixed-window errors / deletions |
| --- | --- | --- | --- | --- |
| 0 | 346 | 13 / 0 | 9 / 0 | 10 / 0 |
| 0.5 | 346 | 12 / 0 | 17 / 2 | 115 / 13 |
| 1 | 346 | 8 / 0 | 44 / 4 | 265 / 44 |

The frozen 8 kHz reference recovered most words on this second synthetic source panel (70 errors, 6 deletions) versus 33 clean-source errors and no deletions. The real room-audio result remains a separate limitation; synthetic success does not establish room generalization, stable speaker labels or P4 fit.

## Matched two-output comparisons

Candidate minus control; negative means fewer errors. Repeated overlap/level conditions stay grouped by source pair. Only four pairs per panel: the source-pair resampling intervals are descriptive sensitivity checks, not strong population inference. These per-speaker word-error scores use oracle pair-global stream mapping; runtime person identities remain unimplemented for shared heads.

| Comparison | Panel | Control / candidate update | Error difference | Word-error percentage-point difference | Source-pair resampling interval |
| --- | --- | --- | --- | --- | --- |
| dual → dual-balanced; matched update budget | development | 256 / 256 | -74 | -14.02 | -27.64 to -3.67 |
| dual → dual-balanced; matched update budget | development | 1024 / 1024 | 8 | 1.52 | -0.81 to 3.73 |
| dual → dual-balanced; development-selected procedures | qualification | 1024 / 1024 | -8 | -1.59 | -9.05 to 4.71 |
| dual-balanced → dual-nonlinear; matched update budget | development | 256 / 256 | -25 | -4.73 | -15.60 to 8.64 |
| dual-balanced → dual-nonlinear; matched update budget | development | 1024 / 1024 | -11 | -2.08 | -15.25 to 13.58 |
| dual-balanced → dual-nonlinear; development-selected procedures | qualification | 1024 / 1024 | -9 | -1.79 | -10.31 to 6.84 |
| qat-control → qat-qat; matched update budget | development | 256 / 256 | 1 | 0.19 | -0.78 to 1.65 |
| qat-control → qat-qat; matched update budget | development | 1024 / 1024 | -18 | -3.41 | -7.58 to 0.19 |
| qat-control → qat-qat; development-selected procedures | qualification | 256 / 1024 | 11 | 2.18 | 0.00 to 5.05 |
| qat-control → qat-wide; matched update budget | development | 256 / 256 | 11 | 2.08 | 0.00 to 6.08 |
| qat-control → qat-wide; matched update budget | development | 1024 / 1024 | -2 | -0.38 | -1.36 to 1.74 |
| qat-control → qat-wide; development-selected procedures | qualification | 256 / 1024 | -20 | -3.97 | -11.56 to 2.66 |
| qat-control → qat-wide-distinct; matched update budget | development | 256 / 256 | 8 | 1.52 | -0.87 to 5.88 |
| qat-control → qat-wide-distinct; matched update budget | development | 1024 / 1024 | -5 | -0.95 | -1.85 to -0.26 |
| qat-control → qat-wide-distinct; development-selected procedures | qualification | 256 / 1024 | -10 | -1.98 | -7.28 to 2.38 |
| qat-wide → qat-wide-distinct; matched update budget | development | 256 / 256 | -3 | -0.57 | -0.98 to 0.00 |
| qat-wide → qat-wide-distinct; matched update budget | development | 1024 / 1024 | -3 | -0.57 | -2.34 to 0.33 |
| qat-wide → qat-wide-distinct; development-selected procedures | qualification | 1024 / 1024 | 10 | 1.98 | -1.28 to 4.81 |

## Author-rate 16 kHz reference separator follow-up

Same 15 real windows and fixed recognizer/frontend/LM. All mixed/headset/oracle-timing control transcripts agree exactly between runs. These are separately pretrained separator weights, so this is a system comparison, not an isolated sample-rate effect.

| Reference separator | Words | Errors | Deletions | Insertions |
| --- | --- | --- | --- | --- |
| 8 kHz | 313 | 229 | 105 | 34 |
| 16 kHz | 313 | 243 | 127 | 32 |

The 16 kHz author-provided system did not improve real room transcription: 14 more errors and 22 more deletions. The speaker bandwidth finding therefore cannot be promoted into a claim that preserving bandwidth alone fixes overlapping word recovery. Both float reference pipelines remain over the P4 budget.

## Selected shared-export static memory screen

| Arm | Update | Serialized model bytes | Distinct static live tensor bytes at 600 / 2,000 / 3,000 frames |
| --- | --- | --- | --- |
| single-order | 256 | 20112112 | 460800 / 1536000 / 2304000 |
| dual | 1024 | 20152048 | 460800 / 1536000 / 2304000 |
| dual-balanced | 1024 | 20152016 | 460800 / 1536000 / 2304000 |
| dual-nonlinear | 1024 | 20234656 | 460800 / 1536000 / 2304000 |
| qat-control | 256 | 20152032 | 460800 / 1536000 / 2304000 |
| qat-qat | 1024 | 20152000 | 460800 / 1536000 / 2304000 |
| qat-wide | 1024 | 20935360 | 460800 / 1536000 / 2304000 |
| qat-wide-distinct | 1024 | 20935504 | 460800 / 1536000 / 2304000 |
| qat-wide initialization | init | 20935440 | 460800 / 1536000 / 2304000 |
| qat-wide-distinct initialization | init | 20935312 | 460800 / 1536000 / 2304000 |

These shared-head changes retain the same static activation peak at these shapes. That is not an integrated RAM result: allocator behavior, scratch, loading peak, audio queues, decoder, speaker work and other firmware remain excluded. Total application target stays 30,000,000 bytes.

## Matched QAT training completed

Both arms started from the identical selected balanced-model checkpoint/export, seed49196, data order and 1,024-update budget. All 4,096 example records match exactly, including raw PCM and frontend feature hashes. Each has 4,035 unique mixtures and 833 ordinary single-speaker retention examples. Folded-weight checkpoint reconstruction passed the per-layer assertions at updates256 and1,024.

| Arm | Training seconds | Last logged training loss |
| --- | --- | --- |
| qat-control | 772.6 | 1.4508 |
| qat-qat | 2447.6 | 1.4929 |

Training loss is not a recognition result. The exported development comparisons and selected-checkpoint checks are recorded in their tables. Retention, real overlap, runtime speaker identities and full-app P4 gates remain necessary before promotion. The wider-block trial uses the same initial balanced checkpoint as the float control.

## Word recovery versus speaker/channel assignment

Fixed raw channel order and correct person labels are different requirements. Oracle per-clip reassignment isolates word recovery. The tracked column uses actual unchanged clusterer profile IDs, with only one global one-to-one profile/person mapping per source pair for scoring; extra or unknown profiles count as insertions.

| Reference | Panel | Words | Raw channel errors | Oracle per-clip errors | Actual profile errors |
| --- | --- | --- | --- | --- | --- |
| reference | development | 528 | 40 | 40 | 167 |
| reference | qualification | 504 | 37 | 37 | 155 |
| reference16k | development | 528 | 32 | 32 | 73 |
| reference16k | qualification | 504 | 154 | 28 | 28 |

The 16 kHz qualification raw-channel score includes 126 extra errors caused by channel permutation: oracle reassignment reduces154 to28. This is not an acoustic word-loss regression. Actual profile tracking also scores28 on those cases. Its development tracked score remains worse than its word-recovery ceiling. Real room transcription remains worse with this separately pretrained 16 kHz system.

| Shared arm | Update | Panel | Pair-global per-speaker errors | Oracle per-clip per-speaker errors |
| --- | --- | --- | --- | --- |
| dual | 1024 | development | 401 | 400 |
| dual | 1024 | qualification | 426 | 422 |
| dual | 256 | development | 519 | 516 |
| dual-balanced | 1024 | development | 409 | 409 |
| dual-balanced | 1024 | qualification | 418 | 417 |
| dual-balanced | 256 | development | 445 | 444 |
| dual-nonlinear | 1024 | development | 398 | 392 |
| dual-nonlinear | 1024 | qualification | 409 | 405 |
| dual-nonlinear | 256 | development | 420 | 416 |
| qat-control | 1024 | development | 412 | 412 |
| qat-control | 256 | development | 412 | 412 |
| qat-control | 256 | qualification | 415 | 413 |
| qat-qat | 1024 | development | 394 | 394 |
| qat-qat | 1024 | qualification | 426 | 423 |
| qat-qat | 256 | development | 413 | 413 |
| qat-wide | 1024 | development | 410 | 410 |
| qat-wide | 1024 | qualification | 395 | 393 |
| qat-wide | 256 | development | 423 | 423 |
| qat-wide-distinct | 1024 | development | 407 | 407 |
| qat-wide-distinct | 1024 | qualification | 405 | 404 |
| qat-wide-distinct | 256 | development | 420 | 420 |
| qat-wide-distinct | init | development | 409 | 409 |
| qat-wide | init | development | 407 | 407 |

The nonlinear1024 development export has314 joined-word errors but398 per-speaker errors, versus409 per-speaker errors for balanced linear outputs. The joined-word gain does not establish clean speaker-specific transcripts. Per-clip oracle reassignment only reduces398 to392, so swaps alone do not explain most of this failure.

## Selection aligned with separate-speaker transcripts

For dual outputs, the primary checkpoint criterion is now summed per-speaker development errors with one oracle output assignment per source pair; earlier update wins a tie. Joined-word scores remain diagnostic. This stricter criterion is declared before QAT/wider exported development outcomes. Original architecture qualifications remain historical locked checks; the selected architecture updates are unchanged. Original selection artifacts are preserved. If the stricter criterion changes a later selected update, it receives separate fixed-suite evaluation outputs.

| Arm | Selected update | Development per-speaker errors | Qualified checks |
| --- | --- | --- | --- |
| dual | 1024 | 401 | complete |
| dual-balanced | 1024 | 409 | complete |
| dual-nonlinear | 1024 | 398 | complete |
| qat-control | 256 | 412 | complete |
| qat-qat | 1024 | 394 | complete |
| qat-wide | 1024 | 410 | complete |
| qat-wide-distinct | 1024 | 407 | complete |

## Primary dual-output selected checks

Qualification uses per-speaker errors with pair-global oracle assignment. Real-room counts allow per-clip oracle assignment; neither provides runtime identity labels. Ordinary/noise checks count both outputs. Only completed stricter-selection checks appear.

| Arm | Update | Panel | Words | Errors | Deletions | Insertions |
| --- | --- | --- | --- | --- | --- | --- |
| dual | 1024 | qualification | 504 | 426 | 287 | 28 |
| dual | 1024 | real | 313 | 242 | 138 | 16 |
| dual | 1024 | release | 687 | 437 | 303 | 9 |
| dual | 1024 | independent | 724 | 439 | 335 | 12 |
| dual-balanced | 1024 | qualification | 504 | 418 | 305 | 28 |
| dual-balanced | 1024 | real | 313 | 264 | 195 | 6 |
| dual-balanced | 1024 | release | 687 | 444 | 295 | 11 |
| dual-balanced | 1024 | independent | 724 | 313 | 205 | 29 |
| dual-nonlinear | 1024 | qualification | 504 | 409 | 278 | 23 |
| dual-nonlinear | 1024 | real | 313 | 276 | 203 | 0 |
| dual-nonlinear | 1024 | release | 687 | 397 | 238 | 9 |
| dual-nonlinear | 1024 | independent | 724 | 222 | 118 | 29 |
| qat-control | 256 | qualification | 504 | 415 | 302 | 30 |
| qat-control | 256 | real | 313 | 248 | 175 | 1 |
| qat-control | 256 | release | 687 | 437 | 288 | 8 |
| qat-control | 256 | independent | 724 | 312 | 204 | 21 |
| qat-qat | 1024 | qualification | 504 | 426 | 297 | 39 |
| qat-qat | 1024 | real | 313 | 248 | 178 | 1 |
| qat-qat | 1024 | release | 687 | 412 | 282 | 7 |
| qat-qat | 1024 | independent | 724 | 234 | 155 | 17 |
| qat-wide | 1024 | qualification | 504 | 395 | 291 | 4 |
| qat-wide | 1024 | real | 313 | 259 | 185 | 2 |
| qat-wide | 1024 | release | 687 | 427 | 270 | 10 |
| qat-wide | 1024 | independent | 724 | 282 | 178 | 22 |
| qat-wide-distinct | 1024 | qualification | 504 | 405 | 293 | 11 |
| qat-wide-distinct | 1024 | real | 313 | 258 | 183 | 1 |
| qat-wide-distinct | 1024 | release | 687 | 458 | 305 | 10 |
| qat-wide-distinct | 1024 | independent | 724 | 290 | 190 | 21 |

## Varied-utterance speaker bandwidth corroboration

Development whitelist only from the existing speaker plan; its final roster is excluded. Nine2/3/4-person conversations,108 turns,19 voices and104 distinct utterances across read speech, meeting headsets and parliamentary speech. Each chosen speaker has four distinct utterances per conversation. Same corrected speaker model, energy-window rule and portable clusterer at0.6. No fitting or policy selection.

| Input | Correct labels | Unknown turns | Split phrases | Merged phrases |
| --- | --- | --- | --- | --- |
| clean-16k | 94 / 108 | 7 | 6 | 2 |
| clean-8k-resampled | 89 / 108 | 11 | 4 | 5 |

Bandwidth preservation improves correct-label count by five turns in this broader development screen. Individual conversations sometimes favor the downsampled input; the earlier96-turn repeated-source effect should not be generalized as universal. This is clean single-speaker input per turn, not overlapping-source or real-device label qualification.

## Same-checkpoint float versus int8, separate-speaker scoring

Same audio, C++ features, fixed decoder and weights within each row. Each system gets one oracle head/source mapping per pair. All rows are development diagnostics on528 repeated reference-word occurrences; this does not implement runtime person labels. Errors / deletions are shown together.

| Arm | Update | Float errors / deletions | Int8 errors / deletions | Int8-minus-float errors / deletions |
| --- | --- | --- | --- | --- |
| dual | 256 | 522 / 481 | 519 / 466 | -3 / -15 |
| dual | 1024 | 428 / 364 | 401 / 314 | -27 / -50 |
| dual-balanced | 256 | 452 / 399 | 445 / 375 | -7 / -24 |
| dual-balanced | 1024 | 412 / 335 | 409 / 339 | -3 / 4 |
| dual-nonlinear | 256 | 417 / 300 | 420 / 299 | 3 / -1 |
| dual-nonlinear | 1024 | 403 / 277 | 398 / 264 | -5 / -13 |
| qat-control | 256 | 415 / 315 | 412 / 334 | -3 / 19 |
| qat-control | 1024 | 396 / 279 | 412 / 327 | 16 / 48 |
| qat-qat | 256 | 403 / 338 | 413 / 347 | 10 / 9 |
| qat-qat | 1024 | 396 / 332 | 394 / 321 | -2 / -11 |
| qat-wide | init | 412 / 335 | 407 / 325 | -5 / -10 |
| qat-wide | 256 | 406 / 307 | 423 / 356 | 17 / 49 |
| qat-wide | 1024 | 386 / 279 | 410 / 321 | 24 / 42 |
| qat-wide-distinct | init | 412 / 335 | 409 / 339 | -3 / 4 |
| qat-wide-distinct | 256 | 412 / 315 | 420 / 341 | 8 / 26 |
| qat-wide-distinct | 1024 | 394 / 291 | 407 / 332 | 13 / 41 |

Quantization can change substitutions and omissions in different directions. The float-trained QAT control at256 has three fewer total errors after export but19 more deletions. The original two-output loss arm at1024 improves both errors and omissions after export. These outcomes do not identify a layer-specific precision benefit. Full overlap-stratified counts remain in the private precision-breakdown.json.

## Ordinary and quiet retention

Same24 read voices and362 words in each condition. Quiet is an attenuated repeat of ordinary audio; these conditions are paired, not independent corpora. Single-output control has no separate-speaker semantics. Dual checkpoints use the primary per-speaker selection.

| Arm | Update | Condition | Words | Errors | Deletions | Insertions |
| --- | --- | --- | --- | --- | --- | --- |
| single-order | 256 | ls_ordinary | 362 | 27 | 2 | 5 |
| single-order | 256 | ls_minus18 | 362 | 26 | 1 | 4 |
| dual | 1024 | ls_ordinary | 362 | 215 | 162 | 7 |
| dual | 1024 | ls_minus18 | 362 | 224 | 173 | 5 |
| dual-balanced | 1024 | ls_ordinary | 362 | 153 | 97 | 16 |
| dual-balanced | 1024 | ls_minus18 | 362 | 160 | 108 | 13 |
| dual-nonlinear | 1024 | ls_ordinary | 362 | 114 | 62 | 14 |
| dual-nonlinear | 1024 | ls_minus18 | 362 | 108 | 56 | 15 |
| qat-control | 256 | ls_ordinary | 362 | 155 | 102 | 11 |
| qat-control | 256 | ls_minus18 | 362 | 157 | 102 | 10 |
| qat-qat | 1024 | ls_ordinary | 362 | 125 | 85 | 7 |
| qat-qat | 1024 | ls_minus18 | 362 | 109 | 70 | 10 |
| qat-wide | 1024 | ls_ordinary | 362 | 144 | 90 | 11 |
| qat-wide | 1024 | ls_minus18 | 362 | 138 | 88 | 11 |
| qat-wide-distinct | 1024 | ls_ordinary | 362 | 145 | 96 | 10 |
| qat-wide-distinct | 1024 | ls_minus18 | 362 | 145 | 94 | 11 |

Verified empty-reference fixtures currently cover 24 model/case checks across dual, dual-balanced, dual-nonlinear, qat-control, qat-qat, qat-wide, qat-wide-distinct, single-order; decoded words total 0. This bounded no-speech check does not replace the ordinary/quiet retention gate.

## Greedy versus LM on identical forward scores

Fixed long float-trained control1024, selected for the observed development precision gap. Each forward pass supplies identical logits to both decoders. This is a post-hoc development mechanism diagnostic, not model/decoder selection or independent qualification. Per-speaker errors use pair-global oracle head assignment.

| Precision | Decoder | Words | Errors | Deletions | Insertions |
| --- | --- | --- | --- | --- | --- |
| float | greedy | 528 | 457 | 217 | 93 |
| float | LM | 528 | 396 | 279 | 37 |
| int8 | greedy | 528 | 465 | 188 | 105 |
| int8 | LM | 528 | 412 | 327 | 0 |

Original LM hypotheses reproduced exactly: True. Cached LM file payload: 2,499,996 bytes; actual totalP4RAM savings remain unmeasured.

## QAT interpretation at the completed training budget

At matched1,024 updates, actual int8 per-speaker development errors fall412→394 and deletions327→321. Only four source pairs contribute; the descriptive source-pair resampling interval for the error difference includes zero. The earlier256 checkpoint did not improve its matched control.

The development-selected models do not show the same advantage on qualification: QAT has426 errors/297 deletions versus control415/302 on504 words. Control selected256 and QAT selected1,024 under the same development criterion; this compares selected procedures, not a matched-update qualification effect. Selections remain frozen. More omitted-word recovery alone does not establish a total-accuracy improvement. Real-room and ordinary/quiet checks remain separate gates.

## Wider-block matched initialization

Block3 internal width expands256→512 while keeping its external256 channels. Source checkpoint digest matches the float control’s initial checkpoint; the QAT-trained model is not used as the source.
Folded parameters grow 18,915,450→19,671,162. Maximum float-fixture difference is 0.00001526. This proves initialization equivalence only; trained accuracy and integratedP4RAM remain unproven.

## Does the first width run use independent added features?

After1,024 updates, the initially duplicated hidden halves have relativeRMS activation differences from 0.00000159 to 0.00000559 on one fixed full-overlap equal-level development mixture. Global paired parameter differences are also small. This is evidence of near-symmetry, not a universal representation-rank proof.

The original run is retained through all scheduled tests. A corrected initialization adds distinct extra filters while preserving the original subnet and initially setting extra-to-original connections tozero. Its preflight has exactly equal top-level float fixture outputs,6–7% hidden differences and nonzero zero-gate gradients on synthetic features, without optimizer updates. It runs only after the original width qualification finishes. This addresses the intended independent-capacity question; it is not an accuracy result.

qat-wide-distinct update256: zeroing only extra-to-original connections changes float logits by max0.138772, with 0.00% of greedy frame IDs changing on the fixed diagnostic input. All weights were restored exactly before normal scoring; this diagnoses feature use, not accuracy.

qat-wide-distinct update1024: zeroing only extra-to-original connections changes float logits by max0.106535, with 0.00% of greedy frame IDs changing on the fixed diagnostic input. All weights were restored exactly before normal scoring; this diagnoses feature use, not accuracy.

## Quieter second speaker at the matched1,024-update budget

Development only, sourceB at−6dB relative toA. All four source pairs remain grouped in the paired analyses; these conditions repeat the same source utterances. Counts below use oracle pair-global head assignment and do not supply runtime labels.

| Arm | Requested overlap | Words | Errors | Misses / words fromA | Misses / words from quieterB |
| --- | --- | --- | --- | --- | --- |
| qat-control | 0 | 88 | 65 | 18 / 46 | 35 / 42 |
| qat-control | 0.5 | 88 | 64 | 15 / 46 | 33 / 42 |
| qat-control | 1 | 88 | 72 | 26 / 46 | 34 / 42 |
| qat-qat | 0 | 88 | 62 | 17 / 46 | 38 / 42 |
| qat-qat | 0.5 | 88 | 56 | 8 / 46 | 37 / 42 |
| qat-qat | 1 | 88 | 72 | 24 / 46 | 34 / 42 |
| qat-wide | 0 | 88 | 65 | 18 / 46 | 37 / 42 |
| qat-wide | 0.5 | 88 | 62 | 15 / 46 | 32 / 42 |
| qat-wide | 1 | 88 | 72 | 25 / 46 | 35 / 42 |
| qat-wide-distinct | 0 | 88 | 68 | 22 / 46 | 35 / 42 |
| qat-wide-distinct | 0.5 | 88 | 62 | 15 / 46 | 33 / 42 |
| qat-wide-distinct | 1 | 88 | 73 | 26 / 46 | 31 / 42 |

## Historical run notes

These notes preserve intermediate states. Completed results above supersede their earlier pending statements.

The compact 89,913-parameter separator completed 1,024 updates from random initialization. Development signal scoring selected update 768 (2.925 dB mean oracle-assigned SI-SDR). This short recipe is compared to a substantially pretrained larger model, so it tests this compact training screen rather than isolating architecture size alone. Its development transcripts produced 427 errors on 528 repeated reference-word occurrences versus 40 for the pretrained separator. Per-clip assignment also produced 427 errors, so stream swaps alone do not explain this regression.

The compact W8A8 convolution export is about 466 KB. Its global normalization contains float arithmetic islands, including dequantization, reductions, division and square root. Calling it an all-integer separator would be incorrect. The reloaded host graph matched all 48,000 output fixture values. The first variable-length call failed because two reshapes captured the 3-second time dimension. A batch-one shape correction preserves learned weights and quantizers, retains the original fixture exactly, and passed 3/6/7.5-second host output-shape checks. This repaired artifact is undergoing downstream scoring. P4 operator linking, numerical parity, peak memory and latency remain unmeasured.

Using the corrected speaker host reference (fixture hash 7c7f07fb...) and the actual portable production clusterer at threshold 0.6, the reference separator's 96 output turns gave 83 correct labels under one global profile mapping per source pair. Two pairs merged into a single profile. An energy-based 3-second crop uses separated output only; source SI-SDR assignment supplies scoring truth. These are repeated synthetic source voices, not an integrated P4 label-accuracy claim. Stable speaker identification remains a required gate.

Fifteen new real AMI test overlap windows have been assembled. Two distant utterance slices were joined only when the complete common region agreed byte-for-byte. The union contains exactly the two fully annotated speech utterances according to source intervals; windows with third-party speech at either boundary were rejected. Four meeting series contribute. Paired headsets provide a simultaneous close-microphone comparison, not a clean-source oracle or a P4 microphone-array result. Historical AMI test exposure remains a limitation. Host recognition is running.

The dynamic int8 separator wrapper also restores the source model’s zero-padding behavior at the last 0–7 samples when input length is not a multiple of its 8-sample stride. This is an explicit runtime adapter requirement; the serialized graph itself reconstructs the stride-aligned prefix. The non-aligned qualification case initially failed length validation and its retry is preserved.

The corrected single-output control completed its 1,024 updates. Its simultaneous-onset loss accepts AB or BA. The first dual-output model produced 365 development deletions, motivating a matched combined-character-normalized PIT follow-up. The first three 4,096-row source-metadata logs agree exactly in order; the active balanced run also matches the corrected control over its completed prefix. This verifies source IDs/hashes, overlap categories and single-speaker inclusion; raw mixture and feature hashes are additionally recorded for the forthcoming QAT pair.

QAT machinery passed both original exported fixtures byte-exactly, an exact float-graph comparison and a nonzero finite-gradient check over 265 folded parameter tensors. The frozen quantization grids come from the actual export; straight-through rounding gradients and saturation are used in training. Both QAT and float controls will use the same folded representation, valid per-utterance inputs, combined-character PIT loss and fixed data seed. Checkpoint reconstruction and actual new export evaluation remain required.

The spatial timing-assisted control completed on the same four available clips. Mono with oracle timing made 39 errors on 80 words. With oracle timing for direction estimation and target cropping, delay-and-sum made 36 errors and null steering made 42. Blind steering remained worse (76 and 67 errors respectively, compared with 58 for the single whole-clip mono output). The three-error oracle gain is a small, privileged-control observation and does not establish a production hardware benefit. The initial 14.1 cm spacing estimate assumed channel numbering around the ring and is unverified. The confirmed array radius is 10 cm. The lag-7 results are retained separately, and the primary rerun uses a ±10-sample bound covering the full 20 cm diameter.

Widening block 3 is explicitly retained in the sequential program. A function-preserving initialization preflight for 512 internal channels adds 755,712 folded parameters, leaves the external 256-channel interface and two-output projection unchanged, and differs by at most 0.000211 on one existing feature fixture. This is not a training or accuracy result. Actual widened training/export and full-app memory remain pending.

