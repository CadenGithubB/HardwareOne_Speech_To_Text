"""Constructed checks for the overlap gate labels and scorer (tools/overlap_gate).

Run: python3 -m unittest tests.test_overlap_gate
These prove the arithmetic on hand-built cases; they do not score any real gate.
"""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from overlap_gate import labels, scorer  # noqa: E402


class LabelTests(unittest.TestCase):
    def test_same_speaker_overlapping_turns_count_once(self):
        merged = labels.merge_speaker_intervals([('A', 0.0, 1.0), ('A', 0.8, 2.0), ('A', 2.0, 2.5)])
        self.assertEqual(merged, [('A', 0.0, 2.5)])
        counts = labels.frame_counts(merged, 0.0, 2.5)
        self.assertEqual(counts.size, 250)
        self.assertTrue(np.all(counts == 1))

    def test_two_speakers_produce_two_only_in_the_shared_span(self):
        merged = labels.merge_speaker_intervals([('A', 0.0, 2.0), ('B', 1.0, 3.0)])
        counts = labels.frame_counts(merged, 0.0, 4.0)
        self.assertEqual(counts.size, 400)
        self.assertTrue(np.all(counts[:100] == 1))
        self.assertTrue(np.all(counts[100:200] == 2))
        self.assertTrue(np.all(counts[200:300] == 1))
        self.assertTrue(np.all(counts[300:] == 0))

    def test_count_cap_and_window_clipping(self):
        merged = labels.merge_speaker_intervals([(s, 0.0, 1.0) for s in 'ABCDE'])
        counts = labels.frame_counts(merged, 0.5, 1.5)
        self.assertEqual(counts.size, 100)
        self.assertTrue(np.all(counts[:50] == labels.COUNT_CAP))
        self.assertTrue(np.all(counts[50:] == 0))

    def test_collar_covers_200ms_each_side_of_every_boundary(self):
        merged = labels.merge_speaker_intervals([('A', 1.0, 2.0)])
        collar = labels.collar_mask(merged, 0.0, 3.0)
        self.assertEqual(collar.size, 300)
        # boundaries at 1.0 s and 2.0 s: frames with centres in [0.8,1.2] and [1.8,2.2]
        expected = np.zeros(300, dtype=bool)
        expected[80:120] = True
        expected[180:220] = True
        self.assertTrue(np.array_equal(collar, expected))

    def test_runs_roundtrip(self):
        values = np.array([0, 0, 1, 1, 1, 2, 0], dtype=np.int8)
        encoded = labels.runs(values)
        self.assertEqual(encoded, [[0, 2, 0], [2, 5, 1], [5, 6, 2], [6, 7, 0]])
        self.assertTrue(np.array_equal(labels.expand(encoded), values))
        self.assertEqual(labels.runs(np.zeros(0)), [])

    def test_summary_excludes_collar(self):
        counts = np.array([0, 1, 1, 2, 2, 2], dtype=np.int8)
        collar = np.array([0, 0, 1, 1, 0, 0], dtype=bool)
        s = labels.summarize(counts, collar)
        self.assertEqual((s['silence_frames'], s['single_frames'], s['overlap_frames'], s['collar_frames']), (1, 1, 2, 2))


