# Overlap gate plan · 5 November 2026

Status: plan only. No code, model, default or firmware change has been made. Host-only until the
P4 gates in section 8 are reached. This plan follows the closed loss round three
([STT_LOSS_ROUND3_MAIN_REVIEW.md](STT_LOSS_ROUND3_MAIN_REVIEW.md)).

## 1. Why a gate, not another separator

Every two-output model tried so far (seven round-one arms, round two, round three) fails the same
way first: it splits one speaker into two streams and transcribes both. In round three both
selected models emitted text on both outputs in 64/64 ordinary and 64/64 quiet single-speaker
cases, and ordinary errors rose from 170 to about 1,600 on the same 1,461 words. The overlap
errors were never the deciding failure; the collateral damage on single-speaker speech was.

Nothing in the pipeline decides whether a segment contains overlap. A separator therefore runs on
all audio and pays the duplication cost on the large majority that has one voice.

An overlap gate is a small classifier that answers one question per segment: do two or more
people speak at the same time here? With it:

- The unchanged single-speaker path runs on every segment, so its accuracy is protected by
  construction, not by a training objective.
- Any future two-stream model runs only on flagged segments and is evaluated only there.
- Even with no two-stream model, a reliable flag is product value: the caption can carry an
  "overlap" marker where words are known to be missing.
- It fits the memory that actually exists. Integrated captures show about 1.5–2.6 MiB of free
  PSRAM; the round-three separator's decoder tensor alone needed 6.14 MB.

## 2. What the gate outputs and where it plugs in

Per recognizer segment (`StreamWork` with retained PCM, `stt_stream.h:41-52`): a frame-level
overlap posterior at the recognizer's 10 ms feature hop, reduced to an overlapped-frame fraction
and a boolean flag at a frozen threshold. Phase one is **flag only**: raw caption text is
untouched, and the flag travels as metadata beside the existing per-sequence speaker event
(`product::speaker`, `examples/p4_eye_captions/main/product.cpp:315-322`), not inside the
caption. This matches the standing rule that raw captions are preserved and formatting is a
separate presentation.

Routing (phase two, only after a two-stream model exists and the gate passes): on a flagged
segment the same retained PCM is passed to the second path *after* the baseline caption is
emitted. The baseline caption is never replaced; the second path adds the other speaker's words.
Scoring counts both streams on flagged segments and the baseline alone elsewhere.

## 3. Signals already computed per segment

From a read-only audit of `firmware/components/hw1_stt/stt/` (file:line references are to that
directory unless noted):

| Signal | Where | Cost to read | Caveat |
|---|---|---|---|
| Int8 CTC logits [frames × 29], blank = class 28, half frame rate | `Decoder::decode` hook, `quartznet_runtime.h:49-54`, `.cpp:585-587` | Zero extra inference | Hook already exists; blank probability and entropy per frame are a few arithmetic ops |
| 64-bin log-mel features, 160-sample hop | `quartznet_frontend.h:5,15,29-42` | Already computed during capture | Natural input for a dedicated small classifier |
| Speaker trunk frame vectors T′×C and SAP attention weights | `speaker_model.h:93-95`, `.cpp:173-202` | Already computed when the speaker job runs | Private members; needs an accessor. Runs only after a Final, on core 1, 0.9–6.9 s later |
| Clusterer `Assignment.matches > 1` (Ambiguous) | `speaker_cluster.h:47-61,101-114` | Free | Phrase-level only, and only once profiles exist |
| 10 ms RMS, noise, threshold and peak | `stt_segmenter.h:100-103,262-288`; `StreamPipeline::level()/noise()` | Free | Energy alone cannot distinguish two voices from one louder voice |

## 4. Three gate candidates

Ordered by cost. All are scored on the same frozen panels (section 6) so they can be compared.

**G0 · heuristic floor.** Per-frame logit entropy and non-blank density from the decode hook,
plus segmenter energy statistics. No model, no new memory. Expected to be weak; it sets the floor
that any learned gate must beat, and it can run on the P4 immediately.

**G1 · speaker-trunk dispersion.** Within-segment dispersion of the existing speaker frame
vectors (for example the second eigenvalue share of their covariance, or a two-centroid
separation score weighted by SAP attention). No new weights. Needs one accessor on
`SpeakerModel`, no change to the speaker algorithm or its output. Arrives with the speaker
label, so it suits a metadata flag but is too late to route a second pass before the caption.

