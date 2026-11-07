# Next training experiment: compact 16 kHz separation

Started on 4 November 2026 after the user's launch instruction. The experiment compares **longer supervised training against teacher-assisted training of the same compact separator**, with the existing 25397 recognizer and speaker algorithms frozen. Both arms completed 8,192 updates on the same frozen 32,768-example manifest; full ordered-input and code/initialization provenance checks passed. All six development checkpoint comparisons are complete, selecting A4096 and B8192 under the frozen rule. Both selections, both controls and both selected float diagnostics are complete and audited. Both native separator selections have substantially more profile-attributed word errors than the no-separator control. Accuracy, speaker-label and integrated P4 qualification remain open.

## Execution evidence · 4 November · interim

The first 20,202 A/B examples have identical ordered recipes, PCM hashes, conditioned inputs, targets and gains. Initial weights, training/loss code and configuration hashes also match. Teacher metadata obeys the warmup and two-source gates; 7,662 of 8,059 teacher evaluations so far were accepted. This is a partial-run provenance audit, not a full completed-run comparison. At update 1,024, all 177 state tensors, 591 effective quantizers, canonical exported graph and embedded fixture agree between arms; differing raw export hashes reflect serialization differences. Both exports are still evaluated independently.

At 8:44 PM EST both training arms had completed all 8,192 updates. The final audit verifies all 32,768 examples in each arm against the frozen manifest and each other: exact recipe, source/target PCM, conditioned inputs/targets and gains match, with identical initialization/configuration/training/loss hashes. Teacher evaluation occurs on 14,263 post-warmup two-speaker examples and accepts 13,560; metadata obeys the declared gate schedule and contains finite gain coefficients. Arm A took 1,530.8 seconds and B 3,826.6 seconds on MPS; these are training times, not P4 inference benchmarks. The final audit supersedes the earlier partial-input counts above. Private evidence: both `complete.json` files and `matched-input-audit.json`. The main training controller exited zero; B8192 export and the remaining accuracy comparisons continue under their existing workers.

All six trained exports subsequently passed their independent verifier and a separate checkpoint/native/ESPDL digest audit (`all-exports-audit.json`). B8192 is 552,480 bytes. The export queue exited zero; scoring and the post-scoring metadata watcher remain active. The refreshed seven-artifact static screen includes the initial model and all trained checkpoints, each with the same 6,523,904-byte named-activation peak. No device measurement or promotion claim follows from these host checks.

The corrected export policy keeps all normalization cores in FP32 and convolutions int8. It was chosen after a nonfinite-output failure at A4096, before checkpoint accuracy was inspected. Initial, all three A checkpoints, B1024 and B4096 passed independent clean-process fixture reload and variable-length checks. This does not establish P4 operator support, runtime speed or total application peak.

A serialized-graph memory screen covers those six corrected exports at their three-second shape. Each has 6,523,904 bytes of simultaneously live distinct named activation tensors at the decoder's `InsertZeros` operation, despite trained model files of only about 0.55 MB. The older 8 kHz compact graph screen was 3,453,952 bytes. This accounting counts graph views separately and omits allocator aliasing/reuse, alignment, scratch, model parameters/loading and all other app features; it is neither a measured P4 peak nor a rigorous bound on integrated memory. It identifies decoder upsampling as a scheduling/implementation risk under the mandatory 30,000,000-byte total-app ceiling. Host full-clip output arrays also need a bounded rolling device implementation. Do not infer memory compliance from the small parameter count or sum this static figure with unrelated sampled firmware peaks. Evidence: `static-memory-audit.json` and artifact hashes.

The early A1024 checkpoint has 4,556 profile-attributed errors on 3,400 development reference words, versus 2,462 for the existing recognizer without separation. This is not a selected checkpoint or final A/B conclusion. Per-case oracle source-assigned diagnostics show 119 two-source deletions versus 1,061 without separation, but insertions rise from 498 to 1,428, and ordinary-speech errors rise from 58 to 471 on 425 words. Lower omissions alone therefore do not establish useful recovery. These source-assigned diagnostics allow ideal output assignment and must not be presented as actual stable speaker-label performance. The clean-source control and later checkpoints remain in the serial evaluation queue.

Post-hoc clean LibriSpeech diagnostics locate an early duplication failure independently of AMI annotation ambiguity. All 32 ordinary single-speaker clips produce nonempty transcripts from both outputs: 575 output words for 287 reference words, versus 287 output words without separation. The better output contains 263 reference words in order and the other output contains 246; the two transcripts share 259 words in order. These text matches are diagnostics, not a new score or an output-discard rule. Cached PCM hashes were rechecked: the median weaker-output energy is 25.4 dB below the input and 8.34 dB below the stronger output, with median signed cosine similarity −0.851 to the input. This supports a quieter, polarity-inverted speech residual being transcribed. It does not establish the behavior of later checkpoints, the precise training cause or a safe activity threshold. No loss, inference threshold or selection rule is changed during this matched run. Evidence: `output-diagnostics.json`; values count both outputs.

The development known-source control has now completed: 886 profile-attributed errors on 3,400 words, versus 2,462 without separation. On two-source cases, ideal per-case source assignment gives 349 errors and 87 deletions on 2,550 words. The gap between known-source acoustic and profile-attributed results shows that providing separate audio does not by itself establish stable labels under the frozen caller policy. All four LibriSpeech source pairs retain two profiles, while the two AMI pairs produce three and four profiles and unknown words; AMI crosstalk/reference limitations apply. This is a diagnostic using the known individual synthetic sources, not an implementable separator or a product accuracy floor. The controller has advanced to A4096 development scoring; selections remain unfrozen.

