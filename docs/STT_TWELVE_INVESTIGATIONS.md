# STT investigation log

**All twelve investigations are complete.** Keep current int8 as the accuracy
baseline. The block-14 export scored 147 errors against 146 for current int8 on
the 687-word release suite. Its earlier read-speech gain did not carry across
this condition mix.

1. **Prioritize distant meeting speech in model selection.** Identical meeting
   segments produced 110 errors on the distant mic versus 57 on the headset.
   Both AMI training sources together delivered about 22% of rows but only 7%
   of audio time. Evaluate any change to that mix on paired microphones.
2. **Score exported checkpoint finalists with the C++ frontend and production
   decoder.** The logged runner-up beat the logged winner 98 to 101 on the
   633-word read-speech panel, reversing their float ordering. The gap is small.
3. **Inspect invalid preview jobs.** Across three device captures, 103 jobs
   finished without a valid draft and used 66.64 seconds of worker time.
   Thinning all previews delayed stable words, so target those jobs first.
4. **Check quiet capture coverage before changing augmentation.** The loudest
   of three aligned device recordings was 7.4 dB quieter than the quietest of
   96 augmentations. More units and rooms are needed to set a target level.

The investigations run in the order below. The reference acoustic model is the
current gen2-25397 INT8 export with the saved meeting language model. Private
inputs, transcripts, replay code and per-example evidence for this series belong
under `private/sequential-stt/`. The P4 benchmark is assigned to its board owner.

| # | Investigation | State |
| --- | --- | --- |
| 1 | Caption boundary losses and repeated words | Complete, paired replay and three verified hard cuts |
| 2 | False words on silence and noise, with quiet-speech recall | Complete, six noise conditions and 24 speech controls |
| 3 | Language-model fixes and regressions | Complete, four decoder arms |
| 4 | High-loss versus random training transcript audit | Complete, automated evidence review of 10 clips |
| 5 | Realized training corpus sampling | Complete, 512 actual loader microbatches |
| 6 | Training frontend versus portable C++ features and transcripts | Complete, 48 matched inputs and four frontends |
| 7 | Missing short words and meaning-changing omissions | Complete, aligned 633 reference words |
| 8 | Gain, clipping, noise and real microphone distance | Complete, 16 controlled clips and 24 meeting pairs |
| 9 | Augmentation versus device recording distributions | Complete, three aligned device captures and 96 augmentations |
| 10 | Saved checkpoint ranking before and after export and decoding | Complete, three same-run real exports on 633 words |
| 11 | Draft revision, final stability and redundant preview work | Complete, actual P4 events plus separate playback replay |
| 12 | Reusable release comparison across the measured conditions | Complete, two real exports and 48 matched cases |

## 1. Caption boundaries

The first controlled screen pairs the 64 fresh development clips in stable
index order into 32 annotated sequences. Each sequence has 600 ms of leading
silence for ambient calibration, either a 150 ms or 1,200 ms join, and 1,200 ms
of trailing silence. These constructed sequences stress joins and the ten-second
limit. They do not reproduce the distribution of pauses in natural conversations.

The whole-sequence and segmented arms receive identical PCM. The segmented arm
uses the production C++ StreamPipeline, the standalone caption endpoint settings
and 500 ms tail. A synchronous worker drains every final, isolating endpoint
effects from queue pressure. The scorer retains word edits, first and last
reference-word outcomes, segment extents, hard-limit flags and individual segment
outputs. Clip-edge alignment is a text-based proxy. Attributing an error to a
physical cut requires checking the emitted ranges. Evidence is in
`private/sequential-stt/01-boundaries/`.

Across 32 paired sequences containing 633 reference words, both arms made 105
word errors (16.59%). Splitting improved six pairs and worsened six. It reduced
insertions from nine to five and deletions from six to five, while substitutions
rose from 90 to 95. Both arms deleted one reference-initial word and zero
reference-final words. Correct final words fell from 49/64 to 47/64. No adjacent
captions repeated the exact same join word. The 71 emitted final captions had
zero hard-limit endpoints. Short-gap pairs changed from 61 to 56 errors and
long-gap pairs from 44 to 49. The two groups contain different utterances, so
this difference cannot establish a pause-length effect.