**G2 · dedicated classifier.** A small network on the 64-bin log-mel features: target under
50,000 int8 parameters, weights under 100 KB, arena under 512 KB including activations for a
20 s segment (64 × 2,000 frames = 128 KB int8 input). Produces a per-frame posterior for
{no speech, one speaker, two or more}. This is the standard overlap-detection formulation used by
diarization systems and is the only candidate expected to be strong. It needs training (section 5).

G1 and G2 are not exclusive. If G2 is adopted, G1 remains a cheap cross-check on finals.

## 5. Training data: the part separation never had

Separation needs clean individual sources; real rooms never provide them, which is why synthetic
success did not transfer. Overlap detection needs only **who spoke when**, and the AMI corpus
already on disk has it.

- `/Volumes/Audiodrive/stt/ami/{sdm,ihm}/*.parquet` carry `meeting_id`, `speaker_id`,
  `begin_time`, `end_time`, `text` and audio for every utterance. The overlap-investigation
  audit (`private/training-track/overlap-investigation/audit.py`) already reads these columns.
- Local stores: ami-sdm-train 74.7 h / 155 speakers, ami-ihm-train 75.6 h, validation 8.7 h /
  21 speakers, test 8.4 h / 16 speakers. The single distant microphone (sdm) matches the P4 and
  G2 far-field condition; headsets (ihm) give a matched clean view of the same moments.
- Frame labels follow from overlaying each meeting's utterance intervals: count of active
  speakers per 10 ms frame. This is real overlap, real rooms, real loudness ratios, at scale.

Rules carried over from the earlier work:

- Fit on AMI train meetings only. Select on AMI validation. Test once on AMI test. Verify meeting
  and speaker disjointness in phase zero rather than assuming the corpus split.
- The 24 distant overlap clips, the 32 real pairs and the 163-case saved panel stay out of
  fitting and selection. They are reporting panels.
- AMI timing comes from forced alignment; exclude a ±200 ms collar around every speaker
  boundary from training loss and from frame scoring, as diarization scoring does.
- Synthetic two-speaker mixtures from the existing round-two manifest builder may be added for
  controlled loudness ratios and the −12…+12 dB range, but the selection metric is real AMI.
- Record training exposure: the recognizer was trained on AMI train. The gate is a separate
  model, so that is acceptable for the gate, but any downstream caption score on AMI test must
  carry the same exposure note the earlier reports carry.

## 6. Evaluation

**Frame level** (AMI validation/test, real32, 24 overlap clips): miss rate and false-alarm rate
with the 200 ms collar, and area under the miss/false-alarm curve.

**Segment level** (what routing actually uses): for each existing scored segment, flagged or
not, against the label "any overlapped frame outside the collar". Report precision and recall at
the operating point chosen on AMI validation **before** test panels are scored.

**Operating point.** A false alarm is the expensive error: it triggers the duplicating path on
single-speaker speech. Choose the threshold on validation at a fixed false-alarm ceiling and
report the recall it buys, rather than maximizing a combined score. The ceiling is set in phase
zero and frozen in `experiment.json` before any panel is scored.

**Panels, all existing, no new capture:**

| Panel | Role | Source |
|---|---|---|
| 155 single-speaker and noise cases of the saved 163-case panel (P4, G2, release, LibriSpeech ordinary/quiet/loud, background) | Negatives; must stay unflagged | `private/stt-loss-round3-review/baseline.json` |
| 8 overlap cases of the same panel | Positives | same |
| 32 real pairs, distant and headset streams; median window 6.0 s, overlapped span 0.11–3.72 s, median 1.15 s | Positives with exact per-speaker intervals | `private/training-track/compact16k-loss-round3/real-pairs.json` |
| 24 distant AMI overlap clips with competitor intervals | Positives, 1–3 competitors | `private/training-track/overlap-investigation/annotation-audit.json` |
| 323-case synthetic qualification panel | Known geometry, both classes | round-three `eval-suite.json` |
| AMI test, 8.4 h | Only large fresh held-out test | stores + Parquet |
| Two continuous recordings (G2, P4) | Segment-level behaviour across caption joins | `baseline.json` continuous |

