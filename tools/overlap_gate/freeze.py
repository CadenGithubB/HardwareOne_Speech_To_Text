"""Freeze the overlap-gate experiment: labels, splits, panels, collar, false-alarm ceiling and
the selection rule, with content hashes, before any gate is scored.

Every decision is a constant below so it is visible in review. The script only hashes files and
writes experiment.json; it fits nothing and scores nothing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

HOP_MS = 10
COLLAR_MS = 200
FRAME_THRESHOLD = 0.5
MIN_OVERLAP_FRAMES = 10            # 100 ms of valid two-speaker frames makes a segment "overlap"
FALSE_ALARM_CEILING = 0.02         # at most 2% of single-speaker/noise segments may be flagged
TRAIN_SPEAKER_EXCLUSIONS = ['FIE038', 'MIO036']   # appear in both AMI train and validation
IHM_ONLY_MEETINGS = ['IS1003b', 'IS1007d']        # headset metadata without distant rows; not labelled
G2_BUDGET = dict(max_parameters=50000, max_weight_bytes=100000, max_arena_bytes=524288)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def pin(path: Path, **extra) -> dict:
    path = Path(path)
    return dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size, **extra)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', type=Path, default=Path('.'), help='repository root')
    ap.add_argument('--labels', type=Path, default=Path('private/training-track/overlap-gate'))
    args = ap.parse_args()
    root, lab = args.root, args.labels
    summaries = {s: json.loads((lab / f'summary-{s}.json').read_text()) for s in ('train', 'validation', 'test')}
    reconcile = json.loads((lab / 'reconcile.json').read_text())
    assert reconcile['passed'], 'reconcile.json must pass before freezing'

    mic = json.loads((root / 'private/stt-loss-round3-review/baseline.json').read_text())
    groups = {}
    for c in mic['cases']:
        groups[c['group']] = groups.get(c['group'], 0) + 1
    suite = json.loads((root / 'private/training-track/compact16k-loss-round3/eval-suite.json').read_text())
    conditions = {}
    for c in suite['cases']:
        k = f"{c['partition']}/{c['condition']}"
        conditions[k] = conditions.get(k, 0) + 1

    r3 = root / 'private/training-track/compact16k-loss-round3'
    review = root / 'private/stt-loss-round3-review'
    experiment = dict(
        name='overlap-gate',
        phase='0 frozen',
        frozen_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
        plan='docs/STT_OVERLAP_GATE_PLAN.md',
        question='Per recognizer segment: do two or more people speak at the same time?',
        labels=dict(
            hop_ms=HOP_MS, collar_ms=COLLAR_MS, classes={'0': 'no active speaker', '1': 'one', '2': 'two or more (cap 3)'},
            source='AMI parquet metadata, distant rows; headset rows verified identical for validation/test',
            files={s: pin(lab / f'labels-{s}.json', utterances=summaries[s]['utterances'], hours=summaries[s]['hours'],
                           meetings=summaries[s]['meetings'], speakers=summaries[s]['speakers'],
                           fraction_outside_collar=summaries[s]['fraction_outside_collar']) for s in summaries},
            summaries={s: pin(lab / f'summary-{s}.json') for s in summaries},
            reconcile=pin(lab / 'reconcile.json', passed=reconcile['passed']),
            ihm_only_meetings_not_labelled=IHM_ONLY_MEETINGS,
            no_zero_speaker_frames='Windows are one speaker\'s own utterance, so count 0 never occurs here. Silence and noise negatives come from the stores and fixtures listed under negatives.',
        ),
        splits=dict(
            fit='AMI train meetings, distant and headset audio, minus TRAIN_SPEAKER_EXCLUSIONS own-utterance windows',
            train_speaker_exclusions=TRAIN_SPEAKER_EXCLUSIONS,
            select='AMI validation (18 meetings, 21 speakers); threshold chosen here once',
            test='AMI test (16 meetings, 16 speakers) scored once after selection',
            disjointness=reconcile['disjoint'],
            negatives_for_fitting=['demand-noise-train', 'musan-noise', 'rirs convolved silence'],
            never_fitted=['the 32 real pairs', 'the 24 distant overlap clips', 'the 163-case saved microphone panel',
                          'the 323-case synthetic qualification partition', 'the three no-speech fixtures', 'AMI test'],
        ),
        segment=dict(
            frame_threshold=FRAME_THRESHOLD, min_overlap_frames=MIN_OVERLAP_FRAMES,
            label='>= min_overlap_frames valid frames with two or more speakers',
            score='fraction of valid frames with posterior >= frame_threshold',
        ),
        operating_point=dict(
            false_alarm_ceiling=FALSE_ALARM_CEILING,
            rule='tools/overlap_gate/scorer.py select_threshold on AMI validation utterance windows: admissible thresholds have segment false-alarm rate <= ceiling; choose highest recall; ties go to the higher threshold. Frozen before any test panel is scored; never changed afterwards.',
            adoption_gate='Flagged fraction of the 155 single-speaker/noise saved-microphone cases <= ceiling and zero flags on the three no-speech fixtures, at the validation-selected threshold.',
        ),
        candidates=dict(
            G0='logit entropy / blank statistics from the decoder hook plus segmenter energy; no model',
            G1='dispersion of existing speaker-trunk frame vectors; no new weights; one accessor',
            G2=dict(description='small classifier on 64-bin log-mel features, per-frame {0,1,2+} posterior', budget=G2_BUDGET),
        ),
        reporting=dict(
            frame=['miss rate', 'false-alarm rate', 'ROC area', 'all over frames outside the collar'],
            segment=['precision', 'recall', 'false-alarm rate at the frozen threshold'],
            downstream='oracle-gated and gate-gated recombination of frozen baseline and B1024 outputs per case, scored with the unchanged speaker-attributed scorer',
        ),
        panels=dict(
            saved_microphone=pin(review / 'baseline.json', cases=len(mic['cases']), groups=groups, continuous=len(mic['continuous']),
                                 role='155 negatives (all groups but overlap), 8 overlap positives, 2 continuous recordings'),
            real_pairs=pin(r3 / 'real-pairs.json', pairs=32, role='positives with exact per-speaker intervals; distant and headset streams'),
            overlap_clips=pin(root / 'private/training-track/overlap-investigation/annotation-audit.json', clips=24, role='distant positives, 1-3 competitors'),
            synthetic_suite=pin(r3 / 'eval-suite.json', conditions=conditions, role='two-speakers positives; ordinary/quiet negatives; no-speech fixtures'),
            ami_test=dict(labels='labels-test.json', role='only large fresh held-out test; scored once'),
        ),
        frozen_outputs_for_recombination={
            name: pin(path) for name, path in [
                ('baseline_qualification', r3 / 'scores-baseline-0-qualification/results.json'),
                ('baseline_regression', r3 / 'scores-baseline-0-regression/results.json'),
                ('B1024_qualification', r3 / 'scores-B-1024-qualification/results.json'),
                ('B1024_regression', r3 / 'scores-B-1024-regression/results.json'),
                ('A4096_qualification', r3 / 'scores-A-4096-qualification/results.json'),
                ('A4096_regression', r3 / 'scores-A-4096-regression/results.json'),
                ('B1024_saved_microphone_audit', review / 'comparison-B-1024-6611a4c52675/audit.json'),
                ('A4096_saved_microphone_audit', review / 'comparison-A-4096-f6ce5aa370fb/audit.json'),
            ]},
        code={str(p.relative_to(root)): sha(p) for p in sorted((root / 'tools/overlap_gate').glob('*.py')) + [root / 'tests/test_overlap_gate.py']},
        constraints=dict(
            fixed_recognizer_speaker_model_clusterer_defaults_unchanged=True,
            host_only_until_phase_4=True,
            raw_caption_text_unchanged=True,
            total_application_peak_bytes=30000000,
            no_threshold_or_label_changes_after_test_scoring=True,
        ),
        environment=dict(python='private/layer-sensitivity-20261103/export-venv/bin/python', pydeps='/Volumes/Audiodrive/stt/pydeps',
                         note='system python3 lacks numpy; run tests/test_overlap_gate.py with the venv'),
    )
    out = lab / 'experiment.json'
    out.write_text(json.dumps(experiment, indent=2) + '\n')
    print(json.dumps(dict(written=str(out), sha256=sha(out), labels={s: experiment['labels']['files'][s]['sha256'][:12] for s in summaries},
                          ceiling=FALSE_ALARM_CEILING, panels=list(experiment['panels'])), indent=1))


if __name__ == '__main__':
    main()
