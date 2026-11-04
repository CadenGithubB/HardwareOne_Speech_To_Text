# X2f pacing and storage prevention — 3 November 2026

The user approved proceeding after the completed 24-change screen and recommendation.
Scope: apply the tested x2f pacing/fast-first behavior with existing 600/1000 ms pauses;
then prevent empty automatically shaped CSV log artifacts and reserve capped-log rotation
space. Keep fixed models, speaker identity rules, accounts, settings and partitions.
No HardwareOne push, main merge or outward filing is authorized.

## Working source and cleanup

- Production base: HardwareOne `claude/p4-l2-64`, `027eef22`; the benchmark base
  `9520a5b1` contains unrelated diagnostic changes and is not the production patch base.
- Isolated checkout: `/Users/cadbecaimacmini/Documents/Codex/Projects/hardwareone-stt-adoption`,
  branch `codex/stt-x2f-storage`. Existing original and benchmark checkouts stay untouched.
- The app worktree tool refused the cross-repository source because it is outside this
  chat's workspace folders, so this is an ordinary Git worktree of the selected repository.
- Disk preflight: 35 GiB available. Expected additional build/dependencies: about 1–2 GiB.
  One build directory will be reused for the baseline and incremental changes.
- Selected app/ELF/sdkconfig/build identity, source patches and private device results go
  under ignored `private/adoption-20261103/`. Keep the known fixed-production `soak-app.bin`
  rollback. Do not use the old crashing `original-slot.bin`.
- After the selected image and source commits are preserved, remove this task's disposable
  compiler output and redundant dependency copies; retain the source checkout for review.
  Record actual retained/recovered space before completion.

## Validation boundaries

Build the P4 saved profile with ESP-IDF 5.5.5 and verify the actual sdkconfig is 64-byte
L2 / 250 MHz PSRAM. Exercise production pacing and log lifecycle/rotation code with
relevant host regressions and focused failure tests. Use only the MAC/partition-checked
app-only remote helper for physical tests, own busy.lock, keep ring reconnect off and
play existing local audio through Mac mini speakers at 50%. No audio upload is needed.
Rerun a watchdog-bearing test at least once; do not silently promote a faulty build.
Host tests do not prove SD/FAT power-loss durability or general model accuracy.

## Implemented and validated locally

HardwareOne local commits: `04827588` applies production x2f pacing; `f68e4adc`
adds storage prevention. No push or main merge. The production image inherits the
fixed `027eef22` base, without benchmark hooks or default speaker diagnostics.

The pacing helper uses a 600 ms minimum, twice the previous draft compute time,
and a fresh fast first draft per phrase. Closing pauses remain 600/1000 ms.
The x2f-only image passed live conv2 and conv3 smoke tests: 38 and 47 captions,
zero watchdog warnings, zero panics and zero audio overruns. Ring reconnect was
disabled before both sessions and on final readback; perf logging was disabled.
These are deployment smoke tests, not another matched accuracy qualification.

Automatic boot/day CSV sessions defer directory/header creation until an eligible
row. Existing targets, manual CSV, TEXT and TRACK preserve startup validation.
Sealing occurs before file creation, and R1 dedup state advances only after a
complete append, allowing an identical sample to retry after refusal/failure.
This does not make partial rows atomic or prove power-loss behavior.

Capped logs budget the existing 100 KiB non-log floor plus the pending write and
rotation temporary copy. Before copying, a fresh capacity check on the actual tier
rejects an unaffordable rotation while retaining the appended original. Reserve
arithmetic saturates and the 85% target calculation cannot overflow. Existing SD
rename/recovery behavior is retained; no new deletion or retention policy.
The existing no-SD fallback still appends to flash after overflow latches; this
patch does not guarantee that all future logging can never fill the filesystem.
The fresh check protects rotation-copy headroom, not a global write quota.

Actual-code host checks passed: sanitized pacing policy, continuous/full-phrase
broker tests; GPS startup 341 checks and deferred owner 329 checks; row writes
134 scenarios / 4,549 assertions; capped logs 84 scenarios / 34,310 assertions.
Settings passed with health disabled (9,517) and enabled (9,708), selection passed
43,388 checks, and capacity snapshot source guards passed.

Both production builds used ESP-IDF 5.5.5. Actual sdkconfig is byte-identical to the
baseline, including `CONFIG_CACHE_L2_CACHE_LINE_64B=y` and
`CONFIG_SPIRAM_SPEED_250M=y`. Combined app is 6,026,192 bytes, leaving 1,399,856 bytes
in the verified 7,426,048-byte app partition. App, ELF, SDK configuration, build
identity, hashes and source patch are preserved privately before cleanup.

