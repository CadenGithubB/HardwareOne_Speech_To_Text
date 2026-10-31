#!/usr/bin/env python3
"""Replay a conversation playlist's clean audio through the speaker model on the Mac and the production
clusterer, to separate limits of the model and voices from the device's playback and microphone path.

  spkreplay.py MANIFEST [--session SESSION_DIR] [--thresholds 0.6,0.55] [--shuffles 200] [--rows]

Segments: by default every playlist clip is one phrase (perfect segmentation), cut with the device's 300 ms
pre-roll and 500 ms trimmed tail (--pre-ms, --tail-ms), whose length also counts toward the new-speaker
minimum. With --session, the phrases the device actually clustered (TL spk label lines, in sequence order)
are cut at their played spans (analysis.json span_play_s) and given the device's logged phrase length.
Audio comes from the manifest's wav (or --wav), resampled to 16 kHz int16 as the device receives it.

Embeddings: tools/stt_p4/speaker export_speaker.feats_for (the device front end's centre crop and
repetition) into proto.py's float ResNetSE34L. The device runs the w8a16-quantized trunk, so small
similarity differences are expected. Needs numpy and torch, scipy unless the wav is 16 kHz, and proto.py's
STT_ROOT / HW1_SPEAKER_CLOVA (the clova checkout with baseline_lite_ap.model).

Clustering: the embeddings go, in order, through firmware/components/hw1_stt/stt/speaker_cluster.h (the same
header as HardwareOne aa6508fd), compiled with $CXX or c++ from cluster_replay.cpp. Each --thresholds value
(default: the session's logged threshold, else 0.6) is replayed with --min-new-ms.

Reports: per threshold, scores as spkdiag.py (accuracy, coverage, labelled accuracy), clusters, splits and
merges and reasons; with --session the device's decisions beside the replay's and, while both histories
agree, device minus replay best similarity; with --shuffles, the same over seeded random phrase orders
(sensitivity only: real turns are not random). Also every same- and different-speaker phrase pair's
similarity, and each speaker's later phrases against its first phrase of at least the new-speaker minimum
(what a one-phrase centroid sees). Mixed phrases and phrases without a reference are clustered but not
scored. Numbers and IDs only.
"""
import argparse
import array
import collections
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import spkdiag  # noqa: E402
from spkeval import best_mapping  # noqa: E402

SR = 16000
HEADERS = ROOT / 'firmware/components/hw1_stt/stt'
DRIVER = HERE / 'cluster_replay.cpp'
SPEAKER_TOOLS = ROOT / 'tools/stt_p4/speaker'


def playlist_wav(manifest, man, wav=None):
    return Path(wav or man.get('wav') or Path(manifest).with_name('playlist.wav'))


def read_wav(path):
    with wave.open(str(path), 'rb') as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit(f'{path}: expected 16-bit mono')
        pcm = array.array('h')
        pcm.frombytes(w.readframes(w.getnframes()))
        if sys.byteorder == 'big':
            pcm.byteswap()
        return w.getframerate(), pcm


def cut(rate, pcm, span):
    """16 kHz int16-valued audio of a played span, as floats in [-1, 1)."""
    a, b = max(0, round(span[0] * rate)), min(len(pcm), round(span[1] * rate))
    x = pcm[a:b]
    if rate == SR:
        return [v / 32768.0 for v in x]
    import numpy as np
    from scipy.signal import resample_poly
    g = math.gcd(SR, rate)
    y = resample_poly(np.asarray(x, dtype=np.float64), SR // g, rate // g)
    return (np.clip(np.round(y), -32768, 32767) / 32768.0).astype(np.float32)


def model_embedder():
    sys.path.insert(0, str(SPEAKER_TOOLS))
    import numpy as np
    import torch
    import export_speaker  # imports proto.py: needs the clova checkout
    torch.set_num_threads(2)
    model = export_speaker.proto.load_model()

    def embed(x):
        with torch.inference_mode():
            return model(export_speaker.feats_for(np.asarray(x, dtype=np.float32)))[0].numpy().tolist()
    return embed


def unit(e):
    n = math.sqrt(sum(v * v for v in e))
    return [v / n for v in e]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


class Clusterer:
    """speaker_cluster.h behind a small stdin/stdout driver (cluster_replay.cpp)."""

    def __init__(self, workdir):
        self.exe = Path(workdir) / 'cluster_replay'
        subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++17', '-O2', f'-I{HEADERS}', str(DRIVER),
                        '-o', str(self.exe)], check=True)

    def run(self, sessions, threshold, min_new, max_speakers=8):
        """sessions: lists of (samples, embedding) in order. Returns one assignment list per session."""
        dim = len(sessions[0][0][1])
        lines = [f'config {dim} {threshold!r} {min_new} {max_speakers}']
        for k, phrases in enumerate(sessions):
            if k:
                lines.append('reset')
            lines += ['phrase %d %s' % (n, ' '.join('%.9g' % v for v in e)) for n, e in phrases]
        out = subprocess.run([str(self.exe)], input='\n'.join(lines) + '\n', capture_output=True, text=True,
                             check=True).stdout
        results, current = [], []
        for line in out.splitlines():
            if line == 'reset':
                results.append(current)
                current = []
                continue
            f = line.split()
            current.append({'spk': int(f[0]), 'reason': f[1], 'matches': int(f[2]), 'best': int(f[3]),
                            'best_sim': round(float(f[4]), 4), 'second': int(f[5]), 'second_sim': round(float(f[6]), 4),
                            'created': f[7] == '1', 'updated': f[8] == '1'})
        results.append(current)
        return results


