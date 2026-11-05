# Selected separator qualification

**Incomplete comparison: A4096 is scored and audited; B8192 and both controls are pending.** Neither model is approved for deployment. Production defaults remain unchanged.

Selections were frozen after all six development scores: A4096 and B8192. The qualification suite contains 355 cases and 9,011 reference words. These differ from the development cases and denominator, so raw totals must not be compared across partitions.

## Completed primary result

| Global profile-attributed metric | A4096 |
|---|---:|
| Total word errors | 11,177 |
| Substitutions | 2,552 |
| Missed words | 1,643 |
| Extra words | 6,982 |
| Reference words | 9,011 |

Both separator outputs count. Errors can exceed reference words because extra words are included. The baseline qualification score is not available yet; these totals alone do not establish a comparative gain or regression on this partition.

## Separate oracle acoustic diagnostic

This permits source assignment per case and does not establish stable speaker labels. It must not be substituted for the primary global profile-attributed metric.

| Condition | Reference words | A4096 errors | Missed words | Extra words |
|---|---:|---:|---:|---:|
| Ordinary single speaker | 1,037 | 1,158 | 35 | 1,032 |
| Quiet single speaker | 1,037 | 1,132 | 34 | 991 |
| Synthetic two-speaker mixtures | 6,222 | 6,013 | 269 | 3,409 |
| Recorded real overlap | 715 | 717 | 61 | 306 |
| Synthetic silence, fan and taps combined | 0 | 0 | 0 | 0 |

Extra output remains a substantial part of the single-speaker scores. No stream was muted or discarded to improve these counts. Zero output on three synthetic noise fixtures is not broad background-audio qualification.

## Audit and limits

The main read-only audit passed all 355 case identities and 710 output streams, actual exported/native model identities, saved PCM hashes, greedy transcripts reconstructed from int8 logits, speaker-vector bounds, production portable-cluster replay, complete global profile assignment, unknown-word penalties, minimum mapping cost and condition/error arithmetic. This verifies consistency of the stored result; it does not independently validate every reference annotation or establish device execution.

The 32 real-overlap cases use existing recordings and both annotated speakers, with no other annotated turn in the selected union. They are not fresh physical-room captures. Historical external pretraining exposure remains incompletely known. Development annotation caveats remain disclosed in docs/STT_EARLY_SEPARATOR_COMPARISON.md; development selection has not been revised using qualification results.

Pending work: selected B8192 qualification, baseline and known-source qualification controls, the complete qualification decision audit, saved P4/G2 microphone and regression comparisons, and their result audits. Integrated P4 memory, realtime behavior and live accuracy are conditional on passing host acceptance; G2 live tests also require the glasses to return.

Private evidence: `private/training-track/compact16k-round2/scores-A-4096-qualification/results.json`, SHA-256 `8fde13542679b3badb794e1a1f61d99ddb15bf9692910cd9835f17d6525135ab`; `private/stt-model-comparison/audit-scores-A-4096-qualification.json`; and the archived result under `private/stt-model-comparison/audited-results/`. Shared evaluation protocol: `a3010c5a387e2705b03ce3c8a203baedd3128cae35bec52c0f8ca612c3ca9eb8`.