A4096 development scoring subsequently completed with 4,302 profile-attributed errors on 3,400 words: 958 substitutions, 783 deletions and 2,561 insertions. It improves on A1024's 4,556 errors but still trails the 2,462-error baseline. Oracle source-assigned two-speaker errors/deletions are 2,457/166 on 2,550 words; ordinary and quiet errors are 452/430 on 425 words each. All 32 clean ordinary LibriSpeech clips still yield words from both heads, totaling 573 output words for 287 reference words. The weaker head's median energy is now 32.1 dB below the input, yet it still carries recognizable speech. This is evidence of continuing duplication despite greater residual suppression, not a reason to tune an output gate on these results. A8192 is now being scored; neither arm has been selected or qualified.

All supervised checkpoints are now scored on development:

| A update | Profile-attributed errors / 3,400 words | Unknown output words | Unknown turns |
| --- | ---: | ---: | ---: |
| 1,024 | 4,556 | 498 | 49 |
| 4,096 | 4,302 | 391 | 40 |
| 8,192 | 4,471 | 910 | 80 |

The full budget therefore does not resolve the supervised regression. A8192's oracle source-assigned two-speaker errors/deletions are 2,452/185 on 2,550 words, and ordinary/quiet errors are 426/423 on 425 words each. All 32 clean ordinary single-speaker clips still produce words from both heads: 560 output words for 287 references, with the weaker head's median energy almost 40 dB below the input. Better suppression alone has not removed recognizable residual speech or established reliable labels. A4096 is the best supervised development checkpoint under the declared rule, but formal selections wait for all B scores, and qualification has not begun. The controller has advanced to B1024; at that warmup checkpoint both arms have no teacher term.

B1024 subsequently completed with exactly the same 4,556 errors as A1024. A separate result audit verified equality for all 243 development cases and 486 output streams: PCM hashes, transcripts, speaker embeddings, global profile assignments and all metrics agree. This extends the tensor/quantizer/graph warmup checks to actual downstream outputs and confirms the no-assistance control behavior; it is not evidence of teacher benefit. `warmup-score-audit.json` pins both independently produced score reports. B4096 and B8192 comparisons remain in progress/queued.

Post-hoc uncertainty reporting is prepared without changing the frozen selection metric. `paired_uncertainty.py` resamples connected conversation groups together: synthetic pairs and single-speaker groups sharing a speaker stay in one cluster, as do real meeting-series variants. This leaves only six speech clusters in development, rather than treating the 3,400 repeated word occurrences as independent evidence. Paired percentile intervals use 10,000 deterministic resamples and report candidate-minus-reference percentage-point differences; no-reference-word/noise errors are reported separately. Matching-checkpoint teacher comparisons and selected-model qualification comparisons are included as their final reports become available. Four analytic checks cover zero/constant differences and clustering by shared voices/meeting series. These are diagnostic intervals, not a new acceptance threshold, and the AMI reference-completeness and corpus-exposure limitations remain.

B4096 development completed with 4,342 profile-attributed errors on 3,400 words (914 substitutions, 817 deletions, 2,611 insertions), compared with A4096's 4,302. The post-hoc paired difference is +1.18 percentage points, with a six-cluster percentile interval of −1.58 to +4.34 points; this does not demonstrate teacher benefit or establish a reliable ordering. Oracle two-source errors/deletions are 2,478/169; ordinary and quiet errors are 452/443 on 425 words each. All 32 clean ordinary LibriSpeech clips still yield nonempty transcripts from both heads, totaling 574 output words for 287 reference words; the weaker-output median energy is 35.2 dB below input. Unknown output words/turns are 352/40. B8192 is now being scored; selection and qualification remain pending. Evidence: the completed B4096 score report, `output-diagnostics.json` and `paired-uncertainty.json`.

At 9:45 PM EST all six development scores had completed:

| Updates | A supervised errors | B teacher-assisted errors |
| --- | ---: | ---: |
| 1,024 | 4,556 | 4,556 |
| 4,096 | 4,302 | 4,342 |
| 8,192 | 4,471 | 4,071 |

All rows use the same 3,400 reference-word occurrences. The 2,462-error no-separator baseline remains substantially better. At matched update 8,192, B improves the observed primary count by 400 errors, but the six-cluster post-hoc interval for the difference is −20.41 to +0.09 percentage points and still includes zero. Qualification remains necessary. B8192 has 1,021 substitutions, 921 deletions and 2,129 insertions; its oracle source-assigned two-source errors/deletions are 2,362/280, versus A8192's 2,452/185. Reduced total errors therefore do not establish better omission recovery. B8192 ordinary/quiet errors are 356/325 on 425 words each, with zero words from the three synthetic no-speech fixtures. On clean ordinary LibriSpeech all 32 clips still transcribe both heads, totaling 512 words for 287 references; for quiet speech 29 of 32 clips still have two nonempty heads. Unknown words/turns are 495/56.

The frozen development-only procedure selected A4096 and B8192. A separate audit reconciled the choices to all six report hashes and the declared minimum-error/earliest-tie rule. `selections-complete.json` SHA256 is `c235e18444923a41154d5738c8975d9a598dbfef57e7d806648516206b21cbc3`; `selection-audit.json` pins the choices. The controller has begun A4096 qualification, followed by B8192 and the baseline/known-source controls. No qualification result has informed fitting, thresholds or these selections.

A bounded, post-selection float diagnostic is queued after all primary native development and qualification scoring finishes. It evaluates exactly the two development-selected checkpoints in their original PyTorch float32 separator form on the same 243 development cases, retaining the actual exported recognizer/greedy decoder, corrected speaker reference, portable clustering, RMS conditioning, stitching and PCM conversion. This diagnostic does not choose settings or reopen qualification. Its separate scorer, protocol, cache and result folders preserve the native sequence. The gap includes separator input/weight/activation/output quantization and export lowering, so it cannot identify one layer's precision as the cause. Loaded Asteroid/filterbank Python source hashes and Torch version are pinned. Float inference is host-only; a favorable diagnostic does not establish a deployable float P4 path. `run_float_diagnostic.py` waits on `scoring-complete.json`, then runs A and B serially under the existing evaluation admission lock. This diagnostic is declared while B8192 and all qualification scores remain unseen.

