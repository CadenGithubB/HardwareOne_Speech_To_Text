# P4 numerical qualification, 4 November 2026

The two numerical failures in the capture-lock handoff at ec22e39 have different causes. The speaker package needs an export correction. Block 14 needs a firmware build correction. The installed models, speaker thresholds and application defaults stayed in place throughout this investigation.

## 1. Speaker export and reference

The installed speaker package SHA-256 is `650f48bd23f804238caec6aa561d8951c61a099ba03d11e722af696ec3628f83`. Its trunk is `fa6638a78d3306e216f572c3faa8067ceabceaf9459ae6a14e6f51d800c3f006`. The package's original expected output is `52ce0662b4a53ae617e79aa68d8c00748eedaf9d63098186826beb47e98ffbcc`. The archived model still fails that fixture. Four previously tested paths gave 9,386 values outside its one-unit tolerance. Direct ReLU alone left 2,501 outside tolerance and a maximum error of 17.

Using the original learned model, 126 ordered calibration clips and the installed trunk's embedded input, a regenerated native PPQ graph reproduced the **original expected output exactly**. This established a usable host reference before changing any arithmetic.

* Sixteen standalone ReLU nodes carried coarse lookup-table attributes, while the native reference calculated a direct ReLU. On the P4 their serialized tables quantize positive inputs onto a much coarser grid. The SDK already implements direct ReLU when the attribute is absent.
* At stage 3, the first batch normalization implemented as a bias-bearing depthwise convolution, the preceding activation hash matched. Exact integer multiplication, bias addition and nearest-even rescaling reproduced the whole P4 output. Float32 intermediate accumulation reproduced the original PPQ output. Only eight of 96,000 values differed at this stage, all by one unit. The two computations round on different sides of requantization.
* Widening convolution and fully connected accumulation reproduced the traced stages through the first residual addition under direct ReLU. A mismatch remained at a later multiply. Widening the other arithmetic operations (multiply, add and reductions) while retaining the existing quantized parameters, activation grids, saturation, nearest-even rounding and sigmoid tables reproduced **all 181 available whole-tensor P4 hashes**, including the final tensor. Trace coverage excludes shape-only/layout points without a matching native tensor.
* The corrected reference comes from running the host graph over the input. It does not consume a P4 output dump. A separate synthetic input and independent predicted output exercise generalization beyond the embedded example.

The candidate package is `0542b793a2d5250a7707c554478a97117747a0c1cb63ebed94dc5c99406499f6`. Its generation removes the 16 ReLU lookup attributes from the pinned blob, installs the independently calculated fixture output and recomputes the package integrity digest. A separate structural comparison verified all 202 initializers, the head and package header, graph topology and tensor metadata, and the original embedded input unchanged. This includes the learned weights, thresholds and sigmoid tables. Normal ESP-DL deserialization selects the direct operation. The old fixture failure remains recorded against the original artifact.

On the P4, the candidate produced the independently predicted `7c7f07fb94061d11108f6fe7a7e00e06f63a4f451e44a93d84436b73ec19a7dd` output. For each of ordinary and prepared execution on one and two cores, the probe ran the own fixture cold, repeated it warm, used the second input, then restored the first input. **All 16 comparisons were byte-exact** over 9,600 int16 values. Each mode constructed a new model from fresh bytes. A second firmware image repeated all 16 checks. It then loaded a fresh copy through the real product speaker loader and enabled the SDK self-test. The original SDK test returned 0 and two identical synthetic PCM inputs produced the same finite, nonzero embedding through the product frontend and pooling. Microphone segmentation, full application concurrency, physical acoustic playback and mixed voice overlap are outside this matrix.

### Speaker labels and difficult pairs

A separate host screen used 170 held-out turns in 17 two-speaker conversations, 34 speakers across three source sets. Each voice had one enrollment clip, excluded from scoring, and five separate test turns. For each source we selected the closest available disjoint pairs by enrollment cosine from the original floating speaker model. The remaining voices provided comparison pairs. This measures voices the model finds similar. Human similarity judgments were unavailable.

