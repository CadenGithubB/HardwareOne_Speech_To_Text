# Early separator development comparison

4 November 2026. **All three supervised checkpoints are worse on the frozen development scores.** This completes the supervised development comparison. Teacher-assisted results, final checkpoint selection and held-out qualification remain pending. Production defaults are unchanged.

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

The known-source input control has now completed and passed the same audit. It bypasses the learned separator and supplies the individual source recordings. Global profile-attributed errors are 886 versus the mixture baseline's 2,462 on 3,400 words. Synthetic two-speaker oracle errors are 349 versus 2,025 on 2,550 words; within the all-LibriSpeech subset they are 151 versus 1,359 on 1,722 words. This shows useful headroom when separate inputs are available. It is an ideal-input diagnostic, not a deployable separator, guaranteed achievable ceiling or physical-microphone result. The AMI reference caveat still applies to its full-panel score.

These are stored-window development scores, not live captions or a fresh-room qualification. The 32 real-overlap qualification cases have not been used in this comparison. These numbers also do not show that speech detection recovered quiet microphone audio: the detector investigations and caption-admission limits remain separate.

All five completed result files passed the main chat's read-only audit: 486 output streams per run, case/reference and PCM identities, greedy transcripts reconstructed from saved int8 logits, speaker-vector bounds, actual portable-cluster replay, complete global mapping, unknown-word penalties, minimum assignment cost, condition totals and primary error arithmetic. All three supervised results also match their actual exported models and independently verified native artifacts. These checks support result consistency; they do not validate every ground-truth annotation or prove P4 execution.

Continue the frozen development comparisons for both arms and all declared checkpoints, select on that panel, then run the untouched qualification panel. The main microphone comparison remains deferred until selection and qualification results exist. No firmware trial is justified by this early result.

Private evidence is under `private/stt-model-comparison/`: `early-development-comparison.json`, `early-output-waveform-diagnostic.json`, `early-clean-speech-diagnostic.json`, `audit-scores-A-1024-development.json`, `audit-scores-A-4096-development.json`, `A4096-development-summary.json`, `audit-scores-A-8192-development.json`, `A8192-development-summary.json`, `audit-scores-baseline-0-development.json`, `audit-scores-sources-0-development.json`, `audited-results/` and `audited-protocols/`. The source results are in `private/training-track/compact16k-round2/`. Their common evaluation protocol is `a3010c5a387e2705b03ce3c8a203baedd3128cae35bec52c0f8ca612c3ca9eb8`.
