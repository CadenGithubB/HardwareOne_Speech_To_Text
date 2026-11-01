# Ten next experiments for speaker identification

These are prioritized hypotheses and decision tests, not claimed fixes. They
build on [AB_TEST_RESULTS.md](AB_TEST_RESULTS.md) through the failed deferred
confirmation experiment. The goal is better speaker labels while preserving
transcription, label coverage, latency, RAM headroom and stability. The fixed
speech-recognition model remains unchanged. No device work is part of this plan.

## What the evidence currently supports

- The first Conversation 1 run created a duplicate cluster at sequence 3; 15
  subsequent unknowns were explicitly ambiguous between the two clusters.
- Clean clip 2 versus clip 0 scored 0.606. Clean audio at the first session's
  phrase spans scored 0.5648 at sequence 3, close to the device's 0.558. Boundary
  selection is therefore a promising factor to test, not a proven universal
  cause or a measured microphone-only penalty.
- Logged same/different AUC was 0.859 for one-phrase centroids and 0.953 for
  centroids holding four or more phrases. Those groups differ in more than age;
  this association does not prove that waiting alone fixes identification.
- The two-phrase deferred variant reduced reserved-corpus split phrases per 100
  from 7.64 to 0.97 but increased merges from 1.11 to 3.47. Confirmation alone is
  insufficient under the no-increased-merge requirement.
- Conversation 4's median speaker-label lag was 22,734 ms. Extra embedding work
  needs an explicit compute/latency budget. The benchmark does not establish
  ordinary-use crash frequency.

## Ranked approaches

### 1. Audit where the audio path loses speaker separation

**Idea:** Trace the same PCM through resampling, the native C++ speaker frontend,
the Python frontend and the embedding stage. Verify crop offsets, padding,
scaling, feature normalization and sample-length handling before changing them.

**Why:** We have not isolated preprocessing, quantization and physical playback.
The window-boundary comparison changes the result on clean source audio too.
The actual C++ frontend crops PCM before feature extraction, normalizes each
mel band over the retained frames, and repeats short feature sequences. The
model's training frontend matters: removing normalization blindly changes the
input distribution and is not a validated improvement.

**Decisive test:** Use identical sample ranges and int16 PCM for native/Python
feature fixtures, including silence tails, clipping, short phrases and long
phrases. Measure feature differences, embedding cosine and same/different
separation at each supported stage. Compare quantized embeddings only through
a validated runner/fixture; the present Mac float replay is not that runner.
If full quantized replay is unavailable, identify that gap explicitly. Actual
microphone effects require matched recorded input, which current clean replay
cannot reconstruct.

**Cost/risk:** Small to medium diagnostic work. Normalization differences may be
necessary for the checkpoint; this audit could find no implementation defect.

### 2. Choose the speaker window using voiced speech

**Idea:** Select a contiguous, speech-rich, stable window inside a caption's
audio rather than always taking its center. Count voiced duration separately
from pre-roll, tail and silence. Keep caption segmentation and text unchanged.

**Why:** The current approximately three-second center window can represent a
different piece of speech as caption boundaries move. Padding contributes to
the supplied phrase length but supplies no additional speaker evidence.

**Decisive test:** Compare the current crop with one fixed, reference-free window
selector using the same model and clustering. Stratify by voiced duration and
turn boundaries; include short utterances and mixed-speaker audio. Evaluate
splits, merges, unknowns and selection failures, not only the original clip.
Use annotations only to score the selection, never to choose it in the candidate.

**Cost/risk:** Medium. Voice activity is not speaker-change detection, and voiced
frames can still include two people. Avoid joining discontiguous fragments as
though they were one continuous utterance.

### 3. Check agreement across two windows for uncertain phrases

**Idea:** For a questionable phrase only, embed two distinct speech-rich windows.
Use agreement as extra evidence; disagreement prevents a confident profile
creation or update. An already stable match keeps the ordinary one-window path.

**Why:** A single window cannot tell us whether a borderline vector represents
the person's voice reliably. Repeating short audio does not add new evidence.

**Decisive test:** Save window-level similarities privately and compare a fixed
two-window policy against one embedding on unseen speakers. Show the fraction
requiring a second inference, merge/split changes, unknowns and compute demand.
Overlapping windows must not be counted as independent confirmation.

**Cost/risk:** Medium to high. Extra inference can worsen the existing label
backlog. Very short phrases may not contain two useful windows at all.

### 4. Protect speaker profiles from poor-quality updates

