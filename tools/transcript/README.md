# Standalone transcript viewer and vocabulary editor

This is a localhost browser interface for the minimal P4 captions example, not a copy of HardwareOne. Recording and recognition run offline on the P4; USB supplies optional control/viewing. No accounts, cloud API or additional AI model are used.

## Run

```sh
python3 tools/transcript/serve.py
# USB mode: use a Python with pyserial 3.5 (the exported ESP-IDF environment provides it)
python3 tools/transcript/serve.py --port YOUR_SERIAL_PORT
```

Open http://127.0.0.1:8765. The port can change; list devices first. Close serial monitors before USB mode. The bridge binds only to loopback, requires the local browser origin for commands, and never writes transcripts to the Mac. Its bounded in-memory history holds 1,024 events; import the SD recording after a history gap. Closing this browser does not stop the standalone device's recording. Closing the bridge releases USB. Titles and speaker aliases live in browser memory until exported; a page reload loses unexported annotations.

Without USB, use **Import SD recording** or **Load demo replay**. Demo speaker and draft events are fixtures; this standalone microphone app currently emits final captions only and never runs a speaker model. The importer can recover complete records preceding an unterminated, damaged final JSON line; it reports recovery and keeps the recording unfinalized. Malformed JSON in the middle is rejected. Loaded notes support literal text search, display titles, speaker aliases when labels exist, and JSONL export with annotations. Search is limited to loaded recordings. SD listing is limited to 128 names per request; the viewer holds 128 recordings/20,000 phrases each and imports at most 16 MiB per file. Larger archives should be handled outside this small viewer.

## Device commands

Commands run between inference calls. They may wait for a phrase to finish processing. None runs a shell.

| Command | Result |
|---|---|
| `help` | Show commands |
| `vocab add HardwareOne` | Add lowercase recognition preference and exact display casing |
| `vocab add ESP32\|esp` | Explicit single-word recognition form plus display alias; type the pipe without a backslash |
| `vocab remove hardwareone` | Remove by lowercase recognition form |
| `vocab list` | Read active vocabulary |
| `vocab reload` | Reload the SD file without restarting |
| `note start` | Finish any saving note and create a new recording |
| `note stop` | Close the saving note; continue captions in a separate unsaved session |
| `notes` | List recording filenames |
| `note read FILENAME [BYTE_OFFSET]` | Read up to eight complete records and return the next offset |
| `clock set UTC_EPOCH_SECONDS` | Set the local clock; subsequent recordings use it |
| `status` | Current boot identity, saving state and vocabulary count |

**Recording boundary semantics:** this minimal example records results accepted between commands, not a sample-accurate microphone start/stop boundary. Inference and capture continue during/after `note stop`; queued audio can complete after a command and belong to the next recording. Raw sample offsets are relative to the continuous capture stream. HardwareOne should retain its own stop/drain semantics when integrating these features.

## Vocabulary file

`/sd/STT Models/user_vocab.tsv` has one display term per line, optionally followed by a tab and explicit spoken form:

```text
HardwareOne
OpenAI
ESP32	esp
```

The last example uses a literal tab, not the characters backslash+t. Limits: 256 distinct recognition words, 31 ASCII characters per spoken word, 63 printable ASCII characters per display alias, no whitespace in either term. Spoken words use lowercase a-z and internal apostrophes. Invalid entries reject the whole reload and retain the last active dictionary. Multi-word pronunciation mappings and pronunciation learning are not implemented. Ambiguous aliases can create misleading display substitutions; use them deliberately.

Edits stage a complete new file, flush it, rename the previous version to `.bak`, then promote `.tmp`. At boot the loader recovers `.bak` if the main file is absent. This reduces interrupted-edit risk but is not a guarantee against FAT/card power-loss corruption. If a save fails, the active dictionary remains unchanged. Recognition hotword strength comes from the existing LM header; user additions do not rebuild the LM and cannot overcome every acoustic ambiguity. The optional LM must load for recognition preferences to apply; display formatting still works with greedy recognition.

## Recording format

`/sd/STT Notes/*.jsonl` contains schema-1 JSON records:

- `start`: stable session ID, boot/power-on counters (decimal strings), per-boot session number, persistent ordering domain, random boot nonce, reset reason, source, optional UTC, `clockKnown` and monotonic start time.
- `final`: sequence, immutable `rawText`, `text` presentation, start/end sample offsets (decimal strings), forced-boundary flag, cumulative dropped-phrase counter, excerpt title.
- `end`: outcome, elapsed duration, phrase count. Absence means unfinalized/interrupted, never confirmed success.

Serial output adds the prefix `STT_EVENT `; files do not. The viewer also accepts `draft` (`sequence`, monotonic `version`, `text`), `speaker` (`sequence`, `speaker` 0–15 or -1, `ready`) and exported `annotation` records. These prepare UI integration without adding diarization to this example. Input and formatted text are kept separately. Stable receipt identities and owner authorization remain the responsibility of HardwareOne adapters.

The NVS namespace `hw1_stt_demo` stores one committed startup blob. Every startup advances boot count; ESP_RST_POWERON advances the power-on counter. This is a reset-reason count, not a perfect physical plug/unplug count. Counters cover starts since feature installation, not device lifetime. An NVS erase resets the ordering domain/counters; normal app-only updates retain them. Counter failures report unavailable persistent order and never erase NVS to recover. UTC requires a valid device clock; the viewer's explicit time button sets it from the Mac. An offline reboot may lose calendar time; the durable boot/session order still works.

Saved files are appended and flushed/closed per event. Save errors leave recognition running and report failure. No audio is saved. Do not remove the card during writes. The loopback viewer uses existing speaker IDs only and never identifies people across recordings.

## Verification

```sh
python3 tests/test_transcript.py
node tests/test_viewer.mjs
python3 tests/test_bridge.py
# Export IDF_PATH or set CJSON_DIR to the supplied cJSON dependency
python3 tests/test_product_storage.py
```

See `docs/STT_PRODUCT_HANDOFF.md` for actual build/device evidence, changes from the original plan and the HardwareOne integration checklist.