Four sequences constructed from onset/offset-trimmed clips yielded 23 whole
versus 26 segmented errors across 103 words but still triggered no hard cuts.
The archived long22 stress fixture did trigger three. For its 150 annotated
words the whole-audio oracle scored 13 errors (11 S, 2 D, 0 I), and five actual
finals scored 14 (12 S, 1 D, 1 I). No emitted join repeated a word. The host
whole-sequence reference extends the frontend duration guard for this 49-second
fixture. A supported-length prefix passed exact feature parity. Together these
runs provide no evidence for a global boundary-setting change. Whole versus
split decoding also changes normalization and acoustic context.

## 2. False words and quiet speech

Each noise condition ran for one minute through the production endpoint logic
and the frozen int8 recognizer with the saved LM. Silence, synthetic room tone,
cycling fan noise, and isolated taps each emitted zero words. Fan and tap inputs
nevertheless triggered eight and two recognition segments, respectively. Two
DEMAND background recordings (living room and office) produced three and one
words. Their sources can include incidental voices, so the four words are
background-triggered output rather than confirmed hallucinations.

Doubling the adaptive speech floor from 45 to 90 suppressed the words in both
recordings. Eight held development utterances at each of three input RMS levels
contributed 82 reference words per level. At RMS 80 the higher floor increased
errors from 19 to 20, at 160 both made 17 errors, and at 640 errors rose from 17
to 18. At 640 one deletion appeared. These results support leaving the current
floor in place while collecting a larger labeled background/quiet-speech set.
Evidence is under `private/sequential-stt/02-noise/`.

## 3. Decoder attribution

All arms decoded the same 64 saved int8 logit sequences (633 reference words).
Greedy decoding made 112 errors. Beam search with both LM weight and word bonus
zero made 110. Adding only the configured word bonus increased errors to 115.
Adding the saved language-model scores reduced them to 103. The production arm
reproduced every previously frozen LM transcript. The 12-error decrease from
115 to 103 isolates the LM score at the deployed bonus and beam settings.

The LM corrected the spelling of the place names *Queens* and *Rhine* in the
beam-plus-bonus comparison. It also fused the correctly recognized two-word
phrase *airplay top* and removed the final plural in *The War of the Worlds*.
Rare names and technical terms such as *caciquismo* were already wrong in the
acoustic beam and remained wrong with the LM. This distinguishes decoder-induced
regressions from errors visible before the LM was enabled. Keep the saved decoder
as the reference and test named terms separately when changing its settings.
Private per-utterance comparisons are under `private/sequential-stt/03-decoder/`.

## 4. High-loss training transcript audit

The audit scored 240 unaugmented 2–9 second training examples at the saved best
checkpoint, evenly sampled across five sources. Within each source it held one
random control aside and selected the highest-loss example among the other 47.
The metric uses the trainer's log-softmax, CTC loss and transcript-length divisor.
An initial selection omitted log-softmax and produced invalid negative scores.
Only the corrected results in `04-label-audit/verified/` support these findings.

Two of five high-loss cases deserve transcript review. In a People's Speech
example, both recognizers continue a classroom instruction after the label ends.
In a VoxPopuli example, both stop three words before the label ends. In contrast,
a separately trained Citrinet recovered every word in the high-loss LibriSpeech
case, including an uncommon term. Common Voice sports vocabulary and a disfluent
AMI segment remained ambiguous. Three random controls matched Citrinet exactly.
The People's Speech control agreed with the training model, and the AMI control
was easier on the matched headset channel than the distant microphone.

