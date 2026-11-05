# Main review of the active-loss A/B

**The broader accuracy goal remains active.** The separate training chat owns the existing `compact16k-loss-round3` training, export and evaluation workers. This main-agent review changes no frozen experiment, fitting code, model or production setting. It does not establish a trained accuracy gain.

## The changed factor

Arm A calls the original supervised loss. Arm B replaces only the active-source term with target-energy-normalized waveform reconstruction error in log units: `10*log10(MSE / target_power + 0.001)`, with the existing denominator safeguard. Both retain complete two-output permutation assignments and the same inactive-output energy formula. Teacher assistance is disabled in both arms.

This is **not an empty-output-penalty A/B**. The inactive formula is unchanged, though changing the active term can change which complete assignment wins. The experiment tests whether a reconstruction objective that accounts for amplitude and polarity avoids an undesirable assignment preference in the earlier objective. The minimum active-source value is -30 dB at zero reconstruction error; this is an objective value, not measured audio SNR or recognition accuracy.

## Independently reproduced counterexample

The target is one clean tone plus silence. One prediction contains that tone with a small interfering tone on the first output and silence on the second. The alternative adds a clean copy at 0.1% amplitude to the second output. Lower loss is preferred.

| Objective | No duplicate | Tiny clean duplicate |
|---|---:|---:|
| Original A | -9.996417 | -10.096494 |
| Candidate B | -9.792120 | -9.792115 |

The original objective prefers the duplicate-containing prediction; the candidate does not in this constructed case. This is a demonstrated analytic preference, not proof that it caused the prior trained models' duplicated text. The candidate still needs actual two-speaker and quiet-speaker retention tests.

The main review reproduced the values using the actual frozen loss modules, checked control equality with the original function and checked six finite, nonzero-gradient cases spanning silence, one speaker and a quiet second target. No optimizer or neural forward pass was run by this review.

## Contract and data checks

- All seven launch-frozen files, six prior dependencies and seven scoring-driver files match the admission hashes. The independent exporter verifier is also pinned.
- Runtime, metrics and selection-rule files are byte-identical to round two. Separator forward, PCM conversion and transcription functions have identical ASTs; the surrounding workflow changes roots and evaluation partitions.
- The reused 243-case development panel is exactly unchanged and explicitly exposed. It is not a new holdout.
- Qualification uses 16 newly reserved voices / 64 utterances, yielding 323 synthetic cases. The main review found no source-hash or corpus-prefixed speaker-ID overlap with the training manifest, and no source-hash overlap with the prior evaluation suite.
- All 320 speech-case mixtures exactly equal their declared integer source sums; 608 unique qualification PCM paths were hashed. Three synthetic nonspeech cases are separate. This verifies construction, not every spoken reference or broad noise behavior.
- The old 32 real-overlap cases retain their inputs and references and are labelled **regression**. They cannot serve as fresh independent real-room qualification.
- The actual A1024 checkpoint matches all 177 state tensors of the prior supervised A1024 checkpoint, with the same model arguments and finite values. This verifies the control replay through that point, not later updates, optimizer correctness or candidate learning.

The reservation's historical exclusion-file hashes match their current files. This does not resolve unknown recognizer/pretraining exposure or cross-corpus identity aliases. Local disjointness is not a claim of universal population independence.

## Remaining main-agent work

Audit both arms' complete matched-input records and completed exported-model results; verify the unchanged export policy and frozen development-only selections; then review fresh synthetic qualification and clearly separate old real-overlap regression. Compare selected candidates on the same saved microphone/regression panel without tuning thresholds or suppressing an output. Neither a preparation check nor a lower training loss is an adoption result.

Both speakers' words and stable labels, P4 execution, realtime behavior and at most 30,000,000 bytes simultaneous total-application peak remain requirements. Fresh independent real-overlap evidence is not available in this local round; no product qualification or firmware promotion follows from its synthetic panel alone. Hardware access and Bluetooth changes are outside the current host-only work.

Private evidence: `private/stt-model-comparison/audit_round3_contract.py` and `round3-contract-audit.json`; original declarations remain under `private/training-track/compact16k-loss-round3/`. Existing worker handles belong to the training chat and must not be duplicated. User-facing checks remain on the five-minute cadence.
