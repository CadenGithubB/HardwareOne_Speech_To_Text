# P4 cache-counter measurement plan

Status: source/documentation audit only. No counters have been enabled or read
on the designated P4 yet. No cache, CPU, PSRAM or model settings changed.

The current [Espressif counter documentation](https://docs.espressif.com/projects/esp-idf/en/latest/esp32p4/api-reference/system/cache_cnt.html)
clarifies misleading register names: the hardware `HIT` counter counts completed
accesses, including those that waited for a fill. `MISS` counts repeated stall
events, not missed requests. `NXTLVL_RD` counts line fills; the documented miss
ratio is line fills / completed accesses. Writebacks and requester conflicts
are separate. L1-to-L2 activity must not be labelled external PSRAM bytes.
The documented newer `esp_cache_cnt` API is absent in this installed SDK; do
not upgrade the SDK as part of this experiment.

## Pinned local inputs

- IDF 5.5.5: b774170ff46c393eeb5e495ea37936038d3f4f4f.
- Actual authorized P4 revision: v3.2. The saved profile resolves minimum 301,
  maximum 399, and therefore the `hw_ver3` register header applies.
- Local `components/soc/esp32p4/register/hw_ver3/soc/cache_reg.h` SHA-256:
  77576fded69d19ce075dc4286a04e14c636e1a099632c9bf36f3f9e7be40dedc.
- Existing profile: L1 line 64 B; L2 line 128 B; L2 size 0x20000;
  CPU 400 MHz; configured PSRAM 250 MHz. These are observations, not proposed
  changes. Retain the complete matching sdkconfig with every selected image.

These offsets are relative to `DR_REG_CACHE_BASE`, from the installed header.
Use header macros, not copied numeric MMIO addresses. Keep bus names until
requester/core mapping is independently verified.

| Stream | Completed accesses | Stall events | Conflicts | Line fills | Writebacks |
|---|---:|---:|---:|---:|---:|
| L1 DBUS0 | 0x1c0 | 0x1c4 | 0x1c8 | 0x1cc | 0x1d0 |
| L1 DBUS1 | 0x1d4 | 0x1d8 | 0x1dc | 0x1e0 | 0x1e4 |
| L2 DBUS0 | 0x340 | 0x344 | 0x348 | 0x34c | 0x350 |
| L2 DBUS1 | 0x354 | 0x358 | 0x35c | 0x360 | 0x364 |

L1 control is offset 0x17c; L2 control is 0x2fc. For both, DBUS0/1 enables are
bits 4/5 and their write-triggered clears are bits 20/21. Bus 2/3 fields are
reserved in this revision's header. Overflow raw/clear/enable registers are
separate. Register names alone are insufficient evidence of event semantics.

## Bounded diagnostic implementation and gates

1. Work on an isolated HardwareOne diagnostic branch off aa6508fd. Retain the
   known-input setup, original SDK override identity and fixed models. Do not
   mix teardown workload changes into the counter experiment.
2. Verify actual chip and partition table, preserve the original full app slot,
   then use app-only flashing and unconditional original-app restoration.
3. Refuse ownership if selected counters are already enabled, interrupt-enabled,
   overflowed or contain unexplained prior data. Preserve all unrelated bits.
   Track ownership locally; never clear another profiler's counters.
4. Host-test actual counter-control code against synthetic MMIO: owned masks,
   clear/enable/disable order, zero denominators, overflow rejection, early
   failure restoration and no writes to cache geometry/policy registers.
5. On target, validate frozen counts while disabled and reset-to-zero behavior.
   Start with small bounded, volatile read workloads and increasing working
   sets; include an empty measurement control. Verify nonzero, coherent events
   and reject any overflow instead of inferring a wrap count.
6. Only then bracket known-input acoustic inference and selected stage groups.
   Stop counters before reading/formatting results. Include both bus streams;
   background capture, interrupts and the other CPU can contribute noise.
   Keep those workloads equal and report scope rather than assigning all events
   to a single C++ routine.
7. Collect at least five boot-level repeats with unchanged features, logits and
   greedy-output hashes. Report completed accesses, stalls, conflicts, fills
   and writebacks separately, with timing and measurement overhead. This is
   profiling evidence, not an optimization win.
8. Use measured hotspots to choose a code-only candidate. Require output parity
   and matched performance/regression gates before promoting anything. Do not
   convert event counts into PSRAM bandwidth without a validated traffic model.

This plan closes the semantics question; actual control/readback, calibration,
overflow/ownership behavior and stage measurements remain open.