def segments(man, session, min_new, pre, tail):
    """Phrases to replay, in order, and how many device label lines could not be cut."""
    if session is None:
        return [{'id': c['i'], 'clips': [c['i']], 'ref': c['speaker'], 'mixed': False, 'device': None,
                 'span': (c['start_s'] - pre, c['end_s'] + tail),
                 'samples': round((c['end_s'] - c['start_s'] + pre + tail) * SR)} for c in man['clips']], 0
    rows = sorted(spkdiag.phrase_rows(session, min_new)[4], key=lambda r: r['seq'])
    rows = [r for r in rows if r['pipeline'] == 'labelled']
    keep = [r for r in rows if r.get('span_play_s')]
    return [{'id': r['seq'], 'clips': r['clips'], 'ref': r['ref'], 'mixed': r['mixed'], 'device': r,
             'span': tuple(r['span_play_s']), 'samples': r['samples']} for r in keep], len(rows) - len(keep)


def score(segs, assigns):
    keep = [(s['ref'], a['spk']) for s, a in zip(segs, assigns) if s['ref'] is not None]
    refs, preds = [k[0] for k in keep], [k[1] for k in keep]
    right, mapping = best_mapping(refs, preds)
    labelled = sum(1 for p in preds if p >= 0)
    single = [(s['ref'], a['spk']) for s, a in zip(segs, assigns) if s['ref'] is not None and not s['mixed']]
    return {'scored': len(keep), 'accuracy': spkdiag.pct(right, len(keep)), 'coverage': spkdiag.pct(labelled, len(keep)),
            'accuracy_labelled': spkdiag.pct(right, labelled), 'speakers': len(set(refs)),
            'clusters': len({a['spk'] for a in assigns if a['spk'] >= 0}), 'mapping': mapping,
            'reasons': dict(collections.Counter(a['reason'] for a in assigns)),
            **spkdiag.structure([x[0] for x in single], [x[1] for x in single])}


def pair_similarity(segs, embs, threshold):
    same, different = [], []
    idx = [i for i, s in enumerate(segs) if s['ref'] is not None and not s['mixed']]
    for k, i in enumerate(idx):
        for j in idx[k + 1:]:
            (same if segs[i]['ref'] == segs[j]['ref'] else different).append(dot(embs[i], embs[j]))
    return spkdiag.similarity_report(same, different, threshold)


def first_phrases(segs, embs, min_new, later=6):
    """Each speaker's first phrase long enough to start a cluster, its next phrases against it, and the
    first phrases against each other."""
    anchors, to_first = {}, {}
    for i, s in enumerate(segs):
        if s['ref'] is None or s['mixed']:
            continue
        if s['ref'] not in anchors:
            if s['samples'] >= min_new:
                anchors[s['ref']], to_first[s['ref']] = i, []
            continue
        if len(to_first[s['ref']]) < later:
            to_first[s['ref']].append({'id': s['id'], 'sim': round(dot(embs[anchors[s['ref']]], embs[i]), 3)})
    spk = sorted(anchors, key=str)
    cross = {f'{a}/{b}': round(dot(embs[anchors[a]], embs[anchors[b]]), 3)
             for k, a in enumerate(spk) for b in spk[k + 1:]}
    return {'anchor_ids': {k: segs[v]['id'] for k, v in anchors.items()}, 'to_first': to_first, 'between_first': cross}


def device_comparison(segs, assigns, with_rows):
    rows, deltas, agree, first, history = [], [], 0, None, True
    for s, a in zip(segs, assigns):
        d = s['device']
        dev = {'spk': d['spk'], 'reason': d.get('reason'), 'best': d.get('best'), 'best_sim': d.get('best_sim')}
        if history and dev['best_sim'] is not None and dev['best'] is not None and dev['best'] >= 0 \
                and dev['best'] == a['best']:
            deltas.append(dev['best_sim'] - a['best_sim'])
        same = dev['spk'] == a['spk'] and dev['reason'] == a['reason']
        agree += same
        if not same:
            history = False
            first = first if first is not None else s['id']
        rows.append({'seq': s['id'], 'device': dev, 'replay': {k: a[k] for k in ('spk', 'reason', 'best', 'best_sim')}})
    out = {'decisions': len(rows), 'agree': agree, 'first_divergence_seq': first,
           'device_minus_replay_best_sim_while_agreeing': spkdiag.quantiles(deltas)}
    if first is not None:
        out['at_first_divergence'] = next(r for r in rows if r['seq'] == first)
    if with_rows:
        out['rows'] = rows
    return out


