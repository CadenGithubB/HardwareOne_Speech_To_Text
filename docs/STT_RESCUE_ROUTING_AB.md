# Additive quiet-speech rescue routing

4 November 2026. **Retain the current default.** Keeping baseline jobs unchanged avoids the earlier speech-regression cases, but this fixed rescue policy fails the background-output gate and does not improve the actual continuous G2 recording.

This is a new routing comparison, not another threshold sweep. The raw baseline segmenter keeps every existing job, its publication time and its exact recognition samples. A second segmenter uses the previously tested 1.25× noise/floor16/three-of-five onset policy. A rescue can be added only when its complete sample interval is disjoint from all baseline jobs, including jobs that publish later. No gain, filtering, model change or output-word editing is applied.

The causal release rule waits until the rescue end plus 300 ms pre-roll and one 10 ms frame has passed. It also waits for any earlier-starting raw candidate to settle. Published overlap rejects the rescue. Raw finishing is processed before an end-of-session rescue flush. This avoids using a session-wide “baseline was empty” oracle.

## Physical clip replay

Each condition contains 73 reference words. These are reused isolated recordings; G2 crops have only 150 ms lead-in versus 500 ms fresh calibration. Clip gains are assessed alongside continuous replay below.

| Condition | Raw errors | Additive errors | Raw missed words | Additive missed words |
|---|---|---|---|---|
| p4-quiet | 73 | 45 | 73 | 22 |
| p4-ordinary | 41 | 28 | 35 | 19 |
| g2-quiet | 73 | 53 | 73 | 34 |
| g2-ordinary | 40 | 37 | 27 | 19 |

## Regression and confirmation

| Panel | Reference words | Raw errors | Additive errors |
|---|---|---|---|
| Release | 687 | 187 | 187 |
| independent-ls_ordinary | 362 | 41 | 41 |
| independent-ls_minus18 | 362 | 43 | 43 |
| loud | 362 | 41 | 41 |
| overlap | 103 | 66 | 66 |
| background | 0 | 4 | 16 |

All 45 release cases and every independent/read/loud/overlap case retain exactly the baseline text: no rescue job was added there. Synthetic silence, room tone, fan and taps still emit zero words. Two extra fan jobs emit no text. Recorded living-room output rises from three to 15 words; office output stays at one word. That recorded ambience can contain genuine voices, so the extra output is not proof of hallucination. It nevertheless violates the declared no-extra-background-output criterion.

The background panel has 30 raw jobs plus five rescues. Extra work was prospectively treated as a live-runtime qualification obligation for this architecture. The policy fails its word gate independently, so no inference-job threshold is needed to reject it.

## Continuous replay

Both sequences have 146 reference words. P4 continuity is constructed from 16 recordings; G2 is an actual saved continuous capture.

| Source | Raw errors | Additive errors | Rescue jobs | End-only rescues |
|---|---|---|---|---|
| p4_concatenated_recordings | 88 | 74 | 8 | 1 |
| g2_actual_continuous | 97 | 97 | 0 | 0 |

The actual G2 stream gets no accepted rescue: its candidate ranges intersect baseline jobs. Isolated G2 gains therefore do not establish improvement in continuous use. The P4 sequence gains eight jobs, seven released before session end. This conservative routing cannot recover quiet speech that requires expanding an existing raw job's context.

## Timing and verification

The 163-case panel adds 31 rescues to 194 raw jobs; 17 isolated rescues depend on session-end flushing. Across those cases and both continuous sequences, maximum traced hold after rescue publication is 0.49 s, and the oldest accepted audio is 7.55 s old at release. These are trace properties, not model-processing latency or measured RAM.

No late-before-earlier ordering conflict occurs in this panel; source-order and publication-order texts are identical. A device implementation would still need bounded retention, raw-priority scheduling, chronological output and speaker-profile update rules. Unchanged raw PCM alone does not prove unchanged live timing or speaker behavior.

The audit verified 165 records and 249 cached recognition inputs, original raw publication times and samples, the causal release rule, and no overlap with later raw jobs. Every raw/cue trace was first checked against the already-tested endpoint ranges. Five synthetic guard tests cover pre-roll, unresolved raw overlap, discard and session-end precedence. No neural model was executed and no shared heavy evaluation worker was started.

An initial trace omitted an explicit pre-finish marker when labelling session-end-only releases. The corrected trace/audit preserves every scored range, release time and hypothesis across all 165 records; only timing classification metadata was clarified. Initial evidence is retained separately. No parameter or acceptance threshold was retuned after observing scores.

No production firmware, model or settings changed; no candidate advanced to hardware. The training comparison remains independently active. Private reproduction: `private/stt-rescue-routing/`, including protocol.md, trace.cpp, routing.py, check_routing.py, run.py, audit.py, report.py, selection.json and the per-case records.
