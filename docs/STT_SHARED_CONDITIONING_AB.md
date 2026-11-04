# Shared STT conditioning A/B

4 November 2026.

**Retain the current default.** Conditioning only the speech detector recovered captions on both source recordings, but every candidate failed at least one required speech-accuracy or quiet-recovery condition. No candidate advances under the declared gates.

The most promising routing change preserves raw samples for recognition and conditions only the detector. On the actual continuous G2 recording, its high-pass/gain variant reduced edits from 97 to 74 on 146 words. On concatenated P4 recordings it reduced 88 to 65. These are development results on eight phrases repeated at two levels. The P4 concatenation is constructed continuity, and neither is a new live firmware qualification.

## What was tested

Eight processing policies separate DC removal, high-pass filtering, additional pre-emphasis, bounded gain and their combinations. Three follow-up policies route the bounded-conditioned signal only to endpoint decisions. The recognizer then receives the raw samples at those endpoints. Both sources use the same coefficients and policies. The G2 recording-rearm fix was excluded.

The causal gain rule targets RMS 512 in native int16 units, allows at most 24× amplification and reserves peak headroom at 29,204. It decreases immediately and recovers by at most 5% per 1,024-sample block, including after attenuation. Filter history stays floating point. This differs from the old recorder’s int16-truncated history. Live integration would need consistent block buffering and a latency measurement. Forty-eight processor checks passed.

All arms use checkpoint 25397, its real int8 export, the portable C++ frontend without dither, the saved meeting LM at full strength and no custom vocabulary. The production C++ decoder reproduced all 32 archived P4 transcripts. Completed Python-reference cases were preserved and compared again after the decoder switch.

## Physical recordings

Each source/level column below has 73 reference words. The first table gives complete-window model edits. The second gives final-caption edits from isolated segmenter replay.

### Complete-window recognition

| Policy | P4 quiet | P4 ordinary | G2 quiet | G2 ordinary |
|---|---|---|---|---|
| Raw | 45 | 28 | 48 | 25 |
| DC removal | 44 | 27 | 47 | 26 |
| High-pass | 46 | 27 | 46 | 25 |
| Added pre-emphasis | 43 | 28 | 50 | 23 |
| Both filters | 44 | 30 | 50 | 28 |
| Bounded gain | 56 | 32 | 46 | 25 |
| High-pass + bounded | 56 | 32 | 45 | 27 |
| Both + bounded | 70 | 41 | 46 | 21 |

### Caption endpoint replay

| Policy | P4 quiet | P4 ordinary | G2 quiet | G2 ordinary |
|---|---|---|---|---|
| Raw | 73 | 41 | 73 | 40 |
| DC removal | 73 | 41 | 73 | 39 |
| High-pass | 73 | 41 | 73 | 41 |
| Added pre-emphasis | 73 | 53 | 73 | 37 |
| Both filters | 73 | 53 | 73 | 40 |
| Bounded gain | 60 | 34 | 58 | 38 |
| High-pass + bounded | 62 | 36 | 57 | 41 |
| Both + bounded | 70 | 40 | 62 | 37 |

### Detection-only caption replay

| Policy | P4 quiet | P4 ordinary | G2 quiet | G2 ordinary |
|---|---|---|---|---|
| Gain for detection only | 48 | 27 | 54 | 37 |
| High-pass/gain for detection only | 45 | 25 | 54 | 36 |
| Both/gain for detection only | 53 | 22 | 62 | 37 |

G2 crops have only 150 ms of lead-in, while a fresh detector calibrates for 500 ms. Those isolated endpoint scores can lose early speech during calibration. They are not a continuous-listening qualification. Filter/gain state was preserved across the original full G2 recording before cropping. P4 state resets per recorded window.

## Continuous detector replay

The detector is initialized once per sequence here. G2 uses its actual continuous recording. P4 concatenates the 16 recorded windows, preserving a distinction from live hardware capture. Both references contain 146 words.

| Policy | P4 concatenation edits | Actual G2 sequence edits |
|---|---|---|
| Raw | 88 | 97 |
| DC removal | 89 | 98 |
| High-pass | 92 | 99 |
| Added pre-emphasis | 126 | 91 |
| Both filters | 126 | 89 |
| Bounded gain | 89 | 90 |
| Gain for detection only | 69 | 75 |
| High-pass + bounded | 92 | 84 |
| High-pass/gain for detection only | 65 | 74 |
| Both + bounded | 75 | 86 |
| Both/gain for detection only | 78 | 82 |

The gain persists in continuous G2 replay, so the isolated-crop calibration artifact does not account for the whole improvement. Conditioning model input and conditioning only admission are different interventions. More admitted audio can recover words while increasing work or background output.

## Wider regression panel

The panel contains 45 release-speech cases, 48 read/quiet cases from 24 speakers, 24 loud variants, eight annotated overlapping distant-meeting clips and six one-minute backgrounds. The read/quiet phrases differ from the physical screen but have already been scored elsewhere in the project. They are not a pristine population holdout. Reserved Common Voice material was untouched.

