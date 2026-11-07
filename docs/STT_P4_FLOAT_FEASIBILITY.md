# Unquantized-model feasibility on our ESP32-P4

Measured 3 November 2026. Conclusion: the P4 can compute floating point, but our
current QuartzNet15x5 cannot be resident in full FP32 or FP16 on this 32 MiB
board. The current ESP-DL convolution path also cannot execute FP32 convolutions.
This is a source/parameter audit, not a new hardware benchmark.

## Exact model and memory accounting

Counted actual parameters after inference batch-normalization folding, using
`tools/stt_p4/quartznet_graph.py` and checkpoint `ckpt-gen2-25397`, weight SHA
`e1873cc934e7c645c8d8b91dbe60834a3d0ff623e8eb3b700ef132159d24be6d`.
There are **18,847,040 weight values and 38,685 biases**. This avoids counting
training-only batch-normalization state or guessing from checkpoint file size.

The saved ESPDL SHA is
`47e58faa01470d32dad88f1faa46e3f61dff0fd605aa542103aefd11502dae72`,
matching the model identity pinned in this checkout's `stt_model_identity.h`.
Its actual cached payload is 20,112,128 bytes (19.18 MiB).

| Representation | Parameter bytes, excluding metadata and activations | MiB |
| --- | ---: | ---: |
| FP32 weights and biases | 75,542,900 | 72.04 |
| FP16 weights and biases | 37,771,450 | 36.02 |
| INT8 weights with INT32 biases | 19,001,780 | 18.12 |
| INT16 weights alone, excluding biases | 37,694,080 | 35.95 |

Even FP16 and all-INT16 weights exceed 32 MiB. FP16 is reduced-precision floating
point; it is not identical to the original FP32 model. These are uncompressed
parameter costs, not promised serialized file sizes or peak runtime allocations.

Recorded board measurements report 31.33 MiB of PSRAM heap and only about
1.5–2.6 MiB free in different integrated workloads. These are historical captures,
not a fresh measurement of the current running firmware. See
`STT_OPTIMIZATION_PLAN.md` section 4 and `STT_EXPERIMENT_RESULTS.md`.
Freeing the language model, speaker work or audio queues cannot make 72 MiB of
resident weights fit in 32 MiB.

For six seconds of input, the largest individual activation is 307,200 values:
0.293 MiB at INT8, 0.586 MiB at INT16, or 1.172 MiB at FP32. This is **one tensor**,
not total working RAM; residuals, simultaneous inputs/outputs, scratch buffers,
metadata and frontend also occupy memory. At the engine's 30-second maximum that
single tensor becomes 5.859 MiB at FP32. The existing INT8 admission formula is
`2048*ceil(feature_frames/2)+65536` bytes for its arena allowance; it is not a
validated float or mixed-precision memory plan.

## Processor and runtime support

The P4 has a single-precision FPU, so running a suitably small floating-point
network is possible with suitable software. It is not inherently restricted to
integer models. [ESP-IDF P4 introduction](https://docs.espressif.com/projects/esp-idf/en/v5.5.5/esp32p4/get-started/index.html).

Our manifest pins patched ESP-DL 3.3.12. The inspected local
`dl/module/include/dl_module_conv.hpp` deserializer constructs convolutions only
for INT8, INT16 and W8A16; FP32 returns no convolution module. The current upstream
[operator table](https://github.com/espressif/esp-dl/blob/master/operator_support_state.md)
also lists FP32 Conv as unsupported. Exporting a float model is not evidence that
this runtime can execute it.

The application's `quartznet_runtime.cpp` additionally checks INT8 input/output,
quantizes features into `int8_t`, and decodes `int8_t` logits. Changing precision
therefore needs an appropriate export, runtime integration, revised allocation
budgets and numerical parity checks. It is not a switch in the existing app.

Static shape execution counts **942,352,000 convolution multiply-accumulates per
second of audio** (5,654,112,000 for six seconds), excluding frontend, additions,
activations and decoder. This is workload, not measured FP32 latency. No valid
float throughput or realtime claim can be made from the current INT8 timings.

## Alternatives and next step

- **Smaller FP32 model:** possible in principle. Requires architecture/accuracy
  work and a float-capable inference implementation. Memory fit alone does not
  establish realtime operation.
- **Stream this model's float weights from SD:** avoids holding all weights at
  once, so memory alone does not make this mathematically impossible. The largest
  individual convolution's FP32 parameters are 2,101,248 bytes. A one-layer-at-a-time
  design would normally read about 75.54 MB per complete pass, plus compute and
  working buffers. This requires a different loader/executor and measured storage
  and compute throughput; it is not a demonstrated realtime solution. Compression
  of a file does not solve resident decompressed-memory requirements.
- **Mixed INT8 weights / INT16 activations:** the most relevant candidate given
  the measured activation sensitivity. ESP-DL supports this from 3.3.11, with
  depthwise convolutions falling back to INT16. This model has 1,761,600 depthwise
  weight values, so treating every weight as still INT8 would undercount memory.
  Assuming INT64 biases throughout, parameter storage before metadata is about
  20,918,120 bytes (19.95 MiB); this is a planning estimate, not an exported size.
  Activation storage also increases. Given tight existing headroom, selectively
  promoting sensitive layers is preferable to assuming a whole-model conversion
  fits. [ESP-DL quantization and mixed-precision documentation](https://docs.espressif.com/projects/esp-dl/en/latest/tutorials/how_to_quantize_model.html).

Next investigate selective activation precision/calibration on the development
set, produce a real candidate export, then measure actual peak RAM and P4 timing.
Keep the reserve unscored until a candidate is frozen. This audit does not claim
that INT16 recovers the host float-activation result; that must be measured.

Reproducible parameter/shape measurement script and JSON:
`private/p4-float-feasibility-20261103/`. No training, reserve inference, firmware
changes, flashing or board access occurred.