After selection, a synthetic-only float admission check strictly loaded A4096 and B8192 against their pinned checkpoint hashes and verified all state tensors were finite. Both models returned finite float32 two-source outputs at the original input length for silence, noise, quiet noise, a non-aligned input and a six-second input: ten successful checks in total. The selections remained unchanged. Evidence: `selected-float-preflight.json`; no ASR score, fitting or qualification audio was used in this check.

## First completed host qualification · A4096

The supervised selection completed all 355 qualification cases with 11,177 profile-attributed errors on 9,011 reference-word occurrences: 2,552 substitutions, 1,643 deletions and 6,982 insertions. Unknown output words/turns are 2,194/105. These primary insertion counts include unknown/misassigned or split-profile words; they are not all literal acoustic hallucinations.

| Qualification condition | Reference words | Oracle source-assigned errors | Deletions | Insertions |
| --- | ---: | ---: | ---: | ---: |
| Synthetic two-speaker mixtures | 6,222 | 6,013 | 269 | 3,409 |
| Ordinary single-speaker | 1,037 | 1,158 | 35 | 1,032 |
| Quiet single-speaker | 1,037 | 1,132 | 34 | 991 |
| Real AMI overlap | 715 | 717 | 61 | 306 |

All three synthetic no-speech fixtures produced zero words. The separately scored real-overlap profile-attributed count is 912 errors, 159 deletions and 404 insertions on 715 words. The gap from per-case oracle source assignment preserves the label-continuity cost rather than hiding it. Ordinary/quiet extra words remain severe. The baseline/known-source qualification controls are not yet complete, so comparisons against the controls and final host acceptance remain pending.

`score-audit-A-4096-qualification.json` reconciles the completed report to all 355 frozen cases/references, group/condition totals, code and model hashes, and 709 unique cache records across 710 output streams. Cached PCM hashes and logit byte counts agree. This is evidence reconciliation rather than a second inference run or P4 test. The report SHA256 is `8fde13542679b3badb794e1a1f61d99ddb15bf9692910cd9835f17d6525135ab`.

## Second completed host qualification · B8192

The teacher-assisted selection completed the same 355 cases and 9,011 reference-word occurrences with 11,524 profile-attributed errors: 2,543 substitutions, 2,170 deletions and 6,811 insertions. Against A4096, that is 347 more errors, including 527 more deletions and 171 fewer insertions. Unknown output words/turns increased to 2,748/137. The selected models differ in update count as required by the frozen development selection; this is the selected-recipe comparison, rather than a matched-update isolation of the teacher term.

The post-hoc paired difference is +3.85 percentage points, with an 11-cluster percentile interval of −5.45 to +14.14 points. This panel does not demonstrate an overall teacher benefit or a reliable ordering. It does show why fewer extra words alone are insufficient: the teacher selection omits more reference words.

| Qualification condition | Reference words | Oracle source-assigned errors | Deletions | Insertions |
| --- | ---: | ---: | ---: | ---: |
| Synthetic two-speaker mixtures | 6,222 | 5,880 | 317 | 3,130 |
| Ordinary single-speaker | 1,037 | 1,082 | 33 | 958 |
| Quiet single-speaker | 1,037 | 1,057 | 36 | 898 |
| Real AMI overlap | 715 | 650 | 139 | 180 |

All three synthetic no-speech fixtures produced zero words. On real overlap, profile-attributed errors decreased from A's 912 to B's 810, but deletions increased from 159 to 243. Per-case oracle assignment likewise reduced total errors from 717 to 650 while increasing deletions from 61 to 139. This is a tradeoff, not evidence that both speakers' words are recovered better. Ordinary and quiet duplicate/extra words remain severe.

`score-audit-B-8192-qualification.json` passed the same roster, aggregate, provenance and cache reconciliation as A: 355 cases, 710 output streams and 709 unique cache records. Report SHA256: `5716b222470d06c595d6b7b01c0b8bba01a0b2c793780b8f47964897dfbabc39`. `paired-uncertainty.json` records the diagnostic interval. Neither audit recomputes inference or proves P4 timing/memory. Baseline/known-source qualification and the predeclared selected float diagnostic remain pending; selections and fitting remain unchanged.

## Completed no-separator qualification comparison

All three systems below used the identical frozen 355-case qualification panel and 9,011 reference-word occurrences, with the same recognizer, greedy decoder and speaker-label scoring.

| System | Profile-attributed errors | Substitutions | Deletions | Insertions |
| --- | ---: | ---: | ---: | ---: |
| No separator | 6,447 | 2,048 | 2,987 | 1,412 |
| Supervised A4096 | 11,177 | 2,552 | 1,643 | 6,982 |
| Teacher-assisted B8192 | 11,524 | 2,543 | 2,170 | 6,811 |

A reduces deletions by 1,344 but adds 5,570 insertions and 504 substitutions; B reduces deletions by 817 but adds 5,399 insertions and 495 substitutions. Neither satisfies the desired combined accuracy improvement. Primary insertions include unknown or incorrectly assigned profile words and do not all represent literal acoustic hallucinations. Post-hoc paired clustered intervals place A minus baseline at +52.49 percentage points (95%: +42.09 to +61.46), and B minus baseline at +56.34 points (+42.55 to +68.29), with 11 speech clusters. These diagnostics reinforce the observed regression, while retaining the small-corpus/generalization limitations.