**Downstream proof without training anything.** Every panel case already has frozen baseline
and round-three B1024 outputs. Recombine them per case by gate decision: baseline where the gate
says one speaker, B1024 where it says overlap. Score with the unchanged speaker-attributed
scorer. Do this first with an **oracle gate** from the labels: that is the best any gate could
deliver with the existing separator. If oracle-gated B1024 still loses to baseline on the overlap
cases (round three had B 83 versus baseline 66 errors there), the separator remains the limit and
the gate's value is confined to removing collateral damage and to the flag. Either way this is
the upper bound and it costs no inference.

## 7. Phases

| Phase | Work | Done when |
|---|---|---|
| 0 · labels and protocol | Derive frame labels from Parquet for train/validation/test; reconcile against real32 utterance intervals and the 24-clip audit; verify split disjointness; freeze panels, collar, false-alarm ceiling and selection rule in `experiment.json`; scorer passes constructed swap/empty/boundary cases | Labels and protocol frozen; scorer checks pass |
| 1 · floor and oracle | G0 heuristics on all panels; oracle-gated recombination of baseline and B1024 | Floor and upper bound reported |
| 2 · G1 | Host harness exposes speaker frame vectors (existing `tests/stt_speaker_cluster_harness.cpp` and `spkaudioaudit.py` paths); dispersion statistics scored on panels | G1 compared with G0 at the frozen operating point |
| 3 · G2 | Train the small classifier on AMI train (+ optional synthetic), select on validation, test once; export int8 through the existing ESP-DL exporter; fixture reload and static memory screen as in round two | Test-panel result, verified export, static peak under 512 KB |
| 4 · P4 flag-only | Integrate behind a compile-time flag, skipped when the caption reserve is short like the speaker job; measure simultaneous peak PSRAM/internal RAM, per-segment latency, no caption text change | Section 8 gates measured on the board |

Phases 1 and 2 need no training and can start as soon as phase 0 freezes the protocol.

## 8. Gates for adopting the flag

- False alarms on the 155 single-speaker/noise cases at or below the frozen ceiling, and zero
  flags on the three verified no-speech fixtures.
- Recall on real32 and the 24 overlap clips reported at that operating point; no threshold
  changes after test scoring.
- Raw caption text byte-identical with the gate on and off, on the release benchmark.
- Measured simultaneous total-application peak within 30,000,000 bytes with the gate loaded,
  PSRAM and internal RAM reported separately.
- No regression in caption latency on the 16-phrase device profile beyond the measured gate cost.
- Partition table inspected and a private rollback image preserved before any flash, as always.

## 9. What this does not do

It recovers none of the second speaker's words. It does not change the 21% release-suite or 38%
distant-microphone baseline WER. Quiet speech the energy detector rejects before recognition
(`stt_segmenter.h:15`) is still rejected; the quiet caption cells at 73/73 errors for every model
are a detector question, not a gate question. The gate's job is narrower: make the single-speaker
path safe to keep, make overlap visible, and make any future two-stream model testable only where
it matters.

## 11. Phase zero complete · labels and protocol frozen (5 November 2026)

Code: `tools/overlap_gate/{labels,scorer,reconcile,freeze}.py`; checks in `tests/test_overlap_gate.py`
(16 constructed cases: same-speaker merge, two-speaker spans, count cap, collar geometry, run
encoding, collar-excluded errors, inverted and silent gates, ROC bounds, segment label minimum,
swapped and empty flags, ceiling-respecting and tie-conservative threshold selection). Run them
with `private/layer-sensitivity-20261103/export-venv/bin/python -m unittest tests.test_overlap_gate`;
the system `python3` lacks NumPy.

**Labels** (`private/training-track/overlap-gate/labels-{train,validation,test}.json`), derived
from AMI Parquet speaker intervals only, no audio read. Per utterance window: active-speaker count
per 10 ms frame (cap 3) and a ±200 ms boundary collar, run-length encoded, plus the matched local
store index where the (speaker, normalized text, length ± 35 ms) match is unique.

| Split | Utterances | Meetings | Speakers | Hours | Frames outside collar: one / two-plus | Windows with overlap | Store match unique / ambiguous / none |
|---|---:|---:|---:|---:|---|---:|---|
| train | 107,319 | 135 | 155 | 77.1 | 81.6% / 18.4% | 50,007 | 79,024 / 6,531 / 21,764 |
| validation | 13,098 | 18 | 21 | 9.0 | 80.6% / 19.4% | 6,188 | 9,998 / 768 / 2,332 |
| test | 12,643 | 16 | 16 | 8.7 | 79.3% / 20.7% | 5,865 | 8,994 / 954 / 2,695 |

