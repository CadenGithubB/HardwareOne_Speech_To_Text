# P4 microphone orientation at one foot

**Keep the microphone facing the speaker for this setup.** Turning it away increased quiet word errors from 45 to 58. Ordinary word errors stayed at 28 overall, although individual captions changed.

## Question

Can changing which way the microphone faces recover quiet words without making ordinary captions worse? The user reported that the P4 was one foot from the Mac mini with its microphone facing the mini. That is orientation A. Orientation B turns the board 180 degrees horizontally, around the microphone’s marked position. Keep the same surface, microphone height, speaker volume and source bytes across runs.

## Measurements

Eight phrases, including four recorded human meeting excerpts, supply 73 reference words at each level. Every phrase appears at ordinary playback level and 16 dB quieter. Ordinary sources target −20 dBFS RMS with 1 dB of peak headroom. The controller verifies Mac playback volume is 50% and unmuted on entry. Each saved six-second P4 window has a byte count and CRC from the device. The diagnostic image and model match the preceding [acoustic path study](STT_ACOUSTIC_PATH_REPORT.md). The frozen orientation suite SHA-256 is `205f21b6b259f9e88f0efe97a5cfb7501551fb6c3deebad066aa125fb2fd97b4`.

The primary comparison is quiet word errors, with deletions reported separately. Compare ordinary speech per phrase, including increases that aggregate counts could hide. A promising screen proceeds to a reversed-order repeat, independent clips, loud speech, overlapping speakers, silence/noise and live caption checks before any recommendation to adopt B. A regression can reject B at screening. Private recordings, hypotheses, manifests and the physical test protocol are in `private/orientation-ab/`.

## Results and decision

| Condition | Reference words | Facing speaker, A | Facing away, B | Missed words, A → B |
|---|---:|---:|---:|---:|
| Quiet | 73 | 45 errors (61.6%) | 58 errors (79.5%) | 20 → 32 |
| Ordinary | 73 | 28 errors (38.4%) | 28 errors (38.4%) | 12 → 12 |

B worsened six of eight quiet phrases and improved two. On ordinary speech, B worsened two phrases, improved three and tied three. The unchanged ordinary total masks changes in both directions. Both captures contained all 16 checksummed six-second windows. Neither recording had clipped samples. Estimated playback extents fitted inside all windows, although correlation was weak on some quiet clips.

B failed the primary quiet-speech screen. Retain A. The frozen escalation rule did not call for a reversed-order repeat, independent clips or loud, overlapping, background-noise and live-caption qualification of a rejected candidate. Those conditions remain unmeasured. A single A-then-B comparison at one distance and in one room cannot establish a universal optimum or distinguish directionality from other placement and order effects. No gain or model change was evaluated. Hardware transfer, per-phrase counts, alignment checks, diagnostic identities and app restoration are recorded under `private/orientation-ab/`.
