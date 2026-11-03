# STT decisions and next actions — 3 November 2026

The initial sweep has not established a new general recognition/speaker-accuracy win.
It has identified configurations to avoid, a bounded pacing candidate, measurement
problems, and a concrete runtime failure to reproduce. Production defaults are unchanged.

| Decision | Evidence | Action |
|---|---|---|
| Prefer x2f for further pacing qualification | Twelve conv2–4 ABBA captures: lower mean WER on each fixture, pooled speaker correctness held, label medians 1.650–2.754s versus production 5.436–23.503s. Zero watchdogs in six x2f captures versus 11 in six production captures. | Strongest pacing candidate; complete mandatory reliability matrix before default adoption. Conv4 final-text latency and shown-text freshness are tradeoffs; no general accuracy or long-soak claim. |
| Keep exact-coverage speculative reuse | Forcing final re-decode raised label median 2.690 → 7.363s on conv2 and 3.199 → 14.744s on conv3; five speaker jobs rejected for audio pressure and one session watchdog. | Do not adopt forced re-decode. This does not compare disabling speculation entirely. |
| Do not promote normalization from these screens | Initial conv2 harm did not recur in the clean repeat (28/38 correct, one unknown); conv4 repeat is 25/34 with eight unknowns. | No consistent quality-preserving benefit; changed-condition repeats lack fresh bracketing controls. Do not generalize either initial harm or later recovery. |
| Do not promote noise freezing yet | WER 18.84/26.61% versus final controls 19.04/26.39%; the initial apparent gain is not established beyond control drift. One extra initial-control conv2 merge. | Keep as a research lead only; no claimed general accuracy improvement. |
| Do not promote the tested four-term vocabulary configuration | Target hits 0/8 versus controls 1/8 and 0/8; synthetic WER 21.05% versus 15.04/18.05%. Natural unknowns 10 versus 9/3; one late-control alignment is unqualified. | No target-term benefit established at the existing 1.0-nat bonus; preserve editable vocabulary as user data, with no default vocabulary or model change. |
| Keep production closing pauses | Long-pause400 improves conv1 WER by one word but increases unknowns; short700 and combined pauses raise WER. | Retain 600/1000ms. |
| Fix evaluation before believing small changes | Identical-image controls changed WER 15.83 → 22.85% and 24.89 → 30.47%; noise estimates changed too. Stale onset and mixed-clock speech-end fields were corrected in analysis. | Retain both controls, raw unknown coverage, exclusions and rejected alignment fits. No cherry-picked baseline or causal claim. |

## Historical storage-confounded failure and recovery target

The four-term vocabulary image completed its target/control fixture, but its natural
conv3 test failed: `STT audio queue full; backend cannot keep up`, with 21 in-session
watchdog warnings and no panic. Fixed production was restored and verified. The planned
final two controls did not run. Do not interpret the failure as proof of a particular
code defect before the matched repeat and stage evidence.

The exact-image/conv3 repeat was stopped because LittleFS reported no free space
before test audio began; it produced no captions. The original failure also contains
22 filesystem-full errors. The repeat contains 26. These are storage-confounded
attempts, not evidence that vocabulary caused the watchdogs. The fixed-production
app was written and verified after the interruption (10:06 on 3 November).

A new read-only inspection measured 352,256 bytes free. The command audit file was
514,346 bytes, already above its 512,000-byte cap. Source inspection shows rotation
copies up to 85% of the cap (435,200 bytes) into a sibling temporary file while holding
the filesystem lock. The overflow check requests only the append-line size plus 512
bytes, subject to a 100 KiB floor; it does not reserve that rotation copy. This is a
concrete mismatch to investigate, not yet a demonstrated cause/fix for every watchdog.
The three previously authorized logs total only 46,104 bytes in that inspection;
clearing those alone cannot provide the audit rotation headroom.

The previous 128 KiB free-space gate was insufficient. Do not continue tuning or
claim a clean watchdog reproduction while storage errors persist.

## Requested checks completed

1. **Storage recovery verified.** All 889 approved header-only targets are absent;
   free space was 7,618,560 bytes after cleanup and 7,196,672 after the final tests.
   Private backups remain. No production retention policy is inferred.
2. **Mandatory warning matches completed.** The 37-group matrix has no missing later
   observations. Forced-redecode conv3 repeats a worker family at different positions;
   conv2's new warnings do not recur on its extra match. No deterministic defect is proved.
3. **Broader pacing measured.** Twelve ABBA captures support x2f as the preferred pacing
   candidate, with its shown/final-text tradeoffs and qualification limits retained.
