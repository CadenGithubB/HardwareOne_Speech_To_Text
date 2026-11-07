"""Phase four, step 0: score G2c under the exact device rule, on the host, with the int8 graph.

Device rule (STT_OVERLAP_GATE_PHASE4_PLAN.md section 1):
  raw 64-bin log-mel rows -> int8 at the export's input exponent -> fixed 200-frame chunks, last
  chunk padded with the silence log-mel constant -> int8 logits [100 x 3] per chunk at the output
  exponent -> softmax per 20 ms frame -> frame marked when P(two or more) >= 0.5 -> segment
  fraction over the segment's own 20 ms frames (padding excluded) -> flag when >= THRESHOLD.
No collar. Labels are the frozen protocol labels, unchanged.

Writes phase4/device-rule-scores.json (per-panel metrics beside the protocol scores),
phase4/answer-key.json (per-clip decisions for the 32 whole saved-microphone windows and the 8
overlap clips), overlap_gate.sha256 and silence-constant.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overlap_gate import labels, scorer  # noqa: E402
from overlap_gate import g2_common as g2  # noqa: E402
from overlap_gate.g0_extract import R3, intervals_to_labels, read_pcm, sha  # noqa: E402

ROOT = g2.ROOT
CHUNK = 200
WHOLE_GROUPS = ('p4-quiet', 'p4-ordinary', 'g2-quiet', 'g2-ordinary')


class DeviceGate:
    def __init__(self, export_dir: Path, threshold: float):
        sys.path[:0] = [str(ROOT / 'tools/stt_p4'), str(ROOT / 'private/training-track/compact16k-round2'),
                        str(ROOT / 'private/training-track/overlap-ab'), str(ROOT / 'private/training-track/overlap-ab/deps')]
        from esp_ppq.api import load_native_graph
        from esp_ppq import TorchExecutor
        status = json.loads((export_dir / 'status.json').read_text())
        self.espdl = export_dir / 'g2.espdl'
        assert sha(self.espdl.read_bytes()) == status['espdl_sha256']
        self.executor = TorchExecutor(graph=load_native_graph(str(export_dir / 'g2.native')), device='cpu')
        self.in_scale = 2.0 ** status['input_exponent']
        self.out_scale = 2.0 ** status['output_exponent']
        self.threshold = threshold
        self.silence = np.array(json.loads((g2.FEATURES / 'silence-feature.json').read_text())['per_bin_mean'], np.float32)
        self.status = status

    def quantize_rows(self, feats: np.ndarray) -> np.ndarray:
        """[64, T] float raw log-mel -> the dequantized values the device's int8 input represents."""
        q = np.clip(np.rint(feats / self.in_scale), -128, 127)
        return (q * self.in_scale).astype(np.float32)

    def frame_posteriors(self, feats: np.ndarray) -> np.ndarray:
        """P(two or more) per 20 ms frame over the segment's own frames (padding excluded)."""
        T = feats.shape[1]
        n_out = (T + 1) // 2
        post = []
        for start in range(0, T, CHUNK):
            piece = feats[:, start:start + CHUNK]
            if piece.shape[1] < CHUNK:
                piece = np.concatenate([piece, np.repeat(self.silence[:, None], CHUNK - piece.shape[1], axis=1)], axis=1)
            x = torch.from_numpy(self.quantize_rows(piece))[None, :, :, None]
            with torch.inference_mode():
                y = self.executor.forward(inputs=x)[0][0, :, :, 0].numpy()          # [3, 100] dequantized logits
            assert np.isfinite(y).all()
            q = np.clip(np.rint(y / self.out_scale), -128, 127) * self.out_scale  # exactly what int8 output carries
            z = q - q.max(axis=0, keepdims=True)
            p = np.exp(z)
            p /= p.sum(axis=0, keepdims=True)
            post.append(p[2])
        return np.concatenate(post)[:n_out]

    def decide(self, feats: np.ndarray):
        p2 = self.frame_posteriors(feats)
        marked = p2 >= scorer.FRAME_THRESHOLD
        fraction = float(marked.mean()) if marked.size else 0.0
        return dict(frames_20ms=int(p2.size), marked_frames=int(marked.sum()), fraction=fraction, flag=bool(fraction >= self.threshold)), p2


