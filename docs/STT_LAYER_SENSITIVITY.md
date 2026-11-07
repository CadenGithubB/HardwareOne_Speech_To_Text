# Selective activation precision: development experiments

**Block 14 is the first candidate to benchmark.** Of the two real full-model
exports, it improved both decoders and delivered the lowest saved-LM error count.
Block 3 is cheaper but its lead in the isolated host simulation did not survive
real export. All measurements below are host results on development data.

| Real full-model artifact | Greedy errors | Saved-LM errors / WER | File growth vs original |
| --- | ---: | ---: | ---: |
| Current INT8 | 112 | 103 / 16.27% | — |
| Block 3: `main.0` depthwise + `main.1` pointwise | 114 | 101 / 15.96% | 10,848 bytes |
| Block 14: `main.6` depthwise + `main.7` pointwise | 109 | **97 / 15.32%** | 41,776 bytes |

3 November 2026. This investigation compares internal precision changes in the
frozen gen2-25397 acoustic model. It uses the 64-clip/32-speaker fresh Common Voice
development screen (633 reference words). Higher-quality decoding uses the same
saved LM with unchanged parameters. The 64-clip reserve is excluded.

## Single-domain tests

The four nodes with the largest observed producer clipping fractions were selected
before scoring any intervention. All are depthwise convolutions. Each host probe
changes **one output quantizer domain**, including matching consumer uses, from
signed INT8 to signed INT16. Its scale is divided by 128: approximately twice the
original range and 128 times finer rounding. Other domains and all weights/biases
stay fixed. The combination rule selects up to two LM-improving domains, with
lower greedy error as the first tie-breaker. These runs use the same clips, not
independent replications. No change to stored acoustic weights is required.

The two original fixtures must pass exact baseline parity before every run.
Feature PCM hashes and references are checked for every clip. Reloading the
original full-development logits reproduces the original LM transcripts. Paired
error counts compare identical utterance IDs; speaker-bootstrap intervals are
exploratory (10,000 draws of 32 speakers with replacement, seed 20261103).

## What the memory figures mean

For a six-second input, promoting the selected output adds **76,800 bytes** for
blocks 2 or 3 (256 channels), or **153,600 bytes** for blocks 10 or 14 (512
channels). These are single live tensors, not peak heap increases. Buffer reuse,
conversions, neighboring activations and alignment affect the actual arena.
Depthwise fallback to 16-bit also adds one byte per weight: 8,448 in block 2 or
3, 32,256 in block 10, 38,400 in block 14, before alignment or other changes.

## What real export changes

A host precision probe isolates an interface, but ESP-DL dispatches whole
operators. A controlled compiler check used the actual weights/topology of
blocks 9–10, with synthetic calibration only to validate the export path. The
mixed path uses W16A16 for the selected depthwise convolution and W8A16 for its
pointwise consumer. The real two-block artifact gained two `RequantizeLinear`
nodes, from 26 to 28 total nodes, and grew from 3,658,768 to 3,694,368 bytes.
It contains three 16-bit intermediate tensors; input and output remain INT8 at the external boundaries. Both embedded fixture
values matched the exporter host executor byte-for-byte; a separate native-graph
round trip also passed. This is a compiler check, not a speech-accuracy test.

A full block-14 export was chosen for an initial test because it improved both
screening decoders, whereas block 10 worsened greedy decoding. It is an export
pilot, not the declared best layer. It dispatches `/blocks.14/main/main.6/Conv`
as W16A16 and `/blocks.14/main/main.7/Conv` as W8A16. The original 102 calibration
clips, frontend source and saved LM are held fixed. Export evidence must include
actual parameter widths, fixture parity and recognition scores; a host probe
alone cannot qualify an artifact. Native PPQ graphs are trusted local evaluation
artifacts, not input formats for the product.

## Device status and reproduction

The board is in use by another session. No serial probe, flashing, SD transfer or
hardware benchmark was performed. In this checkout the resident path in
`quartznet_runtime.cpp` admits only INT8 intermediate tensors; the speech compile
requirements/generator are also INT8-specific. A mixed candidate needs an
isolated firmware build with appropriate kernel selection, tensor sizing and
admission checks. Host file growth cannot establish peak PSRAM or caption latency.
Coordinate with the board owner before any future device work.

Private run plan, exact commands, progress, comparisons, logits, export and
fixture evidence: `private/layer-sensitivity-20261103/`. Source tools:
`quantization_probe.py --activation-node NAME` (repeat for combination),
`evaluate_precision_probe.py` for the saved LM, `export_quartznet.py --precision-op
NODE=SCHEME --save-native` for an experimental export, and
`evaluate_mixed_candidate.py` for trusted local native-graph scoring. Original
data, deployed artifacts and firmware are unchanged.

## Single-layer results

