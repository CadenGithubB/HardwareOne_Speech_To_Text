# Overlapping speech investigation

4 November 2026. Research and annotation audit. No new overlap model has been trained in this investigation. The user confirmed the required behavior is to caption both speakers’ words with speaker labels.

Our current model improved isolated distant speech from 117 to 101 errors on 364 words after the full-encoder continuation, while overlap worsened from 165 to 174 errors on 271 target-speaker words. Overlap deletions increased from 77 to 94. Preserve the isolated benefit as an explicit development constraint in the next experiment, alongside ordinary speech and release controls.

## What the current score measures

The existing 24 distant overlap clips use the normalized reference of one annotated AMI utterance. Other speakers' words are absent from that reference. The annotation audit reconciled each clip to the original AMI test metadata. Seven clips contain one competing speaker, twelve contain two, and five contain three during some portion of the window. These counts describe distinct competing speakers across the window, not simultaneous voice count at a single instant. Median annotated overlap duration is 56.2% of the clip.

Consequently this is target-speaker transcription under interference. It is not an all-speaker meeting-transcription score. Correctly hearing an unreferenced competitor can create an insertion or substitution. Target-word deletion counts remain relevant, but cannot describe all words missed across the room. Overlap proportions come from human annotation intervals, not an acoustic estimate.

The deployed and trained hypotheses each contain 33 token occurrences appearing in overlapping competitors' whole-utterance vocabulary but absent from the target reference vocabulary. This is a review flag only. Competitor utterances can extend outside the clip, shared words are excluded, and word coincidence does not establish speaker attribution. No insertion count was relabeled using this heuristic. Raw competitor annotations and case IDs are private in `private/training-track/overlap-investigation/annotation-audit.json`.

## Approaches used by other systems

| Approach | What it does | Consequence for this P4 project |
| --- | --- | --- |
| Train with competing speech | Mix labeled voices with controlled timing and loudness, so the recognizer learns speech under interference. Some systems also use clean-speech teachers during training. | A first experiment can preserve the existing inference graph and its memory cost. Labels must specify the intended speaker policy. This alone does not establish recovery of both equally loud voices. |
| Continuous speech separation | Produce separate audio streams from a mixture, then recognize each stream. Microsoft's CSS research uses continuous output channels to handle changing overlap. | Requires separator weights, streaming state, buffers and additional recognition work. The full 30,000,000-byte app budget and P4 time must be measured. A host result would only establish an accuracy ceiling. |
| Target-speaker extraction | Use a separate voice sample to guide extraction of a chosen speaker. SpeakerBeam learns a voice representation and uses it to extract that voice. | Relevant to following one person. Our existing speaker embedding would need a deliberately trained extractor or recognizer conditioning path. Embedding availability alone does not recover masked audio. |
| Joint recognition of multiple speakers | Serialized output training teaches a recognizer to emit different speakers' transcripts in a defined order. Other systems use multiple output streams and permutation-invariant losses. | Relevant to captioning both voices. Requires new output/training semantics, stream handling and attribution. The current single CTC text stream has no speaker separator symbol or speaker-conditioned outputs. |
| Microphone arrays and beamforming | Combine spatially distinct channels to improve a chosen direction or feed separation. | Depends on separately available, synchronized physical microphone channels. The evaluated current input is mono. No array benefit has been qualified for this capture path. |
| Overlap-aware diarization | Mark when multiple people are active and assign activity to speakers. | Can help route and evaluate recognition. Activity labels alone do not reconstruct either person's missing words. |

These are published strategies, not claims that every commercial recognizer uses the same implementation or solves overlap reliably.