The acoustic comparison also fails to rescue the result: per-case oracle source-assigned ordinary/quiet errors are 146/144 without separation versus 1,158/1,132 for A and 1,082/1,057 for B, on 1,037 words per condition. Synthetic two-speaker errors/deletions are baseline 5,158/2,784, A 6,013/269 and B 5,880/317 on 6,222 words. Separation recovers words from the second source but generates enough extra/misrecognized words to increase total errors. Real-overlap profile-attributed errors/deletions are baseline 611/260, A 912/159 and B 810/243 on 715 words. No system produces words on the three synthetic no-speech fixtures.

`score-audit-baseline-0-qualification.json` passed frozen roster/count/provenance/cache reconciliation (710 stream slots, 505 unique cache records); its scope remains metadata reconciliation, not repeated inference or P4 proof. Baseline report SHA256: `43ca5ba6d0dccde9d9ec6d45dce69e280881af9be5d43e902c970d2876142888`. Known-source qualification is running, after which the predeclared float diagnostic can distinguish a float-versus-export gap from a failure already present in the trained separator. No defaults, selections, losses or thresholds were changed from qualification results.

## Primary host scoring complete · known-source control

The known-source control completed all 355 qualification cases with 1,808 profile-attributed errors on the same 9,011 words (834 substitutions, 554 deletions, 420 insertions), versus 6,447 without separation and 11,177/11,524 for the selected native separators. This control feeds individual source recordings to the same recognizer and speaker pipeline; it uses information unavailable to a deployed system and is not a deployable alternative. Its strong result demonstrates substantial recoverable information in the source recordings, while retaining recognition and label errors.

Per-case oracle source-assigned errors are 856/6,222 words on synthetic two-speaker cases and 211/715 on real AMI source recordings. Real profile-attributed errors are 316/715, exposing a further label-continuity cost of 105 errors even with known sources. Individual AMI headset channels also differ acoustically from the distant microphone, so that control does not isolate separation quality alone. Ordinary/quiet errors remain 146/144, matching the no-separator control.

`score-audit-sources-0-qualification.json` passed frozen roster/count/provenance/cache reconciliation: 710 stream slots, 539 unique cache records. Report SHA256: `c8942887c171c24219f30c4b819ef3258c3016b6fa0a8c810e0cb37d83249281`. The scoring controller and post-scoring auditor both exited successfully. `qualification-audit.json` verifies frozen selections and all four qualification reports: both separators fail lower real-overlap total errors and ordinary/quiet nonregression, while improving real-overlap deletions and producing no words on the three synthetic noise fixtures. This is a failed combined host gate, not a P4 qualification.

The predeclared A4096/B8192 development-only float diagnostic has started under its separate pinned protocol. It retains the native recognizer and speaker pipeline and does not reopen selections or qualification. Integrated P4 execution/realtime, total concurrent application peak at most 30,000,000 bytes, fresh physical-room generalization and broader no-speech behavior remain unverified. No board access is part of this stage; the STT P4 Bluetooth remains disabled for the user's G2/R1 tests.

## First selected float diagnostic · A4096 development

On the identical 243 development cases and 3,400 reference-word occurrences, the original float32 A4096 separator produced 4,351 profile-attributed errors (894 substitutions, 868 deletions, 2,589 insertions), versus 4,302 from the native quantized export (958/783/2,561). Float therefore adds 49 observed total errors and 85 deletions; it does not rescue the supervised selection. Both remain substantially worse than the 2,462-error development no-separator baseline. These are development diagnostics, separate from the 9,011-word qualification counts.

Per-case oracle source-assigned two-speaker errors/deletions are float 2,409/161 versus native 2,457/166 on 2,550 words. Ordinary/quiet float errors are 420/403 versus native 452/430 on 425 words each. Thus some acoustic totals improve in float without improving the primary speaker-attributed result. Float unknown words/turns are 561/55. The three synthetic no-speech fixtures remain zero. The gap includes input, weight, activation and output quantization plus export lowering; it does not isolate a particular layer or precision change.

`float-score-audit-A-4096.json` verifies case/reference equality, common native/float protocol fields, frozen source/model provenance, aggregate counts and 485 unique cache records across 486 stream slots. It performs no independent inference or loaded-library source replay. Float report SHA256: `d40046cc85664b7836503160196aaf249466ef5105f5b7f7257031641406ea3a`. The B8192 float comparison remains pending, and both original selections and qualification reports remain unchanged. No float P4 deployment, memory or timing claim follows from this diagnostic.

## Selected float diagnostics complete · B8192 and duplicate outputs

B8192 float completed the same 243 development cases with 3,971 profile-attributed errors on 3,400 words (988 substitutions, 808 deletions, 2,175 insertions), versus native 4,071 (1,021/921/2,129). Float removes 100 total errors and 113 deletions but adds 46 insertions. This modest improvement remains far from the 2,462-error no-separator development baseline. A's float result is slightly worse than native. The trained separator therefore already fails before quantization; changing precision alone does not resolve the observed combined error regression.

B float oracle source-assigned two-speaker errors/deletions are 2,321/206 on 2,550 words, versus native 2,362/280. Ordinary/quiet errors are 369/335 versus native 356/325 on 425 words each, so the float improvement is not uniform across conditions. Three synthetic no-speech fixtures remain zero. Unknown words/turns are 451/42. `float-score-audit-B-8192.json` passed 243-case/reference, protocol, aggregate and 485-cache reconciliation across 486 stream slots. Report SHA256: `583bb5e7806e06ffcef8c3528037cb482f05a79c52ed2568dec22fd86c89e058`.

The refreshed development-only `output-diagnostics.json` confirms duplicate recognizable content in float too. On 32 clean ordinary LibriSpeech cases with 287 reference words, A float outputs 552 words and B float 520; every case has two nonempty output transcripts. The weaker head contains 213/162 in-order reference-word matches for A/B. Its median energy is 29.3/38.7 dB below the input, with negative signed input cosine −0.614/−0.533. Quiet B float still transcribes both heads on 31 of 32 clips. These cached text/waveform diagnostics establish that tiny residual outputs can remain recognizable; they do not prove source attribution or justify suppressing a head by an arbitrary energy threshold. Quiet/unequal genuine speakers must still be preserved.

