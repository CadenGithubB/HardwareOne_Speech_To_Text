# Watchdog reproduction requirement — 3 November 2026

The user requires at least one rerun of the same test after a watchdog, to check
whether it fires again at the same spot. This requirement is part of the active
qualification work; completing the 24 initial screens alone does not finish it.

- Cover in-session and boot/setup warnings. Identify cases by exact firmware SHA256,
  input fixture/hash, input mode and test settings. Existing matching repetitions may
  supply evidence if those conditions are verified; otherwise queue a new run.
- Prioritize the in-session warnings: wider-beam conv3, forced-redecode conv3, and the
  earlier pacing/pause runs. Audit earlier run sets as well as the current chain.
- Compare device uptime, time since capture start, input/segment progress, starved CPU,
  running tasks, and MEPC/RA symbols from the matching archived ELF when available.
  Report same-signature recurrence, no recurrence, different warning, or incomparable
  conditions. A successful rerun alone does not prove a fault is fixed.
- Treat original plus matching rerun as one reproduction set; a recurring warning is
  recorded as reproduced, not an instruction to rerun forever. Retain every result.
- Keep firmware and parameters unchanged. Preserve ring reconnect off and other current
  user constraints. Do not recreate a full filesystem, erase flash, or re-enable peers
  to imitate historical conditions; disclose any resulting comparability limit.
- Use the approved remote helper, verified app-only flashing, fixed-production rollback,
  the board lock, Mac mini speakers at 50%, and ignored private logs/audio/metadata.
- Do not change production defaults or recommend promotion while watchdog qualification
  remains unresolved. No branch pushes or outward-facing reports are authorized.

Next: inventory warnings and existing matching repeats; run uncovered cases after the
currently serialized vocabulary group releases the board. No additional tuning arms.

## Inventory checkpoint — 3 November

The initial 09–24 physical groups contain 51 captures and 126 watchdog events,
including setup. Grouping by verified flash-image SHA256, source WAV SHA256 and
live-microphone mode gives 27 warning-bearing image/input groups. Twenty-three have
only one capture; four have existing repeat candidates whose setup and event locations
still need comparison. This does not include earlier pacing or interrupted pre-recovery
captures, so it is not the complete qualification matrix. Do not count shared firmware
with different input as a same-test rerun.

The three priority conv3 cases were symbolized with their corresponding archived ELF:

- Wider beam (#18): sampled PC/RA in decoder `logOf`/`dAddOut`.
- Forced re-decode (#23): sampled PC/RA in
  `spi_flash_disable_interrupts_caches_and_other_cpu`.
- Vocabulary (#24): samples include LittleFS reads/directory access, flash read,
  flash/cache coordination and task/IPC functions. Its log also contains 22
  filesystem-full errors. The interrupted repeat has 26 such errors and zero captions.

These PC/RA samples identify where tasks were observed, not full causal backtraces.
There is no basis to attribute all warnings to vocabulary, decoding or storage alone.
Prioritize the clean-storage repeats of these cases; preserve their distinct signatures.
Private numeric inventory and symbol records are under
`private/resume-20261102/overnight/watchdog-inventory.json` and
`watchdog-priority-symbols.json`.