**Idea:** Use quality to decide whether a phrase is allowed to modify a profile,
separately from whether it can receive a label. Keep uncertain evidence out of
the running centroid until it has stronger support.

**Why:** Production accumulates each sufficiently long unique match. Supplied
length is not voiced duration, and one wrong update can change future matches.
We have not yet established how much centroid contamination contributes.

**Decisive test:** Compare ordinary updates with a fixed quality gate based on
voiced duration, clipping and window consistency. Trace centroid movement on
failure cases and test adversarial mixed/poor audio. Maintain original labels
for a separate control so the effect of update protection is isolated.

**Cost/risk:** Small to medium after window metadata exists. Rejecting too many
updates can freeze a weak early profile and reduce coverage.

### 5. Keep a few representative examples per speaker

**Idea:** Retain two or three representative vectors and their dispersion instead
of relying on one accumulated mean alone. A new phrase should agree with a
coherent group of examples; a single high-scoring exemplar is insufficient.

**Why:** A mean hides contradictory assignments and within-speaker variation.
The failed confirmation rules lacked a rich representation of evidence for
keeping similar voices separate.

**Decisive test:** Replay a fixed small-exemplar policy with the same embeddings.
Test both same-person variation and different-person near matches. Report
merge/split changes, unknowns, update behavior, operations and bytes. For eight
speakers, three 512-float examples each occupy 49,152 bytes before metadata;
that is an estimate, not a measured P4 allocation.

**Cost/risk:** Medium. A maximum-over-exemplars rule would make false matches
easier; require a stated consensus/coherence rule and test that failure mode.

### 6. Calibrate confidence using evidence quality and competing matches

**Idea:** Estimate how trustworthy a decision is using similarity, the nearest
competitor, profile dispersion, voiced duration and amount of supporting speech.
Calibrate this on separate speakers rather than applying another global cutoff.

**Why:** The logged one-phrase and mature-centroid distributions differ, and
same/different similarities overlap. One cosine value has different evidential
strength depending on context. Quality-aware scoring is a research direction,
not a guarantee that overlapping speakers become separable.

**Decisive test:** Fit a simple, inspectable scorer on a development partition;
freeze it and evaluate calibration, false joins, false splits and abstention on
disjoint speakers. Compare against the production rule and the existing global
threshold sweeps. Do not train on final-test identities or use reference labels
at runtime.

**Cost/risk:** Medium. Requires honest calibration data and can overfit. This
changes the scoring backend, not the fixed acoustic transcription model.

### 7. Retain competing explanations and allow a later split

**Idea:** First test a whole-session refinement using the same saved embeddings;
then, only if it helps, consider a bounded live version. Preserve evidence for
both “same person” and “different people” so later context can repair a mixed
cluster as well as a duplicate. Do not automatically merge on one shared match.

**Why:** The deferred prototype kept one committed explanation after confirmation.
It could recover some duplicates but still committed to wrong-person merges.

**Decisive test:** Benchmark an unsupervised sequence-aware refinement against
the greedy rule on identical embeddings. Score whether it actually recovers
both split and merged cases before adding live complexity. A live experiment
must cap history, hypothesis count and delay in seconds and explicitly handle
label revisions; current immutable-label assumptions would need review.

**Cost/risk:** High. Whole-session results cannot be presented as live results;
new labels must not silently rewrite raw captions or saved identity history.

### 8. Establish an evaluation set with genuinely separate speakers

**Idea:** Freeze a final-test set of people and recordings absent from all rule
development. Keep corresponding clean/channel versions together. Add natural
turns and short replies rather than relying mainly on shuffled utterances.

**Why:** Our existing “reserved” even/odd dialogues can share speakers and have
already been used in prior experiments. Repeatedly fitting those cases risks
optimizing a benchmark instead of the user's ordinary conversations.

**Decisive test:** Audit speaker overlap using IDs, create disjoint development,
calibration and final-test partitions, and freeze the protocol. Use available
unused corpus speakers first; new real microphone recordings are a separate
future acquisition task if needed. Show natural-order and synthetic sensitivity
results separately, with paired intervals at a defensible recording/speaker unit.

**Cost/risk:** Small to medium using existing stores. This is an enabling task,
not an accuracy fix by itself; it should run alongside the first experiments.

### 9. Give speaker work a measured scheduling budget

**Idea:** Keep caption delivery independent of expensive speaker decisions and
schedule speaker inference around an explicit queue-age and compute budget.
Use extra windows only when worthwhile; expose expired/unknown results clearly.

