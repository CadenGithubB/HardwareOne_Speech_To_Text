# P4 recognizer training, 4 November 2026

Two new full-encoder checkpoints and a paired-teacher diagnostic were trained from 25397. The frozen development rule selected update 1024. The selected W8A8 export made 275 errors and 142 deletions on 635 distant meeting words. The deployed export made 282 errors and 124 deletions. Keep the deployed recognizer.

## Why this recipe

The previous general run delivered only about 7% of training seconds from AMI meetings, and three matched physical captures fell below the old augmentation level range. Tiny head and last-block updates had worsened distant word errors. This continuation trains every encoder block and the output layer, freezes batch-normalization running statistics, and retains the exact P4 model architecture and character vocabulary. The fixed saved meeting LM and production no-dither C++ frontend score all arms. Host training uses the matching undithered training frontend and signed-16 requantization for quiet examples.

The full run took 1,024 AdamW updates in batches of eight, peak LR 0.000005, with gradient clipping, warmup and cosine decay. Half the speech draws were eligible for quiet-level augmentation targeting −54 to −34 dBFS, capped at original level. A subset also received background from the training noise store at 10–25 dB SNR. Unmodified ordinary examples and no-speech examples were interleaved. This combined experiment cannot isolate the effect of any one change.

| Training store | Rows | Audio hours | Words | Quiet rows |
| --- | --- | --- | --- | --- |
| ami-ihm-train | 1361 | 1.56 | 16676 | 675 |
| ami-sdm-train | 3354 | 3.87 | 41496 | 1705 |
| demand-noise-train | 240 | 0.27 | 0 | 0 |
| librispeech-train-clean-100 | 1665 | 2.20 | 21819 | 829 |
| peoples-clean-train | 1019 | 1.25 | 12347 | 503 |
| voxpopuli-train | 553 | 0.75 | 7787 | 261 |

## Checkpoint selection

The two new checkpoints were exported before selection and compared on the same 32 AMI validation recordings (16 paired spans outside the release suite). The deterministic criterion was total int8 + LM word edits with the earlier update winning ties. Both columns use identical C++ features and the same saved LM.

| Continuation update | Reference words | Float + LM errors | Int8 + LM errors | Float deletions | Int8 deletions |
| --- | --- | --- | --- | --- | --- |
| current | 368 | 106 | 116 | 44 | 43 |
| 256 | 368 | 110 | 116 | 39 | 37 |
| 1024 | 368 | 109 | 109 | 45 | 46 |

## Paired teacher diagnostic

The teacher was the frozen floating-point 25397 headset model. The distant student trained with ground-truth CTC on all 96 training spans in exactly the archived order. Temperature-2 frame KL was added when the absolute signal correlation was at least 0.07, the bounded correlation peak was interior to ±80 ms, and headset greedy WER was at most 50%. Target frames were shifted by the nearest output frame (20 ms) and cropped at the boundary. Median absolute waveform lag was 2.53 ms and median absolute correlation was 0.445. 82 pairs passed. Across all training pairs the headset and distant frozen greedy predictions made 292 and 544 edits on 1082 words. Ground truth still supervised all pairs. The transcript-only control uses the same layers, optimizer, inputs, initialization and 24 updates. Whole-waveform delay cannot prove local phoneme alignment during overlap.

## Matched exported scores

Each cell is **word errors / deletions**. Errors include deletions. The two microphones cover the same words. The release condition weights reflect a regression suite with some reused sources.

| Condition | Words | Deployed | Transcript only | Teacher | Full encoder |
| --- | --- | --- | --- | --- | --- |
| All distant | 635 | 282 / 124 | 293 / 136 | 291 / 136 | 275 / 142 |
| Isolated distant | 364 | 117 / 47 | 123 / 52 | 122 / 52 | 101 / 48 |
| Overlapping distant | 271 | 165 / 77 | 170 / 84 | 169 / 84 | 174 / 94 |
| Matched headset | 635 | 138 / 55 | 141 / 60 | 141 / 58 | 126 / 51 |
| Release suite | 687 | 146 / 38 | 147 / 40 | 146 / 41 | 155 / 41 |
| Release natural | 82 | 16 / 0 | 16 / 0 | 16 / 0 | 18 / 0 |
| Release quiet | 82 | 19 / 0 | 18 / 1 | 18 / 1 | 19 / 6 |
| Release noise10 | 82 | 26 / 5 | 27 / 5 | 27 / 5 | 29 / 7 |
| Release ami_ihm | 108 | 21 / 14 | 21 / 14 | 20 / 14 | 17 / 10 |
| Release ami_sdm | 108 | 30 / 15 | 33 / 16 | 33 / 17 | 35 / 13 |
| Release caption_joins | 75 | 20 / 3 | 18 / 3 | 18 / 3 | 19 / 2 |
| Release forced_cuts | 150 | 14 / 1 | 14 / 1 | 14 / 1 | 18 / 3 |
| Release silence | 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Release taps | 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Release fan | 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