The float controller exited successfully; both completion-marker report hashes and the unchanged selection hash reconcile. No worker remains in this round. Preserve this completed run and its failed combined host gate. The next training hypothesis must address duplicate recognizable output and loss/amplitude behavior, rather than assuming wider layers, fewer parameters or float alone will repair it. Smaller candidates remain untrained admission screens; their accuracy and the requested 80% benefit retention remain unproved. P4 total memory and realtime qualification remain separate and unverified.

## Loss/frontend contract diagnosis · no fitting

A synthetic sweep of the unchanged `losses.py` exposes a possible failure mechanism. Its SI-SDR speech term is insensitive to sign and approximately insensitive to scale, while amplitude reconstruction has weight 0.5 and each head is averaged. A 20 dB SI-SDR synthetic source at correct gain gives total loss −9.9975; reducing the active output by 40 dB gives −9.7548, only 0.2427 worse despite gross amplitude loss. The empty-head energy term's contribution for a −60 dB copy is just 0.000005 under the direct assignment.

PIT makes a second issue explicit in this controlled example: adding a tiny *clean* source copy beside the full-gain noisy source reduces total loss by 5.0991, because the cleaner tiny head can be assigned to speech while the strong noisy head pays the silence penalty. This is a deliberately constructed counterexample, not proof that every trained output takes that assignment. It demonstrates that lower objective value need not correspond to fewer recognizable duplicate words. The earlier assertion expecting a fixed total-loss increment failed because it overlooked PIT reassignment; the diagnostic now tests the direct inactive penalty and the observed reassignment separately.

The actual portable no-dither frontend was run on the first eight ordered clean ordinary LibriSpeech development clips, with no ASR inference. All eight produce byte-identical normalized log-mel features after exact sign reversal. Per-utterance normalization removes much overall level information, but attenuation is not exact invariance: −20/−40 dB amplitude changes yield median feature RMS differences 0.2961/0.6891 because PCM quantization and the log guard matter. Together with cached low-energy output transcripts, this explains why simply driving waveform energy down is an inadequate criterion for eliminating recognized words.

Evidence: `diagnose_loss_contract.py` and `loss-contract-diagnostic.json`, with frozen loss/frontend hashes, 30 synthetic combinations, three analytic assertions and 32 portable frontend executions. No optimization, threshold selection, qualification audio, board access or production changes occurred. The next isolated training A/B should compare the original objective with an amplitude-sensitive, bounded speech objective and a stronger silence treatment. Declare the exact hypothesis and selection procedure before fitting; preserve the completed round and do not retune against its qualification outcomes. Any later promotion needs an untouched qualification panel.

A metadata audit found other speakers' annotated speech overlapping 11 of the 16 reserved AMI headset utterances used in development. It does not prove that crosstalk is audible in those microphones, but these synthetic AMI references describe the intended source speakers and cannot establish complete coverage of every audible background word. Preserve the frozen primary scores, disclose this limitation and report clean LibriSpeech diagnostics separately. The 32 real-overlap qualification spans use a different construction with both complete utterance annotations and no other annotated turns within their union. Neither panel is a new physical-room capture. Private evidence: `matched-input-audit.json`, `warmup-audit.json`, `reference-completeness-audit.json` and the frozen score reports under `private/training-track/compact16k-round2/`.

## Loss-only follow-up launched · 5 November 2026

A separate run at `private/training-track/compact16k-loss-round3/` now compares the original supervised objective against one changed factor: the active-source term becomes `10 log10(MSE / max(target_power, 1e-8) + 0.001)`, with minimum −30 dB per source. The inactive-source penalty, both PIT assignments, architecture, initial checkpoint, ordered 32,768-example manifest, conditioning, Adam schedule, clipping, batch four and 8,192-update budget remain matched. Neither arm uses the teacher. Both arms retrain serially; the old control is preserved rather than silently substituted. Sixteen analytic checks passed before launch, including control delegation, permutation symmetry, finite gradients and the constructed duplicate counterexample. This tests a loss recipe; it does not isolate the contribution of every term inside the replacement formula.

Before fitting, 16 unused VoxPopuli validation voices with four full utterances each were reserved against the enumerated prior evaluation manifests, calibration and speaker-development/final plans. Their raw source hashes do not overlap the training manifest. The frozen suite has 243 reused/exposed development cases, 323 new synthetic qualification cases and 32 old real AMI regression cases; 1,159 unique evaluation PCM files were hashed. The qualification roster is new relative to these local manifests, not proof of absence of historical recognizer/pretraining exposure or cross-corpus aliases.

The local AMI pool has only two remaining validation voices after excluding earlier evaluation and final-reserved identities, and no remaining unreserved test identities. The earlier plan for an identity-disjoint new AMI qualification panel is therefore unavailable locally. This follow-up is explicitly a host diagnostic experiment: old AMI is regression-only, and independent real-overlap/product acceptance remains unproved. This limitation was recorded before fitting; no qualification result was used to change the new recipe.

`launch-admission.json` pins code/config/suite/initialization/data hashes. Training controller82650 has launched on MPS and the A control has produced optimizer progress. The same training admission lock serializes both arms; one math thread is used. Do not modify the frozen training or evaluation inputs after launch, and do not restart live workers from observation timeouts. Check every five minutes, quiet on routine progress. The heartbeat now points to the round3 continuation file. P4, both speakers' words and stable labels, and at most 30,000,000 bytes concurrent total application peak remain mandatory and unqualified. Host-only work continues with the STT P4 Bluetooth disabled.

## Loss-only follow-up · training and exports complete

