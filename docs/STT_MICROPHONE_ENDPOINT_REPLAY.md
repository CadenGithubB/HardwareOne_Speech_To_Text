# Speech detection on the saved P4 recordings

The current caption segmenter suppressed all eight quiet microphone recordings in the orientation-A set. Complete-window recognition made 45 word errors on their 73 words. With no captions admitted, the segmented path missed all 73 words. This exposes a speech-admission problem on these inputs before recognition.

| Saved microphone input | Whole-window errors | Default full-tail segmentation | 500 ms tail segmentation |
|---|---:|---:|---:|
| Ordinary, 73 words | 28 | 41 | 43 |
| Quiet, 73 words | 45 | 73 | 73 |

Both modes suppressed all eight quiet phrases and two ordinary phrases. These comparisons use identical recorded samples, the portable C++ frontend without dither, deployed int8 weights and the same language model. The actual C++ StreamPipeline was replayed with a synchronous final worker. This isolates endpoint behavior from queue contention. Raw final hypotheses were scored against the same references.

Each six-second recording starts a fresh segmenter, including its 500 ms calibration. It ends with an explicit finish. This is an isolated-phrase admission test. Continuous listening may maintain a different noise estimate and requires a separate check. The default adaptive speech floor is 45 in native PCM RMS units. Input levels and the adaptive noise estimate both influence admission. Lowering that floor remains an untested candidate.

The next controlled firmware experiment is a bounded admission-threshold A/B on the saved quiet and ordinary recordings, paired with background-only and non-speech false-caption checks before live qualification. Keep recovery and false captions as separate acceptance gates.

Evidence is under `private/mic-boundaries/` and `private/mic-boundaries-full/`. Those directories preserve the actual C++ replay source, binaries, per-case sample cuts, transcripts and scores. No threshold was changed by this experiment.
