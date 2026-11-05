# Selected separator qualification

**Both selected models fail necessary host accuracy checks against the completed baseline.** All four qualification results and the complete decision audit have passed the main consistency checks. Neither model is approved for deployment. Production defaults remain unchanged.

Selections were frozen after all six development scores: A4096 and B8192. The qualification suite contains 355 cases and 9,011 reference words. These differ from the development cases and denominator, so raw totals must not be compared across partitions.

## Completed primary result

| Global profile-attributed metric | Baseline | A4096 | B8192 | Source-input control |
|---|---:|---:|---:|---:|
| Total word errors | 6,447 | 11,177 | 11,524 | 1,808 |
| Substitutions | 2,048 | 2,552 | 2,543 | 834 |
| Missed words | 2,987 | 1,643 | 2,170 | 554 |
| Extra words | 1,412 | 6,982 | 6,811 | 420 |
| Reference words | 9,011 | 9,011 | 9,011 | 9,011 |

Both separator outputs count. Errors can exceed reference words because extra words are included. Relative to baseline, A adds 4,730 primary errors and B adds 5,077. Both reduce primary missed words overall, but extra text outweighs that benefit. These are held-out stored-audio comparisons, not live P4 results.

Selected B8192 has 347 more primary errors than selected A4096: 527 more missed words, offset partly by 171 fewer extra words and nine fewer substitutions. The lower teacher-assisted development total did not translate into a lower primary qualification total. This is a descriptive comparison, not a significance claim or a reason to change the frozen selections.

## Separate oracle acoustic diagnostic

This permits source assignment per case and does not establish stable speaker labels. It must not be substituted for the primary global profile-attributed metric.

| Condition | Reference words | Baseline errors | A errors | B errors | Source-input control |
|---|---:|---:|---:|---:|---:|
| Ordinary single speaker | 1,037 | 146 | 1,158 | 1,082 | 146 |
| Quiet single speaker | 1,037 | 144 | 1,132 | 1,057 | 144 |
| Synthetic two-speaker mixtures | 6,222 | 5,158 | 6,013 | 5,880 | 856 |
| Recorded real overlap | 715 | 594 | 717 | 650 | 211 |
| Synthetic silence, fan and taps combined | 0 | 0 | 0 | 0 | 0 |

Extra output remains a substantial part of the single-speaker scores. No stream was muted or discarded to improve these counts. Zero output on three synthetic noise fixtures is not broad background-audio qualification.

The A-to-B oracle acoustic total falls from 9,020 to 8,669 while the primary global profile-attributed total rises. These are different metrics with different assignment scopes; their difference is not a pure speaker-error count. Words emitted without an assigned profile rise from 2,194 to 2,748 across all groups.

In the ten real-overlap groups, baseline primary errors are 611, versus A's 912 and B's 810. Primary missed words fall from baseline 260 to A 159 and B 243. Oracle missed words fall from 291 to 61 and 139 respectively, while oracle extra words rise from 147 to 306 and 180. Recovering more reference words therefore does not establish better total accuracy.

Both models fail ordinary/quiet error nonregression on oracle acoustic counts, and the required real-overlap total-error improvement under both primary and oracle comparisons. Both reduce real-overlap missed words and produce zero words on the three synthetic noise fixtures. The failed necessary checks rule out a live firmware promotion from these candidates; the known-source diagnostic does not reverse the completed baseline comparisons.

The completed source-input control bypasses the learned separator. Synthetic cases receive the known individual source recordings; real cases receive the paired headset recordings, which are not guaranteed clean or isolated. Its 1,808 primary errors and 316 real-overlap primary errors show useful headroom with more separate or cleaner inputs. This is not a deployable separator, an achievable ceiling or proof that a different recognizer must be trained. Single-speaker inputs remain identical to the corresponding baseline controls.

## Audit and limits

The main read-only audit passed all 355 case identities and 710 output streams per result, actual learned-model exported/native identities, baseline raw-input identities, saved PCM hashes, greedy transcripts reconstructed from int8 logits, speaker-vector bounds, production portable-cluster replay, complete global profile assignment, unknown-word penalties, minimum mapping cost and condition/error arithmetic. This verifies consistency of the stored results; it does not independently validate every reference annotation or establish device execution.

The source-control audit additionally reconstructs every declared source input and verifies its hash and padding. The 64 real-headset records omit the synthetic schema's sample-count field; their hashed PCM files were checked to match the distant crop length exactly. The audit initially stopped on that schema difference, was corrected, and passed both the qualification and original development source controls. No scorer, model, reference or result was changed. A separate metadata audit recomputed all seven necessary checks per arm and verified the upstream decision report and its result digests.

The 32 real-overlap cases use existing recordings and both annotated speakers, with no other annotated turn in the selected union. They are not fresh physical-room captures. Historical external pretraining exposure remains incompletely known. Development annotation caveats remain disclosed in docs/STT_EARLY_SEPARATOR_COMPARISON.md; development selection has not been revised using qualification results.

Pending work: saved P4/G2 microphone and regression comparisons and their result audits. A separate post-selection floating-point diagnostic is running on the selected development checkpoints to distinguish learned-model behavior from quantization/export effects; it does not reopen selection or fit new weights. The main comparison controller is queued under the same evaluation lock. Integrated P4 memory, realtime behavior and live accuracy remain unqualified; live promotion is not justified by these failed host checks. G2 live tests also require the glasses to return and a candidate that passes host acceptance.

Private evidence: `private/training-track/compact16k-round2/scores-A-4096-qualification/results.json`, SHA-256 `8fde13542679b3badb794e1a1f61d99ddb15bf9692910cd9835f17d6525135ab`; `private/stt-model-comparison/audit-scores-A-4096-qualification.json`; and the archived result under `private/stt-model-comparison/audited-results/`. Shared evaluation protocol: `a3010c5a387e2705b03ce3c8a203baedd3128cae35bec52c0f8ca612c3ca9eb8`.

B8192 result SHA-256: `5716b222470d06c595d6b7b01c0b8bba01a0b2c793780b8f47964897dfbabc39`; audit: `private/stt-model-comparison/audit-scores-B-8192-qualification.json`. The result is also archived privately.

Baseline result SHA-256: `43ca5ba6d0dccde9d9ec6d45dce69e280881af9be5d43e902c970d2876142888`; audit: `private/stt-model-comparison/audit-scores-baseline-0-qualification.json`. The baseline audit verifies each scored control input is the declared raw mixture or empty second stream.

Source-control result SHA-256: `c8942887c171c24219f30c4b819ef3258c3016b6fa0a8c810e0cb37d83249281`; audit: `private/stt-model-comparison/audit-scores-sources-0-qualification.json`. Decision evidence: `private/stt-model-comparison/qualification-decision-audit.json`, pinning upstream decision SHA-256 `b744b4a13e53c3b79d59e4f27137185789c35de1b5f53b28493f644ee28bc649`.
