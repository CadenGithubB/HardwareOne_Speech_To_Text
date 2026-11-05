# STT relative-energy and onset comparison

4 November 2026.

Development winner: **none**. Candidate cleared for live qualification: **none**. Production defaults remain unchanged.

The 1.25× rule with confirmation reduced actual continuous G2 errors from 97 to 68 and constructed P4 errors from 88 to 70. It nevertheless increased distant-microphone errors from 38 to 39, noisy-speech deletions from seven to eight, and recorded-background output from four to 18 words. No tested rule met all retention gates.

This follow-up removes amplification from the detector and tests the speech-to-background contrast directly. It follows the [gain and noise mechanism investigation](STT_DETECTOR_FOLLOWUP.md).

## Comparison

All five arms use raw microphone PCM for detection and recognition, speech floor 16, silence floor 16, the existing 25th-percentile noise estimate and 500 ms calibration. The control retains the existing 2× noise multiplier. Candidate multipliers are 1.5× and 1.25×, each with and without onset confirmation. Confirmation requires three of the last five 10 ms frames to meet onset, including the current frame. Existing 300 ms pre-roll provides context before confirmation. The multiplier also affects trim and release decisions, so this is not an onset-only ratio test.

Processing policies and group gates were frozen before candidate decoding. Tie-breaking among eligible arms was specified while replay was underway, before the full development panel was available. Selection uses physical clips, release speech and backgrounds. It requires no group increase in errors or deletions, strict quiet improvement on each microphone, and no extra background words/jobs. Among eligible arms, selection uses quiet errors, then total development errors, then name. The chosen winner must then retain errors/deletions on independent read, quiet read, loud and overlap confirmation. A failed winner is not replaced using confirmation scores.

## Physical recordings

Errors; 73 reference words per column. Isolated G2 clips have only 150 ms lead-in versus 500 ms calibration; see continuous replay as well.

| Detector | P4 quiet | P4 ordinary | G2 quiet | G2 ordinary |
|---|---|---|---|---|
| Current raw detector | 73 | 41 | 73 | 40 |
| Floor 16; noise ×2 | 73 | 39 | 71 | 40 |
| Noise ×1.5 | 60 | 33 | 56 | 36 |
| Noise ×1.25 | 48 | 29 | 52 | 37 |
| Noise ×1.5; confirm | 59 | 34 | 55 | 36 |
| Noise ×1.25; confirm | 45 | 30 | 53 | 37 |

## Regression and confirmation

Word errors. Backgrounds span six minutes; real recorded ambience may contain voices, so extra output is not proven hallucination. The job-count gate is a conservative workload guard, not measured P4 timing. Data are reused development/regression material, not a fresh population holdout. Loud inputs are digitally scaled; overlap references may omit competing speech.

| Detector | Release /687 | Read /362 | Quiet /362 | Loud /362 | Overlap /103 | Background words | Jobs |
|---|---|---|---|---|---|---|---|
| Current raw detector | 187 | 41 | 43 | 41 | 66 | 4 | 30 |
| Floor 16; noise ×2 | 178 | 41 | 43 | 41 | 66 | 8 | 32 |
| Noise ×1.5 | 179 | 41 | 43 | 41 | 66 | 25 | 27 |
| Noise ×1.25 | 179 | 41 | 43 | 41 | 67 | 19 | 31 |
| Noise ×1.5; confirm | 177 | 41 | 43 | 41 | 69 | 24 | 27 |
| Noise ×1.25; confirm | 178 | 41 | 43 | 41 | 70 | 18 | 30 |

## Continuous replay

Each source has 146 reference words. G2 is actual continuous capture. P4 is a concatenation of 16 recordings. Each detector starts once per sequence.

| Detector | Constructed P4 /146 | Actual G2 /146 |
|---|---|---|
| Current raw detector | 88 | 97 |
| Floor 16; noise ×2 | 87 | 98 |
| Noise ×1.5 | 71 | 77 |
| Noise ×1.25 | 69 | 69 |
| Noise ×1.5; confirm | 73 | 81 |
| Noise ×1.25; confirm | 70 | 68 |

## Per-phrase release changes

All 45 release cases are retained individually, including misses. Counts compare total word errors against the raw baseline; the private per-case file also records substitutions, insertions and deletions.

| Detector | Improved | Tied | Worsened |
|---|---|---|---|
| Floor 16; noise ×2 | 4 | 41 | 0 |
| Noise ×1.5 | 4 | 40 | 1 |
| Noise ×1.25 | 4 | 40 | 1 |
| Noise ×1.5; confirm | 7 | 36 | 2 |
| Noise ×1.25; confirm | 6 | 37 | 2 |

## Selection results

| Detector | Failed development gates |
|---|---|
| Floor 16; noise ×2 | p4-quiet no quiet gain; background increases errors; background more jobs |
| Noise ×1.5 | release-noise10 increases deletions; release-ami_sdm increases errors; release-ami_sdm increases deletions; background increases errors |
| Noise ×1.25 | release-noise10 increases deletions; release-ami_sdm increases errors; background increases errors; background more jobs |
| Noise ×1.5; confirm | release-noise10 increases deletions; release-ami_sdm increases errors; release-ami_sdm increases deletions; background increases errors |
| Noise ×1.25; confirm | release-noise10 increases deletions; release-ami_sdm increases errors; background increases errors |

No development winner was selected. Read/quiet/loud/overlap scores above remain diagnostic; no candidate advanced to live qualification.

## Verification and limits

The audit verified 825 arm records: 815 physical/validation and ten continuous. It reconstructed raw PCM hashes, checked decoder-input cache identities, cuts and edit arithmetic, and verified frozen policies. Every replay also checks the unchanged 2×/floor45 shadow control against archived production-control cuts. The fixed recognition checkpoint, int8 export, portable frontend and LM match the preceding experiment. Both confirmation implementations passed calibration, isolated-impulse rejection, three-of-five acceptance, expiry and reset checks.

No model, production firmware or processing default changed. A candidate is not adopted from this host replay: live P4 capture integrity, latency, peak memory, draft captions and speaker effects would still need qualification. Live G2 access remains unavailable while the user has the glasses. The training chat is now actively training its matched separator arms. An early exported checkpoint exists, but remains unselected and unqualified; a model comparison is pending its fixed selection and qualification decision. No new-model accuracy gain is claimed here.

Private reproduction: `private/stt-relative-detector/`, including protocol.md, selection-order.md, frozen sources, run.py, select.py, qualify.py, audit.py, the per-case records and cache.