Both loss arms completed 8,192 updates. `matched-input-audit.json` reconciles all 32,768 ordered recipes and recorded PCM/conditioned-input/target/gain hashes per arm, with unchanged launch code/config/initialization. The control replay reproduces all 177 saved state tensors exactly at updates 1,024, 4,096 and 8,192; its independently scored A1024 development outputs, hypotheses, embeddings, profile groups and counts also match the previous run exactly (4,556 errors/3,400 words). This is useful control reproducibility, not an accuracy result for the changed loss.

All six new checkpoints have actual ESPDL/native exports under the unchanged int8-convolution/FP32-normalization policy and separate clean verifier exit0, with the 96,000-value fixture and four variable-length shapes. `all-exports-audit.json` rehashes the saved artifacts/checkpoints and proof records. B4096's exporter exited −11 after completion; the preserved log and separate successful verifier are retained, rather than treating the completion flag alone as success. The exports range from 552,064 to 554,512 bytes; these sizes do not establish total runtime memory.

Training82650 and export48656 exited0. Only scoring controller73427 remains active; A4096 development is currently running, followed by A8192 and the three changed-loss checkpoints. No changed-loss accuracy result has completed yet. Preserve the frozen scoring inputs and the five-minute cadence. P4 execution/realtime, total concurrent application memory, independent real-overlap qualification and broad no-speech behavior remain open.

## First changed-loss checkpoint · B1024 development

The amplitude-sensitive-loss checkpoint completed 243 exposed development cases with 4,270 profile-attributed errors on 3,400 reference words: 1,092 substitutions, 808 deletions and 2,370 insertions. The matched original-loss A1024 has 4,556 errors (952/770/2,834). B therefore removes 286 total errors and 464 insertions but adds 140 substitutions and 38 deletions. The post-hoc six-cluster paired difference is −8.41 percentage points, with a percentile interval −13.54 to −2.46 points; repeated conditions and shared voices stay clustered. This is an early exposed-development result, not independent qualification or proof of the final recipe.

Per-case oracle source-assigned two-speaker errors/deletions improve from A's 2,533/119 to B's 2,444/210 on 2,550 words: total errors decrease while omissions increase. Ordinary/quiet B errors are 409/364 on 425 words each, versus A's 471/493; the three synthetic no-speech fixtures remain zero. Unknown profile words/turns increase to 825/82, so label continuity is still a substantial limitation. The 2,462-error no-separator baseline remains better overall.

Cached clean single-speaker diagnostics show duplicates persist: 31 of 32 ordinary LibriSpeech cases transcribe both heads, with 554 output words for 287 references, compared with A's 32/32 and 575 words. The weaker head median energy is −17.9 dB relative to input, with positive input cosine +0.577; A's weaker head was −25.4 dB and −0.851. The new objective changes amplitude/polarity behavior, but this is not elimination of duplicate recognizable content. B4096 and B8192 must finish before the frozen selection is made; do not change losses, thresholds or output gating from this early result.

`score-audit-B-1024-development.json` passed frozen roster/count/provenance and 485 unique cache checks across 486 outputs. Report SHA256: `fcb0082560af861c39e14c704710171882569003ad8971375d1f84e370cebc41`. `paired-uncertainty.json` and `output-diagnostics.json` are separate post-hoc diagnostics. P4/total application memory and independent real-overlap qualification remain unproved.

## Changed-loss B4096 development · early improvement does not persist

The changed-loss 4,096-update checkpoint has 4,635 profile-attributed errors on 3,400 words: 932 substitutions, 1,166 deletions and 2,537 insertions. The matched original-loss A4096 has 4,302 (958/783/2,561). B adds 333 total errors and 383 deletions, while removing only 24 insertions and 26 substitutions. Its post-hoc six-cluster paired difference is +9.79 percentage points, with percentile interval −5.68 to +27.32, so this small exposed panel does not establish a reliable population ordering. Unknown words/turns rise to 1,299/132. Primary omissions include the cost of unstable/unknown speaker assignments.

Per-case oracle source-assigned two-speaker errors/deletions are 2,387/226 versus A's 2,457/166 on 2,550 words: acoustic total errors improve while omissions increase. Ordinary/quiet B errors are 365/323 versus A's 452/430 on 425 words each. All three synthetic no-speech fixtures remain zero. These separate acoustic improvements do not override the worse primary speaker-attributed total.

Clean ordinary LibriSpeech duplicate outputs persist on 31 of 32 cases, totaling 538 output words for 287 references; quiet speech still transcribes both heads on 30 of 32. Weaker-output median energy is −20.7 dB versus input, with signed cosine +0.605. The loss replacement has not solved duplicate recognizable speech. Keep the declared full checkpoint schedule, selection rule and qualification embargo; B8192 is now running. No thresholds, loss weights or speaker policy changed from this result.

`score-audit-B-4096-development.json` passed the frozen roster/count/provenance/cache reconciliation (243 cases, 486 stream slots, 485 unique records). Report SHA256: `799711b56586170df03406037a479de71eafc3c9d8ec123d233a6b9a21da515e`. Post-hoc uncertainty and clean-output diagnostics remain separate from selection and P4/product acceptance.

## Loss-only development complete · selections frozen

All six native-export development comparisons are complete on the same 3,400 reference-word occurrences:

| Update | Original loss A errors | Amplitude-sensitive loss B errors |
| --- | ---: | ---: |
| 1,024 | 4,556 | 4,270 |
| 4,096 | 4,302 | 4,635 |
| 8,192 | 4,471 | 4,580 |

The fixed minimum-error/earliest-tie procedure selected A4096 and B1024. Their observed difference is only 32 errors, and both remain much worse than the 2,462-error no-separator baseline. The selected checkpoints differ in update count; the full table preserves the matched-update comparisons. No qualification outcome informed either selection. `selection-audit.json` reconciles both choice files, all six development report hashes and the declared rule.