class ScorerTests(unittest.TestCase):
    def setUp(self):
        self.counts = np.array([1, 1, 2, 2, 2, 2, 1, 0], dtype=np.int8)
        self.collar = np.array([0, 1, 1, 0, 0, 0, 0, 0], dtype=bool)

    def test_perfect_prediction(self):
        pred = (self.counts >= 2).astype(float)
        r = scorer.frame_rates(pred, self.counts, self.collar)
        self.assertEqual((r['positive_frames'], r['negative_frames']), (3, 3))
        self.assertEqual((r['miss_rate'], r['false_alarm_rate']), (0.0, 0.0))

    def test_inverted_prediction_misses_everything(self):
        pred = (self.counts < 2).astype(float)
        r = scorer.frame_rates(pred, self.counts, self.collar)
        self.assertEqual((r['miss_rate'], r['false_alarm_rate']), (1.0, 1.0))

    def test_silent_gate_misses_but_never_false_alarms(self):
        r = scorer.frame_rates(np.zeros(8), self.counts, self.collar)
        self.assertEqual((r['miss_rate'], r['false_alarm_rate']), (1.0, 0.0))

    def test_errors_inside_collar_do_not_count(self):
        pred = (self.counts >= 2).astype(float)
        pred[1] = 1.0  # false alarm inside the collar
        pred[2] = 0.0  # miss inside the collar
        r = scorer.frame_rates(pred, self.counts, self.collar)
        self.assertEqual((r['miss_rate'], r['false_alarm_rate']), (0.0, 0.0))

    def test_roc_auc_bounds(self):
        perfect = (self.counts >= 2).astype(float)
        self.assertAlmostEqual(scorer.frame_roc(perfect, self.counts, self.collar)['auc'], 1.0)
        inverted = 1.0 - perfect
        self.assertAlmostEqual(scorer.frame_roc(inverted, self.counts, self.collar)['auc'], 0.0)
        no_positive = scorer.frame_roc(perfect, np.ones(8, dtype=np.int8), self.collar)
        self.assertTrue(math.isnan(no_positive['auc']))

    def test_segment_label_requires_minimum_valid_overlap(self):
        counts = np.array([2] * 9 + [1] * 10, dtype=np.int8)
        collar = np.zeros(19, dtype=bool)
        self.assertFalse(scorer.segment_label(counts, collar))
        counts = np.array([2] * 10 + [1] * 10, dtype=np.int8)
        collar = np.zeros(20, dtype=bool)
        self.assertTrue(scorer.segment_label(counts, collar))
        collar[0] = True  # one overlapped frame falls in the collar
        self.assertFalse(scorer.segment_label(counts, collar))

    def test_segment_fraction_ignores_collar(self):
        scores = np.array([1.0, 1.0, 0.0, 0.0])
        collar = np.array([1, 0, 0, 0], dtype=bool)
        self.assertAlmostEqual(scorer.segment_fraction(scores, collar), 1 / 3)
        self.assertEqual(scorer.segment_fraction(scores, np.ones(4, dtype=bool)), 0.0)

    def test_segment_metrics_swapped_and_empty(self):
        labels_ = np.array([1, 1, 0, 0], dtype=bool)
        m = scorer.segment_metrics(~labels_, labels_)
        self.assertEqual((m['precision'], m['recall'], m['false_alarm_rate']), (0.0, 0.0, 1.0))
        m = scorer.segment_metrics(np.zeros(4, dtype=bool), labels_)
        self.assertTrue(math.isnan(m['precision']))
        self.assertEqual((m['recall'], m['false_alarm_rate']), (0.0, 0.0))

    def test_threshold_selection_respects_ceiling_and_prefers_conservative_tie(self):
        scores = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05])
        labels_ = np.array([1, 1, 1, 0, 1, 0, 0, 0, 0, 0], dtype=bool)
        # Negatives: 0.6, 0.4, 0.3, 0.2, 0.1, 0.05 (six). Ceiling 0 -> threshold must exceed 0.6.
        r = scorer.select_threshold(scores, labels_, ceiling=0.0)
        self.assertEqual(r['threshold'], 0.7)
        self.assertAlmostEqual(r['metrics']['recall'], 0.75)
        # Ceiling 1/6 admits the 0.6 negative; 0.5 then adds the fourth positive.
        r = scorer.select_threshold(scores, labels_, ceiling=1 / 6)
        self.assertEqual(r['threshold'], 0.5)
        self.assertAlmostEqual(r['metrics']['recall'], 1.0)
        # Equal recall at 0.5 and 0.4 (0.4 is another negative): the higher threshold wins the tie.
        r = scorer.select_threshold(scores, labels_, ceiling=2 / 6)
        self.assertEqual(r['threshold'], 0.5)

    def test_threshold_selection_with_no_admissible_point_flags_nothing(self):
        scores = np.array([0.9, 0.9])
        labels_ = np.array([1, 0], dtype=bool)
        r = scorer.select_threshold(scores, labels_, ceiling=0.0)
        self.assertEqual(r['threshold'], math.inf)
        self.assertEqual(r['metrics']['false_positive'], 0)


class G2Tests(unittest.TestCase):
    """Shape and target-grid checks for the G2 classifier; no training, no data."""

    @classmethod
    def setUpClass(cls):
        try:
            import torch  # noqa: F401
            from overlap_gate import g2_common
        except Exception as e:  # pragma: no cover - environment without torch
            raise unittest.SkipTest(f'torch unavailable: {e}')
        cls.g2 = g2_common

    def test_to_20ms_targets_and_mask(self):
        counts = np.array([0, 0, 1, 1, 2, 3, 1, 1], dtype=np.int8)
        collar = np.array([0, 0, 0, 1, 0, 0, 0, 0], dtype=bool)
        target, mask = self.g2.to_20ms(counts, collar)
        self.assertEqual(target.tolist(), [0, 1, 2, 1])          # count 3 is capped to class 2
        self.assertEqual(mask.tolist(), [True, False, True, True])  # collar in either 10 ms frame masks the 20 ms frame

    def test_model_shape_and_budget(self):
        import torch
        model = self.g2.G2Net(torch.zeros(64), torch.ones(64))
        self.assertLessEqual(self.g2.parameter_count(model), 50000)
        out = model(torch.zeros(2, 64, 200))
        self.assertEqual(tuple(out.shape), (2, 3, 100))
        out = model(torch.zeros(1, 64, 301))
        self.assertEqual(tuple(out.shape), (1, 3, 151))

    def test_posterior_upsampling_matches_label_grid(self):
        import torch
        logits = torch.zeros(3, 5)
        logits[2] = 10.0
        post = self.g2.overlap_posterior_10ms(logits, 9)
        self.assertEqual(post.size, 9)
        self.assertTrue(np.all(post > 0.99))
        post = self.g2.overlap_posterior_10ms(logits, 12)
        self.assertEqual(post.size, 12)


if __name__ == '__main__':
    unittest.main()
