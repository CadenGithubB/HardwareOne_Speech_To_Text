# Pointwise address-walk experiment

The `.inc` files contain the actual tiled 1×1 loop extracted from HardwareOne
`aa6508fd`'s patched ESP-DL 3.3.12 and its experimental candidate. Upstream
ESP-DL code is covered by [LICENSE.esp-dl](LICENSE.esp-dl). The candidate preserves
the 16 KiB filter tile, 64-pixel spatial tile, output-channel tiling, body call
order, full input-channel reduction, bias/factor pointers and fallback rules.
Only a one-column rectangle's pixel addresses advance by row stride instead of
recomputing quotient/remainder and products per pixel.

`tests/test_pointwise_addresses.py` includes both real loops with a synthetic
argument container and recording body. It compares accepted/fallback results,
ordered addresses and the loop's address/tile argument fields, including a control run
through the candidate with its diagnostic selector off. ASan/UBSan cover 600
seeded rectangles, mixed activation/filter widths, strides and body origins,
misalignment, null body, unsupported activation, remainders and empty shapes.
This is a call-level test, not an emulation of the P4 assembly or a host speed
claim. The candidate include is byte-identical to the built vendor function.

`p4-pointwise-probe-0637d23f.patch` adds the temporary local HardwareOne probe
`c6252b6e` on the existing fixture diagnostic `0637d23f`. It updates the reviewed
SDK patch/digests and adds an atomic diagnostic selector and counters; no runtime
setting is introduced. The original selector is restored after the probe. The
normal model's weights, tile sizes, compiler options, CPU/RAM clocks, speaker
frontend/rules and ordinary preview settings remain fixed. This is not a
production integration patch.

While PDM capture is already active, before the normal feature pool and
speaker worker start, the acoustic `ModelCache`
replays the privately owned fixed PCM through the production feature, int8 model
and greedy decoder path. Both modes share the same cache, arena and buffers.
Four warm-up calls precede three alternating pairs per boot. Nonnull diagnostics
request exact feature/logit hashes and a finer inference timer; normal calls pass
null. Text is compared by hash, never logged. Hashes remain private. Each pair
also logs model stage totals, yield time, eligible tiled/one-column/512→512 call
counts, scoped heap minima and inference-time free memory. Heap measurements
include other firmware tasks and are not exclusive allocation attribution.

The probe uses greedy decoding without the LM and excludes a real microphone
queue, endpoint timing and display delivery. A fixed-input computation result
does not qualify a live application improvement. Both modes receive the same
hashing, counters and heap instrumentation. Extra probe code/placement can affect
cache behavior; a production-style app comparison is a later gate for a winner.

Use the established `p4speakerparity.py prepare/run/cleanup` ownership lifecycle
and five reboot trials, with app-only flashing after MAC/partition checks. Always
restore and full-slot-verify the original app, including on failure. Keep logs,
audio, fixture and tensor identities private. Then summarize:

```sh
python3 tests/test_pointwise_addresses.py
python3 tests/test_p4pointwise.py
python3 tools/device_tests/kernels/p4pointwise.py private/.../trial-*
```

The parser requires all metric blocks, end markers, successful comparison and
identical nonzero tensor/text identities across boots. It rejects watchdogs,
overruns, fatal markers and changed shapes/call counts. Its paired bootstrap
resamples whole boot means (10,000 draws, seed 17); three within-boot pairs do
not become three independent reboot trials. The summary prints no raw identities.


Outcome: five boots / 15 timed pairs / 50 hash-equal model calls. No measurable
speedup: inference +1.157667 ms, boot-bootstrap 95% [-3.437533, +5.275533] ms.
Measured headroom matches. The candidate is rejected for promotion; see
`docs/AB_TEST_RESULTS.md` for full numbers and restoration evidence.
