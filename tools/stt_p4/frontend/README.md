# Portable QuartzNet frontend and CTC

The single C++17 implementation lives in `components/hardwareone/stt/`.
The experiment probe and host tests compile those production files directly;
this folder contains references, generators, and tests only. The implementation converts **raw mono 16 kHz int16 PCM** into contiguous
float32 `[T,64]` features. `T = ceil(samples/160)`, without padded frames; the
ESP-DL input is the same bytes viewed as NHWC `[1,T,1,64]`. Accepted recordings
contain 320–480,000 samples (20 ms–30 s). It is a whole-utterance frontend,
not incremental streaming: normalization requires all valid feature frames.

`compute_features` uses caller-owned storage, has no heap/filesystem/HAL calls,
and does not change microphone gain or settings. Allocate input, output, and
workspace separately. At the 30-second bound, PCM needs 960,000 bytes, features
768,000 bytes, and `FrontendWorkspace` 8,200 bytes on the verified host ABI
(use `sizeof` on the target). The workspace includes a 512-sample ring instead
of another complete float waveform. All 64 mel filters use the 498 nonzero
checkpoint coefficients. Compile with `-ffp-contract=off`, without fast-math.

Do not feed the existing processed WAV/recorder path into this function: that
path already applies pre-emphasis. The contract requires the raw HAL samples
before HardwareOne's software DC removal, high-pass, pre-emphasis, gain, and
clipping chain. PCM scaling here is exactly `int16 / 32768`.

The frontend applies deterministic Gaussian dither at amplitude `1e-5`, then
pre-emphasis `0.97` exactly once; centered reflect-padded FFT 512, hop 160,
checkpoint Hann window 320; squared magnitude, checkpoint mel filters, and
`log(mel + 2^-24)`. Dither resets to `0x12345678` at each utterance. Its generator
is xorshift32 followed by Box–Muller; the exact float32 operations and uniform
mapping appear in the C++ and independent Python reference. This deliberately
does not reproduce Torch's RNG. C/C++ math-library last-bit variation remains
possible across processors; fixture checks qualify the actual target.

CMVN uses each mel bin's valid frames only, unbiased sample variance (`T-1`),
and denominator `sqrt(variance) + 1e-5`. Mean and variance sums use float64;
mean and variance are cast to float32 before subtraction/square root. This
stabilizes near-silent input: the original Torch float32 mean reduction could
shift a mean by one ULP and amplify it to approximately 0.10 normalized units,
even when both FFT paths produced identical log-mel values. The mathematical
normalization is unchanged; its reduction precision is explicit and shared
with export/calibration.

`frontend-contract.json` pins this behavior and the hashes of the C++ source,
header, generated constants, provenance manifest, and Python reference.
`contract.py` resolves the C++ files in the production directory while retaining
the original basename keys, so deduplication does not change the model identity. Its
SHA256 is the frontend identity carried in the model envelope:

```
ca91eb9683f7151b8be1a01532a6790c6eb7d515f67169a207751e3fc48cc58b
```

`ctc_feed` accepts float32 or common-scale int8 scores in `[frames,29]` order.
It uses first-index argmax ties, blank 28, and vocabulary space + a–z + apostrophe.
Its state preserves blank/repeat collapse across arbitrary chunk boundaries.
Output remains NUL-terminated; overflow is reported, and `ctc_finish` trims
trailing spaces and prevents further writes. Leading spaces are suppressed.
The 3,000-frame cumulative bound exceeds the model's maximum 1,500 output
frames. Float scores must be finite; NaNs are rejected before state mutation.

## Reproduce host checks

Run from the worktree root with the already isolated, pinned host ML environment
from `experiments/speech_portable/stt-requirements.txt`. No model download occurs
in these commands. The exact checkpoint and public fixture provenance are in
`experiments/speech_portable/float_quartznet.py` and the constants manifest.

```sh
python3 experiments/stt_p4/frontend/contract.py --check
python3 experiments/stt_p4/frontend/test_model_container.py
experiments/speech_portable/private/stt-quartznet/venv/bin/python experiments/stt_p4/frontend/export_constants.py --check
experiments/speech_portable/private/stt-quartznet/venv/bin/python experiments/stt_p4/frontend/test_frontend.py --sanitize
experiments/speech_portable/private/stt-quartznet/venv/bin/python experiments/stt_p4/frontend/test_runtime_quantization.py
experiments/speech_portable/private/stt-quartznet/venv/bin/python experiments/stt_p4/frontend/test_transcripts.py
```

Results and generated feature/PCM fixtures stay in ignored
`experiments/stt_p4/private/frontend/`. The quantizer test extracts and compiles
the actual runtime rounding loop; it tests negative and positive half-ties,
adjacent representable values, saturation, and both speech feature buffers.

Host checks on 2026-09-28 passed with ASan/UBSan:

- Nine frontend fixtures: silence, near-silence, impulses, short random inputs,
  a full 30-second sinusoid, and both public speech clips. Maximum error across
  all fixtures was `4.36e-4`, mean error at most `1.15e-5`. Regression thresholds
  are `6e-4` maximum and `2e-5` mean absolute error.
- Silence fixtures matched exactly. Speech maximum errors were `8.70e-6` and
  `1.02e-4`; their int8 model inputs were byte-identical to the Torch reference.
- Actual runtime quantization matched NumPy nearest-even on 124,579 edge/random
  values and all 149,440 speech feature values.
- Float transcripts from C++ features, the portable Torch reference, and the
  original Torch RNG/reduction path were identical for both speech clips.
- The runtime container validator accepted the real pinned envelope and rejected
  all 768 one-bit header mutations, all 96 truncated header lengths, incorrect
  total sizes, and invalid reader behavior under ASan/UBSan. These tests cover
  the envelope gate; the runtime separately checks decompressed model SHA256
  before the vendor parser. Tests compile the canonical production validator
  and verify the production runtime gate order.
- CTC tests passed all chunk split positions, float/int8 parity, tied scores,
  bounded output truncation, NaN rejection, extent overflow, and finalization.

These two clips are sanity checks, not held-out accuracy evaluation. Host
parity establishes neither P4 timing nor a realtime streaming capability.
The synchronous frontend has no cancellation callback; its target execution
latency must be measured before choosing watchdog/cancellation expectations.

## Constants and attribution

`export_constants.py` verifies the SHA256 of the inspected NVIDIA checkpoint
and configuration before `torch.load(..., weights_only=True)` with PyTorch
>=2.6. It exports exact window/mel float bits plus deterministic FFT tables.
The archive hash, tensor hashes, official download URL, and generated-header
hash are recorded in `constants-manifest.json`.

The source model is [NVIDIA QuartzNet5x5LS-En](https://catalog.ngc.nvidia.com/orgs/nvidia/-/models/nemospeechmodels/1.0.0a5).
NVIDIA's [maintainer clarification](https://github.com/NVIDIA-NeMo/Speech/discussions/1681)
states CC-BY-4.0 for its NGC NeMo checkpoints unless otherwise specified;
the downloaded archive did not include a separate license file. Preserve
NVIDIA attribution and checkpoint provenance with redistributed derived
constants/model artifacts. The reference algorithm follows the inspected
checkpoint and [NeMo feature implementation](https://github.com/NVIDIA/NeMo/blob/v1.0.0rc1/nemo/collections/asr/parts/features.py).
