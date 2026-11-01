# Feature-cache writer / retirement ownership

The frozen `.inc` sources are derived from HardwareOne aa6508fd, copyright
2026 CadenGithubB, under [LICENSE.hardwareone.md](LICENSE.hardwareone.md).
`worker_reference.inc` intercepts only the DSP entry to control scheduling;
the DSP implementation is the actual shared `quartznet_frontend.cpp`.
The retirement and volatile-wipe helpers are unchanged production code.

The original task writes its uncommitted eight-row batch straight into cache
storage outside `gSTTMux`. The inference worker can retire that cache and wipe
those rows outside the lock. A late DSP completion overwrites the wipe even
though its generation/state check subsequently refuses to commit the batch.
This is not evidence that a wrong prefix was delivered or that it caused the
historical allocator assertions.

`feature-cache-ownership-aa6508fd.patch` is the narrow repair (local HardwareOne
3fff3013): stage the batch in the feature worker's existing
`FrontendWorkspace::conditioned[512]`, then under the lock verify the original
live generation, copy the rows and publish their committed count together.
The incremental DSP leaves that array unused internally; the explicit alias
contract and `tests/test_feature_batch_workspace.py` verify it. Batch size,
publication granularity, feature arithmetic, pool size and configured task stack
stay the same. The standalone `StreamPipeline` already computes private rows
and commits them under its lock; no whole-application synchronization is done.

```sh
python3 tests/test_feature_batch_workspace.py
python3 tests/test_feature_cache_ownership.py --hardwareone /path/to/HardwareOne
python3 tests/test_feature_cache_ownership.py --hardwareone /path/to/HardwareOne --thread-sanitize
```

The default test reproduces late writes for orphan retirement and attached-cache
release, checks zero stale values after repair, and verifies normal rows byte
for byte. ThreadSanitizer expects the frozen reference to report both races as
positive controls; candidate and normal paths must pass. Optional `--evidence`
stores reports in a private directory without overwriting previous evidence.
Apple's sanitizer is configured explicitly for exit code 66 without its default
abort/symbolizer behavior. It also sets `ignore_interceptors_accesses=0`: this
Mac defaults to ignoring interceptor accesses, which can hide memcpy races.
`tests/test_tsan_memcpy.py` calibrates unlocked positive and locked negative
controls before relying on a clean copy-heavy test. Host lock/task adapters use a mutex and a scheduling
gate; they do not emulate the P4 scheduler. `--hardwareone` binds the extracted
paths to actual source and verifies the shared DSP. It strips only the exact
separate P4 scheduling hook from the diagnostic worker.

`p4-feature-ownership-probe-3fff3013.patch` is temporary diagnostic ebe29cdf,
applied on the earlier known-PCM parity diagnostic plus the normal fix. It adds
a frozen original task as positive control and a keyed gate for synthetic runs.
During startup, while PDM capture may already be active but before the normal
feature pool and speaker worker start, it creates the real original/candidate feature
tasks at core 0, priority 1, with the original 3,072-byte stack. It supplies the
owned fixed PCM through a wrapping stream ring and tests normal capture, orphan
retirement and attached-cache release. Normal rows are compared on core 1 with
the unchanged DSP; late cases resume an in-flight batch after retirement. All
synthetic workers join before their buffers are wiped/freed. Extra probe buffers
are freed before normal capture, and no data values are logged.

Use the established private fixture prepare/run/cleanup lifecycle. Start with
one smoke reboot; after its six cases pass, collect five separate reboot trials.
`p4feownership.py` checks successful normal equality, old late-write positive
controls, candidate zero-stale results, original stack size and observed stack
headroom. It rejects incomplete/truncated blocks and lifecycle faults:

```sh
python3 tests/test_p4feownership.py
python3 tools/device_tests/feature_cache/p4feownership.py --smoke private/.../smoke/trial-*
python3 tools/device_tests/feature_cache/p4feownership.py private/.../matrix/trial-*
```

No playback is needed. Flash only the MAC/partition-verified app slot and always
restore/full-slot-verify the original app. Private PCM, raw logs and model data
are never committed. Forced schedules establish a correctness defect/repair,
not its frequency, a WER gain or the cause of an observed device crash. The
separate direct-ring overwrite question is not covered by the fixed-ring tests.


Checkpoint: all 42 forced checks across seven P4 boots pass, including both old
late-write positive controls and repaired zero-stale cases. Only five lifecycles
complete; two stop/teardown faults remain (hardware-watchdog reset and core-0
heap-allocation load-access fault). The intended matrix has four clean runs and
two failed attempts, plus a separate clean smoke. This is not a qualified app
update or demonstrated WER/reliability improvement. All attempts are retained;
unchanged retries stopped. Original app restored and owned fixture removed.

The incremental `p4-teardown-probe-ebe29cdf.patch` is diagnostic instrumentation
on top of the ownership probe, not a production repair. It adds low-allocation
ROM-console markers and full heap-integrity scans at the following boundaries.
A failed scan aborts after its numeric marker, preserving the first failure.
Scans perturb timing; neither successful cleanup nor timing from these runs
qualifies an uninstrumented app. The acoustic model, cluster rule and clocks
are unchanged.

