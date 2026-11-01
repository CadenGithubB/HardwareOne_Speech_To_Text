# Standalone STT readability and recording handoff

Updated 21 October 2026. Functional qualification is complete on the connected P4X-EYE with its model card. This document explains the agreed changes, the original plan, what was implemented and tested, and how the HardwareOne firmware agent should integrate the reusable pieces. All source edits are confined to HardwareOne_Speech_To_Text. No HardwareOne checkout was modified.

Implementation checkout: `/Users/cadbecaimacmini/Documents/ChatGPT/HardwareOne_Speech_To_Text`.

The source baseline is commit `a2ef959e85b6bba95f1cecf57768bd1ff075f8c9`. The recovered implementation is now included in this repository; see Git history for its publication commit. No speech model training, punctuation model or diarization changes were made.

## Agreed behavior

- Improve readability using ordinary formatting: whitespace, paragraph starts, standalone I and its contractions, and configured term casing. Preserve raw recognition output.
- Let people add names and terms after model training, without retraining, rebuilding the language-model file or flashing firmware. One entry supplies recognition preference and display casing.
- Prepare shared transcript events and presentation for later browser/glasses/saved-reader parity.
- Save useful offline recordings with excerpt titles, completion state, optional calendar time and persistent power-cycle/boot/session ordering.
- Provide review/search/export through a lightweight interface appropriate to this standalone project.
- Exclude automatic punctuation classifiers, Mac punctuation models, semantic summaries and speaker-processing changes.

## Original implementation plan

1. Build a bounded portable C++ vocabulary and formatting component with host tests.
2. Connect the existing decoder custom-word mechanism to an editable SD vocabulary file; apply edits between phrases.
3. Add recordings with raw text and metadata, explicit start/end state and independent error reporting.
4. Persist boot/power-on counters in an isolated NVS namespace. Add USB commands for vocabulary, saving and review.
5. Build a localhost browser viewer and USB adapter. Exercise draft/final/label events with fixtures without adding a new draft or speaker producer to this minimal app.
6. Build the P4 application, inspect and preserve the device's existing partitions, back up its current firmware and use app-only flashing for hardware tests.
7. Update this document with actual behavior, evidence and integration limits.

## Plan compared with implementation

| Area | Implemented | Difference or limit |
| --- | --- | --- |
| Formatting | Bounded C++ whitespace normalization, paragraph-start casing, I contractions and exact whole-word display aliases. Raw words are retained separately. | No inferred punctuation or general name recognition. The standalone app treats a note as one paragraph; HardwareOne supplies speaker-turn boundaries. |
| Vocabulary | SD TSV file plus serial/browser add, remove, list and reload; connected to the decoder's existing CustomWords argument. | Single recognition words only: 256 entries, 31 ASCII characters each. Display aliases permit 63 printable ASCII characters with no spaces. No pronunciation learning. A valid LM is required for recognition preferences; display formatting also works with greedy recognition. |
| Storage | One append-only JSONL recording containing start, final and end records, raw/formatted text, excerpt title, clock flags, counters and sample positions. | The plan considered raw text plus a metadata sidecar. JSONL keeps both together in this formerly storage-free example. HardwareOne can preserve its existing text writer and use a sidecar for the equivalent metadata. |
| Startup ordering | Persistent boot count, power-on-reset count, per-boot session sequence, reset reason and random persistent ordering domain. | PowerCycleNumber counts ESP_RST_POWERON resets, not a perfect electrical plug/unplug history. Counts begin at feature installation; an NVS erase creates a new ordering domain. |
| Time | Optional UTC, explicit clock-valid flag and monotonic note duration. Explicit USB command/browser button sets time from the computer. | Offline cold boot can lose calendar time. Previously unknown dates are never replaced with download/reconnection time. |
| Viewer | USB live final captions, SD listing/paged read, file import, literal search of loaded notes, titles, per-recording speaker aliases, JSONL export, stable paragraphs and follow-live/manual review. | Titles/aliases are in browser memory and exported annotations; they are not written back to SD. Search does not index the entire card. |
| Draft and speaker parity | Shared event reducer consumes provisional drafts and existing late speaker assignments; fixture tests cover deduplication and grouping. | The minimal P4 microphone app still produces finals only. There is no new draft worker or speaker model. HardwareOne must connect its existing producers. |
| Porting | Portable module, standalone adapters, tests and the integration checklist below. | No automatic firmware/UI sync installer was added. The existing tools sync script does not transfer these components into the significantly newer HardwareOne application. |

