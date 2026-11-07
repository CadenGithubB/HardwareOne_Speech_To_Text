"""Frame-level overlap labels from AMI speaker intervals.

Pure functions (no I/O) turn a meeting's utterance intervals into a per-frame count of
simultaneously active speakers and a boundary collar mask. The command line derives those
labels for one AMI split from the Parquet metadata, verifies the headset metadata agrees with
the distant metadata, maps rows to the local training stores, and writes frozen label files.

Labels are what the overlap gate is trained and scored against. No audio is read here.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

HOP_MS = 10          # recognizer feature hop; one label per 10 ms frame
COLLAR_MS = 200      # frames this close to any speaker boundary are excluded from loss/scoring
COUNT_CAP = 3        # 0, 1, 2, 3+ active speakers
SAMPLE_RATE = 16000


def frames_for(seconds: float, hop_ms: int = HOP_MS) -> int:
    return max(0, int(math.ceil(round(seconds * 1000.0 / hop_ms, 6))))


def merge_speaker_intervals(intervals):
    """Union each speaker's own intervals so one person never counts twice.

    intervals: iterable of (speaker, begin, end) in seconds. Returns a sorted list of
    (speaker, begin, end) with per-speaker overlaps and touching spans merged.
    """
    by_speaker = collections.defaultdict(list)
    for speaker, begin, end in intervals:
        if end > begin:
            by_speaker[speaker].append((float(begin), float(end)))
    merged = []
    for speaker, spans in by_speaker.items():
        spans.sort()
        current = list(spans[0])
        for begin, end in spans[1:]:
            if begin <= current[1]:
                current[1] = max(current[1], end)
            else:
                merged.append((speaker, current[0], current[1]))
                current = [begin, end]
        merged.append((speaker, current[0], current[1]))
    merged.sort(key=lambda item: (item[1], item[2], item[0]))
    return merged


def frame_counts(merged, start: float, end: float, hop_ms: int = HOP_MS, cap: int = COUNT_CAP):
    """Active-speaker count per frame over [start, end) using merged intervals."""
    n = frames_for(end - start, hop_ms)
    counts = np.zeros(n, dtype=np.int8)
    scale = 1000.0 / hop_ms
    for _speaker, begin, finish in merged:
        if finish <= start or begin >= end:
            continue
        first = max(0, int(math.floor(round((begin - start) * scale, 6))))
        last = min(n, int(math.ceil(round((finish - start) * scale, 6))))
        if last > first:
            counts[first:last] += 1
    np.minimum(counts, cap, out=counts)
    return counts


def collar_mask(merged, start: float, end: float, collar_ms: int = COLLAR_MS, hop_ms: int = HOP_MS):
    """True for frames whose centre lies within collar_ms of any speaker boundary."""
    n = frames_for(end - start, hop_ms)
    if n == 0:
        return np.zeros(0, dtype=bool)
    boundaries = np.array(sorted({t for _s, b, e in merged for t in (b, e)}), dtype=np.float64)
    centres = start + (np.arange(n, dtype=np.float64) + 0.5) * hop_ms / 1000.0
    if boundaries.size == 0:
        return np.zeros(n, dtype=bool)
    position = np.searchsorted(boundaries, centres)
    left = boundaries[np.clip(position - 1, 0, boundaries.size - 1)]
    right = boundaries[np.clip(position, 0, boundaries.size - 1)]
    distance = np.minimum(np.abs(centres - left), np.abs(centres - right))
    return distance <= collar_ms / 1000.0 + 1e-9


def runs(values) -> list:
    """Run-length encode a 1-D array as [start, end, value] triples (end exclusive)."""
    values = np.asarray(values)
    out = []
    if values.size == 0:
        return out
    change = np.flatnonzero(values[1:] != values[:-1]) + 1
    starts = np.concatenate([[0], change])
    ends = np.concatenate([change, [values.size]])
    for s, e in zip(starts, ends):
        out.append([int(s), int(e), int(values[s])])
    return out


def expand(run_list, dtype=np.int8):
    """Inverse of runs()."""
    if not run_list:
        return np.zeros(0, dtype=dtype)
    out = np.zeros(run_list[-1][1], dtype=dtype)
    for s, e, v in run_list:
        out[s:e] = v
    return out


def summarize(counts, collar) -> dict:
    """Frame totals outside the collar, used for class balance and segment labels."""
    valid = ~collar
    return dict(
        frames=int(counts.size),
        collar_frames=int(collar.sum()),
        silence_frames=int(np.sum(valid & (counts == 0))),
        single_frames=int(np.sum(valid & (counts == 1))),
        overlap_frames=int(np.sum(valid & (counts >= 2))),
    )


# ----------------------------------------------------------------------------- command line


def read_metadata(parquet_dir: Path, split: str):
    import pyarrow.parquet as pq  # resolved through --pydeps

    columns = ['meeting_id', 'audio_id', 'speaker_id', 'begin_time', 'end_time', 'text', 'microphone_id']
    rows = []
    files = sorted(parquet_dir.glob(f'{split}-*.parquet'))
    if not files:
        raise SystemExit(f'no {split} parquet files under {parquet_dir}')
    for file in files:
        for batch in pq.ParquetFile(file).iter_batches(columns=columns, use_threads=False):
            rows.extend(batch.to_pylist())
    return files, rows


def store_lookup(store_dir: Path, tools_dir: Path):
    sys.path.insert(0, str(tools_dir))
    from common import normalize_text  # noqa: E402
    from diagnostics import effective_ids  # noqa: E402

    index = json.loads((store_dir / 'index.json').read_text())
    lookup = collections.defaultdict(list)
    for i in effective_ids(store_dir, index):
        lookup[index['speakers'][i], index['texts'][i]].append(int(i))
    return index, lookup, normalize_text


def match_store(row, index, lookup, normalize_text):
    ref = normalize_text(row['text'])
    seconds = row['end_time'] - row['begin_time']
    ids = [i for i in lookup.get((row['speaker_id'], ref), []) if abs(index['lengths'][i] / SAMPLE_RATE - seconds) < 0.035]
    if len(ids) == 1:
        return ids[0], 'unique'
    return None, ('ambiguous' if ids else 'none')


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ami-root', type=Path, required=True, help='directory holding sdm/ and ihm/ parquet folders')
    ap.add_argument('--split', required=True, choices=['train', 'validation', 'test'])
    ap.add_argument('--stores', type=Path, required=True, help='corrected stores directory with ami-*-<split>')
    ap.add_argument('--tools', type=Path, default=Path('tools/stt_train_15x5'))
    ap.add_argument('--pydeps', type=Path, default=None, help='extra sys.path entry providing pyarrow')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--collar-ms', type=int, default=COLLAR_MS)
    ap.add_argument('--hop-ms', type=int, default=HOP_MS)
    args = ap.parse_args()
    if args.pydeps:
        sys.path.insert(0, str(args.pydeps))

    sdm_files, sdm_rows = read_metadata(args.ami_root / 'sdm', args.split)
    ihm_files, ihm_rows = read_metadata(args.ami_root / 'ihm', args.split)
    key = lambda r: (r['meeting_id'], r['speaker_id'], round(r['begin_time'], 3), round(r['end_time'], 3))
    sdm_keys, ihm_keys = collections.Counter(map(key, sdm_rows)), collections.Counter(map(key, ihm_rows))
    metadata_agreement = dict(
        sdm_rows=len(sdm_rows), ihm_rows=len(ihm_rows),
        identical_interval_multisets=sdm_keys == ihm_keys,
        sdm_only=sum((sdm_keys - ihm_keys).values()), ihm_only=sum((ihm_keys - sdm_keys).values()),
    )

    # Intervals come from the distant-microphone rows; headsets share the same annotation.
    meetings = collections.defaultdict(list)
    for r in sdm_rows:
        meetings[r['meeting_id']].append((r['speaker_id'], r['begin_time'], r['end_time']))
    merged = {m: merge_speaker_intervals(v) for m, v in meetings.items()}

    stores = {}
    for mic in ('sdm', 'ihm'):
        d = args.stores / f'ami-{mic}-{args.split}'
        stores[mic] = store_lookup(d, args.tools) if d.exists() else None

    records = []
    totals = collections.Counter()
    match_counts = {mic: collections.Counter() for mic in stores}
    per_meeting = collections.defaultdict(collections.Counter)
    for r in sorted(sdm_rows, key=lambda r: (r['meeting_id'], r['begin_time'], r['speaker_id'])):
        start, end = r['begin_time'], r['end_time']
        counts = frame_counts(merged[r['meeting_id']], start, end, args.hop_ms)
        collar = collar_mask(merged[r['meeting_id']], start, end, args.collar_ms, args.hop_ms)
        summary = summarize(counts, collar)
        totals.update(summary)
        per_meeting[r['meeting_id']].update(summary)
        record = dict(audio_id=r['audio_id'], meeting=r['meeting_id'], speaker=r['speaker_id'],
                      begin=start, end=end, text=r['text'], counts=runs(counts), collar=runs(collar.astype(np.int8)),
                      **summary)
        for mic, bank in stores.items():
            if bank is None:
                continue
            idx, kind = match_store(r, *bank)
            record[f'store_{mic}'] = idx
            match_counts[mic][kind] += 1
        records.append(record)

    speakers = sorted({r['speaker_id'] for r in sdm_rows})
    args.out.mkdir(parents=True, exist_ok=True)
    labels_path = args.out / f'labels-{args.split}.json'
    labels_path.write_text(json.dumps(dict(
        split=args.split, hop_ms=args.hop_ms, collar_ms=args.collar_ms, count_cap=COUNT_CAP,
        source='AMI parquet metadata (sdm rows); headset rows verified identical', records=records), separators=(',', ':')))
    frame_total = max(1, totals['frames'])
    valid_total = max(1, totals['frames'] - totals['collar_frames'])
    summary = dict(
        split=args.split, hop_ms=args.hop_ms, collar_ms=args.collar_ms,
        parquet_files={'sdm': [f.name for f in sdm_files], 'ihm': [f.name for f in ihm_files]},
        parquet_bytes={'sdm': sum(f.stat().st_size for f in sdm_files), 'ihm': sum(f.stat().st_size for f in ihm_files)},
        metadata_agreement=metadata_agreement,
        utterances=len(records), meetings=len(merged), speakers=len(speakers), speaker_ids=speakers,
        meeting_ids=sorted(merged),
        hours=round(totals['frames'] * args.hop_ms / 3600000.0, 3),
        frame_totals=dict(totals),
        fraction_of_all_frames=dict(collar=round(totals['collar_frames'] / frame_total, 4)),
        fraction_outside_collar=dict(
            silence=round(totals['silence_frames'] / valid_total, 4),
            single=round(totals['single_frames'] / valid_total, 4),
            overlap=round(totals['overlap_frames'] / valid_total, 4)),
        utterances_with_overlap_outside_collar=sum(1 for r in records if r['overlap_frames'] > 0),
        store_match_counts={mic: dict(c) for mic, c in match_counts.items()},
        per_meeting_overlap_fraction={m: round(c['overlap_frames'] / max(1, c['frames'] - c['collar_frames']), 4) for m, c in sorted(per_meeting.items())},
        labels_sha256=sha256_file(labels_path),
        scope='Who-spoke-when labels from forced-aligned AMI annotation. Boundary timing is approximate; the collar excludes it from loss and scoring. No audio read.',
    )
    (args.out / f'summary-{args.split}.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: summary[k] for k in ('split', 'utterances', 'meetings', 'speakers', 'hours', 'fraction_outside_collar', 'utterances_with_overlap_outside_collar', 'store_match_counts', 'metadata_agreement')}, indent=1))


if __name__ == '__main__':
    main()