Both arms used the same source PCM, float frontend and pooling, model threshold 0.60, two-second new-profile minimum and actual portable C++ production clusterer. A host implementation of the old lookup behavior reproduced the installed model's original P4 output hash before scoring. The corrected host calculation reproduced the candidate. Accuracy counts unknown labels as incorrect and uses an optimal one-to-one assignment of predicted profiles to speakers.

| Screen | Turns | Original correct | Corrected correct | Original unknown | Corrected unknown |
|---|---:|---:|---:|---:|---:|
| Closest enrollment pairs | 80 | 65 | 66 | 13 | 12 |
| Remaining pairs | 90 | 78 | 78 | 11 | 11 |
| Total | 170 | 143 | 144 | 24 | 23 |

AMI headset rose from 41 to 42 correct out of 60, LibriSpeech rose from 55 to 56 out of 60, and VoxPopuli fell from 47 to 46 out of 50. These are simulated-glasses development sets, serial turns and host embeddings. The room microphone and live UI are outside this assessment. Advance the speaker package to application integration review for numerical correctness. The screen gives little evidence of a general label-accuracy gain.

## 2. Block-14 kernel and RAM

The control was `47e58faa01470d32dad88f1faa46e3f61dff0fd605aa542103aefd11502dae72`. The candidate was `432ca0f49f64b2c32b9729cff46fb51dd04210b7e50dfa8288fc84072e2d0c26`. Both model binaries and both original fixtures were held fixed. All four ordinary/prepared and single/multicore combinations reproduced the handoff's failure. A locally reloaded native graph reproduced the candidate's embedded final output byte for byte.

The two device arms agreed through block 13. The candidate residual projection at stage 172 differed from the control and matched its own host reference. There are differences between some host pre-ReLU Add intermediates and both P4 arms, which converge after ReLU. At the changed block the preceding int8 ReLU and the int8-to-int16 conversion matched the host exactly. The following bias-free INT16 depthwise convolution at stage 177 diverged. The device explicitly logged `no Conv kernel for packed key 0x0315` before continuing. The ordinary speaker kernel bank supplies the bias-bearing variant. Adding the bias-free `dl_esp32p4_s16_depthwise_conv2d_per_channel_hwc1` to the isolated probe's requirements repaired execution with the original model. The candidate output error fell from 8,069 of 9,628 bytes to **zero** on cold and both warm calls. The control also passed all three. A renewed matrix with a fresh payload for every model/mode combination passed 24 of 24 exact fixture checks, three per combination.

### Matched device memory and time

Both 663-frame fixtures passed before the probe ran any other shapes. All 18 additional calls completed with matched input hashes and stable output for each model and length. These are allocation-event minima. The device reported one 32 MiB PSRAM heap and five byte-addressable internal heaps. PSRAM peaks are exact for their windows. Internal values are conservative aggregate bounds. The diagnostic yields between stages and excludes the LM, microphone and speaker worker.

| Frames | Control peak PSRAM, bytes | Block 14 peak PSRAM, bytes | Increase, bytes | Control warm inference, seconds | Block 14 warm inference, seconds |
|---:|---:|---:|---:|---:|---:|
| 100 | 20,971,416 | 21,091,912 | 120,496 | 2.015–2.015 | 2.035–2.035 |
| 663, own fixture | 21,549,200 | 22,102,848 | 553,648 | 3.104 | 3.444–3.464 |
| 1,000 | 21,893,016 | 22,704,712 | 811,696 | 3.807–3.827 | 4.297–4.297 |
| 2,000 | 22,917,016 | 24,496,712 | 1,579,696 | 6.227–6.257 | 7.237–7.247 |

The 100/1,000/2,000-frame inference internal bound was 66,040 bytes for either model. At 2,000 frames the construction bounds were 163,552 and 164,108 bytes respectively. Raw load peaks were 20,140,524 and 20,182,300 PSRAM bytes. The extra 41,776 model bytes account for only a fraction of the long-input RAM increase. Load/reconstruction took about 9.5 versus 20 seconds in the isolated file-backed diagnostic. This includes reconstruction of the embedded delta and is unsuitable for projecting direct load time of a candidate installed on SD.

