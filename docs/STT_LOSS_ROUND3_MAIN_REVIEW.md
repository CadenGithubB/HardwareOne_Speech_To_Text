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

The main agent independently audited the completed A1024 and raw-mixture development controls: 243 cases, 486 output streams and 19 profile groups each. Saved int8 greedy transcripts, finite speaker vectors, actual portable cluster replay, global reference/profile mapping and error arithmetic passed. The exported control is linked to its actual checkpoint and numerical-verification record. Both controls exactly reproduce the prior round's observed PCM identities, hypotheses, embeddings, profile assignments and scores: A1024 has 4,556 errors and raw mixture has 2,462, over 3,400 reference words. The subsequently completed A4096 and A8192 audits also pass all 243 cases each and exactly reproduce their prior observed outputs and 4,302 / 4,471 error scores. These are control consistency results, not candidate gains.

A separate host-only comparison controller is queued. It waits for all six development scores, frozen per-arm selections, fresh synthetic qualification, reused real regression, both controls in each partition and the upstream completion record. It then requires independent completed-score audits before comparing selected models on the unchanged 163-case saved microphone/caption panel and two continuous recordings. Those comparisons preserve the original admission cuts and count both output streams. Sixteen isolated missing-evidence/tamper checks passed, including earlier-step ties, stale audits, changed checkpoint/native bytes and mismatched selection records. These are admission tests, not completed candidate tests.

The controller owns a nonblocking lock and uses the existing shared evaluation lock for model execution. It starts no fitting, export or upstream development/qualification jobs. It audits the resulting saved-microphone outputs and stops for acceptance review; it cannot promote firmware. The closed round-two helpers and evidence remain unchanged. New private evidence is under `private/stt-loss-round3-review/`.

Both training arms have now completed 8,192 updates. The main agent verified all 32,768 ordered training records per arm against the frozen manifest: exact recipe, mixture/target PCM, gain and model-input/target digests match. Recorded learning-rate schedules and metadata also passed. This checks saved training traces, without independently reconstructing waveforms or replaying optimization. The completed known-source development control passed the same 243-case/486-stream score audit and reproduces its prior 886-error result exactly. Known sources are a diagnostic, not a deployable separator.

All six exports are saved. The main review reconciled their actual model/native/checkpoint bytes, fixed export policy, int8 interfaces and recorded independent-verifier logs. B4096's export worker returned signal 11 after writing its export report; its subsequent separate verifier exited successfully and reloaded the exact saved artifact to reproduce the 96,000-value fixture. The crash cause is not established. It is recorded rather than described as a clean export-worker exit. These are host artifact checks, not recognition results or P4 qualification.

## First changed-loss recognition result

B1024 has completed and passed the main agent's 243-case / 486-stream saved-logit, portable-cluster and error-count audit. This is one exposed-development checkpoint; neither checkpoint selection nor qualification is complete.

| Error view | Raw-mixture baseline | A1024 original loss | B1024 changed loss |
|---|---:|---:|---:|
| Global profile-attributed errors / 3,400 reference words | 2,462 | 4,556 | 4,270 |
| Ordinary oracle errors / 425 words | 58 | 471 | 409 |
| Quiet oracle errors / 425 words | 66 | 493 | 364 |
| Two-speaker oracle errors / 2,550 words | 2,025 | 2,533 | 2,444 |

B1024 reduces global errors by 286 against matched A1024, but remains 1,808 errors worse than the raw-mixture baseline. Its global insertions fall from 2,834 to 2,370, while substitutions rise from 952 to 1,092 and deletions from 770 to 808. In the separate two-speaker oracle view, deletions rise from 119 to 210. Fewer extra words alone do not establish successful retention.

The ordinary single-speaker cases still produce text on both outputs in 47/48 cases, and quiet cases in 45/48. Extra-head words under oracle assignment fall from 400 to 337 for ordinary speech and from 392 to 286 for quiet speech. The analytic loss change has not eliminated this observed behavior at 1,024 updates. Unassignable recognized words are 825 for B versus 498 for A; no stable-label improvement is established. These are descriptive correlated development views, not a fresh holdout or a trained causal attribution. Later checkpoints and the completed selection are reported below; no tuning or promotion follows from this first result.

## Changed loss at 4,096 updates

B4096 also passed the full 243-case / 486-stream main audit. Its global profile-attributed errors are **4,635**, versus matched A4096's **4,302** and baseline **2,462**, over the same 3,400 reference words. B has 932 substitutions, 1,166 deletions and 2,537 insertions. This checkpoint regresses the primary metric despite fewer extra-head words.

In the separate oracle assignment view, B's ordinary / quiet / two-speaker errors are 365 / 323 / 2,387, versus A's 452 / 430 / 2,457. That local view improves while the global attributed score worsens. Unassignable recognized words rise from A's 391 to B's 1,299. This discrepancy reinforces why per-case remapping or suppression of an output cannot replace stable-speaker scoring. It does not isolate the speaker model, clusterer or separator as the sole cause. The final B checkpoint and development selection are reported below. No model has been promoted.

## Development complete; qualification underway

All six learned-model development results and both controls have now passed the stronger main-agent score audit. The frozen selection records and their exact report digests were independently reconciled. The scores below count global profile-attributed errors over the same 3,400 reference words.

| Updates | Original loss A | Changed loss B |
|---|---:|---:|
| 1,024 | 4,556 | **4,270 — selected B** |
| 4,096 | **4,302 — selected A** | 4,635 |
| 8,192 | 4,471 | 4,580 |

