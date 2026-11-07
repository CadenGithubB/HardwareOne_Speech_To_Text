"""Overlap gate scoring: frame miss/false-alarm with a boundary collar, segment flags, and
the frozen threshold-selection rule.

A false alarm is the expensive error (it would trigger the duplicating two-stream path on
single-speaker speech), so the selection rule fixes a false-alarm ceiling first and buys as much
recall as that allows. Nothing here reads audio or runs a model.
"""
from __future__ import annotations

import math

import numpy as np

FRAME_THRESHOLD = 0.5        # fixed: a frame is "overlap" when its posterior reaches this
MIN_OVERLAP_FRAMES = 10      # a segment counts as overlapped when >= 10 valid frames (100 ms) have >= 2 speakers


def _valid(counts, collar):
    counts = np.asarray(counts)
    collar = np.asarray(collar, dtype=bool)
    if counts.shape != collar.shape:
        raise ValueError('counts and collar must have the same length')
    return counts, ~collar


def frame_rates(scores, counts, collar, threshold=FRAME_THRESHOLD) -> dict:
    """Miss and false-alarm rates over frames outside the collar.

    scores: per-frame overlap posterior (or 0/1 decisions); counts: labelled speaker count;
    collar: boolean mask of frames to ignore.
    """
    counts, valid = _valid(counts, collar)
    scores = np.asarray(scores, dtype=np.float64)
    if scores.shape != counts.shape:
        raise ValueError('scores must align with counts')
    flagged = scores >= threshold
    positive = valid & (counts >= 2)
    negative = valid & (counts <= 1)
    n_pos, n_neg = int(positive.sum()), int(negative.sum())
    miss = int(np.sum(positive & ~flagged))
    false_alarm = int(np.sum(negative & flagged))
    return dict(
        positive_frames=n_pos, negative_frames=n_neg, missed_frames=miss, false_alarm_frames=false_alarm,
        miss_rate=(miss / n_pos) if n_pos else math.nan,
        false_alarm_rate=(false_alarm / n_neg) if n_neg else math.nan,
    )


def frame_roc(scores, counts, collar) -> dict:
    """ROC over valid frames: list of (threshold, false_alarm_rate, miss_rate) and area under ROC."""
    counts, valid = _valid(counts, collar)
    scores = np.asarray(scores, dtype=np.float64)[valid]
    labels = (counts[valid] >= 2)
    n_pos, n_neg = int(labels.sum()), int((~labels).sum())
    if n_pos == 0 or n_neg == 0:
        return dict(points=[], auc=math.nan, positive_frames=n_pos, negative_frames=n_neg)
    order = np.argsort(-scores, kind='stable')
    s, l = scores[order], labels[order]
    tp = np.cumsum(l)
    fp = np.cumsum(~l)
    distinct = np.flatnonzero(np.diff(s)) if s.size > 1 else np.array([], dtype=int)
    idx = np.concatenate([distinct, [s.size - 1]])
    points = [(float(s[i]), float(fp[i] / n_neg), float(1.0 - tp[i] / n_pos)) for i in idx]
    fa = np.concatenate([[0.0], [p[1] for p in points]])
    recall = np.concatenate([[0.0], [1.0 - p[2] for p in points]])
    auc = float(np.trapezoid(recall, fa)) if hasattr(np, 'trapezoid') else float(np.trapz(recall, fa))
    return dict(points=points, auc=auc, positive_frames=n_pos, negative_frames=n_neg)


def segment_label(counts, collar, min_frames=MIN_OVERLAP_FRAMES) -> bool:
    """True when at least min_frames valid frames have two or more active speakers."""
    counts, valid = _valid(counts, collar)
    return int(np.sum(valid & (counts >= 2))) >= min_frames


def segment_fraction(scores, collar, threshold=FRAME_THRESHOLD) -> float:
    """Fraction of valid frames the gate calls overlap; the segment score used for routing."""
    scores = np.asarray(scores, dtype=np.float64)
    valid = ~np.asarray(collar, dtype=bool)
    if scores.shape != valid.shape:
        raise ValueError('scores must align with collar')
    n = int(valid.sum())
    return float(np.sum(valid & (scores >= threshold)) / n) if n else 0.0


def segment_metrics(flags, labels) -> dict:
    """Precision, recall and false-alarm rate of segment flags against segment labels."""
    flags = np.asarray(flags, dtype=bool)
    labels = np.asarray(labels, dtype=bool)
    if flags.shape != labels.shape:
        raise ValueError('flags and labels must align')
    tp = int(np.sum(flags & labels))
    fp = int(np.sum(flags & ~labels))
    fn = int(np.sum(~flags & labels))
    tn = int(np.sum(~flags & ~labels))
    return dict(
        segments=int(flags.size), positives=tp + fn, negatives=fp + tn,
        true_positive=tp, false_positive=fp, false_negative=fn, true_negative=tn,
        precision=(tp / (tp + fp)) if tp + fp else math.nan,
        recall=(tp / (tp + fn)) if tp + fn else math.nan,
        false_alarm_rate=(fp / (fp + tn)) if fp + tn else math.nan,
    )


def select_threshold(segment_scores, labels, ceiling) -> dict:
    """Frozen selection rule.

    Among candidate thresholds (every distinct score, plus "never flag"), keep those whose
    segment false-alarm rate is at or below the ceiling; choose the one with the highest
    recall; on ties choose the highest threshold (most conservative). Returns the threshold
    and its metrics. With no admissible threshold the result flags nothing (threshold inf).
    """
    scores = np.asarray(segment_scores, dtype=np.float64)
    labels = np.asarray(labels, dtype=bool)
    if scores.shape != labels.shape:
        raise ValueError('scores and labels must align')
    candidates = sorted(set(scores.tolist()) | {math.inf}, reverse=True)
    best = None
    for threshold in candidates:  # descending: ties resolved toward the higher threshold
        metrics = segment_metrics(scores >= threshold, labels)
        fa = metrics['false_alarm_rate']
        if not (math.isnan(fa) or fa <= ceiling):
            continue
        recall = 0.0 if math.isnan(metrics['recall']) else metrics['recall']
        if best is None or recall > best['recall']:
            best = dict(threshold=threshold, recall=recall, metrics=metrics)
    return dict(threshold=best['threshold'], ceiling=ceiling, metrics=best['metrics'])