## Source map

| Files | Purpose |
| --- | --- |
| `firmware/components/hw1_transcript/transcript.h`, `.cpp` | Portable vocabulary table, formatter and startup-counter arithmetic; no Arduino, VFS, BLE, USB, accounts or inference dependency. |
| `firmware/examples/p4_eye_captions/main/product.h`, `.cpp` | Standalone SD persistence, JSON events, serial commands, NVS and USB platform adapters. |
| `firmware/examples/p4_eye_captions/main/main.cpp` | Initialize the adapters, pass custom words to LM decode, poll commands between inference calls and publish accepted captions. |
| `tools/transcript/web/model.mjs` | Event reducer, stable phrase identity, draft/final handling, existing-speaker grouping, ordering and torn-final-write import recovery. |
| `tools/transcript/web/app.js`, `index.html`, `style.css` | Browser viewer/controller. `replay.jsonl` contains explicitly simulated drafts and labels. |
| `tools/transcript/serve.py` | Loopback-only USB/import adapter on the Mac; not an embedded web server or HardwareOne authentication replacement. |
| `tools/transcript/README.md` | Commands, limits, formats, vocabulary validation and recording-boundary semantics. |
| `tests/` | Portable C++ sanitizer tests, actual app persistence tests with SDK stubs, viewer tests and loopback HTTP tests. |

The speech engine files under `firmware/components/hw1_stt/stt/` were not changed. Do not copy that older engine snapshot over newer HardwareOne source.

## Vocabulary and formatting contract

`/sd/STT Models/user_vocab.tsv` accepts a display term alone, or a display term followed by a tab and an explicit lowercase recognition form. HardwareOne becomes recognition word hardwareone plus display HardwareOne. A display alias containing digits requires a supported spoken form. The current decoder accepts lowercase letters and internal apostrophes; multi-word mappings are outside this implementation.

Edits are validated and staged before replacing the active file/dictionary. The previous file is retained as `.bak`; a missing main file can recover from that backup. Invalid reloads retain the active dictionary. File replacement reduces interrupted-edit risk but does not guarantee FAT/card power-loss atomicity. The decoder uses a stable dictionary during each synchronous inference call.

Custom words bias existing decoder choices, including words absent from the main LM vocabulary. They do not teach a pronunciation or guarantee recognition. Hotword strength comes from the existing LM header. The acoustic model, decoder alphabet and LM file are unchanged. Display aliases are explicit user substitutions; ordinary formatting never invents replacement words or sentence punctuation.

## Recording and event contract

Files live under `/sd/STT Notes/` and contain schema-1 JSON records. Serial events use the `STT_EVENT ` prefix; files do not.

- `start`: sessionId, bootNumber, powerCycleNumber, sessionNumber, orderingDomain, bootNonce, resetReason, bootDurable, startedUptimeMs, clockKnown, optional startedUtc and source.
- `final`: sequence, immutable rawText, displayed text, startSample/endSample, forcedBoundary, cumulative droppedPhrases, formatted flag and excerpt title.
- `end`: outcome, elapsed duration and phrase count. A missing end is unfinalized/interrupted, never confirmed success.
- Viewer adapters also accept `draft` with independent version/sequence, `speaker` with original phrase sequence and existing assignment/readiness, and exported `annotation` with title and per-recording aliases.

Counters and sample offsets are decimal strings to preserve integer precision in JavaScript. Boot/session counters order notes within the same persistent ordering domain. Different devices or erased NVS generations have no shared counter chronology.

The importer retains complete records preceding an invalid unterminated final JSON line and reports recovery. Corruption in the middle is rejected. Raw records are never silently rewritten to manufacture a successful recording.

`note stop` closes saving results accepted through that command; microphone capture and inference continue in a separate unsaved session. A queued phrase can complete after a boundary. This simple accepted-result lifecycle is not sample-accurate recording control and must not replace HardwareOne's existing stop/drain/cancel semantics. Default startup note duration includes preparation time. Sample offsets refer to the continuous microphone stream.