The raw-mixture baseline is 2,462 errors; known individual sources score 886. The best new-loss checkpoint improves on the selected original-loss checkpoint by only 32 errors and still has 1,808 more errors than baseline. More training did not rescue B under the fixed budget and selection rule. These are exposed-development findings, not independent qualification.

A4096 has also completed the new 323-case qualification partition and passed the main audit of all 646 streams and 25 groups: 15,657 profile-attributed errors (2,934 substitutions, 2,674 deletions, 10,049 insertions) over 11,688 words. Ordinary / quiet / two-speaker oracle errors are 1,608 / 1,584 / 8,348. Its single-speaker ordinary and quiet cases each produce recognized text on both heads in 64/64 cases. B1024 has subsequently completed as reported below; the two qualification controls remain unfinished, so a baseline-relative qualification conclusion is still pending. The old real32 regression and selected saved-microphone comparisons also remain pending. The existing host workers continue without changing selections or settings.

## Both selected qualification models audited

B1024 completed the same 323 cases and passed the main 646-stream / 25-group audit. The locally reserved speech panel does not reproduce B's slight selected-development advantage.

| Error view | Selected A4096 | Selected B1024 |
|---|---:|---:|
| Global profile-attributed errors / 11,688 words | 15,657 | 15,721 |
| Ordinary oracle errors / 1,461 words | 1,608 | 1,598 |
| Quiet oracle errors / 1,461 words | 1,584 | 1,562 |
| Two-speaker oracle errors / 8,766 words | 8,348 | 8,544 |

B's global counts are 2,818 substitutions, 2,732 deletions and 10,171 insertions. Both models still produce recognized text on both heads in all 64 ordinary and all 64 quiet single-speaker cases. Under oracle assignment, ordinary extra-head words are 1,430 for both; quiet extra-head words are 1,393 for A and 1,383 for B. The active-loss change has not resolved the observed duplication on this panel. This is a descriptive paired result, not proof of a sole training failure cause or statistical equivalence. Both produce zero words on the three reused nonspeech fixtures, which cannot establish broad noise robustness.

The raw-mixture qualification control is running and the known-source control follows. Those controls are still needed for baseline-relative checks. The existing real32 regression and the main saved-microphone comparisons remain pending; no model or firmware has been adopted.

## Round three closed · both selected candidates fail (5 November 2026)

All planned host scoring finished: both qualification controls, the old real32 regression for both arms and both controls, and both selected saved-microphone comparisons. The evaluation controller logged "All planned loss-round3 host scoring complete", and main controller 17121 finished at stage `host-comparisons-and-audits-finished`. All 16 completed score reports are archived by SHA under `private/stt-loss-round3-review/audited-results/`. Both microphone comparisons passed the actual-output audit: 163 cases, 32 whole windows, 210 caption segments and 484 decoded-stream checks each. No worker was restarted, and no selection, threshold or setting changed.

The frozen reducer `review_selected.py` uses the same seven necessary host checks as round two and wrote `selected-host-review.json`. **Neither candidate passes; both fail the same four checks:**

| Necessary check (vs raw-mixture baseline) | A4096 | B1024 |
|---|---|---|
| Lower real32 profile-attributed errors | fail (912 vs 611) | fail (809 vs 611) |
| Lower real32 profile-attributed deletions | pass (159 vs 260) | pass (189 vs 260) |
| Lower real32 oracle errors | fail (717 vs 594) | fail (635 vs 594) |
| Lower real32 oracle deletions | pass | pass |
| Ordinary error nonregression (fresh synthetic) | fail (1,608 vs 170) | fail (1,598 vs 170) |
| Quiet error nonregression (fresh synthetic) | fail (1,584 vs 178) | fail (1,562 vs 178) |
| Three reused nonspeech fixtures emit zero words | pass | pass |

On fresh synthetic qualification, global profile-attributed errors over 11,688 words are: raw-mixture baseline 8,874, A4096 15,657, B1024 15,721. The known-source diagnostic is 2,178. Two-speaker oracle errors are 6,817 / 8,348 / 8,544 respectively. Both separators lose more words and add far more duplicate words than the no-separator path. Real32 is reused regression evidence, not independent qualification.

**Saved microphone and caption panel**, oracle acoustic assignment with both output streams counted:

| Panel | Baseline errors | A4096 | B1024 |
|---|---:|---:|---:|
| Whole windows (292 words) | 146 | 288 | 219 |
| Caption segments (2,168 words) | 609 | 2,221 | 2,000 |
| G2 continuous recording (146 words) | 97 | 155 | 129 |
| P4 concatenated recordings (146 words) | 88 | 158 | 115 |

Both candidates regress 17 of 18 group/view cells and improve only background (4 → 0 and 4 → 1 errors). Both P4 and G2 microphone groups regress, so the result does not depend on which shared microphone path is used. Quiet caption cells are 73/73 errors for every arm, baseline included. Independent LibriSpeech and loud caption groups regress by roughly 300+ errors each. This panel uses cached decoding and oracle assignment. It does not test stable labels, fresh rooms or P4 execution.

**Conclusion:** the active-loss change did not produce a usable compact separator. Neither selected model beats the existing single-speaker path on any accuracy gate, so production defaults stay unchanged and no firmware is promoted. Round three needs no more host work. Any further separator investigation needs a new, separately frozen experiment, not retuning of this one. P4 realtime operation, the 30,000,000-byte total-application peak and independent real-overlap qualification remain untested because no candidate reached them.

Private evidence: `private/stt-loss-round3-review/selected-host-review.json`, `comparison-{A-4096,B-1024}-*/audit.json`, `comparison-controller-status.json`. Original declarations remain under `private/training-track/compact16k-loss-round3/`; contract audit in `private/stt-model-comparison/round3-contract-audit.json`.