No selected waveform contained a saturated PCM sample. Clip-edge energy alone
does not prove that speech was cut. This was an automated acoustic and transcript
review. Direct listening was unavailable, so the two suspected label problems
remain unconfirmed. The ten cases were selected for contrast and cannot estimate
the corpus-wide error rate. The first action is targeted review of the two
suspect boundaries. High loss alone would also discard a corroborated label.

## 5. Training exposure

A replay of the actual sampler, waveform augmentation (including LC3), frontend
and collator used the logged gen2 configuration on the corrected manifests. The
first 512 microbatches represent 128 optimizer steps at accumulation four.
They requested 927 rows and delivered 987 rows, 152.29 minutes of valid feature
frames and 24,284 reference words. The collator repeated 71 rows for its bucket
shapes and dropped 11 for bucket capacity. No row was dropped for CTC length.
This measures the current pipeline under the historical mix. Per-row exposure
was not retained in the historical run.

| Source | Configured draw % | Delivered rows % | Audio minutes | Audio % | Words % | Microbatches containing source % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ami-ihm-train | 9.6 | 8.7 | 4.6 | 3.0 | 3.2 | 9.0 |
| ami-sdm-train | 14.4 | 13.7 | 6.1 | 4.0 | 4.6 | 10.5 |
| commonvoice-en-train | 11.5 | 10.2 | 9.6 | 6.3 | 4.5 | 12.5 |
| librispeech-train-clean-100 | 7.7 | 8.8 | 18.3 | 12.0 | 12.4 | 14.5 |
| librispeech-train-clean-360-p28 | 6.7 | 7.0 | 15.5 | 10.2 | 10.9 | 11.5 |
| noise-only | 3.8 | 3.9 | 4.4 | 2.9 | 0.0 | 6.4 |
| peoples-clean-train | 14.4 | 14.8 | 34.4 | 22.6 | 23.7 | 24.6 |
| peoples-clean-train2 | 14.4 | 14.5 | 34.1 | 22.4 | 23.8 | 25.0 |
| voxpopuli-train | 9.6 | 9.7 | 12.2 | 8.0 | 8.1 | 14.8 |
| voxpopuli-train-b | 7.7 | 8.7 | 13.1 | 8.6 | 8.9 | 13.7 |

The corpus weights broadly describe draw frequency. They imply a different
distribution of seconds and words because utterance lengths differ by source
and the bucket collator repeats some examples. People's Speech supplied 45.0%
of audio and 47.5% of words. Both AMI views together supplied about 7.0% of audio.
Per-item loss normalization means audio share alone is not a gradient weight.
Track drawn and delivered item share, valid minutes, words and bucket repeats
separately before adjusting weights. Per-source evidence is under
`private/sequential-stt/05-exposure/`.

## 6. Training and runtime frontend

Sixteen fixed development clips were evaluated unmodified, at 1/64 amplitude,
and as 250 ms prefixes. Each of 48 identical PCM inputs passed through four
frontend variants. Downstream weights, quantizers and saved LM were fixed.
The current C++ inference call in quartznet_runtime.cpp explicitly disables
dither. The training frontend uses random dither, and the reference export
frontend uses a deterministic dither sequence. Earlier export sensitivity and
boundary results used the host reference. Use C++ runtime features for product
comparisons.

| Frontend | Natural errors / 161 words | Natural transcripts differing from C++ | Quiet errors / 161 | Quiet transcripts differing |
| --- | ---: | ---: | ---: | ---: |
| Training, default dither | 32 | 5/16 | 35 | 7/16 |
| Training, dither disabled | 32 | 1/16 | 34 | 1/16 |
| Actual C++, runtime dither disabled | 31 | 0/16 | 34 | 0/16 |
| Actual C++, fixed dither enabled | 31 | 8/16 | 32 | 8/16 |

