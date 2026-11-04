# Isolated block-14 fixture and memory probe

The 4 November numerical follow-up localized the original stable failure to the
missing bias-free INT16 depthwise kernel at block 14 main.6 (dispatch key
`0x0315`). The isolated app now links that kernel. Both models passed their
original fixtures and the matched three-length benchmark completed on the P4.
See [numerical qualification](../../../../docs/STT_NUMERICAL_QUALIFICATION.md)
for memory, timing and the adoption decision.

Use `-DHW1_PRECISION_TRACE=ON` for the separate localization build. It reloads
the payload and constructs a fresh model for each ordinary/prepared and
single/multicore combination, runs the same fixture three times and emits
whole-tensor hashes on the first call. It skips the extended RAM workloads.
Use the default trace-off build for memory and elapsed-time results.

The app mounts the actual model card through the standalone adapter without
entering the product loop or starting PDM, speaker workers, LM loading or note
persistence. It verifies the installed stored envelope and complete control raw
SHA. The embedded private reconstruction delta reads that immutable payload;
the delta travels in the flashed firmware, avoiding a separate full-model or any
audio upload and any scratch write. The complete candidate SHA must
match before its bytes reach ESP-DL. Different envelopes/codecs are refused.

Each model is constructed independently with the existing greedy allocator,
metadata placement and model-local preparation. It runs its own embedded input
and output fixture at 663 frames: one cold and two warm calls, restoring fixture
input before each call because the greedy arena may reuse input storage. The
output comparison is exact int8 bytes. A failed fixture remains failed; memory
observations cannot qualify that model. Logged input hashes reveal any difference
between the models' fixture inputs. Both exports currently contain one test input
and one final test output; other fixture layouts are deliberately refused.

Only after BOTH models pass does the app run additional matched 100-, 1,000- and
2,000-frame workloads (short, ten-second and resident-cap shapes). Each length
constructs a fresh model and performs one cold and two warm calls. Both models
receive identical deterministic int8 inputs, restored before each call; hashes
must remain stable within a model. Different models need not produce equal
outputs. These workloads check shape-dependent memory and repeated execution,
not accuracy or a new numerical reference beyond the own-fixture gate. They do
not qualify every possible model length or full-application memory use.

Every module uses the existing multicore path and yields after joining; the stage
count comes from the actual model. This is matched diagnostic timing, not P4
caption latency, uninterrupted throughput or full-application RAM qualification.
No production int8 activation guards are weakened for mixed intermediate tensors.

Memory windows cover raw load/reconstruction, model construction, and each
prepare/infer call. IDF's local minima are maintained at allocation events and
queried before the window stops. For multiple physical heaps, their summed minima
may occur at different instants: total minus that sum is an upper bound, not an
exact aggregate peak. A boot-time heap walk counts distinct physical regions;
only a single-region capability class is marked exact. The heap registry must
remain stable. Largest-free-block values are end checkpoints, not transient
contiguity minima. The monitor's bookkeeping and embedded delta are probe overhead
and remain present for both models; report actual configuration and image size.
Capability masks are recorded: internal measurements cover byte-addressable
internal heaps, and external measurements cover byte-addressable PSRAM heaps.
Totals/minimum free and their difference describe registered heap space; they
exclude static image storage outside those heaps and are not total SoC RAM use.

The allocation-failure callback uses bounded integer-only ROM output, recording
requested contiguous bytes, capabilities and phase/stage. It does not traverse
the heap, allocate, or infer whether fragmentation caused the failure. Phase
10/11 is control load/build, 20/21 candidate load/build, 100 preparation and
1000+module index inference. Surrounding model/window records identify the model.
An SDK assertion may stop a failed allocation; retain its complete private log.

Use ESP-IDF 5.5.5 and the reviewed staged SDK in a separate private build directory.
Supply `-DHW1_PRECISION_DELTA=/absolute/private/model.delta`. Inspect the actual
sdkconfig for 64-byte L2, standalone 200 MHz PSRAM, model-local preparation,
assertions enabled, allocation abort and heap hooks disabled. Defaults do not
override an existing config. Do not build during acoustic capture.

Only an exclusive controller may operate the board. Verify MAC/actual partition
table and private rollback. Flash only the app through the approved helper;
never flash this directory's link-size table or generated flash arguments.
Repeat a watchdog-bearing image/input/mode unchanged at least once. Restore and
readback-verify the selected app, reconnect/logging off, before releasing the lock.
Keep all model/delta bytes, captures and logs in ignored private directories.