About 20% of all frames fall in the collar. No frame has zero speakers because each window is one
speaker's own utterance; silence and noise negatives come from the DEMAND/MUSAN stores and the
no-speech fixtures, as recorded in `experiment.json`. Headset and distant metadata are identical
for validation and test. Train headset metadata has 1,183 extra rows, all from meetings IS1003b
and IS1007d, which have no distant rows at all; they are not labelled.

**Reconciliation** (`reconcile.json`, all passed): every frozen record reproduces from freshly
read metadata (train, validation, test); all 32 real pairs match their annotation overlap length
within 21 ms, the overlapped region is labelled exactly two speakers and the rest of the window
exactly one, with no third speaker anywhere; all 24 distant clips reproduce the audit's competitor
list and overlap fraction within 0.02; no meeting is shared between splits. Two speakers (FIE038,
MIO036) appear in both AMI train and validation; their own-utterance windows are excluded from the
fitting set, and that exclusion is frozen.

**Frozen protocol** (`experiment.json`, SHA `4f9c8837…`): hop 10 ms, collar 200 ms, frame
threshold 0.5, a segment is overlapped when at least 10 valid frames have two or more speakers,
segment score is the fraction of valid frames at or above the frame threshold. **False-alarm
ceiling 2%** of single-speaker/noise segments. Threshold is chosen once on AMI validation by
`select_threshold` (highest recall under the ceiling, ties to the higher threshold) and never
changed after test scoring. Panels, frozen round-three outputs for the oracle recombination, label
files and this code are pinned by SHA-256. G2 budget: 50,000 parameters, 100,000 weight bytes,
524,288 arena bytes.

Phase one (G0 heuristics and the oracle-gated recombination) can start without training.

## 12. Phase one · oracle ceiling and the G0 floor (5 November 2026)

### Oracle-gated recombination: what a perfect gate buys with the existing separators

`tools/overlap_gate/oracle_recombine.py` reads the pinned round-three outputs (hash-checked
against `experiment.json`) and, per case, takes the candidate's result where the label says
overlap and the baseline's everywhere else. Counts are oracle source-assigned word errors
(acoustic lower bound) for the synthetic and real32 partitions, and the audit counts for the
saved-microphone panel. Result file: `private/training-track/overlap-gate/phase1/oracle-recombination.json`.

| Panel (view) | Baseline | B1024 alone | Oracle-gated B1024 | Excess removed by gate | Excess remaining |
|---|---:|---:|---:|---:|---:|
| Fresh synthetic qualification, 323 cases (oracle words) | 7,165 | 11,704 | 8,892 | 2,812 (62%) | **+1,727** |
| Real32 regression (oracle words) | 594 | 635 | 635 | 0 (all cases are overlap) | **+41** |
| Saved microphone, whole windows | 146 | 219 | 146 | 73 (100%) | 0 |
| Saved microphone, captions, 2,168 words | 609 | 2,000 | 626 | 1,374 (99%) | **+17** |

A4096 behaves the same way (qualification 8,696 gated versus 7,165 baseline; real32 717 versus
594; captions 651 versus 609).

Two conclusions, both firm:

1. **Most of the round-three damage was collateral.** On the saved microphone panel a perfect gate
   removes 99% of B1024's excess errors, because only 8 of 163 cases contain overlap. On the
   fresh synthetic panel it removes 62%. The gate idea does what it was meant to do.
2. **The existing separators lose to the baseline on overlap itself.** On overlapped audio alone,
   B1024 scores 8,544 against the baseline's 6,817 (synthetic two-speaker), 635 against 594
   (real32) and 83 against 66 (saved overlap clips). No gate can turn that into a gain. The
   remaining excess in the table is exactly that deficit. A two-stream model only becomes worth
   routing to when it beats the plain recognizer on overlapped segments, which none has.

So the gate's value today is protection and visibility, not word recovery; and the acceptance
bar for any future second path is now concrete: beat the baseline on the labelled-overlap cases
of these same panels.

### G0 heuristic floor: the recognizer's own uncertainty is not a usable gate

