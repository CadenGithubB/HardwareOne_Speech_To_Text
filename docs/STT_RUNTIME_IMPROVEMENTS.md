# Standalone STT runtime improvements

This work belongs to the reusable STT engine and standalone captions app. Training,
corpus preparation, quantization investigations and their tools are being handled
in another session; do not modify or stage that work. Keep recognition weights and
speaker identity algorithms fixed while qualifying runtime changes.

## Concrete targets found in the current source

| Priority | Improvement | Current evidence | Acceptance check |
|---|---|---|---|
| 1 | Draft scheduling and first-preview recovery | `stt_stream.cpp::take` uses the previous draft's elapsed time even for a new phrase. The standalone scheduler also lacks the tested x2f option. | Exercise actual scheduler sample thresholds, new-phrase reset, final priority, cancellation and ownership. Then measure standalone first draft, shown-text freshness, final text and labels on repeated fixed fixtures. |
| 2 | Reduce capture-lock contention | `take` copies a PCM snapshot and `complete` clears it while holding the stream lock. `retire` clears a whole feature cache under that lock. With the example's ten-second capacity, a snapshot is up to 320,000 bytes and each feature cache is 256,000 bytes. | Measure lock hold/wait and capture backlog on P4. Reduce copying/clearing inside the lock while preserving ownership, privacy clearing, feature generations and exact PCM. These byte counts are source-derived, not measured stall times. |
| 3 | Faster inference with unchanged weights | The earlier integrated profile attributes most acoustic time to convolution, with large pointwise layers prominent. The standalone already has tiling/prepared-argument patches; their presence is not proof that no further reuse/layout gain exists. | Profile current standalone layers, then compare one kernel/layout change with bit-exact logits, decoded text, stage time and memory. Historical HardwareOne timings are not a fresh standalone baseline. |
| 4 | Reliable and explainable speaker results | `speaker_adapter.cpp` has four PCM jobs. Admission failure emits unknown; a full result queue logs and omits the result. Worker wall/total lag exist, but admission, queue wait and terminal completion coverage are not separately reported. | Account for every submitted phrase through known/unknown/canceled outcomes; bound backlog and measure queue versus execution time. Preserve the current embedding model and identity rules. |
| 5 | Expose recognition fallback | `decodeWithLanguageModel` falls back to greedy decoding if the LM is unavailable or decoding cannot allocate. `STTLocalStats::lmUsed` exists, but final recording events do not include it. | Record the actual decoder mode/reason per final, including speculative promotions, and exercise missing-LM/low-memory paths. This prevents silently comparing different recognition configurations. |
| 6 | Standalone qualification using its real event protocol | Existing broader microphone bench evidence is mostly HardwareOne, while this app emits product JSON events and has its own scheduler and profiles. The port report explicitly leaves fresh standalone quality/performance qualification open. | Adapt the runner to the standalone protocol with pinned model/config hashes, sample/host clocks and complete text/label outcomes. Keep the same private fixtures and speaker output settings; no audio upload is required. |

Endpointing/quiet endings remain an accuracy constraint on all candidates. Do not
repeat already rejected pause changes or promote hold/merge rules from conv1.
Preserve raw captions separately from display formatting. None of the candidates
above requires retraining or a punctuation/summary service.

## Implemented: optional x2f scheduler

`StreamConfig::draft_pacing` now accepts `DraftPacing::X2FastFirst`. It retains a
one-second first-preview audio floor; subsequent drafts require at least 600 ms
of new audio or twice the previous draft compute duration. New phrases ignore the
previous phrase's compute duration. Final work still takes priority, and exact
speculative-final reuse and cancellation are unchanged. Wide arithmetic prevents
elapsed-time multiplication/addition from wrapping on the 32-bit P4.

The default remains `Legacy`. Enable the new option through
`CONFIG_CAPTIONS_X2F_DRAFT_PACING` or layer `sdkconfig.x2f` over the base config.
This option changes only draft scheduling, without enabling tail trimming or
changing closing pauses. Programmatic callers can set `draft_interval_ms=0` to
use adaptive audio growth alone; a nonzero explicit wall-clock floor is honored.
The standalone adapter selects zero for this optional mode.

Actual C++ scheduler tests pass with address/undefined sanitizers. They cover the
one-second first-preview floor, exact 600 ms and x2 thresholds, a slow previous
phrase, large elapsed values, explicit wall-clock limits and the retained legacy
policy. Both modes run the concurrent ownership and bit-exact cached-feature /
draft-preemption cases. Existing exact-promotion, resumed-speech, hard-cut,
stop/cancel, queue overflow and stale-generation cases also pass. ThreadSanitizer
passes after its positive/negative memcpy controls confirm that copy races are
observable. These are host correctness checks, not a P4 speed or accuracy claim.

P4 opt-in build passed with ESP-IDF 5.5.5, actual 64-byte L2 / 200 MHz PSRAM
and `CONFIG_CAPTIONS_X2F_DRAFT_PACING=y`. The app is 645,968 bytes. This retains
the standalone base profile speed; it does not adopt HardwareOne's 250 MHz setting.
Device playback, first-draft/final/label latency,
WER/speaker accuracy and long-session behavior remain unqualified for this
standalone change. No device or HardwareOne source is modified by this task.

Private evidence and prior build artifacts are in `private/stt-runtime-20261103/`.
The cached SDK override predated the current pinned patch; it was preserved there
and the current reviewed override was staged and digest-verified before building.
The existing build directory is reused with a separate private candidate sdkconfig;
the prior root sdkconfig is preserved and no source defaults were changed.
