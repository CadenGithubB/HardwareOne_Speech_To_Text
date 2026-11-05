# Separator development comparison

4 November 2026. **All six learned checkpoints are worse than baseline on the frozen development scores.** Development comparison and checkpoint selection are complete: A4096 and B8192. The final teacher-assisted checkpoint reduces errors relative to the selected supervised checkpoint but does not resolve the baseline regression. Held-out qualification remains pending. Production defaults are unchanged.

All completed development runs contain the same 243 cases and 3,400 reference words. The frozen exported 25397 recognizer, greedy decoder, corrected speaker reference and portable clusterer are identical. The separator uses its actual corrected export with float32 normalization and int8 convolutions.

| Global profile-attributed metric | Baseline | A1024 | A4096 | A8192 |
|---|---:|---:|---:|---:|
| Total word errors | 2,462 | 4,556 | 4,302 | 4,471 |
| Missed words | 1,134 | 770 | 783 | 811 |
| Extra words | 543 | 2,834 | 2,561 | 2,484 |

The best supervised development result is A4096. A8192 has fewer insertions but more substitutions and deletions, raising its total by 169. Longer supervised training did not resolve the retention regression. Fewer omissions alone would give the wrong impression. Counting both outputs and their speaker assignments exposes the extra text.

The following diagnostic permits oracle output assignment and counts every word from both streams. It is separate from the global speaker-attributed total above.

| Development condition | Reference words | Baseline | A1024 | A4096 | A8192 |
|---|---:|---:|---:|---:|---:|
| Ordinary single speaker | 425 | 58 | 471 | 452 | 426 |
| Quiet single speaker | 425 | 66 | 493 | 430 | 423 |
| Synthetic two-speaker mixtures | 2,550 | 2,025 | 2,533 | 2,457 | 2,452 |
| Synthetic silence, fan and taps combined | 0 | 0 | 0 | 0 | 0 |

A later metadata audit found other speakers' annotated turns overlapping 11 of the 16 AMI headset utterances reserved for development. That does not prove crosstalk is audible in those microphones, but the synthetic references cannot establish complete coverage of every background word. Keep the frozen full-panel scores and disclose this limitation; an extra AMI word is not automatically a confirmed recognition error.

The second output is a major source of the measured errors. At A1024, both channels produced text in all 48 ordinary and all 48 quiet single-speaker cases. The output assigned to the empty reference contributed 400 ordinary and 392 quiet words. The two hypotheses were exactly identical in 19 ordinary and nine quiet cases. The median correlation between the two saved output waveforms was about 0.89 in each condition. This supports a voice-leakage/duplication diagnosis at A1024.

A clean LibriSpeech-only diagnostic shows the same second-stream problem. It includes every development case whose sources are entirely from the two LibriSpeech stores; it is a post-audit diagnostic, not a replacement selection panel.

| Clean LibriSpeech condition | Cases | Words | Baseline | A1024 | A4096 | A8192 |
|---|---:|---:|---:|---:|---:|---:|
| Ordinary single speaker | 32 | 287 | 24 | 314 | 317 | 298 |
| Quiet single speaker | 32 | 287 | 27 | 315 | 299 | 302 |
| Synthetic two-speaker mixtures | 96 | 1,722 | 1,359 | 1,705 | 1,685 | 1,685 |

At A1024, both outputs generated text in all 64 clean single-speaker cases. The empty-reference output added 286 ordinary and 284 quiet words; exact duplicated hypotheses occurred in 15 ordinary and seven quiet cases. This supports the leakage/duplication diagnosis without relying on the AMI references. These are oracle output-assigned diagnostics, not speaker-label qualification.

At A4096, both outputs still generate text in every clean single-speaker case. The empty-reference output contributes 282 ordinary and 263 quiet words.

At A8192, both outputs still generate text in every clean single-speaker case, adding 273 ordinary and 265 quiet words on the empty-reference output.

Words emitted on an empty-reference stream remain counted. Muting a stream would require a new, separately tested policy that also preserves real second-speaker speech.

The B1024 pre-assistance control also completed and passed audit. It has the same 4,556 profile-attributed errors as A1024. All 486 saved output PCM hashes, hypotheses, speaker vectors, sample counts and logit metadata match exactly on this panel. This supports the expected matched warmup despite different serialized export hashes; it is not evidence of teacher benefit or proof of function equality for every possible input.