At B8192, errors comprise 1,032 substitutions, 835 deletions and 2,713 insertions, with 1,054 unknown words across 89 turns. Relative to A8192, B adds 109 errors and 24 deletions. The six-cluster post-hoc difference is +3.21 percentage points, percentile interval −5.98 to +13.27. Oracle source-assigned two-speaker errors/deletions are 2,531/140 on 2,550 words; ordinary/quiet errors are 440/409 on 425 words each, and all three synthetic noise fixtures remain zero. All 31 of 32 clean ordinary cases with two nonempty heads still produce extensive duplicates, totaling 560 output words for 287 references; quiet cases also have both heads nonempty on 31/32. The final budget therefore does not remove the observed duplication.

`score-audit-B-8192-development.json` passed frozen roster/count/provenance/cache reconciliation (243 cases, 486 stream slots, 485 unique records). B8192 report SHA256: `a4ef15b267d7c6b1a707473a171a1da6da7ea270537b960cace37a67e698c23d`. The live controller has advanced to A4096 on the new 323-case synthetic qualification panel. Both selected models and both controls will be scored there, followed separately by the old 32-case AMI regression panel. Qualification, independent real-overlap acceptance and P4 timing/total memory remain unproved.

## Loss-only selected synthetic qualification · no demonstrated benefit

Both development-selected checkpoints completed the new 323-case synthetic qualification panel with 11,688 reference-word occurrences. A4096 has 15,657 profile-attributed errors (2,934 substitutions, 2,674 deletions, 10,049 insertions); B1024 has 15,721 (2,818/2,732/10,171). B adds 64 errors, including 58 more deletions and 122 more insertions, while removing 116 substitutions. The eight-cluster paired difference is +0.55 percentage points with a percentile interval of −10.53 to +10.81 points. There is no demonstrated overall benefit from the changed-loss selected recipe. Because selection chose different updates, this is a selected-recipe comparison; matched-update development results remain separately reported.

Oracle source-assigned two-speaker errors/deletions are A 8,348/325 and B 8,544/309 on 8,766 words. Ordinary errors are 1,608/1,598 and quiet errors 1,584/1,562 on 1,461 words each; extra output words remain severe. All three synthetic no-speech fixtures produce zero words. Unknown profile words/turns are A 3,357/106 and B 2,587/82. Slightly fewer acoustic omissions or unknown labels do not establish better total word recovery.

Both completed reports passed frozen roster/count/provenance/cache reconciliation: 323 cases, 646 stream slots and 645 unique cache records each. A report SHA256: `bddb58d6b9221fd92e48064390c4226b9c8afedcc97069ee1a01b3ddddffbb5c`; B: `3c197fee8126915f424841d2a77640f27e57207109db08113d53827e43fbc273`. `paired-uncertainty.json` records the post-hoc interval. The no-separator qualification control is running, with known-source control and old AMI regression still pending. No fitting, settings, selection or qualification references changed. This synthetic panel does not prove independent real-overlap, P4 timing or the 30,000,000-byte total application budget.

## Loss-only round closed · both candidates rejected

All remaining scoring completed and passed audit:
- the no-separator qualification control: 8,874 errors over 11,688 words
- the known-source qualification control: 2,178
- old real32 AMI regression: A 912, B 809 versus baseline 611
- both selected saved-microphone comparisons

Under the unchanged seven necessary host checks, A4096 and B1024 each fail four. They fail real32 profile errors, real32 oracle errors, ordinary nonregression and quiet nonregression. They pass only real32 deletions (both views) and zero words on noise. On the saved microphone panel they regress 17 of 18 group cells for both the P4 and G2 microphones. Caption-segment errors are A 2,221 and B 2,000, versus baseline 609, over 2,168 words. Production defaults are unchanged. Details: `docs/STT_LOSS_ROUND3_MAIN_REVIEW.md`.

## Why this experiment

The reference separator recovered both speakers' words well on synthetic mixtures, while the earlier small separator received only 1,024 updates from random initialization and recovered words poorly. That short screen does not settle whether a better-trained compact separator can work. The wider recognizer trials produced small synthetic gains with real-meeting or retention regressions, so they do not support spending more model memory on width now.

Keep 16 kHz audio throughout the next separator. The speaker diagnostics supported preserving bandwidth, although neither reference separator solved real-room word recovery. The frozen 16 kHz teacher actually made more real-room errors than the 8 kHz reference. Its assistance is therefore the hypothesis to test, with clean training targets anchoring both arms; it is not assumed to be a better production system.

## Matched A/B

| Item | A: supervised control | B: teacher assisted |
| --- | --- | --- |
| Student | Same compact two-output separator at 16 kHz | Identical |
| Initialization | Same seeded 91,961-parameter checkpoint | Identical |
| Training budget | 8,192 updates, batch 4 | Identical |
| Input order and augmentation | One frozen, hashed manifest | Identical |
| Ground truth | Both clean training sources, including explicit empty sources | Identical |
| Base loss | Permutation-invariant speech reconstruction and silence-safe empty-output penalty | Identical |
| Teacher assistance | Weight zero | Fixed extra reconstruction term after warmup, on eligible two-speaker training examples |
| Deployment | One small separator plus one reused recognizer | Identical; teacher is absent |

Each arm receives 32,768 examples, eight times the earlier compact screen's update budget. This isolates teacher assistance within the new recipe. It does **not** isolate longer training or 16 kHz versus 8 kHz by comparison with the old experiment.

The student keeps 64 encoder filters, a 32-channel bottleneck, 64 hidden channels and twelve temporal blocks. A 32-sample kernel and 16-sample stride preserve the earlier number of encoded time steps for a three-second window while retaining 16 kHz input. This is a tensor-shape choice, not proof of equal runtime memory or speed.

## Data and loss