| Independent read condition | Words | Deployed errors / deletions | Full encoder errors / deletions |
| --- | --- | --- | --- |
| ls_ordinary | 362 | 23 / 2 | 23 / 2 |
| ls_minus18 | 362 | 22 / 2 | 22 / 2 |

Independent read speech uses 24 distinct LibriSpeech test speakers, one clip each, then the same recording attenuated by 18 dB. The roster was frozen before any candidate scoring. This tests level sensitivity without microphone placement. No further AMI test series passed exclusions for the additional independent roster.

| Distant meeting series | Words | Deployed errors | Full encoder errors |
| --- | --- | --- | --- |
| EN2002 | 181 | 92 | 88 |
| ES2004 | 155 | 75 | 71 |
| IS1009 | 155 | 52 | 56 |
| TS3003 | 144 | 63 | 60 |

On the 48 distant phrases the full encoder improved, tied and worsened [15, 21, 12] versus deployed. The teacher versus its transcript-only control gave [2, 46, 0]. On the 48 release cases the full encoder versus deployed gave [9, 25, 14]. Per-phrase edit and deletion deltas are private in `paired-changes.json`. See individual `scores/` rows for substitutions, insertions, first/last words and hypotheses.

## Provenance and reproduction

The post-run audit verified 7,952 unique source speech digests against the corrected effective indices and raw PCM. The audit reconciled 137 fitted AMI meetings to original annotations. The new fit had zero exact-source overlap with screened evaluation/calibration audio, zero measured speaker-ID overlap with the 635-word and independent panels and zero AMI series overlap with the 635-word panel. Historical 25397 training exposure and cross-corpus speaker aliases are outside this audit. The AMI test screen was already used in earlier project investigations. Reserved Common Voice and P4 playback recordings were excluded.

The private experiment root is `private/training-track/`. Run from the standalone checkout with the existing `private/layer-sensitivity-20261103/export-venv/bin/python`, Python bytecode off and host math threads capped at one per job. Files with fresh-directory guards need a separate empty output location for a rerun.

1. Freeze supplemental inputs with `independent.py`. Run `train.py teacher` for the 96-pair diagnostic and its export. The transcript-only control and frozen screen are under `private/encoder-followup/`.
2. Run `full.py` with MPS available. The fixed seed is 25401. `full/examples.jsonl` records every source row, level category and hash. `full/progress.jsonl` records sampled losses and gradient norms. Mac GPU arithmetic is not asserted bitwise deterministic.
3. Run `qualify.py full` and `qualify.py teacher`. Run `eval.py current dev` and `eval.py current independent` for the new baseline screens. All arms use the reference ordered 100 store calibration clips and the same fixture feature identities. The loader checked each export digest, checkpoint and both of its own output fixtures before scoring.
4. Run `audit.py` and `report.py`. The manifests identify source, software, model, interfaces, operators and calibration inputs. The selection and scores have separate JSON records.

| Arm | Checkpoint SHA-256 | ESPDL SHA-256 | Model bytes |
| --- | --- | --- | --- |
| current | e1873cc934e7c645c8d8b91dbe60834a3d0ff623e8eb3b700ef132159d24be6d | 47e58faa01470d32dad88f1faa46e3f61dff0fd605aa542103aefd11502dae72 | 20112128 |
| control | e91cb5cad00f70e801f353eb4d2c07d290f35ee15d8f6ebc89959ce8d7f1581b | 36fc608ddf6af42e9b4c6b47de699d186c4987330409efef67338e6d5e4ac24f | 20112032 |
| teacher | c05001e32245d635f1f71692758a5162ca41c9d3ef349443a41c895879ecc3a6 | 5672ec76897ce2241abf1ad56ea4cbd503bff7e39dfa62a13182f7bc1f4f8677 | 20112192 |
| 256 | d5aecb7356bbd41b24acca50ae852849b9b4af0c65d8da72a2abb9c3caa7b726 | ae987c28a73616e59acced987020fded006ad02569aea5a1b4e0fe58739e97e9 | 20112176 |
| 1024 | 0fdd86b30a11f3360e237e2e4728d6dca903acba8053d9cd07cd691ce95d265e | c3cf9b3d6ab3c383efa20e6517a315fb2476d0841840226290b2d8cf0a607624 | 20112208 |

The measurements use host execution of the int8 export parameters and quantization grids with both export fixtures verified. Candidate cold/warm P4 output parity, live audio, long-window memory and latency require separate hardware checks. No production model or firmware setting was changed.

## Archived P4 recordings

The already selected candidate was scored on the host against all 32 archived six-second microphone buffers. Every baseline transcript had previously matched the P4 on the same bytes. Each group contains four phrases repeated at each placement and source level. Only four distinct human phrases contribute to these results. The captions skip live endpointing and no physical scores were used for fitting or selection.

