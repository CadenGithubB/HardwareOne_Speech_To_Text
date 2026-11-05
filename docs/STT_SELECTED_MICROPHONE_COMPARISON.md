# Selected separator saved-microphone comparison

**Both A4096 and B8192 completed and failed the saved-microphone/regression comparison. Both actual result audits passed.** Production defaults remain unchanged. These are offline replays of existing audio, not fresh live P4/G2 tests or checkpoint selection data.

The comparison uses the frozen 25397 recognizer and full-strength meeting LM, original raw caption-admission cuts, and both separator outputs. One oracle source assignment applies to each complete independent recording after both streams are decoded. This measures acoustic recognition retention, not stable speaker labels. It differs from training's greedy/profile-attributed evaluation; its totals must not be mixed with those scores.

## Full saved-window recognition

These 32 physical P4/G2 recordings are decoded in full, independently of caption admission. Each row has eight recordings and 73 reference words.

| Microphone / level | Baseline errors | A4096 errors | B8192 errors | Baseline missed words | A missed | B missed |
|---|---:|---:|---:|---:|---:|---:|
| P4 quiet | 45 | 73 | 61 | 20 | 31 | 40 |
| P4 ordinary | 28 | 67 | 51 | 12 | 20 | 22 |
| G2 quiet | 48 | 70 | 54 | 28 | 31 | 39 |
| G2 ordinary | 25 | 78 | 48 | 10 | 13 | 15 |

Every microphone/level group regresses for both models. The bounded host separator matched the full-array reference byte-for-byte on all 32 actual exported-model windows per model. That supports adapter correctness on this panel; it does not establish P4 numerical execution, memory, latency or realtime behavior.

## Caption replay with original cuts

Across all 163 regression cases / 2,168 reference words, caption errors rise from **609 to 2,221 with A and 1,949 with B**. Missed words rise from 381 to A 398 / B 406; insertions rise from 22 to A 1,603 / B 1,301. This panel has already been used in earlier investigations and is a reused regression check, separate from the frozen source-disjoint qualification panel.

| Caption group | Cases | Reference words | Baseline errors | A4096 errors | B8192 errors |
|---|---:|---:|---:|---:|---:|
| P4 quiet | 8 | 73 | 73 | 73 | 73 |
| P4 ordinary | 8 | 73 | 41 | 66 | 57 |
| G2 quiet | 8 | 73 | 73 | 73 | 73 |
| G2 ordinary | 8 | 73 | 40 | 74 | 53 |
| Release controls combined | 45 | 687 | 187 | 703 | 580 |
| Independent ordinary speech | 24 | 362 | 41 | 380 | 350 |
| Independent quiet speech | 24 | 362 | 43 | 367 | 309 |
| Loud speech | 24 | 362 | 41 | 377 | 363 |
| Annotated overlap | 8 | 103 | 66 | 108 | 90 |
| Background recordings | 6 | 0 | 4 | 0 | 1 |

The release controls include natural, quiet, noisy, headset/distant meeting speech, caption joins and forced cuts. Every constituent release group has more total errors with either separator, though individual deletion counts need not move in the same direction.

All eight quiet clips per physical microphone have empty baseline admission. Keeping those cuts means both baseline and candidate miss all 73 words. A post-detection separator cannot recover samples never admitted. Pre-detection separation would be a different policy requiring separate acceptance, scheduling and memory tests.

Background emitted words fall from four to A zero / B one. Recorded ambience can include real distant voices, so this is an output-count observation, not proof that baseline hallucinations were removed. This limited background result does not offset the speech regressions.

## Continuous caption controls

| Replay | Reference words | Baseline errors | A errors | B errors |
|---|---:|---:|---:|---:|
| Actual saved G2 recording | 146 | 97 | 155 | 137 |
| Concatenated P4 recordings | 146 | 88 | 158 | 125 |

Missed words in the G2 replay rise from baseline 76 to A 85 / B 89; in constructed P4 they rise from 72 to A 91 / B 90.

The P4 control is constructed by concatenating recordings and must not be presented as a fresh continuous room capture. These two controls reuse material from the physical clips and are reported separately, not added as independent evidence to the 163-case total.

## Audit and remaining work

The actual result auditor passed 163 cases, both continuous controls, all 32 whole windows, 210 caption segments and 484 decoded-stream consistency checks per model. It verifies frozen admission/model/decoder identities, raw source hashes, finite waveform shapes, cached waveform/proof hashes, PCM conversion, both cached hypotheses, unchanged cut bounds and complete-recording score arithmetic. All 163 source records retain index/group-qualified identifiers, including repeated phrase IDs across microphones. A's initial audit was preserved; expanding those provenance keys changed no score or group total. The serial comparison controller exited successfully after both actual model runs.

Cached decoding is checked for consistency, not independently re-inferred by this audit. The comparison does not prove speaker-label accuracy, fresh-room generalization or device performance. No output was muted and no decoder, detector or model setting was tuned from this panel.

Both models' saved-microphone comparisons and floating-point diagnostics are complete. Their results reinforce the failed qualification gates; no live promotion is justified. A separate subsequent loss-only training experiment is not qualified by this round. Private evidence: `private/stt-model-comparison/comparison-A-4096-3b537791650e/` and `comparison-B-8192-44033fa66811/`, including `identity.json`, per-case files, waveform proofs, both continuous results, `complete.json`, `audit.json` and `summary.json`.
