# System-log storage incident — 31 October 2026

## Device and observed impact

Connected ESP32-P4X-EYE, firmware 0.99.99. LittleFS reported about 9,068 KiB
total and only 4 KiB free. Live firmware emitted `No more free space` and
settings serialization/save failures. STT saving was disabled, so this was not
an accumulation of saved speech transcripts. No firmware was flashed or rebooted.

The user requested a local backup, investigation and deletion of the system log
to free storage before continuing the glasses STT measurements.

`log status` reported INACTIVE and auto-start OFF before backup began. `log stop`
confirmed there was no active system-log writer. Three files were present under
`/logging_captures/system`:

| File | Bytes |
| --- | ---: |
| `vfscheck.log` | 2,964 |
| `vfscheck2.log` | 2,178 |
| `vfscheck3.log` | 8,331,031 |

## Backup and deletion procedure

Raw files and verification evidence are private under
`private/performance/system-log-backup/`, excluded from Git. Each source file is
downloaded via permission-guarded `fileread` with base64 chunks. Every chunk's
offset, returned length and total source size are checked. The local file is
flushed to disk and independently rehashed. A second complete device read must
produce the same SHA-256 before the backup is marked verified in `manifest.json`.

The large log is eligible for deletion only after that verification. The two
small companion logs are preserved on the device. Deletion and final free-space
results are recorded below. The competing Showcase serial
poller is suspended during transfer and resumed afterward; it is not terminated.

## Source-level finding

The inspected local HardwareOne source contains a direct, long-lived append path
for system capture logs in `System_Debug.cpp` (file-output block around line 320).
It writes each routed message with `gSystemLogFile.printf`, flushes periodically,
and updates last-write bookkeeping. That block has no file-size cap, no per-write
free-space/reserve check, no call to `resolveOverflowPath`, and no check of the
returned write length. A full-volume write therefore is not handled there as an
explicit stop/overflow event.

Other log writers use `appendLineWithCap`; VFS also has `resolveOverflowPath`
with a 100 KiB minimum reserve and SD overflow routing. Those protections are
not invoked by this system-capture append block. This distinction explains why
the presence of capped error logs and an SD card did not by itself protect this
capture file. This is a finding from local source corresponding to the device
project, not a binary-level proof that the installed build is byte-identical.

The complete local copy contains 72,826 lines. Directly labelled command-response
captures account for 4,300,380 B (51.62%) and `CMD_FLOW` traces for 2,521,992 B
(30.27%): together **81.89% of the file**. `AUTH` accounts for another 284,260 B
(3.41%). Smaller category counts include nested labels in captured command output,
so these are line-label counts rather than perfect semantic attribution.

Frequently traced command roots include `status`, `memreport`, `taskstats`,
`perftop`, `ring`, `events`, power/battery/Bluetooth status and `g2status`. Those
are routine monitoring operations. An unrestricted capture of both their full
replies and internal execution/authentication traces multiplies each poll's
storage cost. This implicates logging policy and polling verbosity, not audio
recordings, as the dominant file content.

The timestamp span is about 3 h 52 min (uptime 52,825–13,963,195 ms), averaging
about 599 file bytes per second across that span; this is an average over the
recorded interval, not a constant growth rate. The file has no captured
`No more free space` marker: a full log cannot be relied on to record its own
write failures. Live serial output supplied the full-volume/save-failure evidence.

Counts were computed with `tools/report/analyze_system_log.py`; `analysis.json`
is alongside the private backup and contains no message bodies.

## Follow-up implementation targets

- Apply a bounded size/retention policy to system capture files.
- Reserve space before writes; use the existing SD-overflow policy or explicitly
  stop logging if a safe destination is unavailable.
- Check short writes and expose a clear stopped/full state instead of updating
  success bookkeeping unconditionally.
- Keep routine polling replies and verbose command/auth traces out of prolonged
  file captures unless explicitly selected.
- Exercise the actual writer against low-space, failed-flush and SD-removal cases,
  ensuring settings storage retains its reserve.

No changes to the HardwareOne firmware checkout are part of this recovery.

## Confirmed recovery result

All three logs were backed up and verified. The large log SHA-256 is
`bfd2bdc4c17b0a5a751d2a16e987267edaf3fdb9d3720bd211b4fbba0e48403e`.
An initial second-read verification timed out; a resumable read-back then compared
every source byte against the full local copy and completed successfully. Its
manifest records full verification. Only then was `vfscheck3.log` deleted.

LittleFS after deletion: 9,285,632 B total, 933,888 B used, 8,351,744 B free
(10% used). Recovered free capacity: 8,347,648 B. Both small companion logs remain
on the P4. File logging remains inactive and auto-start OFF. Showcase polling
was resumed. No reboot, format or firmware flash was performed.

## Settings validation

At the user's request, both `/system/settings.json` (5,916 B) and
`/system/debug.json` (3,158 B) were backed up and validated **before** retrying
any save. Both matched across two independent device reads, decoded as strict
UTF-8 JSON, had no duplicate keys or non-finite numeric tokens, and passed
root/section sanity checks. There were no leftover `settings.tmp` or `debug.tmp`
files in the directory listing.

After freeing space, `savesettings` returned `Settings saved`. Both files were
read twice and validated again. `debug.json` was unchanged. All non-encrypted
settings values and structure were unchanged. The only main-file differences
were three encrypted credential strings: the LLM HTTP token and two Bluetooth
secrets. Before/after strings have identical lengths and complete, block-aligned
`AES:<IV>:<ciphertext>` envelopes. The inspected `encryptString` implementation
generates a random 16-byte IV for each save, so changed ciphertext on a save is
expected. Secrets were not printed, extracted as plaintext or changed deliberately.

These checks found no truncation or JSON corruption. They do not establish that
every value matches a pre-incident configuration (no earlier baseline exists),
and no reboot/reload or independent credential decryption test was performed.
Private before/after snapshots and changed-path-only evidence are under
`private/performance/settings-validation/`.

The inspected writer uses a temporary file and checks serialized byte count and
file size before renaming over the existing snapshot, preserving the earlier
valid snapshot on a failed write. The observed intact files are consistent with
that protection working during this incident.