`tools/overlap_gate/g0_extract.py` computes two frame scores from the deployed recognizer's int8
CTC logits, with no model and no new memory: normalized posterior entropy, and one minus the
blank probability. The 598 synthetic/real32 cases reuse round three's cached mixture logits; the
163 saved-microphone cases and a seeded 2,000-utterance subsample of AMI validation (seed
20261105, of 9,998 store-matched windows; the full set would take about 4.5 h at the host's
0.5× real-time) were transcribed with the identical frozen frontend binary and export. Audio over
20 s is processed in 20 s pieces, as the production segmenter would cut it. `g0_score.py` applies
the frozen protocol. Results: `private/training-track/overlap-gate/phase1/g0-results.json`.

| Frame-level, outside collar | Synthetic qualification | Real32 | Saved microphone | AMI validation |
|---|---:|---:|---:|---:|
| Entropy ROC area | 0.79 | 0.60 | 0.80 | 0.72 |
| Non-blank ROC area | 0.49 | 0.46 | 0.69 | 0.50 |

At the frozen operating point (segment threshold chosen on the validation subsample at the 2%
false-alarm ceiling): entropy threshold 0.135 gives **3.1% recall** on validation (997 overlapped
of 2,000 windows), 0 of 224 synthetic two-speaker cases, 0 of 25 real32 cases and 0 of 7 saved
overlap clips. Non-blank: 2.4% recall. Both pass the adoption gate only because they flag almost
nothing. As a threshold-free diagnostic outside the protocol, mean entropy separates overlapped
from single-speaker *segments* with ROC area 0.90 on the synthetic and saved-microphone panels
but only 0.70 on real AMI meetings, which are the audio that matters.

Conclusion: there is weak overlap information in the recognizer's output uncertainty, far below
what a 2% false-alarm ceiling needs. A learned gate is required. G0 stays as the floor every
later candidate must beat, and the cached logits remain available as an input feature for G2.

Two protocol consequences surfaced by the scoring and worth knowing: with a ±200 ms collar and a
10-frame minimum, 7 of the 32 real pairs (overlaps of roughly 0.1–0.5 s) and 1 of the 8 saved
overlap clips are not segment positives. Very short overlaps are therefore outside what the gate
is asked to detect; the frame-level metrics still include them.

Phase two (G1, speaker-trunk dispersion) and phase three (G2) are next. Given G0's weakness on
real meetings, G2 is the one expected to matter.

## 13. Phase two · G1 speaker-trunk dispersion is weaker than G0 (6 November 2026)

`tools/overlap_gate/g1_extract.py` runs the frozen speaker trunk (the same native graph and
arithmetic hooks round three used; 75 frame vectors × 128 channels per 2.99 s window, plus the
SAP attention weights) on sliding 2.99 s windows with a 1 s hop, and computes four dispersion
statistics on the L2-normalized frame vectors: second-eigenvalue share, mean pairwise cosine
distance, a two-means split score and attention entropy. The only fitted quantity is a
five-parameter logistic calibration, fitted on a seeded 1,500-utterance AMI *train* subsample
(3,536 windows, excluding the two train/validation speakers), then applied per frame. All
constants were written to `phase2/g1/g1-protocol.json` before any panel was scored. The whole
extraction took under seven minutes; the trunk costs 0.05 s per window on the host.

| ROC area, frames outside collar | Synthetic qualification | Real32 | Saved microphone | AMI validation |
|---|---:|---:|---:|---:|
| Calibrated G1 posterior | 0.67 | 0.46 | 0.74 | **0.63** |
| Best raw statistic (mean pairwise cosine distance) | 0.91 | 0.71 | 0.81 | 0.62 |
| G0 entropy, for comparison | 0.79 | 0.60 | 0.80 | 0.72 |

The calibrated posterior never reaches 0.5 on any frame, so under the frozen protocol every
segment fraction is zero, the validation selection returns "never flag", and recall is 0% on
every panel. The threshold-free bound is what matters: the best single statistic separates
overlapped from single-speaker frames on real AMI validation with ROC area 0.62. No calibration
of these four numbers can beat that, so G1 is not a usable gate on real meetings and is weaker
than G0 there (0.62–0.63 against 0.72).

One finding worth keeping: the pairwise-distance statistic separates *synthetic* two-speaker
mixtures very well (0.91) and real overlap poorly (0.62). The speaker trunk sees real-room
overlap as ordinary single-speaker variation (distance, reverberation, level), the same
synthetic-to-real gap that undid the separators. Any G2 selection has to be made on real AMI, as
the protocol already requires; synthetic separability means little.

