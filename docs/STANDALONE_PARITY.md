# Standalone STT versus HardwareOne: confirmed gaps

**Update:** the [standalone port](STANDALONE_PORT.md) now implements the identified
reusable improvements and passes host/build checks. Fresh standalone device
qualification is pending. The comparison below is the preserved pre-port inventory.

Compared 31 October 2026. **Confirmed: STT development in HardwareOne has not all
returned to this standalone repository.** The standalone is a functional older
baseline, not feature/performance parity with the integrated application.

This comparison inspected the local HardwareOne working tree at HEAD `aa6508fd`
(28 October), including uncommitted changes in `System_STT.cpp`. It is source
evidence, not proof that every inspected line is in the installed 0.99.99 binary.
[The file/hash inventory](stt-source-parity.json) records the exact compared sources.
The standalone remote baseline is `a2ef959e85b6bba95f1cecf57768bd1ff075f8c9`, plus
its recovered October 21 transcript implementation and October 31 reports.

## What differs

The two `stt/` directories contain 13 byte-identical files, six different shared
files and seven files present only in HardwareOne. Differences in model-selection
headers are partly packaging, so file counts alone are not a count of improvements.

| Area | Standalone today | HardwareOne source today | Qualification needed |
| --- | --- | --- | --- |
| Cached weights and resident model | Already present; resident-model compile option enabled | Present | Do not reimplement this as a missing optimization |
| Capture-time features | Runtime accepts a feature prefix, but the app passes null and computes features after closure | Background feature task supplies cached rows; observed final cache reuse 94.1% | Extract scheduler/cache ownership and verify equivalence to batch frontend |
| Drafts and early finals | App publishes finals after closure; viewer handles simulated draft/speaker events only | Live drafts, cancel/preemption, speculative final computation and promotion | Test phrase identity, resumed speech, cancellation and bounded queue behavior |
| Trailing-silence policy | Trimming disabled; app commentary still describes older 200 ms policy | 500 ms retained tail, with early-final policy tied to trimming | Test quiet endings and WER; avoid silently applying a glasses-specific policy to the board microphone |
| Internal SRAM admission | Older free-heap/admission rules and resident heap-delta credit | Separate total/contiguous budgets, allocation observation and no LM eviction merely for internal SRAM pressure | Port helper files and host contracts; test fragmented/low-memory behavior |
| Watchdog handling | Temporarily reconfigures the global watchdog around inference | Retains watchdog subscriptions and uses bounded stage-loop blocking | Verify both-core watchdog health and throughput under sustained inference |
| LM controls and diagnostics | Existing LM/custom-word decode | Additional validated 0–1 LM-strength control and initial/final history diagnostics | Preserve default-strength results; test alternate settings against reference speech |
| Speaker assignment | Older clustering source; optional component is not used by the example | Abstains on ambiguous/unmatched evidence, validates inputs, exposes decision reasons | Speaker feature is not standalone-qualified; validate precision and label coverage |
| ESP-DL patch | Existing tiling/prepared-args/ReLU/PSRAM-metadata optimizations | Additional prepared-factor scratch reuse and metadata-backed temporary argument vectors | Treat patch/runtime as a compatible set; rebuild and check output equivalence |
| Vocabulary and display formatting | Portable `hw1_transcript` plus standalone storage/viewer | Related `stt_transcript` port and platform-specific vocabulary/storage adapters | Reconcile common behavior without replacing platform storage/authentication |
| Product integration | Board PDM mic, serial/localhost viewer, standalone SD/NVS adapters | Glasses audio, session broker, display delivery, account/VFS and app integrations | Keep these adapters separate from the reusable engine |

The shared acoustic frontend, segmenter, speaker embedding model implementation
and metadata helper sources compare identical. The shared runtime header also
matches; matching interfaces do not imply matching app scheduling or internals.

## Does the standalone work?

The recovered standalone app was built and physically qualified on October 21;
[the handoff](STT_PRODUCT_HANDOFF.md) records its exact app hash, device,
partition precautions and limited acoustic checks. On October 31 the actual
portable formatter/vocabulary code, production storage adapter, viewer and bridge
host suites all passed again. Storage tests used ESP-IDF's cJSON, and the HTTP
bridge test required permission to bind a temporary localhost server.

No fresh standalone firmware build, flash, long-running performance benchmark or
accuracy corpus was completed in this publication step. The new performance
numbers come from integrated HardwareOne 0.99.99, **not** this standalone app.
The host tests and earlier device checks do not establish current speed, speaker
accuracy, broad recognition accuracy, or complete SD power-loss recovery.

## Project direction: standalone first, HardwareOne adapter second

Use this repository as the future home for reusable STT behavior and benchmarks.
First reconcile the useful HardwareOne changes into portable modules, preserving
the existing tested baseline and making each change independently reviewable.
Do not copy the entire HardwareOne controller or substitute an older engine into
HardwareOne to make the directories match.

Suggested boundaries:

- Engine: acoustic frontend, cached/resident inference, LM decoding, optional
  speaker inference/clustering, bounded diagnostics and memory policy hooks.
- Streaming pipeline: segmentation, feature caches, preview cadence, speculative
  final ownership, queueing/cancellation and stable result events.
- Adapters: PCM input, clocks/tasks/allocation, storage/settings, output delivery
  and session ownership. Board PDM and glasses inputs use the same pipeline
  contract; HardwareOne keeps its account, VFS, BLE and display infrastructure.
- Qualification: fixed inputs/reference text, lean/debug controls, timing
  distributions, peak/live RAM and largest blocks, I/O activity and word errors.

## Reconciliation and acceptance order

1. Commit the recovered baseline, reports and gap inventory so another machine
   can reproduce the starting point.
2. Reconcile memory/watchdog fixes and the matching ESP-DL patch independently;
   keep default inference/decoder behavior and test numerical output equivalence.
3. Extract capture-time features, drafts and speculative finals with portable
   ownership/cancellation tests and a standalone adapter. Preserve full-audio mode.
4. Reconcile LM controls and optional speaker policy with dedicated accuracy
   fixtures. These change available behavior and need separate evaluation.
5. Perform a fresh standalone build and controlled device qualification for the
   chosen model/LM. Capture cold start, warm timing distributions, preview/final
   latency, live RAM peaks, storage calls and accuracy on fixed inputs.
6. After standalone acceptance, adapt HardwareOne to the qualified components and
   repeat integration tests for its audio, session, storage and display adapters.

The present commit preserves the baseline and makes divergence explicit. It does
not claim those ports or their device qualification are already complete.

Reproduce the inventory on a machine with both repositories:

```sh
python3 tools/report/compare_stt_sources.py \
  --hardwareone-root /path/to/hardwareone-idf \
  --output docs/stt-source-parity.json
```

Raw audio, transcripts, device logs, settings and rollback images remain outside
Git in ignored private directories.
