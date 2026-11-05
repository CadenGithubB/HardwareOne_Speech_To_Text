# Selected separator float/export diagnostic

**The supervised separator already fails before separator quantization.** A4096's complete floating-point development result passed the main audit. B8192's floating-point diagnostic remains pending. These are post-selection diagnostics; checkpoint selections and qualification outcomes remain frozen.

The floating-point separator uses the selected checkpoint's original weights. The exported comparison uses that same checkpoint with int8 convolutions and float32 normalization. The recognizer remains the same frozen int8 25397 model in both cases; this does not test an entirely floating-point STT system or P4 float execution.

| Development primary metric | No separator | Exported A4096 | Float A4096 |
|---|---:|---:|---:|
| Profile-attributed word errors | 2,462 | 4,302 | 4,351 |
| Substitutions | 785 | 958 | 894 |
| Missed words | 1,134 | 783 | 868 |
| Extra words | 543 | 2,561 | 2,589 |
| Reference words | 3,400 | 3,400 | 3,400 |

All comparisons cover the same 243 development cases. Exported A has 49 fewer primary errors than float A; that small descriptive difference is not a significance claim or proof that quantization is beneficial. The useful conclusion is that removing separator quantization/export does not rescue this checkpoint's baseline regression.

Separate per-case oracle acoustic errors remain high in float A: ordinary 420 versus baseline 58 on 425 words, quiet 403 versus 66 on 425 words, and synthetic two-speaker 2,409 versus 2,025 on 2,550 words. Float A adds 354 ordinary and 299 quiet words as insertions. Both outputs remain counted. The result therefore cannot be explained solely by the primary metric's global speaker assignments.

The next training investigation should test targets, objective behavior and model learning rather than assuming higher separator precision will fix A. This result does not establish which training mechanism is responsible, prove the empty-stream loss hypothesis, rule out quantization effects on other checkpoints, or justify another full training run without learning sanity checks. B's diagnostic is still needed before extending the conclusion to teacher-assisted training.

## Isolation and audit

The float protocol matches every native protocol field except the explicitly changed scorer and three added diagnostic fields (precision, Torch version and float model source hashes). Suite, recognition model, frontend/cluster sources, speaker model, decoder, runtime adapter, metric and selection rule are unchanged. All 59 recorded Asteroid/filterbank source modules match their file hashes.

The main result audit verified the selected checkpoint identity, matched exported artifact, all 243 cases / 486 streams, PCM hashes, greedy reconstruction from saved int8 recognizer logits, speaker vectors, portable cluster replay, complete group assignment, unknown-word handling and condition/error arithmetic. This checks stored-result consistency, not independent reference annotations or physical-room generalization. The float/native gap includes separator quantization and export lowering rather than isolating one precision island.

Source result SHA-256: `d40046cc85664b7836503160196aaf249466ef5105f5b7f7257031641406ea3a`. Float protocol: `6d039533174ae40490d1ff8169a5d5c912dae043462e300793316ce37fe51c68`. Native protocol: `a3010c5a387e2705b03ce3c8a203baedd3128cae35bec52c0f8ca612c3ca9eb8`.

Private evidence: `private/stt-model-comparison/audit-scores-float-A-4096-development.json`, `float-protocol-audit.json`, archived results, and `private/training-track/compact16k-round2/scores-float-A-4096-development/results.json`. Saved-microphone comparisons and the B float diagnostic remain in progress. No production model, decoder, detector or firmware default was changed.
