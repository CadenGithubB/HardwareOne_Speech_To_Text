# Standalone audio-path and window-selection experiment

This implements the first standalone development round from
[SPEAKER_NEXT_EXPERIMENTS.md](SPEAKER_NEXT_EXPERIMENTS.md). It audits the existing
frontend, provides an opt-in portable window selector, and evaluates two fixed
selection policies. No policy has qualified for HardwareOne integration.

## Components and behavior

- `speaker_frontend.cpp` is the existing production C++ frontend; its behavior
  is unchanged. Its header comment now states the actual order: crop PCM first,
  extract features, normalize over retained frames, repeat short feature rows.
- `firmware/components/hw1_stt/stt/speaker_window.h` is an experimental opt-in
  selector. No production caller invokes it. It requires caller-provided
  workspace and preserves a contiguous audio range.
- `speaker_audio.py` / `audio_frontend_bridge.cpp` compile and call the actual
  native frontend and selector on identical int16 PCM.
- `spkaudioaudit.py` compares native/Python features and embeddings through the
  same unchanged float speaker model. It does not emulate quantized inference.
- `spkwindows.py` freezes speaker partitions, embeds fixed policies, and scores
  them with the unchanged production C++ clusterer at threshold 0.6.

The model's trained feature normalization remains in place. Very close
native/Python agreement rules out a large discrepancy between those two
implementations on the audited inputs; it does not establish that every
preprocessing choice preserves all useful identity information.

## Policies fixed before development evaluation

1. `center`: production center crop, maximum 47,840 samples (2.99 seconds).
2. `activity`: the contiguous window with the greatest energy-active frame
   count, preserving the original maximum length. Prefer the original center
   when tied.
3. `trim_activity`: trim inactive ends with 100 ms of context and then use the
   activity selector. Shorter features are repeated using the existing frontend.

Activity uses 20 ms RMS frames and 10 ms hops. Its fixed threshold is the larger
of 32 int16 RMS units and one tenth of the phrase's 90th-percentile frame RMS.
This is an energy heuristic, not a learned voice-activity or speaker-change
detector. Noise and a different speaker can qualify as activity. No reference
speaker or clip annotation is used to choose a window.

All policies preserve the original reference, mixed-phrase flag and supplied
duration for clustering. This isolates embedding-window selection; it does not
also change the new-speaker minimum or solve the padded-duration issue.

## Evaluation split and results

All 64 reference IDs present in earlier voiceprint experiments were excluded.
The new source stores are paired clean/simulated-channel versions of
`librispeech-test-clean`, `ami-ihm-test` and `voxpopuli-validation`. Eligible IDs
are deterministically divided before embedding, keeping the same ID and both
channel versions on the same side. Development has 37 IDs and final testing
has 36. These are dataset-ID guarantees, not verified identity de-duplication
across unrelated corpora or a claim about the pretrained model's training data.

Only development audio was embedded/scored. It contains 180 synthetic corpus
conversations (30 per channel store, 24 turns each), plus the four old clean
playlists and five old session-span diagnostics: 189 sets / 4,654 phrases.
The final partition has not been embedded or scored. Old cases are diagnostics,
not an independent validation sample. Corpus dialogues share speakers, and
shuffles are order sensitivity trials.

On 30 speech cases from 15 development IDs, native/Python feature RMS error was
at most 2.08445e-6 and resulting float-embedding cosine was at least 0.99999940.
The audit also includes ten synthetic edge cases. These results do not isolate
device quantization, microphone processing or the physical playback channel.

On pooled development corpus, activity selection changed coverage from 88.9%
to 90.0%, labelled accuracy from 90.8% to 91.4%, split phrases per 100 from
7.78 to 7.57 and merge phrases per 100 from 0.56 to 0.44. All paired 95% delta
intervals include zero. There are also domain-specific regressions; the policy
is not qualified by the aggregate direction alone.

Trimming worsened the original Conversation 1 clean case: first/third-clip
similarity dropped from 0.6060 to 0.5706, coverage from 100% to 68.8%, and split
phrases per 100 increased from 0 to 9.38. This argues against deploying this
aggressive energy-based trimming rule. Detailed distributions, per-store
results and confidence intervals are in [AB_TEST_RESULTS.md](AB_TEST_RESULTS.md).

Neither selector passes the current quality gate. HardwareOne was not modified
or flashed. The final-test partition is reserved for a development-qualified
candidate, rather than repeatedly used to choose rules.

## Reproduction

Use the existing model environment with numpy, scipy and torch, `STT_ROOT`, and
`HW1_SPEAKER_CLOVA`. Paths below are examples within ignored private storage;
embeddings and partition IDs must remain there.

```sh
umask 077
mkdir -p private/speaker/audio-window
python tests/test_speaker_audio.py
python tools/device_tests/speaker/spkwindows.py plan private/speaker/rule-sets.json \
  private/speaker/audio-window/plan.json --root "$STT_ROOT"
python tools/device_tests/speaker/spkaudioaudit.py \
  --plan private/speaker/audio-window/plan.json --per-store 5 \
  > private/speaker/audio-window/frontend-audit.json
python tools/device_tests/speaker/spkwindows.py run \
  private/speaker/audio-window/plan.json private/speaker/audio-window/development.json \
  --partition development \
  --embeddings private/speaker/audio-window/development-embeddings.json
```

Add repeated `--manifest` and `--session` arguments for the old diagnostic
recordings. Omitting them evaluates the new development corpus only. The
experiment refuses to overwrite the plan and main result/embedding files.

## Transfer and remaining checks

The reusable selector is additive and opt-in. A successful future candidate
would be transferred to HardwareOne as a small reviewed adapter change with
shared PCM/selection fixtures, not by replacing its engine directory. The
current selector must not be enabled as a qualified improvement.

Workspace is `2*frames+1` floats: 7,996 bytes for a ten-second input, plus
metadata and sorting stack. The host bridge additionally allocates frontend
and result buffers; that is not the intended firmware allocation pattern.
P4 runtime, wall-clock label latency and memory peaks are unmeasured. Full
quantized-path parity and matched microphone input remain gaps. Native
sanitizer tests and numerical float parity do not fill those gaps.
