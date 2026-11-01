# P4 heap-header write-watch diagnostic

Status: readback, individual-core and dual-armed RTC positive controls complete.
Ten fresh-boot heap-field watch trials completed without catching a write or
reproducing a fault. Original app restored/full-slot-verified after each block.
The corrupting writer remains unknown. Allocated-PSRAM scalar controls passed
on both cores; 128-bit overlap controls also passed on both cores; keep this work separate from ring timing/product qualification.

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

No heap-header watchpoint or corruption-origin finding is complete. The
individual-core synthetic positive controls below do not close the remaining
simultaneous-arming/reset gate.


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


## Individual-core positive controls

18da8a44 (core 0) and f8a2a5bc (core 1) each trapped once at the exact matching
ELF store PC 0x4ff22cd0, MCAUSE 3, after read/adjacent-store controls passed.
Four-byte RTC word 0x50108234 remained 0x13579bdf; adjacent became 0x2468ace0.
Both recovery lifecycles completed without new faults/overruns. Slot 0 was
inactive by recovery and all subsequent both-core readback checkpoints passed.
Core 0's first controller reopened serial; core 1 kept it open through panic,
readback and cleanup. Do not attribute core 0's inactive state to panic alone.
No pre-reset hit-bit observation or PSRAM/DMA coverage is claimed.

Next bounded calibration: arm the same synthetic word independently on both
cores after fresh local ownership checks, deliberately store on core 0, keep
serial open, and verify the non-firing peer as well as the firing core after
reset. Preserve the retained ownership record and prevent rearming after the
trap. Abort/preserve unexpected state; release only exact owned configuration.
This removes the extra-reset confound and checks the recovery sequence needed
for a simultaneous both-core heap watch. Then instrument the actual verified
heap_data field during the earlier known-input fault workload.


## Both-core gate and actual watch

06b04fbe passed the bounded dual-armed/core-0-store calibration: both leases
verified before the trap, both cores inactive afterward without a serial reopen,
recovery STT done, original app restored/verified. Actual heap watch e1044e86
uses explicit arm/off commands while STT is stopped, so the interval covers
startup, known input, teardown and the following status allocation. The new
source-bound arm helper rejects occupied slots, SDK failures and wrong readback;
release still requires a recorded exact owner. No heap header is written.

First five watched boots completed without a trap/fatal/watchdog/overrun; all
eight active slot observations per boot passed. The watch lasted only
2,378–3,982 ms after phase 321. The follow-up adds a six-second host wait after
the terminal reply, retaining both cohorts and every attempt. Derive intervals
from the same clock: ESP log prefixes and explicit esp_timer ms= have a
boot-dependent offset. A negative watch is not a corruption cure and cannot
rule out aliases, DMA, changed timing or writes outside the interval.


## Completed bounded watch matrix

Both e1044e86 cohorts completed five fresh-boot trials. Initial / dwell6 summed
watch intervals: 64,668 / 98,567 ms; same-clock post-phase-321 ranges:
2,378–3,982 / 8,478–10,847 ms. The latter host holds measured 6,009–6,037 ms
after the terminal reply. Combined: 163,235 watched ms, 60 forced ownership
checks, 80 active-slot observations, 40 expected heap-pointer observations and
190 teardown markers. No caught write/fatal/watchdog/overrun. Normal capture
rows/jobs were zero; this is a known-input diagnostic, not live speech qualification.

Both owned fixtures removed and original app restored/verified. Latest healthy
baseline: 5,689,344 B LittleFS free/logging inactive/PDM/model header-footer
unchanged. Future playback remains 50%; all runs were silent.

Next test a controlled store on a separately allocated PSRAM word, with both
cores armed, exact ELF-PC verification and safe reset/owned cleanup. Do not
write the actual heap descriptor for calibration. This tests the memory path
not established by the RTC control. No unchanged heap-watch repetitions or
corruption cure are implied by the ten negative intervals. Preserve the
remaining alias/DMA/timing/register-argument hypotheses until stronger evidence
distinguishes them. No new fault-origin finding is established.


## PSRAM scalar path checkpoint

fcdc25dd/core 0 and 4404da4e/core 1 each allocated eight payload bytes in PSRAM,
armed both cores, passed both read/adjacent controls and caught the exact scalar
store PC 0x4ff22cd0 with MCAUSE 3. Targets were 0x49625bf8 / 0x4826ac8c.
Both cores reset inactive without serial reopening. Recovery STT done, zero
new watchdog/fatal/overrun markers; original app restored/full-slot-verified
after both. Latest healthy baseline: 5,615,616 B LittleFS/logging inactive/PDM/
model header-footer unchanged. No heap descriptor or SD fixture was written.

Only pre-trap probe values were retained; PSRAM contents after reset were not
read and the old allocation was not freed. The parser distinguishes this from
RTC recovery and verifies the cached P4 address window. The full negative heap
watch remains unexplained. Next check 128-bit overlapping stores on an aligned
owned block, with offsets 0 and 4, exact instruction-PC proof and safe release
if the instruction returns. The generic RISC-V compare-address rule motivates
this measurement (link in AB_TEST_RESULTS.md), but does not establish P4 PIE
semantics. Keep scalar, wide, alias and DMA coverage claims separate. Do not
repeat the unchanged ten-watch matrix as a substitute for closing this gap.


## Overlap and source-audit checkpoint

570be9f8 caught the exact 128-bit store at 0x4ff22ccc in conditions core/offset
0/0, 0/4 and 1/4. Six unwatched old-to-new vector checks and six read/adjacent
checks passed first. Both cores reset inactive after each trap with serial
continuous. Final quiet STT smoke done, zero new faults/watchdogs/overruns;
original full app slot restored/verified. Baseline LittleFS 5,562,368 B, logging
inactive/PDM/model header-footer unchanged. No playback/SD fixture used.

The 002e3a0c caller loads heap+16 at 0x4ff36df2 immediately before calling TLSF
at 0x4ff36df4. Its ABI-saved heap handle is 0x4809e424; the bad argument is
0x002960c4. No direct fault-time heap-field dump is present. Preserve that
distinction when choosing the next instrumentation. The SDK's cached/non-cached
offset is 0x40000000; the candidate field alias is 0x8809e434, not yet sampled.

The old map's adjacent 1,596-byte I2C bus array ends at the heap start. A separate
source-bound sanitizer test reproduces unchecked address 128 in the current
pinned cache helper; a guard candidate passes eight cases. The SDK stays
unchanged and no invalid runtime address or causal heap write is established.
Keep the candidate separate, audit actual caller/alias paths, and design any
fault-time cached/uncached snapshot within existing panic-context restrictions.
Do not expand watch ranges or declare the original fault resolved merely from
the passing overlap tests.
