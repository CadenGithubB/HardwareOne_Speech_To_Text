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
