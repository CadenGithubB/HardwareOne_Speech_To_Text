# Fixed-model quantization investigation — 3 November 2026

This follows the 64-clip fresh development screen: float 95 word errors, frozen
int8 112, saved-LM decoding 103, over 633 words. The separate reserve remains
unscored. All interventions here are **host-only counterfactuals**, not exported
models, device results or changes to deployed firmware. Acoustic weights and
saved decoder settings are held fixed.

## Method and controls

`tools/stt_p4/quantization_probe.py` instruments the saved frozen graph. Before
processing any development clip, it requires exact float agreement with the
original folded model and byte-exact int8 fixture agreement with both the existing
frozen evaluator and exported fixture bytes. Every input/reference is checked
against the frozen stage report's PCM identity.

The full 64-clip profile measures local output-quantizer error, clipping after
rounding, and propagated error against the float activation at every node. These
metrics help locate numerical changes; a large tensor error alone does not prove
that a layer caused a word error. Counts describe producer outputs, not every
consumer re-quantization or integer accumulator in the physical P4 runtime.

It also saves scores immediately before the final output quantizer. The existing
output scale is **0.5**, with signed-int8 range −64 to +63.5. A fixed sweep compares
that original scale with **0.25**, **0.125**, and the diagnostic case of no final
rounding. Hidden activation/parameter quantizers remain unchanged. Each int8 output
scale uses the original LM/header settings with the corresponding dequantization
exponent. Original post-quantizer logits must reproduce the earlier NPZ byte-exactly;
all float transcripts and the original-scale LM transcripts must also match.

Two additional interventions use a fixed hash-ranked subset of eight speakers
(16 clips), selected independently of recognition errors:

- `parameters_float`: bypass parameter quantization, including biases, but keep
  activation and final-output quantization.
- `activations_float`: retain parameter quantization but bypass activation and
  final-output quantization.

These distinguish broad sources of sensitivity; they do not isolate a single
physical kernel or establish that the corresponding precision is affordable on
P4. The subset is development screening, not a newly untouched test partition.
No unmeasured higher-precision speed, memory or accuracy benefit is assumed.

The original 102-clip calibration and ESPDL binary remain unchanged. Output-scale
experiments test sensitivity to one calibration choice; they are not a fresh
calibration run or evidence that a candidate binary supports the changed scale.
Private evidence and exact experiment plans are under
`private/quantization-investigation-20261103/`.

## Measured results

All 64 development clips (633 reference words) reproduced the original float
transcripts and int8 logits; the original-scale LM transcripts also matched.
Both exported fixtures passed exact agreement checks.

| Final output step | Greedy word errors / WER | Saved-LM word errors / WER |
| --- | --- | --- |
| Original 0.5 | 112 / 17.69% | 103 / 16.27% |
| 0.25 | 107 / 16.90% | 102 / 16.11% |
| 0.125 | 110 / 17.38% | 104 / 16.43% |
| No final rounding (diagnostic) | 107 / 16.90% | Not measured |
| Full float reference | 95 / 15.01% | Not measured |

The 0.25 step improves five clips and worsens two under greedy decoding; with the
LM it improves two and worsens two, for just one fewer word error overall.
This is insufficient evidence to promote a new export. Removing final rounding
leaves 12 of the original 17 extra greedy errors, so it does not explain most of
the net float-to-int8 gap on this screen. These are net counts, not attribution
of individual errors to independent components.

Pre-output scores range from −6.855 to +28.790. Original 0.5 rounding clips no
scores, but changes the winning token on 88 of 18,349 frames, including 67
blank-to-character changes. Step 0.25 also clips none and reduces those counts
to 46 and 33. Step 0.125 saturates 6,069 of 532,121 scores: its maximum is only
15.875. Finer precision therefore introduces a range tradeoff, not a guaranteed
improvement. Greedy argmax resolves equal scores by token index; blank is last.

On the independently hash-selected eight-speaker subset (16 clips, 155 words):

| Counterfactual | Word errors |
| --- | ---: |
| Full float | 25 |
| Original int8 | 29 |
| Float parameters, quantized activations/output | 30 |
| Quantized parameters, float activations/output | 25 |

The last intervention matches the float error total but differs from float on
four transcripts. This supports activation quantization as the stronger lead on
this subset; it does not prove that parameter quantization is harmless.

Largest producer-output clipping fractions include:

| Node (zero-based block index) | Clipped values | Output scale |
| --- | ---: | ---: |
| `/blocks.10/main/main.0/Conv` | 0.7015% | 0.001953125 |
| `/blocks.14/main/main.6/Conv` | 0.4236% | 0.0009765625 |
| `/blocks.3/main/main.0/Conv` | 0.3882% | 0.001953125 |
| `/blocks.2/main/main.0/Conv` | 0.3803% | 0.001953125 |

These are candidates for intervention, not a causal ranking by recognition loss.

## Recommended next experiment and limits

Prioritize a controlled activation-calibration experiment with fixed weights.
First isolate the listed internal quantizers, then compare a representative,
training-only calibration selection against the original 102 clips. Change one
factor at a time and retain the original export as the control. Evaluate both
greedy and saved-LM decoding: the latter almost erases the observed benefit from
changing only the final output scale. Do not spend a full retraining run on this
hypothesis before measuring that cheaper intervention.

Any selected candidate needs a real export, fixture parity, and streaming/device
checks before deployment. Freeze that candidate and evaluation policy before
scoring the untouched reserve. The current short read-speech development screen
cannot establish meeting-audio gains, runtime cost, or generalization; pretrained
exposure remains unknown.

Three diagnostic unit tests pass, covering quantizer rounding/saturation,
parameter-versus-activation interventions, and the pre-output/float profile.
Production weights, export, decoder settings and dataset manifests were not
changed. No reserve inference, training, firmware deployment or board access was
performed. Private per-utterance evidence remains in the ignored investigation
folder; this document contains only aggregate results.
