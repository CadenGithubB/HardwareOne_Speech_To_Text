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
abort/symbolizer behavior. Host lock/task adapters use a mutex and a scheduling
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