Primary sources support the descriptions above. IBM's multi-speaker augmentation work includes a clean-speech teacher during training. Microsoft's CSS work produces continuous streams with overlap removed. SpeakerBeam conditions extraction on an adaptation utterance. Serialized output training explicitly trains transcripts for multiple overlapping speakers. [IBM augmentation research](https://research.ibm.com/publications/multi-speaker-data-augmentation-for-improved-end-to-end-automatic-speech-recognition), [Microsoft CSS](https://www.microsoft.com/en-us/research/publication/low-latency-speaker-independent-continuous-speech-separation/), [SpeakerBeam](https://www.fit.vut.cz/research/result/c159990/.en), [Serialized output training](https://www.isca-archive.org/interspeech_2020/kanda20b_interspeech.html), [NVIDIA diarization documentation](https://github.com/NVIDIA-NeMo/Speech/blob/main/examples/speaker_tasks/diarization/README.md).

## What our float comparison says

| Overlap condition, same 271 reference words | Total errors | Deletions |
| --- | --- | --- |
| Deployed weights, float + LM | 158 | 69 |
| Deployed weights, int8 + LM | 165 | 77 |
| New trained weights, float + LM | 163 | 77 |
| New trained weights, int8 + LM | 174 | 94 |

The new model has an overlap regression before quantization, and export adds further loss. Quantization-aware training addresses only the second mechanism. Selectively increasing layer precision would also need evidence of an accuracy gain and memory fit. Neither addresses the missing definition of which concurrent words the output should contain.

## Next experiments

The intended caption policy is now frozen to recover both speakers with labels. Freeze the development protocol next. Keep the already-scored 24 overlap clips for descriptive reporting, and use train-only synthesized mixtures and meeting/speaker-disjoint development inputs for fitting and selection. Never select interventions on the test clips. Original model pretraining exposure and cross-corpus speaker aliases remain outside the continuation audit.

For following a main speaker, use a single-speaker lead-in and mix an independently sampled training speaker after it, with fixed seed, controlled loudness ratios and partial overlap. Ground truth belongs to the continuing lead-in speaker. Compare transcript-only training with a reliable clean-view teacher, using exact mixture timing. Include unmodified speech and the previously successful isolated distant examples in every arm. Avoid training empty labels on backgrounds containing unverified speech. Add int8 rounding during a matched training arm, then evaluate actual exported int8 models. Teacher confidence and clean labels must be audited independently of evaluation success.

For recovering both speakers, construct mixtures with both transcripts and source timing. Evaluate a host separation-plus-recognition baseline to find whether the speech remains recoverable, then estimate a compact P4 implementation before committing to a new runtime. Alternatively investigate a small multi-output CTC recognizer trained with permutation-invariant losses, with speaker assignment and continuity explicitly defined. Both are new model/runtime work requiring supported operators, measured total peak PSRAM and latency. A single-reference CTC interference recipe is insufficient evidence of both-speaker recovery.

Evaluate 0%, 10–25%, 25–50%, and greater-than-50% overlap, target/interferer loudness, two versus more voices, and ordinary speech separately. For known synthetic sources, report each speaker's word errors and deletions, words from the wrong speaker and speaker switches. For real meetings, assemble references for every speaker with verified word boundaries at clip edges before using all-speaker scores. Choose the stream-to-reference assignment consistently over a conversation, rather than independently choosing the best speaker for each word. Report speaker-attributed WER and a permutation-invariant transcript metric for an all-speaker system. For a target system keep target WER plus competitor leakage. Report boundary uncertainty explicitly.

Promotion requires lower overlap deletions and total errors, retention of isolated distant and ordinary improvements, no false-word regression on verified no-speech inputs, and the conservative 30,000,000-byte total application peak memory gate, including PSRAM and internal RAM. The historical app already had observations above that target, so a same-sized model does not establish compliance. Score the locked candidate on independent speech after selection. Device numerical parity, maximum supported input and live concurrent operation remain hardware gates.

LibriMix provides reproducible labeled source mixtures and supports a synthetic sanity check. Training mixtures can also be built from our existing corrected train stores without downloading a new corpus. Synthetic success must transfer to separately held real meeting overlap. [LibriMix authors' implementation](https://github.com/JorisCos/LibriMix), [large-scale multi-talker meeting training](https://www.isca-archive.org/interspeech_2021/kanda21_interspeech.html).

Reproduce the local metadata audit from the repository root using `private/layer-sensitivity-20261103/export-venv/bin/python -B private/training-track/overlap-investigation/audit.py`, with host math threads capped at one. It reads original AMI annotations and existing frozen hypotheses. It performs no hardware or audio playback work.

## Selected direction after the user's clarification

Prioritize an all-speaker benchmark and host separation-plus-recognition baseline. Reuse one recognizer sequentially across separated streams where latency permits, rather than assuming two resident model copies. Streaming separators may reserve two audio streams and state, so measure their entire live footprint. Reuse speaker labels across time with continuity checks; output-channel indices are not stable person identities. Quantization-aware training can preserve word recovery within each stream but cannot supply the missing second transcript stream by itself.

The first bounded experiment should use exactly known two-speaker mixtures built from speaker-disjoint held development sources, preserving both clean sources as oracle controls. Vary overlap and loudness independently. Compare recognition of the mixture, recognition of each clean source, and recognition of the separator outputs with fixed LM and C++ features. Score all words with conversation-level speaker assignment and speaker-attributed errors, and retain isolated/quiet regression controls. Then validate the locked approach against real meeting overlap with complete per-speaker references. The clean-source arm gives a recognition ceiling and does not demonstrate that a separator can reach it. Existing test clips stay outside fitting and model selection.

Before any P4 implementation, compare measured separator and recognizer memory with the existing app allocation budget. A successful host separator may be too costly on the P4. If it cannot fit, the next architecture to investigate is a compact shared encoder with two speaker-output paths and permutation-invariant training. That requires a trained model and supported runtime operations before an accuracy or RAM claim. Current evidence supports this investigation, not a claim that it will fit or improve accuracy.

The user revised the working budget on 4 November 2026 to **30,000,000 bytes total peak application memory**, including models, activations, audio, decoder and speaker work. This supersedes the earlier 28 MB target. Report PSRAM/internal RAM and combined allocation peaks explicitly. Older training reports retain their historical budget for provenance.
