# Compare two speech exports

Use `tools/stt_p4/release_benchmark.py` to compare the current export and a
candidate on the same frozen development suite. It compiles the portable C++
frontend with production inference dither disabled, verifies each model's
exported reference output, and applies the same saved language model to both
sets of acoustic scores. For mixed precision, use the project exporter Python
environment and the trusted native graph produced alongside your own export.

Each suite JSON specifies `sample_rate: 16000` and a list of `cases`. Each case
has a unique `id`, a `condition`, `partition` set to `dev`, and `kind` set to
`speech` or `silence`. Use `silence` for a verified no-speech background as well.
The `pcm` path is relative to the suite directory and points to uncompressed
little-endian mono 16-bit samples. Supply its `pcm_sha256` and a `source_hashes`
list containing the original PCM digests before any concatenation or transform.
The script checks these against the exports' calibration audio.

For speech, `reference_groups` contains the normalized reference text of each
annotated utterance in playback order. Supply an empty list for no-speech
audio. The `spans` list contains the nonoverlapping half-open sample ranges fed
to recognition, in order. For a single full clip, specify `[[0, sample_count]]`.
For endpointed cases, freeze the spans emitted by the production scheduler.
An empty span list means the scheduler emitted no caption. Use cases with
annotated joins and actual forced cuts to measure boundary behavior.

Run from the repository root. The Python environment needs the export and
training dependencies. The checkpoint loader uses the project's existing
weights-digest allowlist. Set its documented environment override for the
verified gen2 checkpoint when applicable. To compare two different custom checkpoints,
pass the independently verified digests with `--baseline-weights-sha256` and
`--candidate-weights-sha256`. Each override applies only to its own checkpoint.

~~~sh
python tools/stt_p4/release_benchmark.py \
  --suite /path/to/frozen/suite.json \
  --baseline /path/to/current/export --baseline-checkpoint /path/to/checkpoint \
  --candidate /path/to/candidate/export --candidate-checkpoint /path/to/checkpoint \
  --lm /path/to/meeting.lm --trusted-local-native \
  --output /path/to/new/private/results
~~~

The command writes `comparison.json` and separate per-case reports. Review overall
and per-condition word edits, substitutions, deletions, insertions, first/last
reference-word outcomes, identical words on adjacent caption joins, and words
per minute on no-speech audio. The latter denominator includes the entire input
recording, including periods when the scheduler emitted nothing. The first/last
word counts follow one minimum-edit alignment and can be ambiguous for repeated
words. Conditions sharing source speech provide paired sensitivity tests.
The command reports suite, model, decoder and frontend identities with the
results. Keep references, hypotheses and PCM under the project's private folder.

The suite used for the twelve investigations is under
`private/sequential-stt/12-release/suite.json`. The following command reruns
the measured baseline/candidate comparison on this workstation. Choose a new
output directory for each invocation. The original per-case outputs and
aggregate comparison are in `private/sequential-stt/12-release/block14/`.

~~~sh
deploy=/Volumes/Audiodrive/stt/work/deploy15
ckpt="$deploy/ckpt-gen2-25397"
digest=e1873cc934e7c645c8d8b91dbe60834a3d0ff623e8eb3b700ef132159d24be6d
private/layer-sensitivity-20261103/export-venv/bin/python -B tools/stt_p4/release_benchmark.py \
  --suite private/sequential-stt/12-release/suite.json \
  --baseline "$deploy/export-gen2-25397" --baseline-checkpoint "$ckpt" \
  --candidate private/layer-sensitivity-20261103/export-block14 --candidate-checkpoint "$ckpt" \
  --baseline-weights-sha256 "$digest" --candidate-weights-sha256 "$digest" \
  --lm /Volumes/Audiodrive/stt/work/lm/meeting-gen2-25397.lm \
  --trusted-local-native --output private/sequential-stt/12-release/block14-repeat
~~~
