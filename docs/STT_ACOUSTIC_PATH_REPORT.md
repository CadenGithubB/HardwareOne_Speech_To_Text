# Where the P4 loses words

4 November 2026. Controlled acoustic playback on the connected P4X-EYE at two user-reported positions. Because the user had no spare microphone, the physical comparison uses their agreed alternative of moving the same P4 between repeated playbacks.

**The largest measured loss occurred between the source file and the samples captured by the P4.** On the first pass, the source files produced 12 errors on 73 words. Playing them through the Mac speaker and recording them on the P4 produced 31. On the same captured samples, the P4 and host produced identical words. The matched output checks below isolate fixed-window recognition from the physical recording path.

**Raising quiet speech before playback helped at both placements.** Across the four human meeting phrases, errors fell from 25 to 19 with the P4 resting on the Mac and from 30 to 19 at one foot. The second placement did not consistently improve recognition. The remaining physical path includes the Mac speaker, room, placement, P4 microphone and its capture electronics.

## The matched comparison

The fixed set contains four synthesized ordinary-language control phrases and four isolated human speech excerpts from different AMI meeting series. The references contain 73 words. The human sources are headset recordings. Each was played once at its original level in the first experiment. The phrase and reference list was frozen before running the P4. These are development fixtures. Eight replayed phrases cannot establish an expected word error rate for conversation.

| Path | Errors / words | Word error rate | Substitutions | Deletions | Insertions |
|---|---:|---:|---:|---:|---:|
| Original source file, host inference | 12 / 73 | 16.4% | 6 | 5 | 1 |
| P4 microphone recording, host inference | 31 / 73 | 42.5% | 16 | 14 | 1 |
| Identical P4 samples, P4 firmware inference | 31 / 73 | 42.5% | 16 | 14 | 1 |
| Independent close microphone, simultaneous capture | Unavailable | | | | |

Each window contains six seconds of signed 16-bit mono PCM at 16 kHz. An isolated app used the standalone P4 microphone driver and transcribed each complete window with the project’s firmware recognizer. It sent the samples, checksum, integer acoustic outputs and raw recognition text over USB. The controller verified every offset and CRC before saving the buffers. On the host the portable C++ frontend used the device’s no-dither setting. The model passed both serialized output fixtures before scoring. Both decoders used the same meeting language model, full strength, and no custom vocabulary.

For the source-file control, normalized waveform correlation located the playback within each P4 capture. The host placed the original samples at that offset in a silent six-second window, which preserves frontend window length and approximate phrase position. All eight full sources fit. The absolute waveform correlations ranged from 0.046 to 0.272. Alignment is least certain for quiet speech. The exact host/firmware comparison uses the complete captured bytes and does not depend on this alignment. As a separate control, every digital source was also placed exactly 0.8 seconds into a six-second silent window. With this fixed start time the original files made 12 errors and the level-adjusted files made 8. Thus some of the playback-level benefit could come from the recognizer’s response to level even in the absence of room noise.

The engine produced 300 time steps with 29 integer scores per step, per clip. All **69,600** values matched byte for byte across host and board. Both the host decoder replaying the P4 scores and the on-device decoder returned the same words on every clip. This check covers microphone acquisition through fixed-window inference. The diagnostic bypasses the live caption scheduler, phrase endpoint selection, partial captions and display formatting. A regression confined to those paths remains possible.

## Level and capture

Three of the four human source recordings were exceptionally quiet, around −41 to −45 dBFS RMS. The other meeting excerpt measured −21.8 dBFS and the four synthetic controls measured −15.3 to −16.7 dBFS. The original P4 captures had no samples at either signed 16-bit limit. On identical P4 samples, a host-only gain adjustment to match the source RMS, capped at 1 dB below digital clipping, produced 34 errors versus 31 unmodified. This gain setting requires the original source, so it serves as a diagnostic control.

## Physical playback-level comparison

The second pass repeated the eight phrases in the original position, on the Mac and approximately 1–2 inches away according to the user. The controller left the Mac speaker setting alone throughout both runs. A system query during the second pass reported 50% volume and unmuted output. Four synthesized phrases retained exactly the same source bytes. For the four meeting phrases, a single gain factor targeted −18 dBFS RMS, subject to 1 dB of peak headroom. The gains in fixture order were +19.1, +26.6, +3.5 and +24.1 dB. The second manifest hashes to `9c69829b14f4b7099305407fefe7b5c241da312e4415e64d51ba74993db2f07a`.

| Phrase group | Reference words | Original playback, P4 | Louder meeting playback, P4 |
|---|---:|---:|---:|
| Four synthesized controls, same playback level | 33 | 6 | 5 |
| Four meeting phrases, adjusted playback level | 40 | 25 | 19 |
| All eight | 73 | 31 | 24 |

For the four meeting phrases, individual errors changed from 15, 3, 1 and 6 to 11, 2, 1 and 5. Increasing the level at the sound source helped on this setup. Increasing gain *after* the microphone captured the original meeting phrases moved their error count from 25 to 28. The repeated control phrases varied by one error. With one pass per level, one room, and no counterbalanced order, six fewer errors on the meeting phrases is a descriptive finding for this setup. It does not establish a production automatic gain setting.

The host scored 12 errors again on the second pass’s digital sources, although three meeting phrases changed their individual digital-source score. On the P4 recordings the host and board both scored 24. Every transcript and all 69,600 integer scores matched again. Both hardware runs completed with per-phrase checksum verification and flash-verified restoration of the original P4 app.

## Placement test