## Host and browser verification

All four suites passed:

1. `python3 tests/test_transcript.py`: actual portable C++ under AddressSanitizer/UndefinedBehaviorSanitizer. Covers casing, whitespace, I contractions, exact aliases/whole-word matching, immutable raw input, output bounds/canaries, vocabulary capacity and startup arithmetic/overflow.
2. `python3 tests/test_product_storage.py`: actual product.cpp, real LM custom-word code and IDF cJSON with narrow SDK/NVS stubs and a temporary host SD directory. Covers vocabulary writes, invalid-edit retention, raw/formatted records, end finalization, unsaved-session separation, interrupted replacement recovery and counter failure disclosure. A regression also reads a valid escaped-alias record larger than 8 KiB. It does not emulate FAT or physical NVS transactions.
3. `node tests/test_viewer.mjs`: final deduplication/conflict detection, stale draft handling, late speaker grouping, unknown speakers, UTF-8, large counter sorting and incomplete-final-write recovery.
4. `python3 tests/test_bridge.py`: loopback assets, bounded event history/gap handling, missing-device behavior and Host/Origin restrictions.

Python/JavaScript syntax and whitespace checks passed. Real P4 JSONL was imported into the browser, displayed with its configured casing, renamed and exported. Export inspection confirmed that raw text and the title annotation survived. The USB viewer also listed and read recordings directly from the card and displayed a cold-boot note with Date unavailable, power cycle 1, boot 3 and recording 2. A later dated recording sorted ahead of it by the same boot/session order.

Fixture speaker paragraphs do not establish real speaker accuracy. This task did not alter or evaluate diarization.

## P4 hardware qualification

The successful test board is ESP32-P4 revision v3.2, MAC `e8:f6:0a:e3:a7:68`, at `/dev/cu.usbmodem1101` during testing. Its pre-test app identified itself as HardwareOne 0.99.98.4, built 16 October 2026. A complete 16 MiB flash backup and extracted original app slot were saved privately before replacement.

Built with ESP-IDF 5.5.5 and the existing patched ESP-DL 3.3.12. Application size: **635,584 bytes**. SHA-256:

`741c37a14a0954f03ad20e5bd0a680653a05dbdc6752adfc09bd93cd533e848a`

Actual target factory slot: offset `0x10000`, size `0x715000` (7,426,048 bytes). LittleFS begins at `0x725000`. Only the application was written, and esptool verified its hash. Bootloader, partition table, LittleFS, original model files and unrelated NVS namespaces were preserved.

The earlier no-card failure came from a different attached P4, MAC ending a7:73, with a smaller `0x615000` app slot. Its original 0.99.95 app was restored and the user disconnected it. Neither that board's layout nor the example's generated layout should be assumed for another device.

### Completed physical checks

| Check | Observed result |
| --- | --- |
| SD/model startup | Card mounted. Pinned 20,112,128-byte 15x5 gen2 model loaded and verified. Model warm-up about 15.6 seconds in the first captured boot; Listening followed noise calibration. |
| LM | Existing card LM loaded: 43,003 words, 87,348 bigrams, 23,831 trigrams, 1,599,996 bytes. Captions reported language-model decoding. |
| Vocabulary | Added terms through USB, saved and reloaded them, verified the active list. HardwareOne survived software restart and physical power loss. Temporary Camera casing was removed afterward. |
| Real microphone and formatting | Played a locally generated 26-word sentence through the Mac speaker into the P4 microphone. Saved/read back raw and displayed text; configured camera to Camera mapping worked. No added punctuation. |
| Recording integrity | Received start/final/end from the saved file through paged reads. Phrase sequence and raw/display fields matched. Both controlled runs reported zero dropped phrases. |
| Recognition observation | First controlled run had one word substitution out of 26; the cold-boot repeat had zero word edits. These two tiny acoustic runs are functional checks, not a representative accuracy benchmark or evidence of recognition improvement. |
| Timing observation | First 7.64-second captured phrase processed in about 2,445 ms: frontend 172, model 2,193, decode 75 ms. This is one phrase, not a latency distribution. |
| Software restart | Boot count 1 to 2, power-on count remained 0, ordering domain unchanged, vocabulary retained. |
| Physical power cycle | User unplugged/reconnected the board. Boot count 3, power-on count 1, reset reason 1, same ordering domain, vocabulary retained. |
| Unknown time | After physical power loss, clockKnown=false and startedUtc=null. A speech recording saved successfully and displayed Date unavailable with power/boot/session order. |
| Explicit time sync | Set clock from the computer, then created/finalized a new dated recording. The earlier unknown-date file remained unchanged. |
| Browser integration | Listed and read real card files over USB, compared dated/undated order, imported a readback file, edited its title and verified export. |
| Final build regression | After the reader-buffer fix, flashed the final hash, returned to Listening at boot 4 with the retained vocabulary, and read the original cold-boot start/final/end records successfully. Saving was then stopped. |