def shuffled(segs, embs, clusterer, threshold, min_new, n, seed):
    rng = random.Random(seed)
    orders = []
    for _ in range(n):
        o = list(range(len(segs)))
        rng.shuffle(o)
        orders.append(o)
    results = clusterer.run([[(segs[i]['samples'], embs[i]) for i in o] for o in orders], threshold, min_new)
    scores = [score([segs[i] for i in o], r) for o, r in zip(orders, results)]
    dist = lambda k: spkdiag.quantiles([s[k] for s in scores if s[k] is not None])
    return {'orders': n, 'seed': seed, 'accuracy': dist('accuracy'), 'coverage': dist('coverage'),
            'accuracy_labelled': dist('accuracy_labelled'), 'clusters': dist('clusters'),
            'orders_with_split': sum(1 for s in scores if s['split_speakers']),
            'orders_with_merge': sum(1 for s in scores if s['merged_clusters'])}


def replay(manifest, session=None, wav=None, thresholds=None, min_new=32000, pre=0.3, tail=0.5, shuffles=0, seed=1,
           embed=None, with_rows=False):
    man = json.loads(Path(manifest).read_text())
    wav = playlist_wav(manifest, man, wav)
    warnings = []
    if man.get('wav_sha256') and hashlib.sha256(wav.read_bytes()).hexdigest() != man['wav_sha256']:
        warnings.append('wav sha256 differs from manifest')
    if thresholds is None:
        logged = spkdiag.speaker_lines(spkdiag.analyse.load_session(Path(session))[1])['load'] if session else None
        thresholds = [(logged or {}).get('th') or 0.6]
    rate, pcm = read_wav(wav)
    segs, uncut = segments(man, session, min_new, pre, tail)
    if uncut:
        warnings.append(f'{uncut} device label lines had no played span and were left out of the history')
    embed = embed or model_embedder()
    embs = [unit(embed(cut(rate, pcm, s['span']))) for s in segs]
    out = {'manifest': str(manifest), 'segments': 'session' if session else 'clips',
           'session': str(session) if session else None, 'phrases': len(segs), 'min_new_samples': min_new,
           'warnings': warnings, 'similarity': pair_similarity(segs, embs, thresholds[0]),
           'first_phrases': first_phrases(segs, embs, min_new), 'thresholds': {}}
    with tempfile.TemporaryDirectory(prefix='spkreplay-') as tmp:
        clusterer = Clusterer(tmp)
        for th in thresholds:
            assigns = clusterer.run([[(s['samples'], e) for s, e in zip(segs, embs)]], th, min_new)[0]
            r = {'in_order': score(segs, assigns)}
            if session:
                r['device'] = device_comparison(segs, assigns, with_rows)
            if shuffles:
                r['shuffled'] = shuffled(segs, embs, clusterer, th, min_new, shuffles, seed)
            if with_rows:
                r['assignments'] = [{'id': s['id'], 'ref': s['ref'], 'mixed': s['mixed'], **a}
                                    for s, a in zip(segs, assigns)]
            out['thresholds'][str(th)] = r
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('manifest')
    ap.add_argument('--session', help='replay the phrases this device session clustered, at their played spans')
    ap.add_argument('--wav', help='playlist wav (default: the manifest\'s)')
    ap.add_argument('--thresholds', help='comma-separated, e.g. 0.6,0.55 (default: logged, else 0.6)')
    ap.add_argument('--min-new-ms', type=int, default=2000)
    ap.add_argument('--pre-ms', type=int, default=300, help='clip mode: audio and length before each clip')
    ap.add_argument('--tail-ms', type=int, default=500, help='clip mode: audio and length after each clip')
    ap.add_argument('--shuffles', type=int, default=0, help='also cluster this many seeded random orders')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--rows', action='store_true', help='include every assignment (and device row)')
    a = ap.parse_args()
    thresholds = [float(x) for x in a.thresholds.split(',')] if a.thresholds else None
    print(json.dumps(replay(a.manifest, a.session, a.wav, thresholds, a.min_new_ms * 16, a.pre_ms / 1000,
                            a.tail_ms / 1000, a.shuffles, a.seed, with_rows=a.rows)))


if __name__ == '__main__':
    main()