| Promoted interface | Original clipping fraction | Greedy errors | Saved-LM errors | LM clips improved / worsened |
| --- | ---: | ---: | ---: | ---: |
| Original INT8 | — | 112 | 103 | — |
| Block 3, `main.0` | 0.3882% | 111 | **97** | 5 / 2 |
| Block 2, `main.0` | 0.3803% | 111 | 100 | 3 / 1 |
| Block 14, `main.6` | 0.4236% | 111 | 100 | 4 / 2 |
| Block 10, `main.0` | 0.7015% | 115 | 100 | 6 / 4 |

Block 3 improves saved-LM WER by 0.95 percentage points, from 16.27% to 15.32%;
the exploratory speaker-bootstrap interval for candidate minus baseline WER is
−2.35 to +0.16 points. All four individual intervals include zero. Block 10
clips most frequently but ranks behind block 3, and it worsens greedy decoding.
Clipping is useful for finding candidates, not for ranking transcription gains.

The primary combination is blocks **3+2**: blocks 2 and 14 tied on both scores,
and block 2 has the smaller activation. A first scheduler counted distinct
domains rather than tensor bytes for the final tie-break, launching **3+14**.
The size-based primary pair was recorded before either combination was scored;
3+14 is retained as supplementary evidence.

| Combination | Greedy errors | Saved-LM errors | Saved-LM comparison |
| --- | ---: | ---: | --- |
| Primary: blocks 3 + 2 | 112 | 99 | Two more errors than block 3 alone |
| Supplementary: blocks 3 + 14 | 109 | 98 | One more error than block 3 alone |

Using either component alone serves as the leave-one-out comparison. Both pairs
improve saved-LM decoding against original INT8, but neither matches block 3
alone. The supplementary pair gives the best greedy count of these arms. Since
the product uses the saved LM, the strongest single interface, block 3 `main.0`,
was selected for a second full export alongside the block-14 pilot.

## Full-export controls and memory estimates

The block-14 pilot has the exact original ONNX file and calibration roster. The
ESPDL grew by 41,776 bytes to 20,153,904 bytes. It has 203 nodes versus 201,
including two new conversions and three INT16 intermediate buffers. At the
selected interface, the calibrated range is approximately ±2 instead of the
original ±0.125; the one-domain screen used ±0.25. Of 680 matched operator/tensor
quantizer entries, 18 changed precision or scale; 13 are outside the two dispatched
nodes. None of those 13 is a weight scale. This is candidate-level evidence:
real calibration and conversions do more than widen exactly one interface.

For six seconds of audio, a static count in serialized topological order gives
460,800 simultaneously live activation bytes for original INT8 and 768,000 for
the block-14 export. This counts distinct input/output buffers through their
last consumer; it excludes in-place reuse, alignment, allocator fragmentation,
workspace and other firmware. It is neither measured heap nor an admission budget.

The reloaded **full block-14 candidate** passed both fixtures and scored **109
greedy errors and 97 saved-LM errors**. The original had 112 and 103. With the LM,
six clips improved, one worsened and 57 were unchanged in error count; five
speakers improved and one worsened. The paired, exploratory 95% speaker-bootstrap
interval for candidate minus original LM WER is −2.05 to 0.00 percentage points.
This is host execution of the actual exported candidate's corresponding PPQ
graph, not an on-device measurement.

The two promoted convolutions account for 3,699,200 multiply-accumulates per
second of audio in block 3 (0.39% of the model's convolutions) versus 15,027,200
in block 14 (1.59%). These counts use the actual kernel shapes and 50 post-stride
frames per audio second. They show how much arithmetic changes kernel type; they
are not predictions of latency. Conversion and memory traffic are additional.

The block-3 candidate is 20,122,976 bytes (+10,848). It also has two extra
conversions and three INT16 intermediate tensors. Its calibrated interface range
is approximately ±1 instead of original ±0.25 (host single-domain screen: ±0.5).
The ONNX and calibration roster both match the original. Its six-second distinct
live-tensor estimate remains 460,800 bytes: under this counting model, the peak
is still later, in block 7. This does **not** establish equal peak device RAM.
The board-owning chat confirmed that device qualification remains reserved there;
a later handoff must include the verified app, lock and port state.

Direct saved-LM comparison of the two full exports: block 14 did better on seven
clips and worse on three than block 3; 54 had equal error counts. Block 14 had
four fewer errors net (0.63 percentage points). The 95% speaker-bootstrap interval
for block 3 minus block 14 is −0.93 to +2.03 points. For block 3 versus original,
four clips improved and three worsened; its two-error net gain has interval −1.79
to +0.93 points. Neither screen establishes a population ranking. The observed
reversal shows why single-domain sensitivity is a shortlist, not an export result.

Prioritize the block-14 export for a representative meeting-audio development
comparison and isolated P4 fixture/RAM/latency benchmark. Retain original INT8
as control and block 3 as a lower-cost alternative. The size and static estimates
do not establish that either mixed graph fits the integrated firmware or is fast
enough. Do not promote or spend the reserve until the candidate and policy are
frozen. Four targeted unit tests passed, 81 metadata files across the 40 frozen
stores matched their audit hashes, and the original pinned ESPDL was unchanged.