The final reader uses a 16 KiB buffer so valid formatted records with escaped aliases are not split at the former 8 KiB limit; this is covered by the production-code host regression.

Physical testing also caught an integration bug: the default IDF console could print but did not receive commands in this app. Installing the USB Serial/JTAG driver and selecting its VFS fixed reception; the tested image contains that fix. HardwareOne should retain its existing console infrastructure rather than install this standalone adapter a second time.

No sustained throughput, battery-life, broad vocabulary-benefit or long-duration accuracy benchmark was performed. Under this small functional workload the app completed inference, file writes, commands and readback. Long SD/USB operations can still put pressure on the bounded capture queue. No claim of complete power-loss atomicity or universal storage-failure recovery is made.

## Device state at October 21 qualification and private evidence

At the October 21 qualification, the remaining connected P4 was running the standalone tested app. This historical state is not the October 31 device state: that measurement used integrated firmware 0.99.99, as documented in GLASSES_LIVE_PROFILE.md. Saving is stopped after the tests; microphone/live captions continue. The browser USB viewer can start a new saved recording. The original 0.99.98.4 app is backed up for app-only rollback. The other P4's original firmware was restored before it was disconnected.

Private evidence is under ignored `private/product-retry-20261021/`: original flash/app backups, partition read, image hashes, hardware log, qualification reports, software-restart and physical-cycle status, speech recordings and browser export. Earlier-board evidence is under `private/product-validation-20261021/`. These folders contain private flash/transcript data; do not commit or forward them as part of the agent handoff.

## HardwareOne integration checklist

1. Inspect the current firmware first. Port `hw1_transcript` and its tests narrowly. Do not overwrite the current engine/runtime with this repository's older stt snapshot.
2. Adapt the platform layer to HardwareOne's existing boot identity, clock, authenticated account directories, guarded VFS and storage policy. The standalone SD folder and USB commands have no account model.
3. Feed a stable custom-word snapshot into each existing LM decode. Keep display aliases separate from raw recognition words and preserve owner/session cleanup rules. Evaluate new terms against actual audio rather than treating a successful edit as proof of recognition quality.
4. Preserve the existing raw transcript writer and finalization rules. Store corresponding metadata/annotations separately if the current format is plain text. IDs belong to original phrases; delivery byte receipts still reference raw producer text, not formatted length.
5. Expose existing finalized text, draft/version and speaker snapshots consistently to the browser. Connect those existing producers; the standalone example does not implement replacements.
6. Share grouping/casing policy while retaining each renderer's display budget. Preserve G2 changed-band drawing, page ownership and raw-source scroll anchors. Browser DOM code is not a glasses renderer.
7. Keep HardwareOne's stop/drain/cancel behavior. Simultaneous browser observation of a glasses-owned session requires a same-account read-only observer contract; do not compete for controller ACKs or transfer cancellation authority implicitly.
8. Titles/speaker aliases currently persist through browser export only. Decide how to save edits in HardwareOne metadata under its existing permissions. Full-card search/indexing remains optional future work.
9. Rebuild current required HardwareOne profiles and qualify on the glasses. Standalone P4 success does not establish firmware integration correctness.

`tools/sync_to_hardwareone.sh` copies selected tooling folders into experiments only. It does not install this firmware component or viewer. Review and integrate source changes explicitly against the current HardwareOne checkout.

## October 31 repository handoff

