# Microphone quality across P4 and G2

**The shared STT route already accepts raw PCM from both microphones. We found no unintended recorder gain or duplicate recorder filtering in that route.** Recorder-style processing improved this small physical screen on both sources, but it also changed some captions for the worse and clipped louder compatibility inputs. Retain the current shared path pending broader qualification.

## Scope and decision criteria

Identify whether capture processing loses useful speech, and whether a proposed correction works with both microphone sources. Keep recognition, caption admission and source transport as separate measurements. A physical comparison must use the same playback, level, distance and reference. Software processing comparisons must use identical samples within each source. Preserve ordinary and loud speech, background-caption behavior and capture integrity before promoting a change.

## Installed source audit

The selected app build manifest names clean source revision `048275882ea796e14398d9d0303e7ae7f746a5e3`. Its ELF names the adoption checkout. Relevant HAL, STT, recorder and G2 source files were read from that exact Git revision and saved with hashes under `private/dual-mic-quality/source-provenance.json`.

The source routes are:

- P4 digital PDM microphone → I2S conversion → raw mono PCM → STT.
- G2 microphone → LC3 packets → signed 16-bit LC3 decode → PCM ring → STT.
- Both enter the same recognition frontend and decoder.
- Manual PDM recording additionally uses recorder DSP. Manual G2 recording bypasses that PDM-specific DSP.

The recorder’s `micgain` knob is software multiplication. At the observed setting of 50, the configured multiplier is 24, not unity. That recorder setting does not occur in STT’s read path. The recorded source preference was PDM, with 16 kHz and 16-bit settings. Treat these as recorder settings, not proof that the STT path applies the same processing.

The P4 clock adjustment is already implemented in its hardware adapter. At 16 kHz, it selects the decimation setting that avoids this board microphone’s forbidden PDM clock band. G2 uses decoded 16 kHz audio and does not use that clock. Hardware-specific capture settings can stay in their adapters while sharing a consistent PCM contract and recognition path.

## Processing A/B

The fixed host experiment compares raw input, recorder DC removal alone, recorder DC removal with 24× gain, and the recorder’s DC/high-pass/pre-emphasis chain with 24× gain. The actual recorder function and constants were extracted from the installed app revision and compiled as a host executable. State resets per six-second clip, processing 1,024-sample reads. This measures the proposed processing change, rather than merely comparing different recordings.

Inputs comprise 16 actual P4 recordings from orientation A and 16 codec-only compatibility proxies made from the corresponding digital playback files. The latter pass through the repository’s LC3 wrapper at the G2 stream settings. They do not represent the physical G2 microphone, its automatic level behavior, radio loss or live connection. Each arm measures full-window word errors, clipped samples and final admission counts. Counting admitted segments does not establish their final transcript accuracy.

The raw P4 arm is required to reproduce all previously verified physical P4 transcripts. The actual C++ frontend, deployed int8 graph and saved language model stay fixed. No shared gain, source setting or microphone processing change has been deployed.

## Real microphone results

All speech counts below are full-window word edits, with 73 reference words per cell. The same raw samples are used for all processing arms within a source. The eight phrases consist of four human meeting excerpts and four synthesized controls, repeated at two playback levels.

| Source and level | Raw STT input | DC removal | DC + 24× gain | DC, high-pass, pre-emphasis + 24× |
|---|---:|---:|---:|---:|
| P4, quiet | 45 | 44 | 49 | 43 |
| P4, ordinary | 28 | 27 | 23 | 22 |
| G2, quiet | 48 | 47 | 45 | 45 |
| G2, ordinary | 25 | 26 | 26 | 20 |

The complete recorder chain reduced total errors from 73 to 65 on each physical microphone set. On P4 it improved five phrases, tied nine and worsened two. On G2 it improved six, tied seven and worsened three, including one ordinary phrase. Neither physical set clipped in any of the four arms. These small, repeated-phrase development screens establish an effect of processing. They do not establish a general improvement for users.

The P4 data came from the earlier 16 isolated orientation-A recordings. All raw P4 transcripts reproduced their previously device-verified hypotheses. The real G2 data came from a new continuous recording of the same playback files, after the user confirmed the glasses were near the P4 and speaker. The source selection was strict G2. The installed recorder bypasses PDM DSP for that source, so its WAV supplies raw decoded G2 samples.

The microphones were recorded at different times, with different window lengths and device bodies. These are paired processing comparisons within each microphone. Their scores cannot establish which physical microphone is intrinsically better.