The first post-teacher checkpoint, B4096, completed and passed the same audit. Its 4,342 profile-attributed errors (914 substitutions, 817 deletions, 2,611 insertions) exceed A4096's 4,302 and the baseline's 2,462. Ordinary, quiet and two-speaker oracle errors are respectively 452, 443 and 2,478, versus A4096's 452, 430 and 2,457. The clean LibriSpeech diagnostic has 316 ordinary, 303 quiet and 1,686 two-speaker errors. Both outputs still produce text in all 64 clean single-speaker cases; the empty-reference output adds 285 ordinary and 270 quiet words. Thus this checkpoint does not resolve the extra-stream problem.

B8192 also completed and passed audit. Both selections are now frozen using all three development scores per arm, minimum global errors and earlier-step tie breaking. The selection records match the actual report digests and counts; physical microphone results were not used to choose checkpoints.

| Selected development result | Baseline | A4096 | B8192 |
|---|---:|---:|---:|
| Total profile-attributed word errors | 2,462 | 4,302 | 4,071 |
| Substitutions | 785 | 958 | 1,021 |
| Missed words | 1,134 | 783 | 921 |
| Extra words | 543 | 2,561 | 2,129 |

B8192 has 231 fewer errors than selected A4096, with 432 fewer extra words but 138 more missed words and 63 more substitutions. This is a descriptive development comparison, not held-out acceptance or a significance claim. Its ordinary, quiet and two-speaker oracle errors are 356, 325 and 2,362, compared with baseline 58, 66 and 2,025. Synthetic noise fixtures still produce zero words. The clean LibriSpeech diagnostic has 254 ordinary, 229 quiet and 1,624 two-speaker errors; the empty-reference output adds 224 ordinary and 193 quiet words. Both outputs produce text in 32/32 ordinary and 29/32 quiet clean cases. Teacher assistance reduces the measured leakage problem but does not remove it or justify deployment.

A separate controlled check of the unchanged training loss supports a possible objective mismatch, not a proven training bug. With a perfect active output and a coherent copy at amplitude ratio `a` on the empty output, the mean loss rises by `5*a*a`: a copy at 6% amplitude adds about 0.018. The nine synthetic checks agree with this expression within float32 tolerance. This shows why low-energy leakage can carry a small penalty; it does not prove the cause of these trained outputs or establish a better loss weight. No fitting code, loss or output-muting policy was changed.

The known-source input control has now completed and passed the same audit. It bypasses the learned separator and supplies the individual source recordings. Global profile-attributed errors are 886 versus the mixture baseline's 2,462 on 3,400 words. Synthetic two-speaker oracle errors are 349 versus 2,025 on 2,550 words; within the all-LibriSpeech subset they are 151 versus 1,359 on 1,722 words. This shows useful headroom when separate inputs are available. It is an ideal-input diagnostic, not a deployable separator, guaranteed achievable ceiling or physical-microphone result. The AMI reference caveat still applies to its full-panel score.

These are stored-window development scores, not live captions or a fresh-room qualification. The 32 real-overlap qualification cases have not been used in this comparison. These numbers also do not show that speech detection recovered quiet microphone audio: the detector investigations and caption-admission limits remain separate.

All eight completed result files passed the main chat's read-only audit: 486 output streams per run, case/reference and PCM identities, greedy transcripts reconstructed from saved int8 logits, speaker-vector bounds, actual portable-cluster replay, complete global mapping, unknown-word penalties, minimum assignment cost, condition totals and primary error arithmetic. All six learned-model results also match their actual exported models and independently verified native artifacts. These checks support result consistency; they do not validate every ground-truth annotation or prove P4 execution.

Run the selected A4096 and B8192 checkpoints on the untouched qualification panel, with baseline and known-source controls. The original controller has advanced into A4096 qualification. The main microphone comparison remains deferred until qualification reports and the decision audit exist; a separate one-shot controller is queued to verify sources, audit reports and execute that comparison under the shared evaluation lock. No firmware trial is justified by the development result.

Private evidence is under `private/stt-model-comparison/`: `early-development-comparison.json`, `early-output-waveform-diagnostic.json`, `early-clean-speech-diagnostic.json`, `audit-scores-A-1024-development.json`, `audit-scores-A-4096-development.json`, `A4096-development-summary.json`, `audit-scores-A-8192-development.json`, `A8192-development-summary.json`, `audit-scores-B-1024-development.json`, `warmup-result-comparison.json`, `audit-scores-baseline-0-development.json`, `audit-scores-sources-0-development.json`, `audited-results/` and `audited-protocols/`. The source results are in `private/training-track/compact16k-round2/`. Their common evaluation protocol is `a3010c5a387e2705b03ce3c8a203baedd3128cae35bec52c0f8ca612c3ca9eb8`.