Training-default versus runtime mean absolute feature differences were 0.00213
on natural, 0.01397 on quiet and 0.06475 on short audio. Disabling training
dither reduced these to approximately 0.000001 or less. Maxima on quiet/short
inputs reached 3.36/4.03 with default training dither. The 250 ms prefixes
produced identical transcripts across all arms. Complete-sentence WER would be
invalid on these truncated inputs. The small screen identifies a reproducibility
issue. A change to runtime dither would need a larger accuracy test. Private evidence is in `06-frontend/`.

## 7. Deletions by word, position, energy and decoder

A deterministic word-edit alignment was reconciled against the saved per-clip
deletion counts for all four decoders on 633 words. A reference-constrained CTC
alignment of the frozen acoustic scores provided approximate word intervals for
PCM RMS relative to the utterance. Energy and position refer to this read-speech
development set. This analysis does not locate a speaker's exact word boundaries.

| Group | Reference words | Greedy deletions | Beam only | Beam + word bonus | Deployed LM |
| --- | ---: | ---: | ---: | ---: | ---: |
| All | 633 | 4 | 3 | 2 | 11 |
| 1–3 letters | 247 | 2 | 2 | 1 | 3 |
| 4+ letters | 386 | 2 | 1 | 1 | 8 |
| Lowest relative-energy quartile | 159 | 0 | 0 | 0 | 3 |
| Other energy | 474 | 4 | 3 | 2 | 8 |
| First / middle / last | 64 / 505 / 64 | 1 / 3 / 0 | 1 / 2 / 0 | 1 / 1 / 0 | 1 / 10 / 0 |

The deployed decoder deleted one of 55 occurrences of “the,” none of 17 “a,”
none of six “to,” none of two “not” and none of two “no.” There were zero “never”
examples. The observed excess deletions appeared when language scores were
enabled, even though overall word error improved. The counts do not identify
quiet endings or short words as the main cause here. Negation coverage is too
small for an accuracy claim. Private evidence is in `07-deletions/`.

## 8. Gain, clipping, added background and microphone placement

The portable C++ frontend and fixed gen2 int8 model/LM scored the same 16
development clips (161 reference words) in every controlled condition.

| Input change | Word errors |
| --- | ---: |
| Original | 31 |
| Gain −12 dB / −30 dB | 28 / 32 |
| Gain +12 dB with saturation | 37 |
| Same clipped signal scaled back down | 39 |
| Recorded office background at 20 / 10 / 0 dB whole-clip SNR | 31 / 29 / 32 |
| Speech-only controls at the three corresponding mix levels | 31 / 31 / 31 |

Positive gain saturated 2.60% of samples. Scaling those samples back down
preserved their distortion. This panel shows a clipping penalty and little
consistent response to this particular office background. It cannot establish a
general tolerable SNR or an optimal gain. Gains were applied digitally before
int16 conversion, without a physical preamp or automatic gain control.

The real-microphone comparison covers 24 paired utterances, 14 speakers, 11
AMI validation meetings and 292 words. Each pair was independently reconciled
to the same meeting ID, speaker, begin time and end time in the original
annotation tables. Both PCM identities were screened for calibration overlap.
Headset audio scored **57 errors (19.52%)** and the single distant microphone
**110 (37.67%)**. The distant channel worsened 16 pairs, improved two and tied
six. Microphone placement, competing voices and room acoustics vary together
in this measurement. Use paired distant speech as an accuracy condition when
evaluating changes intended for meetings. Private evidence is in `08-channel/`.

## 9. Training augmentation versus archived device recordings

Three original P4 microphone speech crops passed existing waveform-alignment
gates against their playback file. Capture 4 failed and was excluded from
source-relative measurements. Each accepted source span was run through the
actual training augmenter 32 times with fixed independent seeds, using the
configured noise, babble, room impulse responses and G2 channel. These are
three physical observations from one session and 96 simulated counterparts.

