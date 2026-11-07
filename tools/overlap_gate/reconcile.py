"""Reconcile the frozen overlap labels against independent existing panels.

Checks, all read-only:
  1. Every frozen label record is reproduced from freshly read AMI metadata (sdm and ihm union).
  2. The 32 real pairs: the stored overlap length matches the annotation and the overlapped
     region is labelled exactly two speakers, with no third speaker anywhere in the window.
  3. The 24 distant overlap clips: competitor speakers and overlap fraction match the audit.
  4. Train, validation and test share no meeting and no speaker.
Writes reconcile.json next to the labels. Exit status is nonzero when any check fails.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overlap_gate import labels  # noqa: E402


def read_rows(ami_root: Path, split: str):
    import pyarrow.parquet as pq

    rows = {}
    for mic in ('sdm', 'ihm'):
        for file in sorted((ami_root / mic).glob(f'{split}-*.parquet')):
            for batch in pq.ParquetFile(file).iter_batches(columns=['meeting_id', 'speaker_id', 'begin_time', 'end_time'], use_threads=False):
                for r in batch.to_pylist():
                    rows[(r['meeting_id'], r['speaker_id'], round(r['begin_time'], 3), round(r['end_time'], 3))] = r
    meetings = collections.defaultdict(list)
    for r in rows.values():
        meetings[r['meeting_id']].append((r['speaker_id'], r['begin_time'], r['end_time']))
    return {m: labels.merge_speaker_intervals(v) for m, v in meetings.items()}


def check_records(frozen, merged):
    hop, collar_ms = frozen['hop_ms'], frozen['collar_ms']
    mismatched = 0
    for rec in frozen['records']:
        counts = labels.frame_counts(merged[rec['meeting']], rec['begin'], rec['end'], hop)
        collar = labels.collar_mask(merged[rec['meeting']], rec['begin'], rec['end'], collar_ms, hop)
        if labels.runs(counts) != rec['counts'] or labels.runs(collar.astype(np.int8)) != rec['collar']:
            mismatched += 1
    return dict(records=len(frozen['records']), mismatched=mismatched, passed=mismatched == 0)


def check_real_pairs(pairs, merged, hop):
    results = []
    for row in pairs['rows']:
        a, b = row['utterances']
        m = merged[row['meeting']]
        expected_overlap = a['end'] - b['start']
        stored_overlap = row['overlap_samples'] / labels.SAMPLE_RATE
        start, end = a['start'], a['start'] + row['frames'] / labels.SAMPLE_RATE
        counts = labels.frame_counts(m, start, end, hop)
        # Frame of the overlap start rounds down and of the overlap end rounds up, as in
        # frame_counts; one frame of slack on each side absorbs float rounding of the times.
        f0 = int((b['start'] - start) * 1000 // hop)
        f1 = labels.frames_for(a['end'] - start, hop)
        region = counts[f0 + 1:f1 - 1]
        before = counts[:max(0, f0 - 1)]
        after = counts[f1 + 1:]
        ok = (abs(expected_overlap - stored_overlap) <= 0.021 and region.size > 0 and bool(np.all(region == 2))
              and int(counts.max()) == 2 and bool(np.all(before == 1)) and bool(np.all(after == 1)))
        results.append(dict(id=row['id'][:12], meeting=row['meeting'], stored_overlap_s=round(stored_overlap, 3),
                            annotation_overlap_s=round(expected_overlap, 3), overlap_region_all_two=bool(np.all(region == 2)),
                            max_speakers=int(counts.max()), ok=ok))
    return dict(pairs=len(results), passed=all(r['ok'] for r in results), rows=results)


def check_clips(clips, merged, hop):
    results = []
    for clip in clips:
        start, end = clip['span']
        m = merged[clip['meeting']]
        others = [iv for iv in m if iv[0] != clip['target_speaker']]
        competitors = sorted({s for s, b, e in others if b < end and e > start})
        counts = labels.frame_counts(others, start, end, hop)
        fraction = float(np.mean(counts >= 1)) if counts.size else 0.0
        ok = competitors == sorted(clip['competitor_speakers']) and abs(fraction - clip['overlap_fraction']) <= 0.02
        results.append(dict(id=clip['id'], competitors_match=competitors == sorted(clip['competitor_speakers']),
                            audit_fraction=round(clip['overlap_fraction'], 4), label_fraction=round(fraction, 4), ok=ok))
    return dict(clips=len(results), passed=all(r['ok'] for r in results), rows=results)


def check_disjoint(summaries, train_exclusions):
    """No shared meetings anywhere; shared speakers are allowed only between train and
    validation and only when the frozen fitting set excludes them."""
    out = {}
    names = sorted(summaries)
    excluded = set(train_exclusions)
    passed = True
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            meetings = sorted(set(summaries[a]['meeting_ids']) & set(summaries[b]['meeting_ids']))
            speakers = sorted(set(summaries[a]['speaker_ids']) & set(summaries[b]['speaker_ids']))
            resolved = {a, b} == {'train', 'validation'} and set(speakers) <= excluded
            out[f'{a}/{b}'] = dict(shared_meetings=meetings, shared_speakers=speakers, resolved_by_train_exclusion=resolved and bool(speakers))
            passed = passed and not meetings and (not speakers or resolved)
    return dict(passed=passed, train_speaker_exclusions=sorted(excluded), pairs=out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ami-root', type=Path, required=True)
    ap.add_argument('--labels', type=Path, required=True, help='directory with labels-*.json and summary-*.json')
    ap.add_argument('--real-pairs', type=Path, required=True)
    ap.add_argument('--clips', type=Path, required=True, help='overlap-investigation annotation-audit.json')
    ap.add_argument('--pydeps', type=Path, default=None)
    ap.add_argument('--train-speaker-exclusions', nargs='*', default=[], help='speakers removed from the fitting set because they also appear in validation')
    args = ap.parse_args()
    if args.pydeps:
        sys.path.insert(0, str(args.pydeps))

    report = {}
    merged = {}
    for split in ('train', 'validation', 'test'):
        merged[split] = read_rows(args.ami_root, split)
        frozen = json.loads((args.labels / f'labels-{split}.json').read_text())
        report[f'records_{split}'] = check_records(frozen, merged[split])
    hop = frozen['hop_ms']
    report['real_pairs'] = check_real_pairs(json.loads(args.real_pairs.read_text()), merged['validation'], hop)
    report['overlap_clips'] = check_clips(json.loads(args.clips.read_text()), merged['test'], hop)
    summaries = {s: json.loads((args.labels / f'summary-{s}.json').read_text()) for s in ('train', 'validation', 'test')}
    report['disjoint'] = check_disjoint(summaries, args.train_speaker_exclusions)
    report['passed'] = all(v['passed'] for k, v in report.items() if isinstance(v, dict) and 'passed' in v)
    (args.labels / 'reconcile.json').write_text(json.dumps(report, indent=2) + '\n')
    brief = {k: (v['passed'] if isinstance(v, dict) else v) for k, v in report.items()}
    print(json.dumps(brief, indent=1))
    sys.exit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