Use corrected effective indices from LibriSpeech train-clean-100, the locally available train-clean-360-p28 subset, and AMI headset training. The extra LibriSpeech store contains **about 101.5 hours**, not 360 hours. Inventory counts and hashes are in `private/training-track/compact16k-round2/preflight.json`; raw waveform deduplication and exposure checks must precede fitting. Do not fit Common Voice, calibration, qualification or device-capture audio.

Both arms use 50% two-speaker mixtures, 40% single-speaker examples and 10% noise-only examples from DEMAND training noise. Include 0/25/50/100% overlap, relative speaker levels from −12 to +12 dB, and common gains spanning ordinary and quiet speech. Cropped training waveforms supervise separation only; do not attach whole-utterance text labels to arbitrary crops.

Keep every mixture within three seconds by varying source duration with overlap: at zero overlap use two consecutive 1.5-second crops; at full overlap use two simultaneous three-second crops. The fixed formula and synthetic geometry checks cover the intermediate fractions. Apply gain and peak limiting jointly to the mixture and both targets, preserving their sum.

The launch checks added a shared source-independent RMS normalization before separator quantization, with a gain cap and peak ceiling; restore gain before recognition and speaker processing. This keeps quiet samples from disappearing at the int8 separator input. Both arms use exactly the same transformation. Peak limiting considers the mixture and individual source peaks before PCM conversion. A preparation assertion caught a source-overflow case; the partial manifest was preserved and rebuilt before either arm fitted any data.

Active speech uses negative SI-SDR plus an amplitude-sensitive reconstruction term. Empty targets use an output-energy penalty normalized by mixture energy, with a floor, so single-speaker and noise-only examples do not encounter an undefined silent-target SI-SDR objective.

The teacher is the already cached, pinned 16 kHz Conv-TasNet reference. Assistance applies only when it improves both clean training-source SI-SDR scores by at least 3 dB over the mixture. Align teacher outputs to the clean training sources and match their gains before calculating the extra loss; record the raw teacher digest and gain coefficients. This prevents scale-invariant quality scores from admitting arbitrarily scaled waveform targets. Assistance is zero for the first 1,024 updates, ramps over 256 updates, then has fixed weight 0.25. Do not change these settings after qualification outcomes.

## Selection and rejection

Save updates 1,024, 4,096 and 8,192. Selection must use **actual exported separator outputs followed by the frozen recognizer**, rather than SI-SDR alone. Use the portable greedy decoder for the primary new comparison, consistently across A, B and controls. Keep the existing LM as a separately labelled diagnostic. The earlier LM-based scores are historical controls, not an equivalent primary decoder comparison. This recipe does not replace the recognizer with a fully floating-point model.

Freeze new development and qualification rosters before fitting. Require disjoint source identities between them, exclude reserved speaker-final identities, and audit exact sources against calibration and previous panels. Do not use the earlier independent ASR panel for speaker-policy development. Previously scored real AMI windows remain regression diagnostics; they are not a fresh qualification set.

Select using conversation-level speaker-attributed word errors from the unchanged speaker reference and portable clusterer at threshold 0.6. Use one global mapping of profile identities per conversation; do not remap output channels or identities independently for every clip. Count unknown/misassigned output words and all missing reference words. Also report oracle source-assigned word errors as an acoustic lower bound, plus splits, merges and unknown labels. The scorer must be checked on deliberate swaps, duplicate profiles, empty output and extra words before selection is allowed.

Reject a candidate that fails any of these:

- Lower real-overlap errors and omissions on a locked, independently annotated panel containing both speakers' words.
- Ordinary/quiet retention and no-speech behavior against the frozen single-speaker path, counting both separator outputs.
- Stable labels across changing utterances and successive overlapping windows. Repeated identical source clips are insufficient.
- Actual export/operator and numerical checks, including variable-length tails and any float normalization islands.
- Integrated P4 realtime operation and **at most 30,000,000 bytes total application peak**, including loading, model images, scratch, audio, decoder, speaker work and other firmware allocations. Report PSRAM and internal RAM separately and the combined allocation at the same instant.

The proposed runtime uses three-second separator windows with a 1.5-second hop. Window stitching and channel continuity are explicitly unqualified. The existing 8 kHz compact export contained float normalization islands; the 16 kHz graph must be exported and checked rather than assumed compatible. Neither parameter count nor host memory proves the P4 budget.

## Preparation evidence and launch admission

`private/training-track/compact16k-round2/experiment.json` fixes the proposed arms, seeds, budget and exclusions. `preflight.py` validates a three-second two-output forward pass, teacher loading, permutation invariance, finite single/empty-source losses and finite nonzero student gradients on synthetic signals. It takes no optimizer steps and fits no corpus audio. `initial.pt` pins identical starting weights for both arms.

The launch completed the ordered training manifest, source/PCM hashes, heldout source reservations, annotated AMI validation panel and untrained 16 kHz export checks. The 32,768 examples contain 16,399 two-speaker, 13,080 single-speaker and 3,289 noise-only cases, drawing on 35,291 unique sources. Training excludes the reserved development voices and all available non-training-corpus speaker IDs within each corpus family. Logged prior training-store calibration sources are excluded. Historical external-model exposure and cross-corpus identity aliases are not fully audited.

The qualification panel uses newly reserved AMI validation spans with complete annotations and exact-byte shared-region reconstruction, excluding original calibration source indices and reserved speaker-final identities. It is a corpus qualification panel, not a new physical-room capture. Historical corpus/pretraining exposure remains disclosed. Before selecting checkpoints, finish and verify the speaker-attributed scorer, window-stitching adapter and frozen evaluation-case construction. Device and independent physical-room promotion gates remain separate; this track has no authorization to record audio or access the board.

Use one training, one export and one evaluation job at most, with one host math thread and the existing admission locks. Keep recordings, transcripts, teacher outputs, vectors and checkpoints under ignored `private/`. This preparation does not authorize board access, flashing, playback, recording or changes to production defaults.