**Why:** We observed long label lag and about 3.3 MB of sampled PSRAM relief with
speaker work disabled. That does not prove it caused the bench faults, but it
shows why adding inference indiscriminately is a system-level risk.

**Decisive test:** First simulate candidate inference counts and queue demand
from recorded timing, without claiming an exact device prediction. After an
offline quality candidate passes, separately measure P4 caption latency, label
latency, queue age, coverage, memory, overruns and reliability under ordinary
and instrumented conditions. Dropping work must count against coverage.

**Cost/risk:** Medium; final qualification needs separately authorized hardware
work. Scheduling can improve timeliness but cannot create missing voice identity.

### 10. Benchmark a different speaker embedding model as a fallback

**Idea:** If input fixes and better evidence use still leave substantial overlap,
compare another pretrained speaker model on the frozen audio set. Keep the
speech-to-text recognition model fixed. Treat replacement as a separate decision.

**Why:** Clean audio already exhibits overlap, especially in Conversation 3.
The current model's short-utterance representation could impose a limit that
clustering rules cannot remove; that possibility is not yet established.

**Decisive test:** Run a small offline comparison at matched false-join operating
points, on the disjoint evaluation set. Report short-utterance results, file
size, feature needs, estimated work and deployment feasibility. Only consider
porting a model that shows a meaningful advantage; desktop results and published
benchmark numbers do not establish P4 memory or runtime suitability.

**Cost/risk:** High. New weights, feature contracts and quantization need their
own validation; no model has been selected, downloaded or replaced by this plan.

## Recommended execution order and acceptance

Start with 1 and 2; build the disjoint evaluation protocol in 8 in parallel with
that diagnostic work. Then test 4, followed by a selective version of 3. Test 5
and 6 only against the frozen evaluation protocol. Use 7 as an offline ceiling
experiment if the streaming approaches still fail. Do 9 before deploying any
extra-inference candidate. Keep 10 as a fallback after the current model's input
path has been checked.

Change one component per comparison. Preserve a production control, report
coverage alongside accuracy, and count wrong-person merges separately from
duplicate-speaker splits. Keep the existing no-increased-merge gate and report
paired confidence intervals; a statistically inconclusive merge increase is
not proof of non-regression. A candidate also needs explicit wall-clock label
delay, transcription-latency, memory and reliability results before deployment.
No current candidate has passed these requirements.

## Primary-source context

These sources motivate possible experiments; none validates the proposed changes
on this device or the current recordings.

- [Current model's upstream implementation](https://github.com/clovaai/voxceleb_trainer)
  provides provenance and an evaluation reference for the existing speaker model.
- [Quality Measures for Speaker Verification with Short Utterances](https://arxiv.org/abs/1901.10345)
  studies quality information for short-utterance verification, using different
  models/data; it is motivation for testing idea 6, not evidence of a P4 gain.
- [VBx author implementation](https://github.com/BUTSpeechFIT/VBx) describes an
  embedding/clustering/sequence-refinement pipeline. It is an offline reference
  for idea 7, not a proposed drop-in P4 implementation.
- [ERes2NetV2 paper](https://arxiv.org/abs/2406.02167) studies short-duration
  speaker embeddings and computational tradeoffs; it motivates checking the
  model ceiling in idea 10, without claiming hardware suitability.

## First standalone round status

The [audio-path/window experiment](SPEAKER_AUDIO_EXPERIMENT.md) implements the
CPU frontend audit and two fixed energy-based selectors. Native/Python parity
is close on audited speech; full device quantization parity remains open.
Neither selector passes development validation, so the newly frozen final
speaker partition remains unscored and HardwareOne integration has not begun.
No other roadmap approach is claimed complete by this experiment.


## Target-path and exact-input checkpoint

The following [P4 diagnostic round](SPEAKER_P4_PARITY.md) measured five fixed
inputs across 25 reboots and captured four exact microphone inputs. Results are
in AB_TEST_RESULTS.md: target numerical differences can flip a borderline match,
and microphone-channel changes do not uniformly reduce same-speaker similarity.
The replay now respects retained speaker sample counts. Actual failure-case PCM
and broader target evaluation remain gaps; timestamp projections alone cannot
establish a bad cut. The [overnight queue](SPEAKER_OVERNIGHT_PLAN.md) adds code-only
correctness/performance work with unchanged models/settings/clocks. No selector
or speaker rule is qualified by these diagnostics.