| Phase | Boundary just reached |
|---|---|
| 100 | Speaker end, before worker join |
| 110 | Worker joined and speaker summary logged |
| 120 | Speaker destructor, before model reset |
| 200 | Model reset, before deleting ESP-DL trunk |
| 201 | ESP-DL trunk deleted |
| 202 | Speaker frontend workspace released |
| 140 | Explicit speaker model reset returned |
| 141–145 | Centroids, embedding, job PCM, diagnostic buffer, model blob freed in that order |
| 160 | Speaker state object released |
| 300–301 | Before/after warm backend park/reset |
| 310–311 | Before/after audio buffers wiped and freed |
| 320 | Transcript completion published, before terminal state update |
| 321 | Terminal state published, before worker self-delete |

Each phase has event 0 before its heap scan and event 1 after it. The latter
includes `heap_ok`, scan duration and remaining internal/PSRAM bytes. Model
resets outside a session shutdown can also emit 200–202; the parser starts a
cycle only at 100. `teardowndiag.py PRIVATE_RAW_LOG...` reports numeric fields
only and rejects missing, duplicate or out-of-order markers within a cycle.
A truncated cycle is reported incomplete, never a successful teardown.
Use `--partial` to retain a stream with missing markers: missing event IDs are
listed explicitly, no fields are reconstructed, and the cycle stays incomplete.
Duplicates and reversed events remain errors. The real interleaved phase-301
completion and initially omitted model phases have synthetic omission cases.

```
python3 tests/test_teardowndiag.py
python3 tests/test_teardown_probe.py HARDWAREONE_CHECKOUT
python3 tools/device_tests/feature_cache/teardowndiag.py PRIVATE_RAW_LOG
```


## Trace-only markers and passive collection

`p4-teardown-trace-5e07c4d9.patch` applies on the heap-scan diagnostic, producing
002e3a0c's marker-only emitter. Event 2 is a boundary observation, never a heap
check. The emitter uses ESP_LOGI and the existing `loglink` shared output queue;
ROM printing bypassed that queue and corrupted markers under asynchronous
output. Loglink must be enabled, with system file logging still inactive.
All 19 markers may precede a later fault: they do not qualify a device lifecycle.

`p4teardown.stop_after_teardown(device)` is for this explicitly labelled
idle-capture diagnostic only. It sends stop, passively collects through phase
321, then queries terminal status and checks health. It does not drain speech
mailboxes during collection. On failure it invalidates the token; callers must
reset/recover instead of retrying a stale stop. The controller retains failed
attempts and always restores the original app. No flashing is performed by this
helper itself. `teardowndiag.py` accepts separate heap and trace protocols and
rejects mixed, damaged or reordered events.

```
python3 tests/test_p4teardown.py
python3 tests/test_teardowndiag.py
python3 tests/test_teardown_probe.py HARDWAREONE_CHECKOUT --trace-only
```

## Separate live-ring audit

The row-cache repair does not serialize the PCM producer and feature reader.
`ring_writer_reference.inc` is the unchanged actual producer, under the same
HardwareOne license above. `--ring-audit` forces wrap/overwrite while the DSP is
preempted. Both current worker versions report a TSAN race with interceptor
checking enabled; the ASan/UBSan mode separately verifies zero committed stale
rows and one overrun. This is a reproduced source-level hazard, not a claimed
origin for device crashes or a measured feature/WER regression.

```
python3 tests/test_tsan_memcpy.py
python3 tests/test_feature_cache_ownership.py --hardwareone HARDWAREONE_CHECKOUT --ring-audit --thread-sanitize
python3 tests/test_feature_cache_ownership.py --hardwareone HARDWAREONE_CHECKOUT --ring-audit
python3 tests/test_stt_stream.py --thread-sanitize
```

The actual portable StreamPipeline passes with strict copy checking. The
subsequent stable-window candidate below supplies the separate repair path,
parity checks and actual P4 stack/copy-cost evidence; the original controls
remain unchanged for comparison.


## Stable-window candidate

Normal HardwareOne b7598680 adds a 512-sample private PCM window and serializes
both snapshot reads and producer writes under the same lock. The old overwrite
admission guard and private feature-batch publication remain. No new heap
buffer/configured stack is requested. The array uses 1,024 B of existing stack.
`ring_snapshot_candidate.inc`, `ring_writer_candidate.inc` and
`worker_ring_candidate.inc` are bound to actual production sources and the
shared DSP is unchanged. They use the HardwareOne license above.

For a current ring-candidate checkout, use `--ring-candidate` so the source
binder checks all three variants. The original commands without that flag are
for a cache-row-only checkout; they intentionally reject a different worker.

