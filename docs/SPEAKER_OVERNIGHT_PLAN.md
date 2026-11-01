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
