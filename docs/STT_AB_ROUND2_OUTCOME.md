# STT A/B round-two outcome

**This round is complete and audited. No tested change qualifies for production. The broader accuracy investigation remains active because the separate training chat has already launched a new matched loss-only A/B experiment.**

The fixed recognizer, speaker algorithms, production detector and firmware defaults were not changed by this campaign. All new work here was host-side evaluation, private prototypes, diagnostics and documentation. No candidate advanced to live P4/G2 qualification.

## Completed work and disposition

| Agreed work | Actual evidence | Outcome |
|---|---|---|
| Diagnose detector regressions | Overflow percentile and startup-gain traces; exact-percentile/processor checks | Mechanisms identified; their corrections did not satisfy full speech-retention gates |
| Test selective changes while preserving recognition PCM | Detector mechanism, relative-energy/onset and additive-rescue studies; 2,805 audited arm records | No eligible policy; retain current defaults |
| Compare trained/exported candidates | Six development checkpoints, frozen A4096/B8192 selection, four complete qualification results and decision audit | Both selected models fail four necessary host checks |
| Check whether quantization explains the failure | Original floating-point A4096/B8192 diagnostics, matched protocols and complete result audits | Both also regress in float under this inference pipeline |
| Test saved physical microphone and broad regression audio | Per model: 32 full physical windows, 163 caption cases, two continuous controls, actual bounded/reference equality and result audit | Both regress in every full-window microphone/level group and both continuous controls |
| Qualify a passing candidate live on P4, then G2 when available | Host gates fail for every candidate | Conditional branch not triggered; live numerical/RAM/realtime/speaker behavior remains unqualified |

The detector records reuse fixtures and recognition caches. They are not 2,805 independent acoustic captures. The microphone regression panel is reused; its two continuous controls share material with the physical clips. The frozen qualification panel is reported separately, with its annotation/pretraining limits disclosed.

## Model results

Rows use different panels, denominators and assignment/decoder policies and must not be aggregated or compared across rows.

| Panel / metric | Reference words | Baseline | Selected A | Selected B |
|---|---:|---:|---:|---:|
| Qualification, global profile-attributed errors | 9,011 | 6,447 | 11,177 | 11,524 |
| Saved caption regression, whole-recording oracle errors | 2,168 | 609 | 2,221 | 1,949 |
| Development with float separator, global profile-attributed errors | 3,400 | 2,462 | 4,351 | 3,971 |

The separate source-input qualification control scores 1,808 primary errors. It supplies known synthetic sources or paired real headsets and bypasses learned separation; it is diagnostic headroom, not an achievable ceiling or deployable result.

## Findings that guide the next work

1. Recovering more words is insufficient when extra output increases total errors. Both output streams must remain counted; muting the quieter stream could discard a real quiet second speaker.
2. A separator placed after detection cannot recover rejected audio. Quiet physical clips with no admitted baseline cuts remain all misses in caption replay.
3. Separator precision alone does not resolve these checkpoints' failures. The original floating-point models also regress; target quality, learning behavior, the objective and shared train/inference preprocessing remain investigation areas.
4. The empty-stream loss diagnostic is a hypothesis, not a proved cause: a coherent copy at 6% amplitude adds only about 0.018 to the controlled loss. A new loss must be tested against real quiet second-speaker retention.

The training chat now owns `private/training-track/compact16k-loss-round3/`. Its existing training/export/evaluation workers must not be duplicated or its frozen experiment edited. The main agent's next work is to audit that experiment's contracts and follow its selected actual exports through the declared qualification and saved-microphone checks. The old 32 real-overlap cases are regression data for that new round, not a fresh real-room holdout. This report does not qualify the new loss or promise an accuracy improvement.

## Evidence and remaining limits

The round-two closure audit reconciles all three detector/routing selections, 14 model/control result audits, both actual microphone result audits, source/export/decoder/runtime hashes, archived results, controller completion and the failed hardware-admission condition. Its `full_goal_complete` field is false because the active training-candidate investigation continues. Private evidence: `private/stt-model-comparison/round2-closure-audit.json` and `GOAL_STATUS.md`.

Detailed reports: [detector mechanisms](STT_DETECTOR_FOLLOWUP.md), [relative detection](STT_RELATIVE_DETECTOR_AB.md), [rescue routing](STT_RESCUE_ROUTING_AB.md), [development selection](STT_EARLY_SEPARATOR_COMPARISON.md), [qualification](STT_SEPARATOR_QUALIFICATION.md), [float/export](STT_FLOAT_EXPORT_DIAGNOSTIC.md), [saved microphones](STT_SELECTED_MICROPHONE_COMPARISON.md), and [P4 preflight](STT_SEPARATOR_P4_PREFLIGHT.md).

P4 compile/link and host bounded-array checks are preparation only. They do not prove device execution, simultaneous total-application peak RAM, caption latency, capture integrity, realtime speed or stable speaker labels. No rollback/partition/flash operation was needed because no candidate passed host acceptance. The user's five-minute check cadence remains active for the ongoing investigation.