| Policy | Release (687 words) | Read (362 words) | Quiet read (362 words) | Loud (362 words) | Overlap (103 words) | Background words /6 min | Background jobs |
|---|---|---|---|---|---|---|---|
| Raw | 187 | 41 | 43 | 41 | 66 | 4 | 30 |
| DC removal | 184 | 41 | 43 | 41 | 66 | 4 | 34 |
| High-pass | 184 | 41 | 40 | 41 | 66 | 4 | 35 |
| Added pre-emphasis | 245 | 41 | 43 | 41 | 72 | 0 | 6 |
| Both filters | 246 | 41 | 44 | 41 | 73 | 0 | 6 |
| Bounded gain | 183 | 42 | 43 | 42 | 66 | 6 | 42 |
| High-pass + bounded | 175 | 39 | 42 | 41 | 67 | 4 | 35 |
| Both + bounded | 187 | 41 | 41 | 42 | 67 | 5 | 33 |
| Gain for detection only | 177 | 41 | 43 | 41 | 67 | 10 | 42 |
| High-pass/gain for detection only | 176 | 41 | 43 | 41 | 67 | 7 | 35 |
| Both/gain for detection only | 188 | 43 | 43 | 40 | 65 | 4 | 33 |

These are endpoint-recomputed caption scores. They differ from the earlier fixed-segment release benchmark. Independent read/loud and overlap clips are replayed exactly as stored, including cold-start calibration where no ambient prefix exists. Whole-window results and all per-case outputs are preserved privately. Digitally loud variants test PCM headroom rather than the microphones’ physical response to a louder speaker. The overlap references describe one annotated meeting turn; competing speech can include additional words outside that reference. Those scores do not establish complete all-speaker transcription accuracy.

### Per-phrase changes for the high-pass/gain decision policy

Counts compare the high-pass/gain detector against raw caption replay. Phrase changes are improved / tied / worsened. Missed words count deletions separately from other edits.

| Condition | Raw missed words | Candidate missed words | Improved / tied / worsened |
|---|---|---|---|
| p4-quiet | 73 | 21 | 8/0/0 |
| p4-ordinary | 35 | 8 | 4/2/2 |
| g2-quiet | 73 | 32 | 7/1/0 |
| g2-ordinary | 27 | 18 | 1/7/0 |
| Release | 80 | 67 | 8/33/4 |
| Read | 18 | 18 | 0/24/0 |
| Quiet read | 20 | 20 | 0/24/0 |
| Loud | 17 | 17 | 0/24/0 |
| Overlap | 38 | 38 | 0/7/1 |

## Background output and decision

All synthetic non-speech conditions emitted zero words for all policies. Bounded-gain detection nevertheless triggered seven jobs on one minute of synthetic room tone versus zero raw. Recorded DEMAND ambience can contain genuine incidental voices. Increased output there is background-triggered caption output, not proof that the model hallucinated.

| Detection-only policy | Failed development gates |
|---|---|
| Gain for detection only | release-noise10 increases errors; release-noise10 increases deletions; release-ami_sdm increases deletions; release-forced_cuts increases errors; background increases errors; background increases inference jobs |
| High-pass/gain for detection only | release-noise10 increases errors; release-noise10 increases deletions; release-ami_sdm increases deletions; background increases errors; background increases inference jobs |
| Both/gain for detection only | release-natural increases errors; release-noise10 increases deletions; release-ami_sdm increases deletions; release-forced_cuts increases errors; release-forced_cuts increases deletions; background increases inference jobs |

No-extra-background-jobs is a conservative development guard, not a measured hardware timing limit. The rejection also has speech-accuracy or quiet-recovery grounds, so it does not depend solely on that guard. Some local gains are real. They do not constitute a drop-in improvement across the required conditions. The fixed selectors exclude independent, loud and overlap cases from choosing or retuning a policy.

## Verification and limits

The final audit verified 1815 arm records, including raw-input cache provenance for decision-only outputs, cut bounds, reconstructed validation PCM hashes, reference lengths, edit arithmetic and matching parallel-worker publications. Frozen processing and selector hashes matched. The eight-policy screen contributed 256 physical records and 1,048 validation records; the three detection-only policies added 96 and 393, plus 22 continuous-sequence records.

An early decision-only run shared temporary paths. Its partial outputs and cache were excluded, preserved separately, and regenerated using isolated work directories. Neural workers use separate temporary files. The final audit checks the regenerated canonical results.

No model, production processing setting or firmware image changed in this experiment. The rejected candidates were not flashed. Live P4/G2 latency, CPU contention, power, capture integrity and speaker-label effects remain unqualified for these policies. The user took the G2 away; no live G2 access was attempted while they were away.

Private reproduction evidence is under `private/stt-conditioning-ab/`, including `protocol.md`, `gate-only-protocol.md`, frozen hashes, manifests, `conditioning.cpp`, `screen.py`, `validation/run.py`, `gate-only/`, `continuous-work/`, `select.py`, `final_audit.py` and the cached outputs. The source audit and earlier fixed-gain comparisons remain in [the dual-microphone report](STT_DUAL_MIC_QUALITY.md).

Reproduction identities

- ESP-DL model SHA-256 `47e58faa01470d32dad88f1faa46e3f61dff0fd605aa542103aefd11502dae72`.
- `conditioning.cpp` SHA-256 `6379af91936a3ac55937aed362b02484bd56bf55eaecb0368e44c7ecca55b92a`.
- `screen-manifest.json` SHA-256 `862537eaa38f5944576ca38dfd73009b049e28c0477f8edd9f22920703566777`.
- `validation/manifest.json` SHA-256 `bb15e4c2c64afc40f8f108ab6a3be81313e9d03da4045fedde8c2017c327de10`.
- `decoder-provenance.json` SHA-256 `af92462ec158130f285523eb1916356639f8851efb906c20df7d4546838d2cf7`.
