# Separator P4 preflight

4 November 2026.

The corrected separator export now compiles and links for ESP32-P4. **On-device numerical parity, total RAM and realtime speed remain unproven**. This is static preparation for the training comparison. It does not select a checkpoint or recommend deployment.

The inspected artifact is the early, unselected A4096 export using `int8-convolutions-fp32-norm-core-v1`. Its SHA-256 is `3b537791650e592105dc14b46058f4a7722f5b4c9e717eeae7547d06eda65c55`. Reading its serialized graph did not execute it on the microphone recordings or expose that panel to training selection. Recheck these findings against the eventual selected artifact.

| Quantity | Bytes | Meaning |
|---|---:|---|
| Serialized model | 553,728 | File size, including exported model data |
| Largest graph activation | 6,140,032 | Dense int8 intermediate around the decoder's zero insertion |
| Distinct live activation payload | 6,523,904 | Serialized execution order with separate outputs, before in-place aliasing |

All activation shapes were known for the exported three-second input. The large intermediate is int8; float normalization is not the only memory cost. A small weight file does not imply a similarly small working set.

The activation estimate excludes alignment, allocator fragmentation, model image/parameters, metadata, operator scratch, audio/adapters, the recognizer, speaker model and the rest of the application. It also does not model ESP-DL's actual in-place allocations. It is neither a measured heap peak nor an upper bound on total application memory. The 30,000,000-byte application budget still requires simultaneous internal-RAM and PSRAM measurements during loading and continuous operation.

The staged ESP-DL 3.3.12 source contains float32 execution branches for `ReduceMean`, `Sub`, `Mul`, `Add`, `Sqrt` and `Div`. This supports investigating the numerical export correction without first assuming those operators need new kernels. Branch presence is not a numerical-equivalence test.

The existing standalone example's generated build configuration omits eight required graph operators: `DequantizeLinear`, `Div`, `InsertZeros`, `PRelu`, `QuantizeLinear`, `Sqrt`, `Sub` and `Unsqueeze`. It also omits three selected convolution kernels. A private generator derived all 51 Conv1D/Conv2D signatures from the actual export and the SDK's selectors; ESP-DL's own finalizer accepted both the separator-only configuration and the union with the recognizer and speaker requirements. That configuration check alone did not compile or link firmware. The generated example configuration is not proof of which operators are present in the installed application.

A subsequent isolated ESP-IDF 5.5 probe **compiled and linked successfully for ESP32-P4**. Its generated configuration enables all 16 separator graph operators and the four selected convolution kernels, alongside the recognizer/speaker requirements. ELF inspection confirms the exact 553,728-byte model was embedded and forward implementations for all six normalization operations were linked. Model execution is disabled in the probe; it was never flashed. This establishes compile/link compatibility for this inspected artifact, not on-device execution or correctness.

Do not simply replace the current model file. A future integration must register the separator's requirements, recheck the selected artifact against this compile/link proof, and compare on-device fixture outputs against independently reloaded host outputs. The input, output and gain-restoration adapters must also match.

The current host adapter materializes output and weighting arrays for the complete recording. That is useful for offline evaluation; copying it into a continuously listening device would make memory grow with recording length. The device needs bounded overlap-add storage for its three-second windows and 1.5-second hop. Its processing must keep pace with that hop while preserving capture, draft/final captions and speaker work. No host memory figure proves this.

A private bounded host reference now reconstructs and emits one hop at a time. It matched the snapshotted training adapter byte for byte in 104 comparisons covering chunk sizes, short tails, channel swaps, silence, quiet/loud levels and DC-heavy input. Ten minutes of simulated audio kept its retained NumPy arrays fixed at 1,344,000 bytes. That figure excludes model execution, transient arrays and caller storage. Invalid output and interleaved calls fail visibly. The reference is not a P4 implementation or a measured heap result; its first full-window output still requires three seconds of captured audio. A future device port must retain numerical agreement and meet the live caption latency checks.

The detector investigations found no policy safe to promote. The main comparison therefore waits for the training chat's fixed selection and qualification decision. Physical/regression scoring must count both separator outputs, preserve the existing-model control and distinguish recognition quality from audio that the speech detector never admitted. See [the completed detector comparison](STT_RELATIVE_DETECTOR_AB.md).

Private reproduction is under `private/stt-model-comparison/`: `compile_check.py`, `separator.compile_req.yml`, `separator-compile-provenance.json`, `static_memory.py`, `separator-static-memory.json`, `sdk_audit.py`, `sdk-audit.json`, the isolated `p4-probe/`, `verify_build.py` and `build-proof.json`. The SDK source inspected is the staged override at `firmware/.sdk-overrides/esp32p4/espressif__esp-dl`; the audit pins relevant source hashes. No production source, model or settings changed in this preflight.