Results: `private/training-track/overlap-gate/phase2/g1-results.json`. Both heuristic floors are
now measured. Phase three, the trained G2 classifier, is the remaining candidate.

## 14. Phase three · G2 is a real gate on meetings, and over-flags unfamiliar clean speech (6 November 2026)

**What was trained.** `tools/overlap_gate/g2_common.py`, `g2_train.py`: a 23,811-parameter
classifier on the production 64-bin log-mel (pre-normalization, dither off), six convolution
layers, about 0.9 s of context, three classes per 20 ms frame. Fitted on 76,332 AMI train
utterances (72.5 h, distant and headset audio, two train/validation speakers excluded) plus
DEMAND/MUSAN noise and digital silence as class 0. 12,000 steps, batch 64, Adam with cosine
decay, seed 1; protocol frozen in `phase3/g2-protocol.json` before the first step. The first
attempt was seek-bound reading audio over USB and crashed on a crop-length bug before any
checkpoint; features were then precomputed once per store to local files and the run restarted
(`phase3/implementation-notes.json`; model, data definition, labels and augmentations
unchanged). Validation frame ROC area rose from 0.764 at step 1,000 to 0.852 and plateaued;
the frozen rule selected step 11,000 (0.8517). Training took 27 minutes single-threaded.

**Frozen-protocol results** (`phase3/g2-results.json`). The segment threshold, 0.373, was chosen
once on the validation subsample at the 2% false-alarm ceiling. AMI test was scored once.

| Panel | Frame ROC area | Segment recall | Segment false alarms | Precision |
|---|---:|---:|---:|---:|
| AMI validation subsample (2,000 windows, 997 overlapped) | 0.852 | 27.1% | 1.99% | 93.1% |
| **AMI test, scored once (8,994 windows, 4,328 overlapped)** | **0.852** | **28.6%** | **2.14%** | **92.5%** |
| Saved microphone (163 cases, 7 overlapped) | 0.813 | 3 of 7 | 11 of 156 (7.1%) | 21% |
| Synthetic qualification (two-speaker 192, single 128) | 0.866 | 108 of 128 | 34 of 128 | — |
| Real32 regression | 0.843 | 2 of 25 | 0 of 7 | — |

For comparison, G0 reached 3.1% recall and G1 0% at the same ceiling. On real meetings G2 is a
working gate: it flags about 28% of overlapped segments with 2% false alarms and 92% precision,
and the held-out test matches validation, so it generalizes to unseen meetings and speakers.
Diagnostic threshold-free segment ROC area is 0.82 on test.

**The adoption gate fails, and the reason is specific.** 11 of 155 single-speaker
saved-microphone cases were flagged, against a ceiling of 3. All 11 are clean read speech from
corpora G2 never saw as "one speaker": four Common Voice clips with added office noise and three
LibriSpeech speakers (570, 1415, 480) in each of their ordinary/loud/quiet variants. The 32
device recordings (P4 and G2 glasses) and the 16 AMI release clips produced zero false alarms;
so did the three no-speech fixtures and all six background recordings. The synthetic panel shows
the same pattern: 29 of 64 VoxPopuli "ordinary" clips flagged. G2 learned "AMI single speaker"
rather than "single speaker", because every speech window in training came from AMI. Real32
recall is low (2 of 25) because those overlaps are short (median 1.15 s) relative to the
segment-fraction scoring, not because frames are missed (frame ROC area 0.84).

**Export** (`tools/overlap_gate/g2_export.py`, `phase3/export-int8/status.json`): BatchNorm
folded; the fixed input normalization kept as an exact depthwise 1×1 layer because folding it
into the zero-padded stem changes the first and last two output frames; ESP-DL W8A8 for esp32p4;
calibration from 32 training windows only. Artifact 55,776 bytes, 9 Conv + 3 Add + 3 ReLU + 1
requantize. Embedded fixture reproduced byte-exactly through a clean native reload (tensors are
stored channel-last). Lengths 200 to 2,000 frames verified. Static named-activation peak 25,600
bytes at 2 s, about 256 KB at the 20 s segment maximum, within the 512 KB budget. Int8 versus
float on the validation subsample: ROC area 0.8498 versus 0.8517. Frontend parity: C++ normalized
features equal Python to under 1e-5 and per-bin means to under 1e-6 on five clips, so the device
raw log-mel rows are the trained input. These are host checks, not P4 timing or integrated
memory measurements.

