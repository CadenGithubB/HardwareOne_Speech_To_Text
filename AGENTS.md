# Standalone speech project

This checkout owns the reusable STT engine, standalone P4 example and tools. Work here when requested;
do not automatically synchronize into another HardwareOne checkout. The application in that firmware
may have advanced independently. See docs/STT_PRODUCT_HANDOFF.md for the current plan and qualification.

- Keep the fixed recognition model and speaker algorithms unchanged for the readability work.
- User vocabulary is editable data. Preserve raw captions; formatting is a separate presentation.
- No punctuation model, Mac punctuation service or semantic summary is part of the agreed feature set.
- The standalone browser is a loopback USB/import viewer, not HardwareOne's browser or authentication system.
- Test the actual portable C++ code with tests/test_transcript.py, production app persistence with
  tests/test_product_storage.py, viewer state with tests/test_viewer.mjs and bridge with tests/test_bridge.py.
- Host tests do not prove SD/FAT power-loss behavior, model accuracy or P4 realtime performance.
- Before hardware tests, inspect the actual partition table and preserve a private rollback image.
  Only flash the app at the verified address; generated example partition layouts may differ.
- Keep audio, transcripts, flash backups and device logs in ignored private/ directories. Never commit secrets.
- Update the handoff document with actual results and incomplete checks before another agent integrates.
