# Selected separator qualification

**Both selected models fail necessary host accuracy checks against the completed baseline.** Selected-model and baseline results are audited; the known-source control and complete decision audit remain pending. Neither model is approved for deployment. Production defaults remain unchanged.

Selections were frozen after all six development scores: A4096 and B8192. The qualification suite contains 355 cases and 9,011 reference words. These differ from the development cases and denominator, so raw totals must not be compared across partitions.

## Completed primary result

| Global profile-attributed metric | Baseline | A4096 | B8192 |
|---|---:|---:|---:|
| Total word errors | 6,447 | 11,177 | 11,524 |
| Substitutions | 2,048 | 2,552 | 2,543 |
| Missed words | 2,987 | 1,643 | 2,170 |
| Extra words | 1,412 | 6,982 | 6,811 |
| Reference words | 9,011 | 9,011 | 9,011 |

Both separator outputs count. Errors can exceed reference words because extra words are included. Relative to baseline, A adds 4,730 primary errors and B adds 5,077. Both reduce primary missed words overall, but extra text outweighs that benefit. These are held-out stored-audio comparisons, not live P4 results.

Selected B8192 has 347 more primary errors than selected A4096: 527 more missed words, offset partly by 171 fewer extra words and nine fewer substitutions. The lower teacher-assisted development total did not translate into a lower primary qualification total. This is a descriptive comparison, not a significance claim or a reason to change the frozen selections.

## Separate oracle acoustic diagnostic

This permits source assignment per case and does not establish stable speaker labels. It must not be substituted for the primary global profile-attributed metric.

| Condition | Reference words | Baseline errors | A errors | B errors |
|---|---:|---:|---:|---:|
| Ordinary single speaker | 1,037 | 146 | 1,158 | 1,082 |
| Quiet single speaker | 1,037 | 144 | 1,132 | 1,057 |
| Synthetic two-speaker mixtures | 6,222 | 5,158 | 6,013 | 5,880 |
| Recorded real overlap | 715 | 594 | 717 | 650 |
| Synthetic silence, fan and taps combined | 0 | 0 | 0 | 0 |

Extra output remains a substantial part of the single-speaker scores. No stream was muted or discarded to improve these counts. Zero output on three synthetic noise fixtures is not broad background-audio qualification.

The A-to-B oracle acoustic total falls from 9,020 to 8,669 while the primary global profile-attributed total rises. These are different metrics with different assignment scopes; their difference is not a pure speaker-error count. Words emitted without an assigned profile rise from 2,194 to 2,748 across all groups.

In the ten real-overlap groups, baseline primary errors are 611, versus A's 912 and B's 810. Primary missed words fall from baseline 260 to A 159 and B 243. Oracle missed words fall from 291 to 61 and 139 respectively, while oracle extra words rise from 147 to 306 and 180. Recovering more reference words therefore does not establish better total accuracy.

Both models fail ordinary/quiet error nonregression on oracle acoustic counts, and the required real-overlap total-error improvement under both primary and oracle comparisons. Both reduce real-overlap missed words and produce zero words on the three synthetic noise fixtures. The failed necessary checks rule out a live firmware promotion from these candidates; the remaining known-source diagnostic cannot reverse the completed baseline comparisons.

## Audit and limits

The main read-only audit passed all 355 case identities and 710 output streams per result, actual learned-model exported/native identities, baseline raw-input identities, saved PCM hashes, greedy transcripts reconstructed from int8 logits, speaker-vector bounds, production portable-cluster replay, complete global profile assignment, unknown-word penalties, minimum mapping cost and condition/error arithmetic. This verifies consistency of the stored results; it does not independently validate every reference annotation or establish device execution.

The 32 real-overlap cases use existing recordings and both annotated speakers, with no other annotated turn in the selected union. They are not fresh physical-room captures. Historical external pretraining exposure remains incompletely known. Development annotation caveats remain disclosed in docs/STT_EARLY_SEPARATOR_COMPARISON.md; development selection has not been revised using qualification results.

Pending work: known-source qualification control, the complete qualification decision audit, saved P4/G2 microphone and regression comparisons, and their result audits. Integrated P4 memory, realtime behavior and live accuracy remain unqualified; live promotion is not justified by these failed host checks. G2 live tests also require the glasses to return and a candidate that passes host acceptance.

Private evidence: `private/training-track/compact16k-round2/scores-A-4096-qualification/results.json`, SHA-256 `8fde13542679b3badb794e1a1f61d99ddb15bf9692910cd9835f17d6525135ab`; `private/stt-model-comparison/audit-scores-A-4096-qualification.json`; and the archived result under `private/stt-model-comparison/audited-results/`. Shared evaluation protocol: `a3010c5a387e2705b03ce3c8a203baedd3128cae35bec52c0f8ca612c3ca9eb8`.

B8192 result SHA-256: `5716b222470d06c595d6b7b01c0b8bba01a0b2c793780b8f47964897dfbabc39`; audit: `private/stt-model-comparison/audit-scores-B-8192-qualification.json`. The result is also archived privately.

Baseline result SHA-256: `43ca5ba6d0dccde9d9ec6d45dce69e280881af9be5d43e902c970d2876142888`; audit: `private/stt-model-comparison/audit-scores-baseline-0-qualification.json`. The baseline audit verifies each scored control input is the declared raw mixture or empty second stream.
