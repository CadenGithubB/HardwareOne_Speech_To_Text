# Selected separator saved-microphone comparison

**A4096 completed and failed the saved-microphone/regression comparison. B8192 remains pending.** Production defaults remain unchanged. These are offline replays of existing audio, not fresh live P4/G2 tests or checkpoint selection data.

The comparison uses the frozen 25397 recognizer and full-strength meeting LM, original raw caption-admission cuts, and both separator outputs. One oracle source assignment applies to each complete independent recording after both streams are decoded. This measures acoustic recognition retention, not stable speaker labels. It differs from training's greedy/profile-attributed evaluation; its totals must not be mixed with those scores.

## Full saved-window recognition

These 32 physical P4/G2 recordings are decoded in full, independently of caption admission. Each row has eight recordings and 73 reference words.

| Microphone / level | Baseline errors | A4096 errors | Baseline missed words | A missed words |
|---|---:|---:|---:|---:|
| P4 quiet | 45 | 73 | 20 | 31 |
| P4 ordinary | 28 | 67 | 12 | 20 |
| G2 quiet | 48 | 70 | 28 | 31 |
| G2 ordinary | 25 | 78 | 10 | 13 |

Every microphone/level group regresses. The bounded host separator matched the full-array reference byte-for-byte on all 32 actual exported-model windows. That supports adapter correctness on this panel; it does not establish P4 numerical execution, memory, latency or realtime behavior.

## Caption replay with original cuts

Across all 163 regression cases / 2,168 reference words, caption errors rise from **609 to 2,221**. Missed words rise from 381 to 398 and insertions from 22 to 1,603. This panel has already been used in earlier investigations and is a reused regression check, separate from the frozen source-disjoint qualification panel.

| Caption group | Cases | Reference words | Baseline errors | A4096 errors |
|---|---:|---:|---:|---:|
| P4 quiet | 8 | 73 | 73 | 73 |
| P4 ordinary | 8 | 73 | 41 | 66 |
| G2 quiet | 8 | 73 | 73 | 73 |
| G2 ordinary | 8 | 73 | 40 | 74 |
| Release controls combined | 45 | 687 | 187 | 703 |
| Independent ordinary speech | 24 | 362 | 41 | 380 |
| Independent quiet speech | 24 | 362 | 43 | 367 |
| Loud speech | 24 | 362 | 41 | 377 |
| Annotated overlap | 8 | 103 | 66 | 108 |
| Background recordings | 6 | 0 | 4 | 0 |

The release controls include natural, quiet, noisy, headset/distant meeting speech, caption joins and forced cuts. Every constituent release group has more total errors with A, though individual deletion counts need not move in the same direction.

All eight quiet clips per physical microphone have empty baseline admission. Keeping those cuts means both baseline and candidate miss all 73 words. A post-detection separator cannot recover samples never admitted. Pre-detection separation would be a different policy requiring separate acceptance, scheduling and memory tests.

Background emitted words fall from four to zero. Recorded ambience can include real distant voices, so this is an output-count observation, not proof that four baseline hallucinations were removed. This limited background result does not offset the speech regressions.

## Continuous caption controls

| Replay | Reference words | Baseline errors | A errors | Baseline missed words | A missed words |
|---|---:|---:|---:|---:|---:|
| Actual saved G2 recording | 146 | 97 | 155 | 76 | 85 |
| Concatenated P4 recordings | 146 | 88 | 158 | 72 | 91 |

The P4 control is constructed by concatenating recordings and must not be presented as a fresh continuous room capture. These two controls reuse material from the physical clips and are reported separately, not added as independent evidence to the 163-case total.

## Audit and remaining work

The actual result auditor passed 163 cases, both continuous controls, all 32 whole windows, 210 caption segments and 484 decoded-stream consistency checks. It verifies frozen admission/model/decoder identities, raw source hashes, finite waveform shapes, cached waveform/proof hashes, PCM conversion, both cached hypotheses, unchanged cut bounds and complete-recording score arithmetic. All 163 source records retain index/group-qualified identifiers, including repeated phrase IDs across microphones. The initial audit was preserved; expanding those provenance keys changed no score or group total.

Cached decoding is checked for consistency, not independently re-inferred by this audit. The comparison does not prove speaker-label accuracy, fresh-room generalization or device performance. No output was muted and no decoder, detector or model setting was tuned from this panel.

B8192's saved-microphone comparison and floating-point diagnostic remain unfinished. A's result reinforces its failed qualification gates; no live promotion is justified. Private evidence: `private/stt-model-comparison/comparison-A-4096-3b537791650e/`, including `identity.json`, per-case files, waveform proofs, both continuous results, `complete.json`, `audit.json` and `summary.json`.
