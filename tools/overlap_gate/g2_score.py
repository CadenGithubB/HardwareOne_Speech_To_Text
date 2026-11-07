"""Score the selected G2 checkpoint under the frozen protocol.

Panels: the 598-case synthetic/real32 suite, the 163-case saved microphone panel, the fixed
validation subsample (threshold selection) and the full AMI test split, distant microphone (scored
once). Posterior = P(class 2) on the 10 ms grid. Also writes per-frame arrays per panel in the
same layout as G0, and a parity check of the Python raw log-mel against the C++ frontend.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overlap_gate import labels, scorer  # noqa: E402
from overlap_gate import g2_common as g2  # noqa: E402
from overlap_gate.g0_extract import R3, FRONTEND, PanelWriter, intervals_to_labels, read_pcm, sha  # noqa: E402
from overlap_gate.g0_score import clean, groupby, partition_key  # noqa: E402

ROOT = g2.ROOT


class Writer(PanelWriter):
    """Reuses the G0 layout; 'entropy' slot holds the G2 posterior, 'nonblank' is unused (zeros)."""

    def add_post(self, case_id, group, condition, counts, collar, post, **extra):
        self.add(case_id, group, condition, counts, collar, post.astype(np.float16), np.zeros(counts.size, np.float16), **extra)


def load_model(phase3: Path):
    sel = json.loads((phase3 / 'selection.json').read_text())['selected']
    ck = torch.load(phase3 / sel['checkpoint'], weights_only=True, map_location='cpu')
    assert sha((phase3 / sel['checkpoint']).read_bytes()) == sel['sha256']
    model = g2.G2Net(ck['mean'], ck['std'])
    model.load_state_dict(ck['state_dict'])
    model.eval()
    return model, sel


def posterior(model, frontend, pcm_i16: np.ndarray, n_frames: int) -> np.ndarray:
    audio = pcm_i16.astype(np.float32) / 32768
    with torch.inference_mode():
        logits = model(frontend(audio)[None])[0]
    return g2.overlap_posterior_10ms(logits, n_frames)


def parity_check(frontend, pcm_i16: np.ndarray, work: Path) -> dict:
    """Python raw log-mel vs the C++ frontend on the same PCM.

    The C++ driver emits per-utterance normalized features plus the per-bin means it used. We
    normalize the Python raw log-mel the same way and compare both the normalized features and the
    per-bin means; equality of both implies equal raw features. (Inverting with the driver's
    variance block is not used: its storage convention differs from the Python estimator.)
    """
    work.mkdir(parents=True, exist_ok=True)
    p, f = work / 'parity.pcm', work / 'parity.f32'
    pcm_i16.astype('<i2').tofile(p)
    subprocess.run([str(FRONTEND), str(p), str(f), 'no_dither'], check=True, stdout=subprocess.DEVNULL)
    cpp_norm = np.fromfile(f, '<f4').reshape(-1, 64).T
    cpp_means = np.fromfile(str(f) + '.stats', '<f8')[:64]
    py_raw = frontend(pcm_i16.astype(np.float32) / 32768).numpy().astype(np.float64)
    n = min(cpp_norm.shape[1], py_raw.shape[1])
    py_raw = py_raw[:, :n]
    mu = py_raw.mean(axis=1, keepdims=True)
    sd = np.sqrt(((py_raw - mu) ** 2).sum(axis=1, keepdims=True) / max(n - 1, 1))
    py_norm = (py_raw - mu) / (sd + 1e-5)
    return dict(frames=int(n), normalized_max_abs_diff=float(np.abs(cpp_norm[:, :n] - py_norm).max()),
                per_bin_mean_max_abs_diff=float(np.abs(cpp_means - mu[:, 0]).max()))


def panel_synthetic(model, frontend, w):
    suite = json.loads((R3 / 'eval-suite.json').read_text())
    for c in suite['cases']:
        pcm = read_pcm(c['mixture']['pcm'] if c['mixture']['pcm'].startswith('/') else str(R3 / c['mixture']['pcm']))
        seconds = pcm.size / g2.SAMPLE_RATE
        if c['condition'] == 'real-overlap':
            a, b = c['annotation']['utterances']
            intervals = [(a['speaker'], 0.0, a['end'] - a['start']), (b['speaker'], b['start'] - a['start'], b['end'] - a['start'])]
        elif c['condition'] == 'two-speakers':
            s0, s1 = c['sources']
            intervals = [('s0', 0.0, s0['length'] / g2.SAMPLE_RATE), ('s1', c['offset_samples'] / g2.SAMPLE_RATE, (c['offset_samples'] + s1['length']) / g2.SAMPLE_RATE)]
        elif c['condition'].startswith('no-speech'):
            intervals = []
        else:
            intervals = [('s0', 0.0, c['sources'][0]['length'] / g2.SAMPLE_RATE)]
        counts, collar = intervals_to_labels(intervals, seconds)
        w.add_post(c['id'], c['group'], c['condition'], counts, collar, posterior(model, frontend, pcm, counts.size),
                   partition=c['partition'], overlap_requested=c.get('overlap_requested'), second_db=c.get('second_db'))


def panel_microphone(model, frontend, w):
    sys.path.insert(0, str(ROOT / 'private/stt-detector-followup'))
    cwd = os.getcwd()
    os.chdir(ROOT)
    from cases import cases  # noqa: E402
    os.chdir(cwd)
    baseline = json.loads((ROOT / 'private/stt-loss-round3-review/baseline.json').read_text())
    clips = {c['id']: c for c in json.loads((ROOT / 'private/training-track/overlap-investigation/annotation-audit.json').read_text())}
    for c, b in zip(cases, baseline['cases']):
        pcm = np.asarray(c['pcm'], dtype='<i2')
        assert b['id'] == c['id'] and sha(pcm.tobytes()) == b['pcm_sha256']
        seconds = pcm.size / g2.SAMPLE_RATE
        if c['group'] == 'overlap':
            clip = clips[c['id']]
            start, end = clip['span']
            intervals = [(clip['target_speaker'], 0.0, end - start)]
            intervals += [(k['speaker_id'], max(0.0, k['begin_time'] - start), min(end - start, k['end_time'] - start)) for k in clip['competitors']]
            condition = 'real-overlap-clip'
        elif c['group'] == 'background':
            intervals, condition = [], 'no-speech'
        else:
            intervals, condition = [('s0', 0.0, seconds)], 'single-speaker'
        counts, collar = intervals_to_labels(intervals, seconds)
        # Long clips are scored in 20 s pieces as the segmenter would deliver them.
        post = np.concatenate([posterior(model, frontend, pcm[i:i + 320000], labels.frames_for(min(320000, pcm.size - i) / g2.SAMPLE_RATE))
                               for i in range(0, pcm.size, 320000)])[:counts.size]
        w.add_post(c['id'], c['group'], condition, counts, collar, post)


def panel_store(model, frontend, w, split, records, condition):
    bank = g2.Features(f'ami-sdm-{split}')                 # precomputed raw log-mel, identical to frontend(pcm)
    for r in records:
        counts = labels.expand(r['counts'])
        collar = labels.expand(r['collar']).astype(bool)
        with torch.inference_mode():
            logits = model(torch.from_numpy(bank.slice(r['audio_id']))[None])[0]
        w.add_post(r['audio_id'], r['meeting'], condition, counts, collar, g2.overlap_posterior_10ms(logits, counts.size), store_index=r['store_sdm'], speaker=r['speaker'])


def panel_dev_negatives(model, w):
    """Non-AMI single-speaker dev windows (g2b): negatives for threshold selection, scored with the validation panel."""
    banks = {}
    for d in g2.dev_negatives():
        banks.setdefault(d['store'], g2.Features(d['store']))
        with torch.inference_mode():
            logits = model(torch.from_numpy(banks[d['store']].slice(d['key']))[None])[0]
        w.add_post(d['audio_id'], d['store'], 'nonami-dev-single', d['counts'], d['collar'], g2.overlap_posterior_10ms(logits, d['counts'].size), partition='nonami-dev')


def frame_block(cases, key):
    s = np.concatenate([c[key] for c in cases]).astype(np.float64)
    counts = np.concatenate([c['counts'] for c in cases])
    collar = np.concatenate([c['collar'] for c in cases])
    return clean(dict(cases=len(cases), **scorer.frame_rates(s, counts, collar), roc_auc=scorer.frame_roc(s, counts, collar)['auc']))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--variant', choices=['g2', 'g2b', 'g2c'], default='g2')
    ap.add_argument('--phase3', type=Path, default=None, help='default phase3 for g2, phase3b for g2b, phase3c for g2c')
    ap.add_argument('--skip-test', action='store_true', help='score everything except the one-shot AMI test')
    args = ap.parse_args()
    if args.phase3 is None:
        args.phase3 = {'g2': g2.PHASE3, 'g2b': g2.LABELS / 'phase3b', 'g2c': g2.LABELS / 'phase3c'}[args.variant]
    out = args.phase3 / 'g2'
    out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    model, selected = load_model(args.phase3)
    frontend = g2.RawFrontend()
    exp = json.loads((g2.LABELS / 'experiment.json').read_text())
    ceiling = exp['operating_point']['false_alarm_ceiling']

    val_records = g2.validation_subsample()
    parity = parity_check(frontend, g2.Store('ami-sdm-validation').pcm(val_records[0]['store_sdm']), out / 'work')
    panels = {}
    def validation_panel(w):
        panel_store(model, frontend, w, 'validation', val_records, 'ami-validation')
        if args.variant in ('g2b', 'g2c'):
            panel_dev_negatives(model, w)

    for name, fn in (('synthetic', lambda w: panel_synthetic(model, frontend, w)),
                     ('microphone', lambda w: panel_microphone(model, frontend, w)),
                     ('validation', validation_panel)):
        w = Writer()
        fn(w)
        w.save(out / name, panel=name, checkpoint=selected, scores=['g2_posterior', 'unused'])
        panels[name] = w
        print(f'{name}: {len(w.rows)} cases', flush=True)
    if not args.skip_test:
        test_file = out / 'test-scored-once.json'
        assert not test_file.exists(), 'AMI test has already been scored once for G2; refusing to rescore'
        recs = [r for r in json.loads((g2.LABELS / 'labels-test.json').read_text())['records'] if r.get('store_sdm') is not None]
        w = Writer()
        panel_store(model, frontend, w, 'test', recs, 'ami-test')
        w.save(out / 'test', panel='test', checkpoint=selected, scores=['g2_posterior', 'unused'])
        panels['test'] = w
        test_file.write_text(json.dumps(dict(checkpoint=selected, records=len(recs))) + '\n')
        print(f'test: {len(w.rows)} cases', flush=True)

    def cases_of(w):
        return [dict(r, counts=w.counts[i], collar=w.collar[i], post=w.entropy[i].astype(np.float64)) for i, r in enumerate(w.rows)]

    report = dict(variant=args.variant, selected=selected, parity_check=parity, ceiling=ceiling, frame={}, selection=None, segment={})
    for name, w in panels.items():
        cs = cases_of(w)
        for part, group in groupby(cs, partition_key).items():
            report['frame'][f'{name}/{part}'] = frame_block(group, 'post')
    val = cases_of(panels['validation'])
    # g2b pooled the non-AMI dev negatives into the selection (its frozen protocol); g2c and later apply the
    # ceiling to AMI validation negatives only and report the non-AMI windows separately.
    if args.variant != 'g2b':
        val = [c for c in val if partition_key(c) == 'ami-validation']
    lab_v = np.array([scorer.segment_label(c['counts'], c['collar']) for c in val])
    sc_v = np.array([scorer.segment_fraction(c['post'], c['collar']) for c in val])
    sel = scorer.select_threshold(sc_v, lab_v, ceiling)
    threshold = sel['threshold']
    report['selection'] = dict(panel='ami-validation subsample' + (' + non-AMI dev negatives (pooled)' if args.variant == 'g2b' else ''),
                               cases=int(lab_v.size), positives=int(lab_v.sum()), threshold=threshold, metrics=clean(sel['metrics']))
    for name, w in panels.items():
        cs = cases_of(w)
        lab = np.array([scorer.segment_label(c['counts'], c['collar']) for c in cs])
        sc = np.array([scorer.segment_fraction(c['post'], c['collar']) for c in cs])
        flags = sc >= threshold
        seg = dict(cases=int(lab.size), positives=int(lab.sum()), at_selected_threshold=clean(scorer.segment_metrics(flags, lab)))
        seg['by_partition_condition'] = {'/'.join(k): clean(scorer.segment_metrics(flags[np.array(i)], lab[np.array(i)]))
                                         for k, i in groupby(list(range(len(cs))), lambda i: (partition_key(cs[i]), cs[i]['condition'])).items()}
        if 0 < lab.sum() < lab.size:
            means = np.array([float(np.mean(c['post'][~c['collar']])) if np.any(~c['collar']) else 0.0 for c in cs])
            seg['diagnostic_mean_posterior_roc_auc'] = scorer.frame_roc(means, np.where(lab, 2, 1), np.zeros(lab.size, dtype=bool))['auc']
        if name == 'microphone':
            neg = np.array([c['group'] != 'overlap' for c in cs])
            bg = np.array([c['group'] == 'background' for c in cs])
            seg['adoption_gate'] = dict(negatives=int(neg.sum()), flagged_negatives=int(np.sum(flags & neg)), flagged_fraction=float(np.sum(flags & neg) / neg.sum()),
                                        no_speech_flags=int(np.sum(flags & bg)), passes=bool(np.sum(flags & neg) / neg.sum() <= ceiling))
        if name == 'synthetic':
            seg['no_speech_fixture_flags'] = int(np.sum(flags & np.array([c['condition'].startswith('no-speech') for c in cs])))
        report['segment'][name] = seg
    (args.phase3 / 'g2-results.json').write_text(json.dumps(report, indent=1) + '\n')
    print('parity', parity)
    for k, v in report['frame'].items():
        print(f"frame {k:26s} miss {v['miss_rate']!s:>8.6} fa {v['false_alarm_rate']!s:>8.6} auc {v['roc_auc']!s:>8.6}")
    m = report['selection']['metrics']
    print(f"selected threshold {threshold} on validation: recall {m['recall']} fa {m['false_alarm_rate']} precision {m['precision']}")
    for name, seg in report['segment'].items():
        m = seg['at_selected_threshold']
        print(f"segment {name:10s} precision {m['precision']} recall {m['recall']} fa {m['false_alarm_rate']} ({m['positives']} pos / {m['negatives']} neg) diag-auc {seg.get('diagnostic_mean_posterior_roc_auc')}")
        if 'adoption_gate' in seg:
            print('adoption gate', seg['adoption_gate'])


if __name__ == '__main__':
    main()