Keep the current int8 recognizer. At 2,000 frames block 14 uses another 1.51 MiB of PSRAM and takes about a second longer here. The prior frozen release suite produced 146 versus 147 word errors on 687 words. Isolated success does not establish full application fit or a recognition benefit.

## 3. Distant microphone and training

All 24 original AMI meeting spans were replayed, with identical transcripts, current int8 export, C++ no-dither frontend and fixed LM. All 24 baseline distant transcripts reproduced. Matching each distant recording's RMS to the paired headset raised errors from 110 to 117 on 292 words. The median requested amplitude multiplier was 3.69. Five clips worsened and one improved. Limiting gain by available headroom gave 116 errors. Keep the existing firmware gain.

We cross-referenced the source meeting times with other speakers' annotated turns. For the 8 excerpts with less than 1% overlap, headset and distant errors were 11 and 20 on 100 words. For 6 excerpts with 1% to under 25% overlap they were 12 and 39 on 99 words. For the 10 remaining excerpts they were 34 and 51 on 93 words. Annotated overlap is a proxy for competing voices and does not isolate reverberation. The additional errors from a scalar gain adjustment, together with the remaining gap on overlapping speech, motivated a paired microphone-view training trial.

A delay-and-gain check quantified how much of each distant signal resembled the close microphone. Fitting a delay of up to 100 ms and one scalar gain on the first half explained a median 13.6% of distant-channel energy on the second half. On the 12 less similar signals, errors increased from 29 headset to 64 distant on 140 words. On the other 12, they increased from 28 to 46 on 152 words. Noise, room impulse response, other speakers and changing talker position can all affect this measurement. No human listening judgment is included.

The paired training trial used 96 unique original annotation spans from 65 AMI training meetings and 68 speakers. Both views matched the same meeting, start, end and transcript for every span. None of those meetings occur in the 24-pair evaluation. Starting from checkpoint 25397, the arms froze the encoder and fitted only the final CTC projection with AdamW (learning rate 0.00003, no weight decay, four utterances per update, 24 updates). They used the same shuffled sequence, portable C++ no-dither frontend, transcript targets and update schedule. Only the microphone view changed. This is a bounded test of adapting the output head. It cannot establish the benefit of retraining the full encoder or of adding reverberation augmentation.

We also swept the existing LM strength control on the same 24 paired spans. The host decoder scaled alpha, the word bonus and the hotword bonus together as firmware does. At strengths 0, 0.75 and 1, distant-mic errors were 122, 111 and 110. Headset errors were 64, 57 and 57. The full-strength arm reproduced every stored baseline transcript. Keep strength 1 as the default for these conditions.

### Exported training results

The two changed checkpoints preserved the other 637 checkpoint tensors exactly. Both were exported to int8 with the original ordered calibration inputs and settings and passed their host fixture checks. The paired evaluator replayed 80 cases with the actual portable C++ frontend and fixed decoder. This includes the existing frozen 48 cases plus 32 additional microphone views to cover all 24 meeting pairs. The original column uses the same previously evaluated PCM and references. The 48-case release total overlaps the condition rows. No reserve set was scored.

| Development measurement | Reference words | Current int8 | Headset-trained head | Distant-trained head |
|---|---:|---:|---:|---:|
| Frozen release suite | 687 | 146 | 145 | 145 |
| All 24 headset clips | 292 | 57 | 55 | 56 |
| All 24 distant clips | 292 | 110 | 112 | 113 |
| Natural read speech | 82 | 16 | 16 | 16 |
| Quiet read speech | 82 | 19 | 18 | 18 |
| Noisy read speech | 82 | 26 | 26 | 26 |
| Caption joins | 75 | 20 | 19 | 18 |
| Forced cuts | 150 | 14 | 14 | 14 |
| False words, three no-speech controls | 0 | 0 | 0 | 0 |

Training on distant microphone views instead of headset views cost one additional edit in each 24-clip group, with the remaining 23 clips tied in each group. Relative to current int8, it increased distant errors by three. **Keep checkpoint 25397.** This experiment found no distant-mic improvement from adapting only the character projection. The next training comparison should unfreeze the last encoder block as well, hold the head-only arm as a control, and score overlapping and isolated speech separately. That tests whether updating the acoustic representation helps on the low-similarity signals where scalar gain and output-head training fell short. Use fresh meeting-level validation before promoting any resulting candidate.