4. **Report and restoration closed.** All 24 screens have results and explicit exclusions;
   required host checks pass. Fixed production and persisted ring-off readback are verified.
   Future default adoption, storage-prevention implementation or broader qualification is
   separate work; no unapproved production change is included in this sweep.

See [STT_WATCHDOG_RETESTS.md](STT_WATCHDOG_RETESTS.md) for the user's mandatory rerun
rule and [STT_OVERNIGHT_EXPERIMENTS.md](STT_OVERNIGHT_EXPERIMENTS.md) for numeric records.
No production-default change, branch push, main merge or outward-facing filing is authorized.

## Validation checkpoint — 3 November

Required host checks passed: `tests/test_transcript.py`, `tests/test_product_storage.py`
(with ESP-IDF cJSON), `tests/test_viewer.mjs` and `tests/test_bridge.py`. The scoring
and alignment checks also passed; alignment uses the existing NumPy environment.
These host checks do not qualify microphone accuracy, P4 runtime or SD power-loss behavior.

## Concrete storage-prevention work identified

All 889 approved archived sensor files are exactly the same 88-byte sealed R1 CSV
header, with **zero data rows**. This was verified byte-for-byte against the source's
public magic and R1 column header, not inferred from file size. Their 889 boot directories
still incur filesystem overhead. `System_SensorLogging.cpp` shapes unsynchronized
sessions into `boot-%06lu` directories, and `sensorLogStart` creates the directory and
promotes a staged header before any sample has arrived.

A focused prevention candidate is to defer new boot-directory/file creation until the
first eligible data row, while preserving sealing, path authorization, failure reporting,
header compatibility, first-row retention and clock-rollover behavior. Validate repeated
boots with no R1 samples, first sample after connection, failed header promotion and
resumption into an existing compatible day file. This is identified work, not an
implemented or qualified production change; do not silently disable health logging or
apply an unapproved retention/deletion rule.

The separate rotation-reserve mismatch also remains actionable: account for the temporary
85%-of-cap copy when deciding whether logs can stay on LittleFS. Free-byte checks alone
do not measure directory-traversal cost or prove realtime safety. Finish the clean-storage
captures before claiming a speaker/recognition benefit from this recovery.

## Broader pacing checkpoint

The twelve-capture conv2–4 ABBA comparison is complete and fully RMS-qualified. X2f
holds the measured quality metrics in this screen and gives substantially faster
speaker labels; it is the preferred next pacing configuration for qualification.
The full per-run table, eligible-caption exclusions and latency tradeoffs are in
`STT_EXPERIMENT_RESULTS.md`. Mean WER production → x2f is 21.145 → 20.340%,
29.185 → 28.435%, and 22.340 → 20.745% on conv2/3/4 respectively. Two repetitions
per fixture are descriptive evidence, not a held-out or statistical noninferiority test.

Do not promise faster final text: conv4 reference-final medians rose, and shown-text
medians are slightly later. Keep existing pauses. No production default is changed.
The production watchdogs have matching later controls; remaining original live-warning
cases and two legacy SD-input cases are still running/queued. Final board audit remains.

## Broader hold/merge decision after reference audit

The original six device recordings were re-aligned without changing embeddings or
phrase order: two mixed flags changed, making 196 eligible phrases. Original-rule
replays and repeated-history stress were rerun; no candidate's promotion verdict
changes. Corrected shuffled merges per 100 are production 3.84, hold0.50 5.83,
hold0.45 6.74, young hold 5.20 and merge variants 8.25–8.83. Keep production identity
rules; the conv1 hold improvement does not establish a safe gain on broader voices.
Use the latest corrected tables in `STT_EXPERIMENT_RESULTS.md` for offline numbers.

## Final decisions after the requested sweep

The 24-change sweep and mandatory warning reruns are complete. Prefer x2f pacing
with existing pauses for a separately approved adoption step; keep existing identity
rules and exact speculative reuse. No new general accuracy gain is established.
Final reruns expose normalization/pre-roll variability, so their initial harms are
not treated as universal effects. Do not promote any candidate from a selected
unbracketed repeat. The final full tables, 37-group warning coverage, exclusions,
restoration evidence and unperformed product-level checks are in
`STT_EXPERIMENT_RESULTS.md`.

The next implementation opportunities are the identified empty-header creation and
rotation-reserve fixes, plus separate held-out/long-soak qualification before production
adoption. They are recommendations for future approved work, not claims that those
production changes were implemented here. Current defaults remain unchanged.