The user had no spare microphone, so we used the same P4 microphone sequentially at two placements. The user reported the original placement was on the Mac, approximately 1–2 inches away, and confirmed the second placement was about one foot away. The third pass reused the original source manifest, playback levels, six-second windows, recognition model and Mac volume. Distance, orientation, support and possible vibration coupling to the chassis can all change when the board moves. Placement is the experimental comparison.

The original-level meeting phrases made five more errors at one foot. With level-adjusted playback their total was 19 at both placements. The four control phrases did slightly better at one foot. The largest repeatable change in this study was raising the level of quiet speech before it reached the microphone. Digital gain on already-captured samples did not recover that benefit in the original run.

## All four runs

Each recognition column gives word errors out of 73. “Raised” applies only to the meeting clips. Each run contains the same eight references. The source column uses the estimated onset for that particular playback, which can change its score even when the source bytes are identical.

| Placement and playback | Source → host | P4 mic → host | Same P4 samples → P4 | Integer scores differing out of 69,600 |
|---|---:|---:|---:|---:|
| On Mac, original | 12 | 31 | 31 | 0 |
| On Mac, raised | 12 | 24 | 24 | 0 |
| One foot, original | 14 | 34 | 34 | 0 |
| One foot, raised | 10 | 23 | 23 | 3035 |

Each cell below is a word error count. The same reference was used in all four columns.

| Clip | Words | On Mac, original | On Mac, raised | One foot, original | One foot, raised |
|---|---:|---:|---:|---:|---:|
| Control 1 | 7 | 3 | 2 | 2 | 2 |
| Control 2 | 8 | 1 | 1 | 1 | 2 |
| Control 3 | 10 | 2 | 2 | 0 | 0 |
| Control 4 | 8 | 0 | 0 | 1 | 0 |
| Meeting EN2002a | 17 | 15 | 11 | 16 | 13 |
| Meeting ES2004b | 6 | 3 | 2 | 6 | 2 |
| Meeting IS1009a | 9 | 1 | 1 | 0 | 0 |
| Meeting TS3003b | 8 | 6 | 5 | 8 | 4 |

## The one numerical discrepancy

Across all 32 captures, all 32 raw transcripts agreed. Of 278,400 integer acoustic scores, 3,035 differed, all on the second synthesized control in the final run. The largest difference was six integer steps. The best-scoring character agreed on every one of the 300 frames in that clip.

An isolated flash replayed the exact saved PCM twice, using the same P4 frontend and recognition engine. Cold and warm runs each reproduced the original 8,700 output bytes. Of the 38,400 quantized input features, exactly one differed across platforms. At zero-based frame 131, mel band 35, the host’s scaled feature was −7.4999895 and rounded to −7. The board emitted −8. Feeding the P4’s quantized feature array to the host model reproduced every P4 output byte, including the 3,035 previously different scores. This localizes the discrepancy to frontend arithmetic at a rounding boundary. It did not cause a word error on this clip.

## What to change next

Keep the current model for this use case. Use labeled human speech at measured, realistic playback levels for future P4 acceptance tests, with a quiet condition retained separately. For quiet live speech, evaluate a capture-side improvement on the same recordings and compare missed words. The physical experiment establishes that a stronger signal at the source helped in this room. Software gain after capture did worse in the test. No production gain setting follows from this comparison.

For numerical regression work, retain this private PCM and both feature values alongside the golden outputs. Exact comparisons that start at quantized model input can distinguish an engine regression from a frontend rounding difference. If an end user reports lost words during continuous captions, the remaining untested firmware path is live segmentation and scheduling. A comparison there should preserve the exact finalized sample boundaries.

## Reproduction and scope

The original phrase manifest SHA-256 is `e164eaba5ce8cff15548937132043ebf4b349c260ad1c8b2af6fd235b0681460`. The diagnostic app SHA-256 is `c98dfffc8c5d7c30b4ad130d29b16c38769d8b324ebb161f3e0dff6495c866c8`. The ESP-DL export is `47e58faa01470d32dad88f1faa46e3f61dff0fd605aa542103aefd11502dae72`. Both the on-device log and host file identify the language model as `7bae9ff540bed1ca3065f13abcb9b6e794f9d863080dde116fb0af08525d7823`.

For all four capture runs and the separate numerical replay, the controller verified board identity, the actual partition table and the installed app before writing the diagnostic only at 0x10000. It restored and flash-verified the original app, SHA-256 `b55bf096156476f2e0e9fc15ea06acb2d91d27c32784a92215f76e06fbda0e88`. Private evidence is in `private/three-path/`. It contains the build sources, fixture selection, USB controller, audio and per-case raw results, aligned host scorer and gain control. Device recordings and transcripts stay in that ignored directory.

The Mac’s system audio inventory exposed one output, its built-in speakers, and zero input devices. A simultaneous measurement with a microphone placed close to the speaker would establish how much intelligibility survives the playback step. Source-file inference bypasses the speaker. Existing AMI headset recordings were made in their original meetings, at a different time and place.

The separate replay image SHA-256 is `d40dae54f47410bbff4cc877585cfe18b6f60cc5b8a9d5bbfdb9b4ce81ffd7f4`. Its source PCM hashes to `0bd4249a8ce6fc51af74198c79981526b2f86d1c5835ff6b489b7ebbbe334a54`. Per-run and per-clip scoring can be regenerated locally using the private `score.py`, `score_level.py`, `matrix.py`, `localize.py` and `verify_report.py` with the saved evidence. All four original capture manifests and the replay status record successful restoration.