The headset checkpoint and export SHA-256 values are `8bc795b57706136485ac93d3345acfdc01a135b297c56986116d5564dbd7e585` and `67ceb3962f94db7d977b6eec67e9bd20e549201f95c1eb6f12b1f26e9c449d09`. The distant checkpoint and export are `d1019e67037f0cd01391929d622adc16e49a97d167f109112f42a282a02b23fa` and `9bf3f165f6bef237ca256166f5262f4eb61e871861a8e20e4500506383d8a0f5`. The evaluator input suite digest is `d4d7a90f5ec7289e9a606672da469f5bf59f79cd61969026ff5a457187970a75`. These new training exports were assessed on the host and have no device qualification.

## Reproduction and device state

The starting checkout was `claude/spkeval-diagnostics` at `ec22e39`. Implementation is local commit `829e863`. The board was P4X-EYE `e8:f6:0a:e3:a7:68`. All diagnostic images used ESP-IDF 5.5.5, staged ESP-DL 3.3.12 tree `5a4ca4993f401f3bcb45342a245b1f13b1940217af71fba98c3d30091af2967f`, 64-byte L2 lines, 200 MHz PSRAM, assertions and model-local preparation capability. Ordinary mode skips preparation on a new model. The recognition checkpoint was `e1873cc934e7c645c8d8b91dbe60834a3d0ff623e8eb3b700ef132159d24be6d` and the LM was `7bae9ff540bed1ca3065f13abcb9b6e794f9d863080dde116fb0af08525d7823`.

| Firmware image | Bytes | SHA-256 |
|---|---:|---|
| Original kernel inventory, recognition trace matrix | 1,252,288 | `611264ffb3eb66a1538beaae471dd5a22af9761dd96aa09240188b2f40ed9c6e` |
| Original speaker package, both ReLU traces | 784,992 | `7fc6f6079d2faca322076590d045de361c69274acdaf99fe642f7d0e93deeaed` |
| Corrected kernel inventory, matched RAM benchmark | 1,252,016 | `6960b8c7168191caf730ccc16862d143140c4fcf347206688c1d01af43c630e8` |
| Corrected speaker package, independent fixture matrix | 2,485,424 | `12dea18baea1e7b354b3be59130f965f06ac8111cee5464ceaf7ac380d31863a` |
| Corrected kernel inventory, four-mode recognition matrix | 1,250,448 | `28e2519fe9e9539a4233ef4527e5ffd6c7fd769a96c8640037251f619d4b83f2` |
| Corrected speaker package, matrix plus product loader | 2,530,720 | `946c53279c6724c2d3754e92af9dc34de8a72119f276de53c1bd4b4d329b23d3` |

The exclusive controllers verified the board MAC and actual partition table digest `39b3160f424d886b0939b43d3e127d893a6bb93d843d8e530d8acd8f1a33c5c3` before writing only the app at 0x10000. All six runs completed without observed watchdog or panic. Each restored and readback-verified `b55bf096156476f2e0e9fc15ea06acb2d91d27c32784a92215f76e06fbda0e88`, verified reconnect and logging off, closed the serial port and released the lock. Model bytes on the card were unchanged. The speaker candidate traveled in isolated app images. Block 14 used the preverified file-backed reconstruction delta.

Private evidence lives under `private/numerical-takeover`, `private/numerical-speaker`, `private/numerical-fixed`, `private/numerical-contract`, `private/numerical-final-matrix` and `private/numerical-product`. The first directory includes the regenerated native graph, stage hashes, integer/float diagnostic, two independent candidate builds, training artifacts, per-turn results and the six-run restoration audit. The other directories pair each image with its build/config identities, raw serial log and status. The host transcript, product storage, bridge, viewer, model delta and speaker cluster regressions passed.

## Last encoder block on distant speech, 4 November 2026

