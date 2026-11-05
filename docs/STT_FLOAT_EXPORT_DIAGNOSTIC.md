# Selected separator float/export diagnostic

**Both selected separators regress with their original floating-point weights under this inference pipeline.** Complete A4096 and B8192 floating-point development results passed the main audit. These are post-selection diagnostics; checkpoint selections and qualification outcomes remain frozen. Separator quantization/export is not the sole explanation for the measured failure.

The floating-point separator uses the selected checkpoint's original weights. The exported comparison uses that same checkpoint with int8 convolutions and float32 normalization. The recognizer remains the same frozen int8 25397 model in both cases; this does not test an entirely floating-point STT system or P4 float execution.

| Development primary metric | No separator | Exported A4096 | Float A4096 | Exported B8192 | Float B8192 |
|---|---:|---:|---:|---:|---:|
| Profile-attributed word errors | 2,462 | 4,302 | 4,351 | 4,071 | 3,971 |
| Substitutions | 785 | 958 | 894 | 1,021 | 988 |
| Missed words | 1,134 | 783 | 868 | 921 | 808 |
| Extra words | 543 | 2,561 | 2,589 | 2,129 | 2,175 |
| Reference words | 3,400 | 3,400 | 3,400 | 3,400 | 3,400 |

All comparisons cover the same 243 development cases. Exported A has 49 fewer primary errors than float A; exported B has 100 more than float B. These descriptive differences are not significance claims or proof of a universal quantization benefit/cost. Removing separator quantization/export does not rescue either selected checkpoint's baseline regression.

Separate per-case oracle acoustic errors remain high in float A: ordinary 420 versus baseline 58 on 425 words, quiet 403 versus 66 on 425 words, and synthetic two-speaker 2,409 versus 2,025 on 2,550 words. Float A adds 354 ordinary and 299 quiet words as insertions. Both outputs remain counted. The result therefore cannot be explained solely by the primary metric's global speaker assignments.

Float B's oracle errors are ordinary 369, quiet 335 and synthetic two-speaker 2,321 on those same denominators, with 298 ordinary and 225 quiet insertions. All three remain worse than baseline. Its lower primary float total than exported B comes from 113 fewer missed words and 33 fewer substitutions, partly offset by 46 more insertions.

The next investigation should test targets, objective behavior, model learning and the shared train/inference preprocessing contract rather than assuming higher separator precision will fix these models. This result does not establish which mechanism is responsible, prove the empty-stream loss hypothesis, rule out quantization effects on other checkpoints, or justify another full training run without learning sanity checks.

## Isolation and audit

The float protocol matches every native protocol field except the explicitly changed scorer and three added diagnostic fields (precision, Torch version and float model source hashes). Suite, recognition model, frontend/cluster sources, speaker model, decoder, runtime adapter, metric and selection rule are unchanged. All 59 recorded Asteroid/filterbank source modules match their file hashes.

The main result audit verified each selected checkpoint identity, matched exported artifact, all 243 cases / 486 streams per model, PCM hashes, greedy reconstruction from saved int8 recognizer logits, speaker vectors, portable cluster replay, complete group assignment, unknown-word handling and condition/error arithmetic. A separate comparison audit verified the final diagnostic marker, unchanged frozen selections, both native/float result hashes, case/reference correspondence, counts and conditions. This checks stored-result consistency, not independent reference annotations or physical-room generalization. The float/native gap includes separator quantization and export lowering rather than isolating one precision island.

Source result SHA-256: `d40046cc85664b7836503160196aaf249466ef5105f5b7f7257031641406ea3a`. Float protocol: `6d039533174ae40490d1ff8169a5d5c912dae043462e300793316ce37fe51c68`. Native protocol: `a3010c5a387e2705b03ce3c8a203baedd3128cae35bec52c0f8ca612c3ca9eb8`.

B source result SHA-256: `583bb5e7806e06ffcef8c3528037cb482f05a79c52ed2568dec22fd86c89e058`.

Private evidence: `private/stt-model-comparison/audit-scores-float-A-4096-development.json`, `audit-scores-float-B-8192-development.json`, `float-protocol-audit.json`, `float-comparison-audit.json`, archived results and the source results under `private/training-track/compact16k-round2/scores-float-*/`. A's saved-microphone comparison is complete and failed; B's is still in progress. No production model, decoder, detector or firmware default was changed.