## Physical storage audit and deployment decision

A pre-flash directory-listing audit on the x2f-only image triggered task-watchdog
warnings with CPU0 `cmd_exec_task`, before the storage image was flashed. The
sampled addresses resolve to the FreeRTOS critical-section exit / flash cache
reenable path. This is separate from STT DNN-worker warnings and does not establish
a root cause. The mandatory fresh-boot repeat of the same image/command reproduced the
CPU0 `cmd_exec_task` watchdog warning (two warnings initially, one on the repeat).
The repeated sampled PC/RA differ; this reproduces the command/task failure, not
the exact instruction: repeat PC/RA resolve to `memcpy` / LittleFS `lfs_bd_read`.
Use a narrow target-path inspection for
the no-data test. Root listing is now a separate reproducible follow-up, not a
reason to keep repeating STT or to alter speaker algorithms. Do not treat this as evidence against the unflashed
storage patch or as proof that it fixes the listing warning.

The combined image passed three fresh-boot no-data checks. Sensor CSV logging
was active with R1 selected and autostart ON, ring reconnect remained disabled,
and each new boot target directory was absent on two reads 12 seconds apart.
No watchdog warnings occurred in these three checks. This tests waiting without
data; it does not exercise a real first R1 measurement.

Combined-image live conv2/conv3 stability smoke completed with 38/46 captions
(84 total), zero watchdog warnings, zero panics and zero audio overruns. Final
readback confirmed ring reconnect disabled, perf logging disabled and 7,098,368
free bytes; port and lock were released.

All six live speech captures completed without watchdog warnings, panics or audio
overruns (260 captions total). RMS/clock alignment passed its gates for all six.
The following measurements are live microphone smoke comparisons, not a randomized
held-out accuracy qualification. “Correct speaker” uses one-to-one identity mapping
and includes unknowns in its scored denominator. Mixed phrases are excluded: three
in the first combined conv3 run and one in its repeat; other rows have none.
Unknown counts use every published caption, including mixed ones.

| Image / pass | Fixture | Captions | WER | Correct speaker / scored | Unknown captions |
|---|---|---:|---:|---:|---:|
| x2f only, initial | conv2 | 38 | 23.45% | 27/38 | 3/38 |
| x2f only, initial | conv3 | 47 | 31.12% | 40/47 | 5/47 |
| x2f + storage, initial | conv2 | 38 | 24.85% | 29/38 | 1/38 |
| x2f + storage, initial | conv3 | 46 | 31.55% | 22/43 | 17/46 |
| x2f-repeat | conv3 | 45 | 27.68% | 37/45 | 6/45 |
| storage-repeat | conv3 | 46 | 33.26% | 34/45 | 9/46 |

**Decision: deploy x2f-only (`04827588`), hold storage (`f68e4adc`).**
The combined conv3 repeat improved from 17 unknown labels to nine, but x2f-only
repeated at six (initially five). The combined repeat also has worse WER and fewer
correct speaker labels than the x2f-only repeat. This does not establish that the
storage code caused the difference: the input is acoustic, the runs are not
randomized and recognition/speaker segmentation varies. It is insufficient evidence
to promote the combined image. Do not integrate the storage commit as qualified
production work. It remains a tested local proposal with its idle/host evidence.

Next focused work is to isolate the lazy-CSV and rotation-reserve changes and
measure their effects separately, with repeated bracketed acoustic runs and
private speaker diagnostics as needed. Do not change speaker rules to mask this
result. The initial no-data accumulation problem remains in the selected x2f-only
firmware; the validated source fix is held, not silently deployed.

Automatic approval review rejected recursive deletion of this task's build and
dependency copies because explicit destructive-cleanup approval was absent.
Nothing was deleted. About 1.7 GiB of inspected build/dependency copies remains
in the isolated worktree; preserved private firmware/source evidence is separate.
The cleanup plan lists exact paths and does not include any other checkout.

Final x2f-only selection/readback passed: app SHA `b55bf0961564…`, ring reconnect
disabled, perf logging disabled, 7,106,560 free bytes, port and lock released.
Build cleanup requires user approval; the candidate comparison and source work
are complete. Local source and all private evidence remain preserved. R1 first-row behavior remains host-tested: ring reconnection stays
off, and no artificial health measurements will be injected. Physical SD/FAT
power-loss behavior and deliberate near-full-media behavior remain untested.
