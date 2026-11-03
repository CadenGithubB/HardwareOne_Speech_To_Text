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

## Existing-repeat audit — 3 November

The baseline-before/after pairs in group 21–23 were verified for conv2, conv3 and
long22: identical flashed image SHA256 and source WAV SHA256, completed captures,
ring-disabled readback, saved settings, loglink/perf diagnostics enabled, and no
filesystem-full messages. Setup warnings recur in all three pairs; none has a recorded
in-session warning. This supplies existing repeat evidence for these three baseline
cases, not a fix or an assertion that every warning samples an identical instruction.
For example, long22 setup warnings occur at device uptimes 27.175/41.795/56.834s
before, and 27.392/41.962/57.913s after; running tasks are main/main/cmd_exec_task.
The conv4 baseline's warning-bearing final run still needs a later matching repeat.

Earlier conv1 PCM batches were also checked against original per-run session counters,
raw logs, boot ELF identifiers, and flash SHA256 records matching the saved images:

| Batch | Original per-run session warning counts | Existing later observation |
|---|---|---|
| Local x2f | 1, 0, 0 | The warning did not recur in the following two runs; setup warnings still occur. |
| Long-pause400 | 0, 0, 0 | Setup warnings repeat across the three runs. |
| Production pacing | 0, 0, 0 | Setup warnings repeat across the three runs. |
| Earlier x2f250l64 | Ten zeros | Setup warnings repeat across the ten runs. |
| Short-pause700 | 0, 0, 1 | No later run in this batch; same-image/input rerun required. |
| Combined pauses | 1, 0, 0 | The warning did not recur in the following two runs; setup warnings still occur. |
| Diagnostic conv1 | 0 | Only one capture; setup-warning repeat remains required. |

The former combined-pause statement of 2/3 **in-session** warnings was incorrect;
the original session counters establish 1/3. Whole-log setup warnings must be kept
separate. Historical SD runs use the same recorded PCM path across fresh boots; a
remote PCM hash and peer-policy readbacks were not recorded. Do not recreate old
peer behavior for a new test; retain the comparability limit.

Capture telemetry can be emitted after a watchdog. The audit therefore uses embedded
capture timestamps plus paired Arduino/IDF clock origins, rather than output order,
to distinguish after-capture events. Original session counters include STT startup and
remain a separately reported scope. Capture start is not acoustic playback onset.
Private evidence: `private/resume-20261102/overnight/existing-watchdog-repeats.json`.

The earlier `live-status`, speaker-profile and speaker-int64 groups were audited too:
eight finalized captures, zero whole-log watchdog and filesystem-full messages. The
additional unlisted failed conv2 capture at 22:41 on 2 November has 32 whole-log
watchdog messages (28 in the recorded session counter) and 32 filesystem-full errors.
A later conv2 capture at 22:54 completed with zero of either message and the same P4
ELF identifier prefix. This is a changed-condition repeat, not a controlled fix or proof
of identical historical peer policy. Do not score the failed capture against a full
reference or recreate its full-filesystem condition. Broader clean-storage x2f testing
will provide another current-policy conv2 observation.

Private provenance: `overnight/earlier-capture-watchdog-audit.json` and
`overnight/earlier-storage-failure-repeat.json` under the existing private run root.