```
python3 tests/test_feature_cache_ownership.py --hardwareone HARDWAREONE_CHECKOUT --ring-candidate --parity
python3 tests/test_feature_cache_ownership.py --hardwareone HARDWAREONE_CHECKOUT --ring-candidate --parity --thread-sanitize
python3 tests/test_feature_cache_ownership.py --hardwareone HARDWAREONE_CHECKOUT --ring-candidate --ring-audit --thread-sanitize
python3 tests/test_feature_cache_ownership.py --hardwareone HARDWAREONE_CHECKOUT --ring-candidate
```

The normal full patch is `feature-ring-aa6508fd.patch`; the incremental patch
for the existing row repair is `feature-ring-3fff3013.patch`. Diagnostic patch
`p4-feature-ring-probe-b7598680.patch` adds the known-input comparison separately
(cc6a256d). The reference is the exact 3fff3013 worker/producer with renamed
functions. Each boot executes five matched pairs in alternating order with a
logged flip, verifies stable rows, reads blocked-task CPU/runtime and stack
high-water data, and checks/times snapshot and producer calls. PDM capture is
already active, before the normal feature pool and speaker worker start.

```
python3 tests/test_p4fering.py
python3 tools/device_tests/feature_cache/p4fering.py PRIVATE_TRIAL_DIRS
```

Task CPU uses existing ESP_TIMER FreeRTOS runtime stats; no worker timer hook
is added. Producer microcalls repeatedly use one hot contiguous location.
Snapshot/producer whole-call times include overhead and possible preemption,
not exact critical-section hold time or worst-case streaming-copy latency.
The parser emits only numbers/IDs, rejects damaged/duplicate/misordered records,
and keeps lifecycle status separate from pre-stop numerical checks. Five clean
boots are an isolated diagnostic gate, not full application qualification.
See AB_TEST_RESULTS.md for measured cost and remaining checks.


## Heap/trigger readback discovery

`p4-heap-readback-002e3a0c.patch` adds 647e4858's read-only state discovery to the
archived fault-reproduction workload. It is separate from the stable-window
repair. At four stages it queries both cores through per-core callbacks, saves
and restores TSELECT/IRQ state, reads TDATA1/2/3 and TCONTROL, and samples the
heap header's control pointer. No trigger configuration/address/context writes,
arming or clearing are performed. The portable reader deliberately exposes no
such write operation; its host test compiles the actual template.

```
python3 tests/test_heap_trigger_read.py HARDWAREONE_CHECKOUT
python3 tests/test_p4hwread.py
python3 tools/device_tests/feature_cache/p4hwread.py PRIVATE_RAW_LOGS
```

The parser accepts the older format without TDATA3 as explicitly incomplete
context coverage. The extended footer requires all context records, so damaged
extended logs cannot silently qualify as the older format. It separates
read-only capability bits from configuration, rejects bad/missing/restoration
records, and emits only numbers/IDs. A decoded inactive/reset shape is an
observation, not a lease or lifecycle qualification. Check harness result /
failure records independently, including faults after the last marker.
Actual calibration and heap-write monitoring remain pending.


## Synthetic watchpoint calibration

`p4-heap-calibration-647e4858.patch` applies after the readback diagnostic and
adds a deliberately faulting calibration, not a production STT update. Its
`kHeapCalibrationCore` constant selects exactly one core (the patch selects 1;
18da8a44 selected 0). Preserve separate matching app/ELF/map/source identities.
A four-byte aligned RTC no-init word is initialized before arming; reads and an
adjacent store must return, then `hw1_heap_calibration_store_pc` names the exact
expected faulting store instruction. Verify it against the matching objdump.

Both cores must have the observed empty trigger shape before the test. A fresh
local read occurs under the saved IRQ mask immediately before the SDK arm call.
The retained record prevents automatic rearming after the trap. Recovery clears
only an exactly matching diagnostic trigger (allowing the documented hit bit),
preserves unexpected owners, and verifies both cores inactive. An already empty
state needs no trigger-data/control writes. The test changes no production
model, DSP, stack configuration, clocks or labelling policy. IPC callbacks do
not allocate, log or hold a cross-core lock. No panic-hook change is included.

`python3 tests/test_heap_trigger_lease.py HARDWAREONE` compiles the actual
lease/release header with ASan/UBSan and verifies refusal/owned cleanup/state
restoration. `python3 tests/test_p4hwcal.py` tests strict numeric evidence parsing.
To parse actual private logs, run:

```sh
python3 tools/device_tests/feature_cache/p4hwcal.py PRIVATE_TRAP_LOG PRIVATE_RECOVERY_LOG --core CORE --store-pc MATCHING_ELF_PC
```

The parser requires exactly one expected trap, the matching core/PC/cause, the
read/adjacent negative controls and unchanged watched word at recovery. It
rejects missing/duplicate/damaged markers, failed/refused calibration and extra
traps. Lifecycle health, serial-reset provenance, both-core complete readback
and full-slot rollback must be verified separately; numeric markers alone do
not prove these. Keep all raw logs/registers and app/debug images private.
Do not mistake a deliberate calibration trap for a successful STT lifecycle
or an unexpected production crash. Do not use the RTC calibration target as
evidence that DMA or every memory/cache path is monitored.