| Measurement | Device (median and range) | Augmented (median and range) |
| --- | --- | --- |
| RMS level in dBFS | −50.0 (−56.9 to −47.1) | −26.1 (−39.7 to −3.8) |
| Samples at saturation | Zero in all three | Nonzero in 16/96 |
| Quiet-to-active level, dB | −14.8 (−17.0 to −12.2) | −20.9 (−56.0 to −5.0) |
| Estimated late/direct energy, dB | −19.2 (−21.8 to −16.1) | −14.0 (−41.6 to +0.5) |

Quiet frames are the quietest tenth of the aligned dry source and active
frames its loudest quarter. The quiet-to-active ratio includes residual speech,
reverberation and noise. The transfer estimate uses 15–120 ms delayed energy
relative to a ±6 ms direct window. It distinguished a known 50 ms echo from
dry audio (−11.3 vs −32.5 dB). It includes the loudspeaker and microphone
chain. A calibrated room RT60 would require a separate measurement. Duration changes are
compensated before comparing the envelopes and transfer spectra.

The largest gap was level. Even the quietest augmentation was 7.4 dB louder
than the loudest of the three device crops. The augmentation distribution
covered the measured noise/room proxies, but also generated stronger delayed
energy and clipping. RIR augmentation fired in 42/96 trials, with median
late/direct −8.2 dB compared with −20.3 dB for the other trials. Before
changing those probabilities globally, repeat this comparison in more rooms
and on more units. The controlled gain screen in #8 shows why a distribution
mismatch alone is insufficient evidence of an accuracy penalty.
Private evidence is in `09-augmentation/`.

## 10. Checkpoint selection

Three checkpoints were selected from the same gen2 LR 1e-5 training run before
scoring this development panel. They were the logged winner (step 25,397 at
500.02 training hours), runner-up (24,010 at 472.65 h), and the saved checkpoint
nearest half the winner's training hours (13,338 at 262.57 h). Their logged
broad-development scores were 16.03%, 16.14% and 17.81%, respectively. These
scores come from a different population than the fresh Common Voice panel.

Each checkpoint is compared on the same 64 clips against 633 reference words.
The four paths use the training frontend and float network, the actual C++
frontend and folded float network, the C++ frontend and frozen int8 greedy
decoder, and the latter with the saved production LM. Holding LM settings fixed
asks which checkpoint serves the existing product. Separate decoder retuning
would answer a different question. Earlier host sensitivity tests used the
export-reference frontend, so use the C++ results here for deployment comparisons.

| Training step | Training frontend, float errors | C++ frontend, float errors | Int8 greedy errors | Int8 + saved LM errors |
| ---: | ---: | ---: | ---: | ---: |
| 25,397 | **96** | **95** | 112 | 101 |
| 24,010 | 97 | 97 | **111** | **98** |
| 13,338 | 109 | 109 | 116 | 107 |

All three exports passed fixture parity, used the same ordered calibration inputs
and scored identical references and PCM. The runner-up and midpoint were
exported afresh. The historical winner still led the float paths on this panel,
but the runner-up led both deployed-precision paths. Comparing the runner-up to
the winner with the LM, seven utterances improved, five worsened and 52 had
equal error counts. The three-error net difference is −0.47 percentage points.
A 10,000-draw paired bootstrap by the 32 speakers gave a 95% interval of −1.97
to +0.98 points. Export and decode a shortlist of checkpoints before selection.
The current screen alone does not justify replacing the deployed weights.
Private evidence is in `10-checkpoints/summary.json` and `10-checkpoints/verified.json`.

## 11. Draft stability and preview work

Completed standalone P4 event captures provided the actual emitted draft text,
final caption, sequence/version and corresponding inference duration. The
primary panel uses one baseline run each of conv2, conv3 and conv4. A conv2
repeat and a long22 stress capture are recorded separately. Every emitted final
and draft event was reconciled to the capture inventory. Explicit blank events
used to clear a draft before a final (114 on the primary panel) are excluded
from the recognition revision counts. These are emitted application events. Client paint timing requires separate instrumentation.

