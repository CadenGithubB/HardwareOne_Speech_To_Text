# Corrected splits and fixed-model baseline — 3 November 2026

This work follows the training diagnostics audit. It prepares independent working
manifests and a fresh screening/reserve pair, then compares the saved gen2 model's
float, frozen-int8 and language-model outputs. It does not retrain, recalibrate,
change the installed device, or qualify production behavior.

## Corrected working data

The working root is `private/training-baseline-20261103/corrected/`. Its `stores/`
contains copied indices/filters and independent exclusion manifests. Existing large
`audio.bin` files are linked to the original drive and used read-only; they are not
independent backup copies. Do not run audio-writing preparation tools against these
links. Original manifests are retained under `original-manifests/` and checked
against the originals after preparation.

`prepare_split_baseline.py` applies a conservative policy: test speakers take
precedence over development speakers, and both take precedence over training.
Unknown speaker identities are excluded. This is a future-use split repair; it
cannot erase exposure from models already trained.

| Store/view | Excluded examples | Excluded audio hours | Reason |
|---|---:|---:|---|
| AMI headset training | 437 | 0.449 | Reserved speaker identities |
| AMI distant-mic training | 437 | 0.449 | Same affected speech in the other microphone view |
| VoxPopuli training shard A | 13,056 | 31.561 | 11,840 missing IDs; 1,216 reserved-speaker examples |
| VoxPopuli training shard B | 6,181 | 15.194 | 6,021 missing IDs; 160 reserved-speaker examples |
| VoxPopuli development | 23 | 0.048 | Speakers also present in the existing test partition |
| VoxPopuli existing test | 164 | 0.382 | Missing speaker identities |

The matching G2-simulated VoxPopuli development/test views receive the same
exclusions. Do not count those views as independent speech. Other original stores
retain their effective example lists. The large VoxPopuli reduction is an explicit
tradeoff for defensible speaker separation; the excluded audio is preserved and
could be reconsidered if its identity metadata is recovered. No claim is made that
its speech/transcripts are unusable.

## Fresh Common Voice screening and reserve

`prepare_fresh_commonvoice.py` uses already downloaded `en_train_5.tar` and its
`train.tsv` metadata. It excludes every speaker ID in every current Common Voice
store, including rows outside quality filters. Candidate speakers/clips are ordered
by a fixed SHA-256 seed; selection never uses a model's recognition score. Clips
must be 2–10 seconds with the established transcript normalization/CTC checks.

| Partition | Clips | Speakers | Audio |
|---|---:|---:|---:|
| `commonvoice-fresh-dev` | 64 | 32 | 366.444 seconds |
| `commonvoice-fresh-test` | 64 | 32 | 381.157 seconds |

Independent checks found zero speaker-ID overlap with the 17,169 IDs in existing
Common Voice stores, zero overlap between the two new partitions, and no identical
PCM hashes across the 128 new clips. None of their normalized references occurs in
the existing Common Voice stores. Metadata/audio provenance and exact selections
are retained privately in `fresh-selection.json`.

The screening set becomes development data as soon as its results are examined.
The reserve is not scored. Hashing or inspecting reserve identities is not a model
evaluation. Nineteen stored training logs were fingerprinted; their reported source
mixtures agree with the known nine training stores. This supports separation from
our recorded fine-tuning pools, not a guarantee against undocumented experiments,
alternate speaker accounts, cross-corpus identities, or NVIDIA pretraining exposure.
This is a small read-speech screen, not a meeting, accent-subgroup or microphone
qualification set.

## Frozen identities and evidence

- `split-receipt.json`: original-manifest hashes, exclusions and before/after counts.
- `combined-audit-metadata.json`: split/shape/range checks across all corrected stores.
- `frozen-audit.json`: emitted only after full audio SHA-256 verification and a second
  unchanged-input/speaker check; do not substitute an in-progress status for it.
- `verification-progress.json`: explicit progress/completion status for the full audit.
- `fresh-independent-check.json` in the parent run directory: independently checked
  speaker/PCM separation.
- `history-audit.json`: hashes and recorded source mixtures of available training logs.
- `baseline-identity.json`: saved checkpoint, export, quantization and LM hashes,
  evaluator code identity and Python package versions.

All speech, references, hypotheses, detailed results and private source paths remain
under the ignored run directory. Frozen copied manifests are made read-only when
full verification completes. Source audio is still externally mutable; rerun the
content audit before future training if it may have changed.