## Loudness compatibility and source safety

The separate LC3-only proxy has the same playback references but bypasses physical microphone and room effects. Its ordinary-level errors increased from 10 to 50 with DC plus fixed 24× gain and to 17 with the full recorder chain. Those arms clipped 178,794 and 26,253 samples respectively, versus zero raw. Quiet proxy errors changed from 14 raw to 15 with gain and 16 with the full chain. These results expose the headroom risk of applying one fixed boost to every valid G2-style PCM input.

The proxy is not an additional real G2 microphone test. It is a compatibility check for decoded audio levels that the shared path can encounter. In particular, a gain that benefits the low-amplitude P4 recordings is insufficient evidence to apply that gain to every source.

Keep source-specific conversion and transport inside each adapter. Both adapters should supply correctly timed mono signed 16-bit PCM at 16 kHz to the shared frontend. A future common conditioning candidate needs gain bounded by headroom and should be tested against noise and loud speech. Testing a P4 clock setting does not require imposing a PDM clock on G2, whose adapter decodes LC3 instead.

## G2 capture integrity and timing

The initial connection scan failed while the antenna was disconnected. After the user connected it, the device reported G2 available. One early harness attempt used a recording ID with a zero counter and was rejected before capture. That is a test-controller error, excluded from acoustic results.

Two subsequent attempts each recorded their first phrase successfully, then reported `audio source stalled` on the next owned recording. Closing and reopening the microphone between phrases did not prevent that second-recording failure. Both attempts and their first valid recordings are preserved. These observations concern the exercised owner-correlated bench recording lifecycle. They do not prove that native G2 STT sessions have the same failure.

A single continuous playback avoided rearming and completed without the recorder's degraded flag. It produced 904,800 samples (56.55 s). Transfer validated sequential byte offsets, decoded lengths and a constant total WAV size. The WAV and PCM were saved privately, then the original PDM source preference and disabled/idle recorder state were verified.

Phrase extraction required accounting for timing between playback and captured samples. Eight ordinary-phrase waveform landmarks gave an affine capture position of approximately 9,420 samples plus 0.994576 times the source position. The largest residual was 214 samples (13.4 ms). Six landmarks exceeded absolute normalized correlation 0.20 and the other two measured 0.198 and 0.193. Each crop retains 150 ms before and after the estimated phrase.

The first constant-offset alignment and a stricter all-eight correlation check both failed. The retained alignment uses the consistent timing trend and eight position checks. Only the reference was resampled for locating landmarks. Recognition uses the original G2 samples. The timing trend could involve playback clocks, device clocks or stream delivery; this test does not identify the cause.

G2 processing state runs over the entire continuous recording before slicing, preserving its actual 1,024-sample processing boundaries. P4 processing state resets per physical recording. Per-crop segment-admission counts in the private results are supplementary isolated replay measurements, not a live streaming qualification.

## What the evidence supports

There is a measured recognition loss across the physical capture path and a measured response to conditioning. The source audit does not support an accidental shared gain/filter setting as the explanation. Both raw source sets emitted no quiet segments in the supplementary isolated replay. The tested recorder chain admitted additional segments, but its full-window quiet recognition still made 43 P4 errors and 45 G2 errors on 73 words per source. Source amplitude, speech admission and acoustic recognition remain separate contributors.

Retain the current production path. The next shared conditioning experiment should separate the high-pass/filter benefit from gain, cap gain to preserve loud-speech headroom, and include background-caption controls for both sources. The recorder rearm failure also merits a dedicated G2 lifecycle test. None of these follow-ups justifies applying the P4 recorder chain indiscriminately to G2.

## Reproduction and scope

Private evidence is under `private/dual-mic-quality/`. `source-provenance.json` pins the installed code. `ab-manifest.json`, `ab.py` and `ab-*.json` hold the P4/proxy comparisons. `g2-continuous-01/` holds the actual G2 WAV, PCM, alignment, crops and restoration state. `g2c-ab-*.json` holds its four-arm scores. `compare_real.py` and `audit.py` aggregate and verify the results. All 192 arm records passed the final audit. The 128 real-microphone arm results and 64 codec-proxy results are reported separately.

No model, firmware image, shared gain or source-processing default was changed. This work does not qualify long-running capture, G2 packet-loss handling, speaker-label accuracy, queue pressure, power use or P4 latency for a new preprocessing candidate.