| Primary panel | Result |
| --- | ---: |
| Final captions / finals with a preview | 119 / 116 |
| Valid draft jobs / jobs without a valid draft | 317 / 103 |
| Worker time in valid / invalid draft jobs | 243.72 / 66.64 seconds |
| Finals with a revision that withdrew a displayed suffix | 86 |
| Finals with a revision after text normalization and comparison to raw final | 83 |
| Word occurrences removed across revisions, after normalization | 206 |
| Identical-text draft passes / their worker time | 15 / 10.01 seconds |

Four valid previews had no emitted final and were excluded from final-linked
churn metrics. A suffix revision can keep words further along in the sentence.
The removed-word count therefore uses the longest common word subsequence
between updates. Comparing normalized drafts with raw final text separates
lexical changes from final presentation formatting. Twenty-three finals differed
between raw and formatted text.

Keeping alternate previews on the same recorded timelines would omit 110.04
seconds of measured preview work. It would also delay the first stable appearance
of 297 of 1,369 final words, with a 90th-percentile delay of 1.43 seconds across
all final words. This fixed-trace comparison holds all remaining publication
times constant. Actual scheduling, preemption, and caption latency after a
pacing change require a new run. Investigate why jobs become invalid before
changing the overall preview cadence. Private evidence is in `11-drafts/observed-device.json`
and `11-drafts/observed-summary.json`.

A supplementary replay used measured X2F job sizes/times from two integrated
firmware runs on conv2 and conv3. In 85 paired finals, 173 successful preview
times were eligible and 45 draft jobs were unsuccessful. Forty-nine reconstructed
phrases withdrew a suffix. Three simulated previews repeated identical text,
accounting for 2.49 seconds at the corresponding recorded job durations. Only
22 of the 85 reconstructed finals exactly matched the logged device text. The
digital playback omits the physical microphone/acoustic path. These replay
numbers are kept separate from the actual standalone event counts above.

## 12. Repeatable release benchmark

The [release benchmark](STT_RELEASE_BENCHMARK.md) compiles the portable C++
frontend, validates each model's own export fixtures, checks development PCM
and source hashes, and runs both exports on identical audio with the saved LM.
The frozen 48-case suite includes 45 speech cases and three one-minute
verified no-speech cases. It intentionally reuses some source clips across
conditions to detect sensitivity. Its overall WER is a regression-screen
statistic with those conditions weighted as listed.

| Condition | Reference words | Current int8 errors | Block-14 errors |
| --- | ---: | ---: | ---: |
| Natural read speech | 82 | 16 | 18 |
| Quiet read speech | 82 | 19 | 17 |
| Read speech with added noise at 10 dB SNR | 82 | 26 | 26 |
| AMI headset | 108 | 21 | 22 |
| AMI distant mic | 108 | 30 | 33 |
| Paired caption joins | 75 | 20 | 17 |
| Long fixture with forced cuts | 150 | 14 | 14 |
| **Speech total** | **687** | **146 (21.25%)** | **147 (21.40%)** |

Block 14 improved five cases and worsened six. Both models emitted zero words
over three minutes of silence, taps and synthetic fan noise, and neither
repeated a word across a caption join. Total deletions rose from 38 to 40.
Both lost four initial and two final words across the 49 reference groups.
Independent reruns earlier in the investigation reproduced all 32 baseline
transcripts in the natural, quiet and paired-microphone subsets of this suite.

The earlier 64-clip read-speech export screen favored block 14. This suite
uses the actual C++ frontend and a different condition mix, so the two tests
alone cannot isolate the reason for their differing rankings. Retain the current
int8 default. Treat the separate P4 RAM/latency benchmark as a measurement of
the implementation cost. A production accuracy change still needs a consistent
benefit on representative meeting audio.

Private evidence is in `12-release/suite.json` and
`12-release/block14/comparison.json`. The twelve-item audit in
`private/sequential-stt/completion-audit.json` verifies coverage and fingerprints
the source evidence. The reserve remained unscored.