## Offline comparison method

The checkpoint is saved gen2 step 25397, acoustic weights SHA-256
`e1873cc934e7c645c8d8b91dbe60834a3d0ff623e8eb3b700ef132159d24be6d`.
The existing 102-clip-calibrated export is reused without recalibration. Frozen CPU
int8 inference must first reproduce both original exported fixture outputs exactly.
The saved `meeting-gen2-25397.lm` is used with its unchanged header settings.

The private virtual environment adds ONNX 1.17.0 and protobuf 5.29.5; it references
the existing training environment's Torch/NumPy/SciPy packages read-only. Thus it
isolates the new installations but is not a self-contained copy of every dependency.
Exact package versions and paths are recorded for reproducibility.

The same 64 screening clips go through float, frozen int8 and LM decoding. The
linked comparator checks audio, references, coverage and model identity. The report
must remain `complete: false` with `streaming` missing until a matched measured
capture is supplied. The two-clip probe is only an implementation check and must
not be pooled with the 64-clip screen as extra accuracy evidence.

## Validation status

The 22 existing training-diagnostic checks and three new split-preparation tests
passed. The preparation tests check source preservation, existing filters,
numbered training shards, unknown-ID exclusion and test/development precedence.
The real two-clip probe passed byte-exact export-fixture parity and produced both
float and int8 stage records. Full verification and the 64-clip comparison results
are recorded below when complete.

## Completed offline screening results

The unchanged model/export/LM completed all **64 clips / 32 speakers / 633 words**.
Both export fixtures reproduced byte-exactly before the int8 run. The two-clip
probe is excluded from these counts.

| Stage | Word errors | WER | Substitutions | Deletions | Insertions |
|---|---:|---:|---:|---:|---:|
| Portable float, greedy | 95 | 15.01% | 88 | 2 | 5 |
| Frozen int8, greedy | 112 | 17.69% | 99 | 4 | 9 |
| Frozen int8 + saved LM | 103 | 16.27% | 85 | 11 | 7 |

Float → int8 adds **17 edits / 2.69 percentage points**: seven utterances improve,
17 worsen and 40 retain the same edit count. The LM recovers nine edits overall:
12 utterances improve, two worsen and 50 retain the same edit count. It reduces
substitutions while increasing deletions; do not describe every error type as better.
Identical edit counts do not necessarily mean identical text.

A descriptive paired bootstrap resampling speakers (both clips retained together,
10,000 draws, seed 20261103) gives a 95% percentile interval of **+0.78 to +4.73 pp**
for the int8-minus-float WER difference. The LM-minus-int8 interval is **−2.91 to
+0.17 pp**, and LM-minus-float is **−0.74 to +3.55 pp**. These are exploratory
small-screen uncertainty summaries, not confirmatory general-accuracy claims.

No sampled input/output values reached the reported int8 limits. That does not
rule out internal-layer saturation, rounding error or calibration sensitivity.
The first bounded accuracy experiment should investigate the quantization loss
on this now-development set, keeping weights and decoder settings fixed, before
spending another full training run. Existing float errors still account for most
errors in absolute terms; this screen does not establish quantization as the
largest overall product limitation.

`comparison.json` explicitly reports `complete: false` and `missing_stages:
["streaming"]`. There was no hardware access. The separate 64-clip/32-speaker reserve
was not evaluated. Private `baseline-summary.json` contains the counts, paired
changes and bootstrap intervals; detailed hypotheses remain in private stage files.
The new environment's `pip check` also passed.

## Full data verification completed

All **40 stores** completed full audio SHA-256 hashing, declared-writer-hash checks
where available, index/range checks and the post-scan split audit. No audit issues
or declared-hash mismatch were reported. The original source manifests still match
their preserved hashes; copied working manifests are read-only. The frozen audit
fingerprint is `0a7c0a1861ff1f8746a8f4f87b14aa605cefd6a642a6e84c92cf23c407db6ce8`.
Full scan elapsed time was about 8.6 minutes. For stores without a writer-recorded
hash, this establishes a content baseline rather than proving an independent
original copy is identical. It does not validate the correctness of transcripts.

The final independent readback checked the frozen fingerprint, every working
manifest hash/read-only mode, original-manifest preservation, and that all three
recognition stages used only the screening set. `completion.json` records that
result. No training or device session was started.