**Where this leaves phase three.** G2 passes every host requirement except one, and that one
has a diagnosed cause. The fix is a declared second training variant, G2b, identical except that
single-speaker speech from the other training stores (LibriSpeech train-clean-100, VoxPopuli,
Common Voice, People's Speech), with and without added DEMAND noise, joins the class-1 examples;
selection unchanged on AMI validation plus a development negative set drawn from those corpora's
dev stores, never from the saved-microphone panel; AMI test and the saved panel scored once.
Until then G2 v1 stands as the first candidate to clear the real-meeting bar, and no flag is
adopted.

## 15. Phase 3b · G2b passes the saved-panel gate, exposes a domain shortcut (6 November 2026)

G2b is G2 with one change to the data mix, frozen in `phase3b/g2b-protocol.json` before
training: 30% of speech windows come from four non-AMI single-speaker stores (LibriSpeech
train-clean-100, VoxPopuli, Common Voice, People's Speech; 15 h seeded subset each, VoxPopuli
speakers shared with its validation store excluded), half of them with DEMAND/MUSAN noise added
in the log-mel power domain at 0–20 dB SNR. The threshold-selection set gained 364 seeded
single-speaker windows from those corpora's dev stores. Model, loss, optimizer, steps and seed are
unchanged. Features now live on the Audiodrive (`/Volumes/Audiodrive/stt/overlap-gate/features`,
linked from `phase3/features`); random feature reads from there cost 0.05–0.1 s per batch, so
training speed was unaffected. Selected checkpoint: step 10,000.

| Panel | G2 | G2b |
|---|---|---|
| Saved microphone: single-speaker clips flagged (ceiling 3 of 155) | 11 | **0** |
| Saved microphone: no-speech and background flags | 0 | 0 |
| Saved microphone: overlap clips caught (of 7) | 3 | 2 |
| AMI test, frame ROC area | 0.852 | 0.830 |
| AMI test at the selected threshold: recall / false alarms / precision | 28.6% / 2.1% / 92.5% | 35.3% / **3.6%** / 90.0% |
| Synthetic two-speaker mixtures caught (of 128 qualification) | 108 | **0** |
| Real32 regression, frame ROC area | 0.84 | 0.84 |
| Int8 export | 55,776 B, byte-exact | 56,112 B, byte-exact, ROC −0.001 |

Three conclusions.

1. **The adoption gate passes.** Non-AMI clean speech no longer triggers the flag, with no cost
   on device recordings, AMI clips, noise or silence. This was the stated purpose of G2b.
2. **The G2b selection rule was a design error, now understood.** The 364 non-AMI dev negatives
   are trivially easy (none flagged at any useful threshold), so pooling them diluted the
   false-alarm estimate and the rule picked a lower threshold (0.236 against G2's 0.373). On real
   meetings that threshold gives 3.6% false alarms, above the ceiling. Had the ceiling been
   applied to AMI validation negatives alone, the threshold would be 0.317 and AMI test would give
   30.0% recall at 2.7% false alarms. That is a post-hoc reference, not a substitution; the
   frozen result stands. Any further variant applies the ceiling to real-meeting negatives only
   and reports other-corpus false alarms separately.
3. **G2b learned a domain shortcut.** It detects zero of 128 clean synthetic two-speaker
   mixtures while still detecting real overlap (real32 and saved panel unchanged). The non-AMI
   examples taught it that clean read speech is one speaker regardless of how many voices are
   present, because every non-AMI window it saw had one. The fix is to give it non-AMI
   *two-speaker* positives too, so corpus and voice count are decorrelated: log-domain mixtures of
   two single-speaker windows from the same stores at random offsets and −12…+12 dB relative
   level, labelled by overlaying the two spans. Cheap, needs no waveform mixing, and removes the
   only cue that currently separates the corpora.

Nothing is adopted yet: G2 v1 fails the saved panel, G2b exceeds the real-meeting ceiling at its
frozen threshold and has the shortcut above. Evidence: `phase3b/g2-results.json`,
`phase3b/export-int8/status.json`, `phase3b/history.json`.

## 16. Phase 3c · G2c passes every host gate but one, and is the candidate (6 November 2026)

G2c (`phase3c/g2c-protocol.json`, frozen before training) keeps G2b's non-AMI single-speaker
windows and adds an equal share of non-AMI *two-speaker* positives: two different items from the
same stores, the second shifted by a random onset and scaled −12…+12 dB, combined in the log-mel
power domain, counts from the overlay of the two spans. Corpus therefore no longer predicts voice
count. The false-alarm ceiling is applied to AMI validation negatives only; the 364 non-AMI dev
windows are scored at that threshold and reported separately. Model, loss, optimizer, steps and
seed unchanged. Selected checkpoint: step 11,000. All three variants scored their test sets once.

| | G2 | G2b | **G2c** |
|---|---:|---:|---:|
| Saved microphone: single-speaker clips flagged (ceiling 3 of 155) | 11 | 0 | **0** |
| Saved microphone: overlap clips caught (of 7) | 3 | 2 | **3** |
| No-speech fixtures and background flagged | 0 | 0 | 0 |
| AMI validation (selection): recall at ≤2% false alarms | 27.1% | 36.7%* | 34.3% |
| AMI test, frame ROC area | 0.852 | 0.830 | 0.838 |
| AMI test: recall / false alarms / precision | 28.6% / 2.1% / 92.5% | 35.3% / 3.6% / 90.0% | **33.2% / 2.7% / 91.8%** |
| Synthetic two-speaker caught (of 128) / single flagged (of 128) | 108 / 34 | 0 / 0 | **30 / 0** |
| Synthetic qualification, frame ROC area | 0.87 | 0.38 | **0.92** |
| Real32 overlaps caught (of 25) / false alarms (of 7) | 2 / 0 | 5 / 0 | **6 / 0** |
| Non-AMI dev single-speaker windows flagged (of 364) | — | 0 (pooled into selection) | 13 (3.6%, reported) |
| Int8 export | 55,776 B | 56,112 B | **56,096 B**, byte-exact, ROC −0.002 |

\* G2b's validation figure pooled easy non-AMI negatives into the ceiling, which is why its test
false alarms were 3.6%.

**Reading.** G2c is the first variant that passes the saved-microphone adoption gate *and*
detects overlap regardless of corpus: zero false alarms on all 155 single-speaker clips, all
noise and all silence; synthetic two-speaker detection restored with zero synthetic single-speaker
false alarms (G2 had 34); the best real32 recall so far. On real meetings it sits between G2 and
G2b: frame ROC area 0.838, a third of overlapped segments flagged, 92% precision.

**The one gate it does not meet cleanly** is the 2% false-alarm ceiling *on test*: 2.74%
(128 of 4,666 single-speaker windows) against 1.99% on validation. The validation subsample has
1,003 negatives, so a 2% rate carries about ±0.9 points of sampling noise; G2 showed the same gap
in the other direction (2.1%). The ceiling is a validation-set constraint and was met; the test
figure is the honest generalization estimate and is reported as such. Raising the threshold
after seeing test would be tuning on test and is not done.

**Recommendation.** Carry G2c into phase four as the flag-only candidate: compile-time flag,
reading the frontend's raw log-mel rows, emitting an overlap flag beside the speaker event,
captions unchanged. Phase four is host-to-device work and needs the board: measured simultaneous
PSRAM/internal RAM peak with the 56 KB model and its arena loaded, per-segment latency, numerical
parity of the device's int8 output against `phase3c/export-int8/g2.espdl` fixtures, and the
partition inspection and rollback image the handoff requires before any flash. If a tighter
real-meeting false-alarm figure is wanted first, the declared route is a larger validation
subsample (the full 9 h of AMI validation features are already on the Audiodrive), not a
threshold change.

Evidence: `phase3c/g2-results.json`, `phase3c/export-int8/status.json`, `phase3c/history.json`,
`phase3c/g2/test-scored-once.json`.

## 17. Phase four plan

The flag-only device integration of G2c is planned in
[STT_OVERLAP_GATE_PHASE4_PLAN.md](STT_OVERLAP_GATE_PHASE4_PLAN.md): the device rule (200-frame
chunks, no collar, threshold 0.2451), the speaker-model integration pattern it copies, a host
step that re-scores G2c under the device rule before any board work, the handoff's partition,
rollback and app-only flash procedure, the replay parity and memory measurements, and the gates.

## 10. Constraints kept

Fixed recognizer, speaker model, clusterer threshold 0.6 and production defaults unchanged.
Host-only until phase 4; no board, serial, flash, capture, playback or Bluetooth work. Audio,
labels, checkpoints and exports stay under ignored `private/`. The round-three experiment files
remain frozen and are read, not edited.