The recovered standalone transcript implementation, tests and viewer are versioned
alongside the October 31 reports and sanitized numeric measurements. See
[STT_OPTIMIZATION_PLAN.md](STT_OPTIMIZATION_PLAN.md) for proposed experiments,
[GLASSES_LIVE_PROFILE.md](GLASSES_LIVE_PROFILE.md) for measurement limitations,
and [stt-performance-graphs.html](stt-performance-graphs.html) for the readable graphs.
The optimization proposals have not been implemented. Raw device logs, settings,
recordings and rollback images remain in ignored private storage and are not
available through Git. No new device qualification was performed for publication.

The October 31 [source comparison](STANDALONE_PARITY.md) confirms newer
HardwareOne changes not yet reconciled here. The requested future direction is
standalone qualification first, then HardwareOne adaptation; direct source-copy
synchronization is not sufficient. October 31 host reruns passed all four suites
listed above. No fresh firmware build or device qualification was performed.

## October 31 standalone reconciliation

The identified HardwareOne runtime/memory/watchdog, LM, speaker-policy and SDK
fixes are now ported. The standalone also owns a portable streaming scheduler for
capture-time feature prefixes, drafts and optional speculative finals. See
[STANDALONE_PORT.md](STANDALONE_PORT.md) for exact profiles, validation, adapter
boundaries and remaining device acceptance. This supersedes the earlier
"not yet reconciled" status; it does not supersede historical hardware results.
No speed/accuracy gain is claimed.

