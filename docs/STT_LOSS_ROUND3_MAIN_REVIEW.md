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
- Qualification uses 16 newly reserved voices / 64 utterances, yielding 320 synthetic speech cases plus three reused nonspeech fixtures (323 total). The main review found no source-hash or corpus-prefixed speaker-ID overlap with the training manifest, and no source-hash overlap with the prior evaluation suite.
- All 320 speech-case mixtures exactly equal their declared integer source sums; 608 unique qualification PCM paths were hashed. Three synthetic nonspeech cases are separate and reuse the same PCM as development and the previous round. Their result is a regression check, not fresh noise validation. This verifies construction, not every spoken reference or broad noise behavior.
- The old 32 real-overlap cases retain their inputs and references and are labelled **regression**. They cannot serve as fresh independent real-room qualification.
- Actual supervised A checkpoints at 1,024, 4,096 and 8,192 updates each match all 177 state tensors of their prior round-two counterparts. All six A/B checkpoints have finite state tensors and matching architecture/metadata; B differs from A at all three saved updates. This verifies saved-state/control consistency, not optimizer replay or candidate accuracy.

The reservation's historical exclusion-file hashes match their current files. This does not resolve unknown recognizer/pretraining exposure or cross-corpus identity aliases. Local disjointness is not a claim of universal population independence.

## Completed control scoring and queued microphone comparisons

The main agent independently audited the completed A1024 and raw-mixture development controls: 243 cases, 486 output streams and 19 profile groups each. Saved int8 greedy transcripts, finite speaker vectors, actual portable cluster replay, global reference/profile mapping and error arithmetic passed. The exported control is linked to its actual checkpoint and numerical-verification record. Both controls exactly reproduce the prior round's observed PCM identities, hypotheses, embeddings, profile assignments and scores: A1024 has 4,556 errors and raw mixture has 2,462, over 3,400 reference words. The subsequently completed A4096 audit also passes all 243 cases and exactly reproduces its prior observed outputs and 4,302-error score. These are control consistency results, not candidate gains.

A separate host-only comparison controller is queued. It waits for all six development scores, frozen per-arm selections, fresh synthetic qualification, reused real regression, both controls in each partition and the upstream completion record. It then requires independent completed-score audits before comparing selected models on the unchanged 163-case saved microphone/caption panel and two continuous recordings. Those comparisons preserve the original admission cuts and count both output streams. Sixteen isolated missing-evidence/tamper checks passed, including earlier-step ties, stale audits, changed checkpoint/native bytes and mismatched selection records. These are admission tests, not completed candidate tests.

The controller owns a nonblocking lock and uses the existing shared evaluation lock for model execution. It starts no fitting, export or upstream development/qualification jobs. It audits the resulting saved-microphone outputs and stops for acceptance review; it cannot promote firmware. The closed round-two helpers and evidence remain unchanged. New private evidence is under `private/stt-loss-round3-review/`.

Both training arms have now completed 8,192 updates. The main agent verified all 32,768 ordered training records per arm against the frozen manifest: exact recipe, mixture/target PCM, gain and model-input/target digests match. Recorded learning-rate schedules and metadata also passed. This checks saved training traces, without independently reconstructing waveforms or replaying optimization. The completed known-source development control passed the same 243-case/486-stream score audit and reproduces its prior 886-error result exactly. Known sources are a diagnostic, not a deployable separator.

All six exports are saved. The main review reconciled their actual model/native/checkpoint bytes, fixed export policy, int8 interfaces and recorded independent-verifier logs. B4096's export worker returned signal 11 after writing its export report; its subsequent separate verifier exited successfully and reloaded the exact saved artifact to reproduce the 96,000-value fixture. The crash cause is not established. It is recorded rather than described as a clean export-worker exit. These are host artifact checks, not recognition results or P4 qualification.

## Remaining main-agent work

Complete matched-input and six-export record audits have passed. Remaining work is to audit the rest of the actual recognition results, verify frozen development-only selections, then review fresh synthetic speech qualification and clearly separate the reused nonspeech and old real-overlap regression checks. Compare selected candidates on the same saved microphone/regression panel without tuning thresholds or suppressing an output. Neither a preparation check nor a lower training loss is an adoption result.

Both speakers' words and stable labels, P4 execution, realtime behavior and at most 30,000,000 bytes simultaneous total-application peak remain requirements. Fresh independent real-overlap evidence is not available in this local round; no product qualification or firmware promotion follows from its synthetic panel alone. Hardware access and Bluetooth changes are outside the current host-only work.

Private evidence: `private/stt-model-comparison/audit_round3_contract.py` and `round3-contract-audit.json`; original declarations remain under `private/training-track/compact16k-loss-round3/`. Existing worker handles belong to the training chat and must not be duplicated. User-facing checks remain on the five-minute cadence.