This follow-up compares current checkpoint 25397, the previously exported distant-mic head-only control and a new arm that updates the last acoustic encoder block and character projection. Both adaptation arms start from 25397 and use the same 96 training spans, actual C++ frontend, ordered inputs, targets, AdamW settings and 24 updates. The new arm optimizes the last convolution after batch-normalization folding. Reconstruction into the checkpoint verified its effective weights and bias. The preceding 17 blocks stayed frozen. All three arms use the same saved LM and full strength.

The primary measurement uses one headset and one distant recording of each of 48 distinct annotated meeting spans. There are eight sessions from four meeting series, 14 speakers and 635 reference words per mic. Each session contributes three isolated spans and three with at least 25% annotated competing speech. The overlap group's median is 55%. The isolated group has 364 words and the overlap group has 271. This design balances the two conditions and does not estimate the frequency of overlap in deployment.

These are fresh spans and sessions for the paired adaptation studies. Too few validation meetings remained after excluding calibration and previous screen meetings. Selection used the official AMI test split, whose aggregate scores have previously been available in this project. The new evaluation uses no adaptation meeting series and excludes previously sampled, calibration and fitting PCM hashes. Membership was frozen before inference. The separately reserved Common Voice data was untouched. The frozen 48-case release suite provides additional regression controls.

The same LM scored the floating models on the 48 distant clips. The current model made 117 isolated and 158 overlap errors. Head-only adaptation produced 116 and 158, and last-block-plus-head adaptation produced 116 and 159. The small change in training loss (2.045 to 2.040) did not correspond to an improvement on fresh floating-point transcripts.

To examine what the paired microphone can teach us, we aligned each existing int8 hypothesis to the same labeled reference using a deterministic minimum-edit path. On isolated speech 66 reference words were correct only with the headset and eight only with the distant mic. On overlap speech those counts were 80 and five. This counts reference-word matches, excludes insertions and depends on tie-breaking for repeated words. It gives a reason to test paired-view supervision without treating every headset prediction as correct.

The candidate checkpoint SHA-256 is `e91cb5cad00f70e801f353eb4d2c07d290f35ee15d8f6ebc89959ce8d7f1581b`; its 20,112,032-byte ESP-DL export is `36fc608ddf6af42e9b4c6b47de699d186c4987330409efef67338e6d5e4ac24f`. The fresh suite manifest hashes to `0939a85dab8fda9decb64e40c14a0ac1d167bad3b91ff1ffd3925a6b03932f27`. All 102 calibration examples matched the original export. Comparing serialized tensors against the original identified only the two head tensors in the head-only arm and those plus the last convolution weight and bias in the new arm. All intermediate activation exponents were identical. The private reproduction scripts, manifests, per-case results and export comparison are under `private/encoder-followup/`.

Word edits (substitutions + deletions + insertions); lower is better. These are host scores using the exported integer graphs.

| Recording condition | Reference words | Deployed int8 | Head only | Last block + head |
|---|---:|---:|---:|---:|
| Distant, isolated | 364 | 117 | 120 | 123 |
| Distant, overlap | 271 | 165 | 170 | 170 |
| Distant, all | 635 | 282 | 290 | 293 |
| Headset, isolated | 364 | 60 | 60 | 63 |
| Headset, overlap | 271 | 78 | 79 | 78 |
| Headset, all | 635 | 138 | 139 | 141 |
| Frozen release suite | 687 | 146 | 145 | 147 |

Keep the deployed int8 checkpoint. The last-block candidate raised distant word error rate from 44.4% to 46.1%. Against the deployed model it improved two clips, tied 36 and worsened ten; against head-only it improved one, tied 43 and worsened four. Relative to the deployed model its distant errors rose in all four series: EN2002 +1, ES2004 +2, IS1009 +4, TS3003 +4. The release controls produced no false words on silence, taps or fan in any arm. No candidate was flashed. This rules against this particular 24-update recipe; it does not establish that adapting the encoder can never help.

Next experiment: keep the same trainable layers, optimizer and labels, but add a training target from the simultaneous headset recording using a frozen teacher. Compare against the same distant-only training recipe. Check timing alignment on training pairs, keep the transcript as ground truth, and use new meeting series for evaluation. Report missed words separately under competing speech: the deployed model had 77 deletions on distant audio versus 32 on the headset in that condition. The student alone would run on the P4.