The default profile was later boot-tested on the throwaway P4X-EYE: it boots, keeps
NVS counters and answers USB `status`, but that board had no microSD card, so model
load and captions were not reached. HardwareOne 0.99.98.5 was restored afterwards.
Details are in [the device smoke test](STANDALONE_PORT.md#october-31-device-smoke-test).

## October 31 HardwareOne A/B testing

See [AB_TEST_RESULTS.md](AB_TEST_RESULTS.md) for the test conditions, matched
session distributions, confidence intervals, conversation and technical
recordings, fault history, and limitations. Neither prepared candidate qualified
as a no-regression win. Speaker-off reduced sampled PSRAM use but removed speaker
labels; slower previews delayed first preview. Speaker-label results varied on a
repeated recording, primarily because unknown labels increased in one run.

The fixed model and onboard PDM microphone were used throughout. The original
app image was restored and its complete app slot verified after candidate tests;
the final session stopped STT, found file logging inactive and recorded 7,016,448 B
LittleFS free. The installed and rebuilt baseline binaries differed, so logging
results were not used as candidate A/B baselines. Watchdog warnings and assertion
reboots occurred under instrumented playback; the user reports ordinary use is
more stable, and these tests cannot establish ordinary-use frequency or causation.
Raw audio, logs, transcripts, backups and prepared candidate bundle remain private.

The LM sweep, bit-exact kernel experiments and full RAM attribution remain for a
future agent; no new firmware improvements or integration were performed here.

## Deferred speaker confirmation follow-up

An offline two/three-phrase confirmation prototype is documented in
[SPEAKER_PROVISIONAL_EXPERIMENT.md](SPEAKER_PROVISIONAL_EXPERIMENT.md), with
numeric results in [AB_TEST_RESULTS.md](AB_TEST_RESULTS.md). It recovers the
original duplicate-speaker clean-span replay but increases corpus merge errors;
neither variant passes the no-increased-merge gate. It also delays early labels,
and the three-phrase variant substantially reduces coverage. Production firmware,
the model and the device policy remain unchanged. Do not integrate this research
prototype as a qualified improvement; P4 memory/timing and independent recordings
were not tested. Voiceprints and per-run artifacts remain private.

The ranked [ten-experiment roadmap](SPEAKER_NEXT_EXPERIMENTS.md) starts with
an audit of the audio/feature path, voiced-window selection and separate-speaker
evaluation. Each approach has an evidence basis, a decisive comparison and its
main system cost; they are proposed experiments, not qualified improvements.

## Standalone audio-path round

The [audio experiment](SPEAKER_AUDIO_EXPERIMENT.md) adds an unused opt-in portable
window selector and native/Python audit tools. On 30 speech cases the frontend
implementations closely agree (minimum float-embedding cosine 0.99999940). A new
partition excludes prior reference IDs and separates 37 development IDs from
36 final IDs. Only development has been embedded/scored. Energy-window selection
has inconclusive pooled gains and domain regressions; aggressive end trimming
harms the original failure case. Neither qualifies for HardwareOne integration.
The production model/frontend behavior and clustering are unchanged. Full
quantized-path parity, actual microphone input and P4 latency/memory remain gaps.

## P4 audio and code-only overnight checkpoint

[AB_TEST_RESULTS.md](AB_TEST_RESULTS.md) now records 25 identical-input P4
parity trials and one bounded exact-microphone-PCM capture. Five fixed inputs
repeat across reboots, but a borderline clean same-speaker pair changes from
0.605987 on Mac float to 0.595828 on P4. Float replay alone cannot qualify target
speaker accuracy. The exact-input capture shows signal-path effects are not
uniformly harmful: its 7850 pair is 0.642508 on P4, 0.632405 on Mac using the
same microphone PCM and 0.585196 on waveform-aligned clean PCM. A successful
captured sequence has roughly 299 ms pre-roll; the original failure's actual
PCM is unavailable, so a timestamp-only suspected late onset is not proved.

Session replay now uses the retained speaker prefix instead of the full capture
span; six corrected replays are separate private artifacts. The earlier cached
session comparisons used longer captured inputs. Their historical numbers are
not rewritten; clean/corpus development rejection still stands. New tools and
synthetic cases cover prompt interleaving, vector log truncation, retained-span
reconstruction, nonce/checksum ownership, raw vector norms and waveform timing.

All temporary SD files/folders were removed and the original full app slot was
restored/digest-verified. Last probe: 6,520,832 B LittleFS free, logging inactive,
PDM preferred, model header/footer unchanged. Mac playback is now 50% by user
request; earlier 75% runs remain a separate condition. Overnight work is silent.
See [SPEAKER_OVERNIGHT_PLAN.md](SPEAKER_OVERNIGHT_PLAN.md) for the active queue.

The first code-only candidate clears the speaker frontend frame padding once
per computation instead of every frame. It preserves all 150 host reference
cases under normal and ASan/UBSan builds, with no workspace/model/settings
change. P4 output/performance qualification is pending; no production firmware
has received it. Additional work targets actual correctness and redundant work,
not configuration, model or CPU/RAM clock changes.


The subsequent silent target frontend microbenchmark completed five reboot
trials: 30/30 feature checks exact, average computation 55.381373 -> 54.709907 ms
(-1.212441%; paired boot-bootstrap saving 0.599460–0.743473 ms). This is not a
qualified end-to-end application win. Original app restored/full-slot-verified,
owned fixture removed; final free LittleFS 6,504,448 B, logging inactive/PDM.
A host cleanup read-framing error was fixed with strict bounded re-reads and a
synthetic regression; no device crash occurred. Portable boundary testing passed
720 chunk comparisons with exact source PCM, and the existing streaming suite
passed ThreadSanitizer. See the results report for scope and remaining gates.

The completed 44-condition offline boundary probe adds 1,485 float embeddings
and 8,800 order simulations on the four known conversations. Padding/cropping
changes the 7850 clip 0/2 pair from 0.538 to 0.629; effects are nonmonotonic.
Tail removal improves pooled in-order results but regresses Conversation 4 and
increases Conversation 1 shuffled splits. It is not a qualified default, a
production configuration change or evidence of an incorrect original mic cut.
Final speaker partitions remain unopened. Numeric tables are in the report.

The pointwise address-walk probe c6252b6e is complete and rejected for promotion:
5 reboot trials, 15 timed pairs, 50/50 identical feature/logit/greedy-text hashes.
Inference +1.157667 ms, boot-bootstrap 95% [-3.437533, +5.275533] ms, matching
headroom; zero reported watchdogs/overruns/fatal markers. No production setting,
model weight, tile size or clock configuration changed. The original full app
slot was restored/verified and owned fixture removed; final probe LittleFS free
6,422,528 B/logging inactive/PDM/model header and footer unchanged. Traffic and
complete export-fixture/length coverage remain open; no end-to-end gain is
claimed. The active queue next examines feature-row ownership and actual cache
measurement. Neither source suspicion establishes the cause of past faults.
