# Overnight code and diagnostics work queue

User direction: continue unattended research, accuracy and performance work;
future audible playback is 50% Mac output, onboard PDM only. The earlier 75%
recordings remain a distinct condition. Use silent replay/known-input testing
while the user sleeps. Do not change model weights, production thresholds,
preview/configuration settings, compiler tuning or RAM clocks/timings to claim
a gain. Diagnostic instrumentation is held equal within comparisons. No
unqualified candidate is left installed or automatically integrated elsewhere.
Push only `claude/spkeval-diagnostics` in this repository.

## Priority queue and concrete outputs

1. Finish and verify the current exact-PCM capture; download privately, remove
   owned nonce-bearing files and restore/digest-verify the original app.
2. Align actual speaker input waveforms with the source independently of console
   clocks. Audit missing beginnings/endings, discarded tails and model windows.
   Distinguish measured PCM evidence from energy-envelope/timing estimates.
3. Decompose representation differences: P4 versus Mac on identical microphone
   PCM; Mac on microphone versus waveform-aligned clean PCM; same/different
   speaker pair similarities. Keep raw audio/vectors private.
4. Correct and test replay input reconstruction. Recompute the six existing
   sessions in separate private audit folders; retain original historical data.
5. Run controlled start/tail/window sensitivity experiments. Report coverage,
   labelled accuracy, split and merge errors together, not a selected pair alone.
6. Evaluate promising code-based window selection on the frozen development
   speakers, preserving channel pairs and excluding final-test speakers. Use
   paired uncertainty and per-domain regressions to reject fragile gains.
7. Extend silent known-input P4 tests across selected development inputs near
   decision boundaries. Compare actual target embeddings, not Mac-only results.
8. Reserve the final speaker partition for a candidate that passes development
   gates; do not repeatedly use it to choose rules.
9. Audit portable capture/segmenter code for dropped/duplicated samples, ring
   indexing, pre-roll, pause/continuation boundaries and trimming/padding errors.
   A proposed fix needs a reproducing synthetic case and production C++ test.
10. Audit preview cancellation, speculative-final promotion, queue admission,
    result delivery and stop/drain for correctness or repeated-work bugs. Keep
    existing cadence/settings fixed; changes must repair or avoid actual work.
11. Profile allocations, copies, transforms and queue contention. Investigate
    scratch-buffer reuse and redundant computation with bounded lifetime/ownership
    and unchanged output. Report peaks and throughput, not source-level guesses.
12. Investigate the expensive 512-to-512 pointwise kernels and data movement.
    Try code/layout optimizations only with bit-exact fixture/reference checks;
    RAM/CPU clocks and model weights stay fixed. Preserve a tested rollback.
13. Audit decoder/caption assembly for code-only correctness and accuracy issues:
    dropped results, stale state or malformed boundaries. No vocabulary/LM-strength
    tuning, punctuation model or semantic rewriting is substituted for a fix.
14. Implement small, reviewable candidates supported by those audits. Keep each
    independent change isolated; benchmark unchanged baseline versus candidate
    on identical inputs and at least five matched runs where a gain is claimed.
15. For a promising target candidate, measure device computation, end-to-end
    delivery, transient memory/headroom and reliability. Reject an optimization
    if WER/labels, latency, memory headroom, overruns or crashes regress. Host
    tests alone do not qualify P4 performance or SD power-loss behavior.
16. Commit numeric findings, tool fixes, rejected candidates and remaining gaps;
    update the handoff and optimization plan. Retain selected app/debug/model
    identities and unique private evidence; clean disposable build outputs when
    the active profile is no longer needed. Leave the original P4 app restored.

## Checkpoint

Completed: 25 known-PCM P4 parity trials, five inputs/five reboots each, no
reported watchdog warnings or overruns; original app restored and verified.
A borderline clean pair flips from Mac 0.605987 to P4 0.595828, so float-only
replay is not a target-accuracy qualification.

Completed: source audit found session replay embedded the full captured span
instead of its retained speaker prefix. `spkreplay.py` now uses logged speaker
sample counts, with synthetic coverage. Six sessions were re-analysed in a new
private audit tree; historical source records/reports are preserved.

Completed: one bounded exact-input capture session (four packets, SHA-256 valid,
no reported watchdogs/overruns). Its raw vectors are unnormalized FC output;
the reader now validates finite nonzero vectors and cosine consumers normalize.
The capture files were removed and original app restored/digest-verified;
final probe reports logging inactive, PDM preferred and 6,520,832 B LittleFS free.
Waveform/embedding analysis is complete for this capture: the critical pair
is 0.642508 on P4 microphone input, 0.632405 on float with identical PCM and
0.585196 on aligned-clean float input. The current captured onset is intact;
the old failure cannot be declared a bad cut without its actual PCM. Mac volume was set and verified
at 50% after this last 75% playback. No further audible playback is planned while
working through the overnight silent queue.