def upsample(p2: np.ndarray, n_frames: int) -> np.ndarray:
    up = np.repeat(p2, 2)
    return up[:n_frames] if up.size >= n_frames else np.concatenate([up, np.full(n_frames - up.size, up[-1] if up.size else 0.0)])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--phase3', type=Path, default=g2.LABELS / 'phase3c')
    ap.add_argument('--out', type=Path, default=g2.LABELS / 'phase4')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(2)
    protocol = json.loads((args.phase3 / 'g2-results.json').read_text())
    threshold = protocol['selection']['threshold']
    gate = DeviceGate(args.phase3 / 'export-int8', threshold)
    frontend = g2.RawFrontend()
    (args.out / 'overlap_gate.sha256').write_text(f"{gate.status['espdl_sha256']}  overlap_gate.espdl\n")
    (args.out / 'silence-constant.json').write_text(json.dumps(dict(
        raw_log_mel=gate.silence.tolist(), int8_at_input_exponent=np.clip(np.rint(gate.silence / gate.in_scale), -128, 127).astype(int).tolist(),
        input_exponent=gate.status['input_exponent'], note='raw log-mel of digital silence; pads the last 200-frame chunk')) + '\n')

    panels = {}          # name -> list of dict(id, group, condition, partition, counts, collar, p2_10ms, decision)
    answer_key = []

    def add(panel, case_id, group, condition, partition, feats, counts, collar, **extra):
        decision, p2 = gate.decide(feats)
        panels.setdefault(panel, []).append(dict(id=case_id, group=group, condition=condition, partition=partition,
                                                 counts=counts, collar=collar, post=upsample(p2, counts.size), p2=p2, decision=decision, **extra))
        return decision

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
        add('synthetic', c['id'], c['group'], c['condition'], c['partition'], frontend(pcm.astype(np.float32) / 32768).numpy(), counts, collar)
    print('synthetic done', flush=True)

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
        # Segments longer than 20 s reach the device as 20 s pieces; decide each piece and OR them.
        pieces = [pcm[i:i + 320000] for i in range(0, pcm.size, 320000)]
        feats_all = [frontend(p.astype(np.float32) / 32768).numpy() for p in pieces]
        if len(pieces) == 1:
            decision = add('microphone', c['id'], c['group'], condition, 'saved-microphone', feats_all[0], counts, collar, pcm_sha256=b['pcm_sha256'], samples=int(pcm.size))
        else:
            decs = [gate.decide(f) for f in feats_all]
            p2 = np.concatenate([d[1] for d in decs])
            decision = dict(frames_20ms=int(sum(d[0]['frames_20ms'] for d in decs)), marked_frames=int(sum(d[0]['marked_frames'] for d in decs)),
                            fraction=float(np.mean([d[0]['fraction'] for d in decs])), flag=bool(any(d[0]['flag'] for d in decs)), pieces=len(pieces))
            panels.setdefault('microphone', []).append(dict(id=c['id'], group=c['group'], condition=condition, partition='saved-microphone', counts=counts, collar=collar,
                                                             post=upsample(p2, counts.size), p2=p2, decision=decision, pcm_sha256=b['pcm_sha256'], samples=int(pcm.size)))
        if c['group'] in WHOLE_GROUPS or c['group'] == 'overlap':
            answer_key.append(dict(id=c['id'], group=c['group'], pcm_sha256=b['pcm_sha256'], samples=int(pcm.size), label_overlap=bool(scorer.segment_label(counts, collar)), **decision))
    print('microphone done', flush=True)

    for split, records, condition in (('validation', g2.validation_subsample(), 'ami-validation'),
                                      ('test', [r for r in json.loads((g2.LABELS / 'labels-test.json').read_text())['records'] if r.get('store_sdm') is not None], 'ami-test')):
        bank = g2.Features(f'ami-sdm-{split}')
        for r in records:
            add(split, r['audio_id'], r['meeting'], condition, condition, bank.slice(r['audio_id']), labels.expand(r['counts']), labels.expand(r['collar']).astype(bool))
        print(split, 'done', flush=True)

    # The operating point must be chosen under the rule the device uses: re-select the segment threshold on
    # AMI validation negatives only (device fractions, no collar) at the frozen 2% ceiling. The protocol
    # threshold was chosen with collar frames excluded, which the device cannot do.
    val = panels['validation']
    lab_v = np.array([scorer.segment_label(c['counts'], c['collar']) for c in val])
    frac_v = np.array([c['decision']['fraction'] for c in val])
    device_sel = scorer.select_threshold(frac_v, lab_v, 0.02)
    thresholds = {'protocol_threshold': threshold, 'device_selected_threshold': device_sel['threshold']}

    def clean(o):
        return json.loads(json.dumps(o, default=lambda x: None if isinstance(x, float) and math.isnan(x) else float(x)))

    report = dict(rule=dict(chunk_frames=CHUNK, frame_threshold=scorer.FRAME_THRESHOLD, collar='none on device; labels keep the protocol collar',
                            input_exponent=gate.status['input_exponent'], output_exponent=gate.status['output_exponent'], espdl_sha256=gate.status['espdl_sha256']),
                  thresholds=thresholds, device_selection=clean(dict(panel='AMI validation subsample, device fractions', cases=int(lab_v.size), **device_sel)),
                  panels={}, protocol_reference={})
    per_case = {}
    for name, cs in panels.items():
        lab = np.array([scorer.segment_label(c['counts'], c['collar']) for c in cs])
        frac = np.array([c['decision']['fraction'] for c in cs])
        post = np.concatenate([c['post'] for c in cs])
        counts = np.concatenate([c['counts'] for c in cs])
        collar = np.concatenate([c['collar'] for c in cs])
        entry = dict(cases=len(cs), positives=int(lab.sum()), frame_roc_auc=scorer.frame_roc(post, counts, collar)['auc'], at={})
        for tname, t in thresholds.items():
            flags = frac >= t
            at = dict(segment=scorer.segment_metrics(flags, lab), by_condition={})
            for cond in sorted({(c['partition'], c['condition']) for c in cs}):
                idx = np.array([i for i, c in enumerate(cs) if (c['partition'], c['condition']) == cond])
                at['by_condition']['/'.join(cond)] = scorer.segment_metrics(flags[idx], lab[idx])
            if name == 'microphone':
                neg = np.array([c['group'] != 'overlap' for c in cs])
                at['adoption_gate'] = dict(negatives=int(neg.sum()), flagged_negatives=int(np.sum(flags & neg)), passes=bool(np.sum(flags & neg) / neg.sum() <= 0.02))
            entry['at'][tname] = at
        report['panels'][name] = clean(entry)
        per_case[name] = [dict(id=c['id'], group=c['group'], condition=c['condition'], label=bool(l), **c['decision']) for c, l in zip(cs, lab)]
    for name in ('synthetic', 'microphone', 'validation', 'test'):
        seg = protocol['segment'].get(name, {}).get('at_selected_threshold')
        frame = {k: v for k, v in protocol['frame'].items() if k.startswith(name + '/')}
        report['protocol_reference'][name] = dict(segment=seg, frame=frame)
    (args.out / 'device-rule-scores.json').write_text(json.dumps(report, indent=1) + '\n')
    (args.out / 'device-rule-cases.json').write_text(json.dumps(per_case) + '\n')
    # Per-frame device posteriors (20 ms) and protocol labels (10 ms), so decision rules can be explored without inference.
    post_dir = args.out / 'posteriors'
    post_dir.mkdir(exist_ok=True)
    for name, cs in panels.items():
        np.savez_compressed(post_dir / f'{name}.npz',
                            p2=np.concatenate([c['p2'] for c in cs]).astype(np.float32), p2_offsets=np.concatenate([[0], np.cumsum([c['p2'].size for c in cs])]),
                            counts=np.concatenate([c['counts'] for c in cs]), collar=np.concatenate([c['collar'] for c in cs]),
                            offsets=np.concatenate([[0], np.cumsum([c['counts'].size for c in cs])]))
        (post_dir / f'{name}.json').write_text(json.dumps([dict(id=c['id'], group=c['group'], condition=c['condition'], partition=c['partition']) for c in cs]) + '\n')
    for k in answer_key:
        k['flag_at_protocol_threshold'] = k.pop('flag')
        k['flag_at_device_threshold'] = bool(k['fraction'] >= thresholds['device_selected_threshold'])
    (args.out / 'answer-key.json').write_text(json.dumps(dict(rule=report['rule'], thresholds=thresholds, clips=answer_key), indent=1) + '\n')
    print('thresholds', thresholds)
    for name, e in report['panels'].items():
        ref = report['protocol_reference'][name]['segment'] or {}
        print(f"{name:10s} auc {e['frame_roc_auc']:.4f} | protocol: recall {ref.get('recall')} fa {ref.get('false_alarm_rate')}")
        for tname, at in e['at'].items():
            s = at['segment']
            print(f"   {tname:26s} recall {s['recall']} fa {s['false_alarm_rate']} prec {s['precision']}", at.get('adoption_gate', ''))
    print('answer key clips', len(answer_key), 'flagged at device threshold', sum(k['flag_at_device_threshold'] for k in answer_key))


if __name__ == '__main__':
    main()
