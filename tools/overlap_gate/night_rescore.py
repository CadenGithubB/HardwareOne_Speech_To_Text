"""Night 1 diagnosis: did the device gate compute what the host gate computes, and what does the gate see?

Three comparisons, all with the exact host device rule (DeviceGate, int8 graph):
  A. device vs host on the same audio: for every gated segment, the PCM the P4 saved -> host frontend
     -> host int8 gate, compared frame by frame with the int8 logits the device logged (STT_OVERLAP).
     Equal posteriors mean the device implementation is right and any miss is acoustic.
  B. the source clips as played (from the block WAVs, before the loudspeaker and room): host gate.
     This is how many flags the playlist should produce if the room were transparent.
  C. overlap vs single-speaker contrast on the device audio, using the playlist labels for segments
     matched to clips by time.

  night_rescore.py [--runs N]      writes phase4/night1-rescore.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import wave
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overlap_gate import scorer  # noqa: E402
from overlap_gate import g2_common as g2  # noqa: E402
from overlap_gate.device_rule import DeviceGate  # noqa: E402
from overlap_gate.suppression import drop_short_runs  # noqa: E402

P4 = g2.LABELS / 'phase4'
RUNS = P4 / 'night1-runs'
CARD = P4 / 'night1-card' / 'pcm'
RULE_THRESHOLD = 0.360


def device_p2(j: dict) -> np.ndarray:
    z = np.frombuffer(bytes.fromhex(j['logits']), dtype=np.int8).astype(np.float64).reshape(-1, 3) * 2.0 ** j['exponent']
    z -= z.max(axis=1, keepdims=True)
    p = np.exp(z)
    return (p / p.sum(axis=1, keepdims=True))[:, 2]


def r10(p2: np.ndarray) -> float:
    m = p2 >= scorer.FRAME_THRESHOLD
    return float(drop_short_runs(m, 10).mean()) if m.size else 0.0


def runs(runs_dir: Path = RUNS):
    for line in (runs_dir / 'events.jsonl').read_text().splitlines():
        e = json.loads(line)
        if e['kind'] == 'run-done':
            e['folder'] = re.search(r'b0+\d+', e['pcm_ack'])[0]
            yield e


def align(segments, on_runs, manifests: Path = P4 / 'night1'):
    """Label each device segment with the playlist clip it covers most, after finding the run's clock offset.

    The device stream's sample counter and the WAV's sample index differ by an unknown constant per run;
    choose the offset (10 ms grid) that puts the most segment midpoints inside clips. Segments covering
    less than half of their own length with one clip, or touching two clips, stay unlabelled."""
    out = []
    for e in on_runs:
        m = json.loads((manifests / f"block{e['block']:02d}.json").read_text())
        clips = sorted(m['clips'], key=lambda c: c['start_sample'])
        cs = np.array([c['start_sample'] for c in clips])
        ce = np.array([c['end_sample'] for c in clips])
        seg = [x for x in segments if x.get('run') == e['run'] and 'mismatch' not in x]
        if not seg:
            continue
        s0 = np.array([x['start_sample'] for x in seg])
        s1 = s0 + np.array([x['samples'] for x in seg])
        mid = (s0 + s1) / 2

        def hits(off):
            i = np.searchsorted(cs, mid - off, side='right') - 1
            return int(np.sum((i >= 0) & (mid - off < ce[np.clip(i, 0, None)])))
        coarse = max(range(-200 * 16000, 400 * 16000, 1600), key=hits)
        off = max(range(coarse - 1600, coarse + 1600, 160), key=hits)
        for x, a0, a1 in zip(seg, s0 - off, s1 - off):
            cover = np.clip(np.minimum(ce, a1) - np.maximum(cs, a0), 0, None)
            touching = int(np.sum(cover > 0))
            j = int(cover.argmax())
            if touching == 1 and cover[j] >= 0.5 * (a1 - a0):
                out.append(dict(x, folder=e['folder'], offset=int(off), clip=clips[j]['index'], category=clips[j]['category'], label=bool(clips[j]['label'])))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--runs', type=int, default=None, help='limit gate-on runs (smoke)')
    args = ap.parse_args()
    torch.set_num_threads(2)
    gate = DeviceGate(g2.LABELS / 'phase3c' / 'export-int8', threshold=RULE_THRESHOLD)
    frontend = g2.RawFrontend()
    on_runs = [e for e in runs() if e['arm'] == 'on'][:args.runs]

    # A. device vs host on identical audio
    a = []
    for e in on_runs:
        lines = (RUNS / 'runs' / e['run'] / 'serial.log').read_text(errors='replace').splitlines()
        logged = {}
        for l in lines:
            i = l.find('STT_OVERLAP ')
            if i >= 0:
                try:
                    j = json.loads(l[i + 12:])
                except json.JSONDecodeError:
                    continue
                logged[j['stream_sequence']] = j
        for seq, j in sorted(logged.items()):
            f = CARD / e['folder'] / f's{seq:06d}.pcm'
            if not f.exists():
                continue
            pcm = np.fromfile(f, dtype='<i2')
            if pcm.size != j['samples']:
                a.append(dict(run=e['run'], seq=seq, mismatch='samples'))
                continue
            host = gate.frame_posteriors(frontend(pcm.astype(np.float32) / 32768).numpy())
            dev = device_p2(j)
            n = min(host.size, dev.size)
            a.append(dict(run=e['run'], block=e['block'], seq=seq, start_sample=j['start_sample'], samples=int(pcm.size), frames=int(n),
                          max_abs_diff=float(np.abs(host[:n] - dev[:n]).max()) if n else 0.0,
                          host_max=float(host.max()), dev_max=float(dev.max()), host_r10=r10(host), dev_r10=r10(dev),
                          rms_dbfs=float(20 * np.log10(np.sqrt(np.mean((pcm / 32768.0) ** 2)) + 1e-12))))
        print(e['run'], 'segments', sum(1 for x in a if x.get('run') == e['run']), flush=True)

    # B. source clips as played
    b = []
    for blk in sorted({e['block'] for e in on_runs}):
        m = json.loads((P4 / 'night1' / f'block{blk:02d}.json').read_text())
        with wave.open(m['wav']) as w:
            assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
            audio = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2')
        for c in m['clips']:
            pcm = audio[c['start_sample']:c['end_sample']]
            p2 = gate.frame_posteriors(frontend(pcm.astype(np.float32) / 32768).numpy())
            b.append(dict(block=blk, index=c['index'], category=c['category'], label=bool(c['label']), max_p2=float(p2.max()), r10=r10(p2),
                          flag=bool(r10(p2) >= RULE_THRESHOLD), rms_dbfs=float(20 * np.log10(np.sqrt(np.mean((pcm / 32768.0) ** 2)) + 1e-12))))
        print('block', blk, 'source clips', len(m['clips']), flush=True)

    # D. label device segments from the playlist (time alignment), then rescore the device audio with gain.
    # Gain is an exact log-domain offset on raw log-mel, so this asks only "is level the cause?".
    labelled = align(a, on_runs)
    gains = {}
    for g_db in (0, 6, 12, 18, 24, 30):
        flags = dict(pos=0, pos_flag=0, neg=0, neg_flag=0)
        for x in labelled:
            pcm = np.fromfile(CARD / x['folder'] / f"s{x['seq']:06d}.pcm", dtype='<i2').astype(np.float32) / 32768 * 10 ** (g_db / 20)
            f = r10(gate.frame_posteriors(frontend(pcm).numpy())) >= RULE_THRESHOLD
            k = 'pos' if x['label'] else 'neg'
            flags[k] += 1
            flags[k + '_flag'] += int(f)
        gains[f'+{g_db}dB'] = dict(flags, recall=flags['pos_flag'] / max(1, flags['pos']), false_alarm_rate=flags['neg_flag'] / max(1, flags['neg']))
        print('gain', g_db, gains[f'+{g_db}dB'], flush=True)

    ok = [x for x in a if 'mismatch' not in x]
    diffs = np.array([x['max_abs_diff'] for x in ok])
    src = {}
    for x in b:
        k = (x['category'], x['label'])
        s = src.setdefault(f'{k[0]}/{"overlap" if k[1] else "no-overlap"}', dict(clips=0, flags=0, max_p2=[]))
        s['clips'] += 1
        s['flags'] += x['flag']
        s['max_p2'].append(x['max_p2'])
    for s in src.values():
        s['median_max_p2'] = float(np.median(s.pop('max_p2')))
    summary = dict(
        device_vs_host=dict(segments=len(ok), sample_mismatches=len(a) - len(ok),
                            max_abs_diff_p2=dict(median=float(np.median(diffs)), p99=float(np.percentile(diffs, 99)), max=float(diffs.max())),
                            host_flags=sum(x['host_r10'] >= RULE_THRESHOLD for x in ok), device_flags=sum(x['dev_r10'] >= RULE_THRESHOLD for x in ok),
                            median_segment_rms_dbfs=float(np.median([x['rms_dbfs'] for x in ok]))),
        source_clips=dict(clips=len(b), flags=sum(x['flag'] for x in b), positives=sum(x['label'] for x in b),
                          flags_on_positives=sum(x['flag'] and x['label'] for x in b),
                          median_clip_rms_dbfs=float(np.median([x['rms_dbfs'] for x in b])), by_category=src),
        alignment=dict(labelled_segments=len(labelled), positives=sum(x['label'] for x in labelled)),
        device_audio_with_gain=gains)
    (P4 / 'night1-rescore.json').write_text(json.dumps(dict(summary=summary, segments=a, source=b), indent=1) + '\n')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
