# P4 heap-header write-watch diagnostic

Status: source audit and readback discovery complete; no board trigger has
been armed or calibrated. Keep this separate
from ring-worker timing and from production firmware qualification.

## Evidence being investigated

Two core-0 load-access faults expose an invalid PSRAM heap `heap_data` pointer
while allocating a 6,384-byte serial ExecReq. Their six saved return-address
frames match the separately retained ELFs. The newer fault followed all marked
STT cleanup boundaries. The corrupting writer is unknown. The separately
reproduced PCM-ring race is not established as the cause.

In 002e3a0c, the saved multi-heap handle and ELF external-BSS end are both
0x4809e424. The faulting control pointer is 0x002960c4 and the failed load is
at +16 (0x002960d4). The installed SDK's `heap_t` stores `heap_data` at offset
16; its registration function initializes the pointer once. Do not hardcode
the old app address into a newly linked diagnostic.

## Verified SDK constraints

These are from installed IDF b774170ff46c393eeb5e495ea37936038d3f4f4f:

- `esp_hw_support/cpu.c` explicitly does not check whether a requested watchpoint
  is already in use. The caller must do that.
- `riscv/rv_utils.h` sets a watchpoint by selecting `tselect=wp_num` and writing
  `tdata1`, `tdata2` and global `tcontrol`.
- Breakpoints and watchpoints use the **same** trigger indices on this RISC-V
  implementation. Clear-watchpoint calls clear-breakpoint. Three advertised
  watchpoints are not three slots in addition to separate breakpoint slots.
- Configuration has three triggers and disables the FreeRTOS end-of-stack
  watchpoint option. Hardware stack guard remains enabled; it must stay enabled.
  These facts alone do not prove any trigger is free.
- The SDK routes debugger-attached requests through semihosting. Refuse an
  unexpected attached debugger instead of changing its trigger state.
- The APIs affect the current core. Both cores need separate ownership checks
  and arming; an ordinary task running on one core cannot cover the other.

## Bounded next steps

1. Build a readback-only diagnostic first. Use a synchronous per-core IPC call,
   preserve and restore `tselect`, and collect the actual three `tdata1` / `tdata2`
   states plus `tcontrol` and debugger-attached state on each core. Do not clear
   any slot during discovery. Do not hold a cross-core spinlock across IPC.
2. Decode supported trigger type and active mode/action bits from the actual
   readback. Prefer a conservative initial gate requiring all trigger slots to
   be inactive on both cores. Preserve unexpected state and report it; do not
   overwrite a slot because its index looks convenient.
3. Derive the PSRAM heap start from the new matching link/map and verify the
   runtime header and expected control pointer before arming. Match the actual
   SDK heap layout and registration alignment. Record only numeric addresses
   and IDs; keep raw registers/stacks/logs private.
4. Calibrate a naturally aligned four-byte store watchpoint against a dedicated
   synthetic word on each core, in separately labelled expected-trap runs.
   Verify the trap PC/trigger/core before trusting an absence of traps. These
   deliberate traps are not ordinary STT failures or successful lifecycles.
5. Only after ownership and calibration pass, watch stores to the heap's
   `heap_data` field during the same known-input workload. Keep models, capture
   source, logging, clocks, stack configuration and labelling policy fixed.
   Preserve trigger/global-control state and roll back only owned changes.
6. Retain every attempt. A trap identifies the observed store and needs matching
   ELF/source interpretation; it does not automatically prove that store was
   illegitimate. No trap does not rule out DMA writes, cache effects or events
   outside the armed interval.
7. Apply existing app-only/MAC/partition/rollback/free-space rules and restore
   the original full app slot after each block. Never disable logging or stack
   protections to manufacture a clean result.

No heap-header watchpoint, calibration or corruption-origin finding is complete.


## Readback checkpoint

Source 16bfb713 completed one read-only boot; 647e4858 completed another with
TDATA3 included. At stages 0–3, both cores' three slots read TDATA1=0x21000000,
TDATA2=0, TCONTROL=0, debugger absent; selectors restored. All 24 context reads
in the second image were zero. The heap field at 0x4809e434 consistently held
0x4809e438, matching that image's verified heap layout. No heap mismatch,
watchdog/fatal marker or audio overrun occurred. Two different diagnostic images
with one boot each do not establish ordinary-use reliability or corruption cure.
Original app restored/verified and owned fixtures removed after both blocks.

The readback decoder separates the documented read-only type/maskmax fields
from mutable configuration and tracks absent context reads explicitly. Recheck
all state before claiming a slot; the recorded empty state is not a lasting
lease. TINFO capability probing and post-trap reset behavior remain unverified.
The public reference used is the Espressif TRM linked in AB_TEST_RESULTS.md,
SHA-256 622fe9625d19cf00bd7aa49e65f0b5dd6ef2197f83cb7a88b4405078d6a957d4.

Next calibration should verify: target core, exact store PC/address/span,
trigger hit information, no trap for reads/adjacent writes, and recovery to the
saved owned state. Use a dedicated synthetic word, keep calibration separate
from watching the heap, and retain every unexpected fault. If panic-time
cleanup is added, use the existing System_CrashRecord hook's IRAM/RAM rules:
the other core is already stalled; no allocation, locks, printf or IPC there.
Clear only a positively identified owned trigger on the executing core and
verify both cores after reset before proceeding. Do not assume the other
core's trigger was cleared by a local operation or by an untested reset path.