Completed: production portable segmenter ASan/UBSan audit: 720 chunk-size
comparisons across 120 seeded configuration/stream combinations, 1,076 reference
segments, exact source PCM and boundary metadata. Continuous-voice hard-cut and
partial-end conservation and stopping with a pending quiet-cut suffix passed.
No segmenter correctness fix is supported by these synthetic results. Existing
portable streaming ownership/preemption/promotion tests also passed. Actual
HardwareOne transport/capture and broader code audits remain separate work.

Completed: silent fixed-input P4 frontend reference/candidate benchmark,
local HardwareOne source d6029017. Production frontend remains unchanged in the
diagnostic image; the candidate is a separate namespace. Shared PSRAM scratch
and output addresses, alternating paired order, six target bit-exact checks,
ten timing pairs per boot and five reboot trials. All 30 target feature checks
match. Mean saving 0.671467 ms (1.212441%), boot-bootstrap 95% saving
0.599460–0.743473 ms. This is an isolated frontend result; end-to-end qualification
is pending. Original app restored/full-slot-verified; owned fixture removed after
a strict reader-retry fix for interleaved debug output. Final LittleFS free
6,504,448 B. No reported overruns/watchdogs/fatal markers.

Completed: 44 silent float replay conditions on the four known conversation
playlists, varying one start/tail extraction boundary at a time with production
threshold/minimum length unchanged. These are diagnostic sensitivity probes,
not firmware setting changes, final-partition evaluation or selected gains.

Boundary sensitivity: 135 source phrases, 1,485 embeddings, 8,800 seeded order
simulations. The control scores 122/135 correct, 127 labelled. Removing the
clip-mode tail raises pooled correct to 128 and labelled to 130, but Conversation
4 regresses 100% -> 96.4% and Conversation 1 shuffled splits rise 45/200 ->
80/200. The 7850 clip 0/2 pair ranges 0.538–0.629 across boundaries with the same
float model. No universal padding policy or old-cut fault is established. Full
numeric tables and caveats are in AB_TEST_RESULTS.md; final speakers untouched.


Completed: full-acoustic-model pointwise address-walk probe c6252b6e. The
candidate removes repeated row/column address calculations only for one-column
rectangles. Tile sizes and assembly reduction bodies remain fixed. The extracted
real loop passed 600 ASan/UBSan cases (311 eligible, 145 one-column, 554,628
identical ordered body calls). Actual P4 hash/timing/memory comparison uses five
reboots, four warm-ups and three alternating pairs per boot. No live audio or
production integration is implied by this probe; original-slot restoration is
mandatory. Selected debug/source artifacts are retained and the same owned
build directory stays active for the overnight profile.

Result: 50/50 feature/logit/greedy-text hash matches across both modes and all
five boots. Each inference exercises 184 tiled one-column calls, 106 for 512→512.
Inference change +1.157667 ms, 95% [-3.437533, +5.275533] ms; no measurable
improvement. Headroom observations match; no reported watchdogs/overruns/fatal
markers. Candidate rejected for promotion. Fixture removed, original app restored
and full-slot-verified, final probe LittleFS free 6,422,528 B/logging off/PDM.

Next bounded ownership audit: HardwareOne System_STT.cpp's feature worker writes
rows outside gSTTMux, while sttFeatureRetireOrphans/sttFeatureRelease wipe those
rows outside that lock. A source-level race is suspected, not reproduced or tied
to the historical allocator faults. Extract the real worker/retirement code with
host lock/task stubs and a barrier around the real log_mel_frame_ring call;
run ThreadSanitizer before proposing a fix. Standalone StreamPipeline instead
computes a private row and commits it under its lock. Keep physical ring access
and committed-prefix ownership separate in any conclusion.

Next traffic measurement: the local IDF 5.5.5 hw_ver3 cache_reg.h exposes L1
DBUS0/1 access counters. The designated chip reports revision v3.2, and the
current build is min 3.01/max 3.99. Counter setup/readback semantics, overflow,
prior ownership and correlation to PSRAM transactions still need verification;
do not call cache counters PSRAM bytes or change cache/clock policy. These are
measurement candidates, not completed traffic evidence.


The playback harness's read-only `--expect-volume` default is now 50, matching
the explicit user request and already-set Mac output. Historical runs used
explicit 75 and remain unchanged. This default does not start playback or set
volume; it prevents future default invocations from expecting an obsolete level.

Build continuity: the active local HardwareOne source is
`codex/stt-ab-pointwise` at c6252b6e. Its prepared SDK override uses patch SHA
710aa9beda822bf9c1844d292ad323ccab179198d4885f0bcccef9ba9b59f2f7 and tree SHA
38fe78ed779f143dc413a7947b6c59b006abccd25d6d5ff62946be2a7df09ed1.
After switching source branches, verify/restage the matching reviewed SDK rather
than building against that experimental override silently. The original SDK
patch remains preserved by Git; selected matching app/debug/source evidence is
already archived privately. Keep the owned profile build only while still used.