| Run | Group | Words | Deployed errors | New errors | Deployed deletions | New deletions |
| --- | --- | --- | --- | --- | --- | --- |
| board-01 | Controls | 33 | 6 | 3 | 0 | 0 |
| board-01 | Human | 40 | 25 | 31 | 14 | 28 |
| level-01 | Controls | 33 | 5 | 4 | 0 | 0 |
| level-01 | Human | 40 | 19 | 21 | 10 | 12 |
| one-foot-01 | Controls | 33 | 4 | 5 | 0 | 1 |
| one-foot-01 | Human | 40 | 30 | 37 | 27 | 36 |
| one-foot-level-01 | Controls | 33 | 4 | 15 | 0 | 2 |
| one-foot-level-01 | Human | 40 | 19 | 22 | 8 | 16 |

## P4 memory gate

**Current requirement (4 November 2026): aim for at most 30,000,000 bytes total application peak memory, including models, activations, audio buffers, decoder, speaker processing and other firmware allocations. This supersedes the historical 28 MB gate below and any 31 MB working target. Report PSRAM and internal RAM peaks separately and the concurrent combined peak; the physical 32 MiB PSRAM ceiling is not the working budget. Actual integrated P4 qualification remains outstanding.**

Use a conservative working limit of **28,000,000 bytes** of peak integrated PSRAM, below the physical 32 MiB ceiling. Source-to-source comparison found all 18 encoder blocks updated in both full checkpoints, with the 358 learned tensors changed and parameter shapes preserved. The selected export passed the host fixtures at the same input and output shape and retained the all-int8 convolution path.

| Artifact | File bytes | Nodes | Static live bytes at 600 / 2,000 / 3,000 frames |
| --- | --- | --- | --- |
| current | 20112128 | 201 | 460800 / 1536000 / 2304000 |
| teacher | 20112192 | 201 | 460800 / 1536000 / 2304000 |
| 256 | 20112176 | 201 | 460800 / 1536000 / 2304000 |
| 1024 | 20112208 | 201 | 460800 / 1536000 / 2304000 |

Static live sizes count distinct tensors in serialized order. File size and static live tensors exclude allocator behavior, scratch buffers, audio queues, decoder and speaker work. The earlier isolated deployed model used 22,917,016 bytes peak at 2,000 frames. Prior integrated observations imply roughly 28.7–29.8 MiB in use at some sampled points, already over the new target. Actual new-model integrated peak is unmeasured. **Memory qualification remains open.** Measure load and warm long-window inference with normal concurrent app features on the board-owning track before promotion.

## Where precision affected distant speech

The frozen selected checkpoint was also scored in float on the same 48 held-out distant spans. All four columns use identical features, labels and saved LM. Cells are total word edits / deletions. This diagnostic was run after selection.

| Distant condition | Deployed weights, float | Deployed weights, int8 | Trained weights, float | Trained weights, int8 |
| --- | --- | --- | --- | --- |
| Isolated distant | 117 / 43 | 117 / 47 | 96 / 41 | 101 / 48 |
| Overlapping distant | 158 / 69 | 165 / 77 | 163 / 77 | 174 / 94 |

On all distant words the trained float model made 259 errors versus 275 for the original float weights. After int8 export those totals were 275 versus 282. In overlap the trained float model already missed eight more words than original float. Export added another 17 deletions to the trained overlap result, compared with eight for the original weights. This comparison isolates precision in each model as a whole. It does not attribute the difference to block 3.

## Decision

Keep 25397 installed. The 1,024-update continuation improved isolated distant speech by 16 word errors but lost nine errors during overlap and missed 18 more distant words overall. Three of four meeting series improved in total edits. The release suite regressed by nine errors. Independent ordinary and attenuated read speech tied the control. Across the four previously captured physical setups the candidate worsened the human group each time, from 93 to 111 errors pooled across repeated presentations. The 96-pair teacher was two errors better than its transcript-only control and nine worse than deployed on 635 distant words. Neither candidate qualifies for promotion.

For the next training comparison, retain the P4 int8 tensor shapes. Use development overlap deletions and ordinary-speech retention alongside total edits when selecting a checkpoint. Compare ordinary training with training that simulates int8 rounding on the same inputs and weights. An overlap-stratified sample with verified target-speaker labels would test whether the floating-point regression can also be reduced. The measured gap gives no layer-specific reason to spend more RAM on block 3. The current 30,000,000-byte total application peak gate remains outstanding.

The 240 background training rows used the DEMAND training store and empty references. Individual rows were not independently verified as voice-free. This is a possible source of deletion pressure, not a demonstrated cause. Reproduction of the added checks uses `weights.py`, `ram.py`, `eval.py 1024 capture`, `distant_float.py`, `budget_capture.py`, `decision.py` and `result_chart.py` under the private experiment root.
