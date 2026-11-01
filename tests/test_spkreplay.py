#!/usr/bin/env python3
"""Run spkreplay.py's cutting, real-clusterer replay, scoring and device comparison on a tone playlist.

Ten 16 kHz clips alternate two speakers; each clip is a distinct tone, and a fake embedder maps the tone it
hears to a designed embedding, so a wrong cut picks a wrong embedding. Clip 2 (speaker A) is 0.558 from A's
first phrase: at 0.6 it starts a duplicate cluster and A's later phrases are ambiguous; at 0.55 it joins A.
The synthetic session reuses test_spkdiag.py's log writer. No model, numpy or device is involved.
"""
import array
import hashlib
import json
import math
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'tools/device_tests/speaker'))
import spkreplay  # noqa: E402
import test_spkdiag as logs  # noqa: E402

A, X = 101, 202
VECTORS = [(1, 0, 0), (0, 1, 0), (0.558, 0, 0.83), (0.05, 0.99, 0), (0.8, 0, 0.6), (0, 1, 0.05), (0.75, 0, 0.66),
           (0.02, 1, 0), (0.95, 0, 0.31), (0, 0.99, 0.1)]
TONE = lambda i: 300 + 40 * i


def playlist(root):
    clips, pcm, t = [], array.array('h', [0] * 6 * 16000), 6.0
    for i in range(len(VECTORS)):
        n = 40000   # 2.5 s
        clips.append({'i': i, 'speaker': (A, X)[i % 2], 'start_s': round(t, 3), 'end_s': round(t + n / 16000, 3),
                      'speech_start_s': round(t, 3), 'speech_end_s': round(t + n / 16000, 3)})
        pcm.extend(round(9000 * math.sin(2 * math.pi * TONE(i) * k / 16000)) for k in range(n))
        pcm.extend([0] * 24000)   # 1.5 s gap
        t += n / 16000 + 1.5
    wav = root / 'playlist.wav'
    with wave.open(str(wav), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm.tobytes())
    man = {'wav': str(wav), 'wav_sha256': hashlib.sha256(wav.read_bytes()).hexdigest(), 'clips': clips}
    path = root / 'manifest.json'
    path.write_text(json.dumps(man))
    return path, man


def fake_embedder(lengths):
    def power(x, f):
        c, s1, s2 = 2 * math.cos(2 * math.pi * f / 16000), 0.0, 0.0
        for v in x:
            s1, s2 = v + c * s1 - s2, s1
        return s1 * s1 + s2 * s2 - c * s1 * s2

    def embed(x):
        lengths.append(len(x))
        mid = x[len(x) // 2 - 4000:len(x) // 2 + 4000]
        i = max(range(len(VECTORS)), key=lambda k: power(mid, TONE(k)))
        return list(VECTORS[i])
    return embed


def main():
    with tempfile.TemporaryDirectory(prefix='hw1-spkreplay-') as tmp:
        root = Path(tmp)
        man_path, man = playlist(root)

        # Clip mode: each clip plus 0.3 s before and 0.5 s after, also counted as phrase length.
        lengths = []
        r = spkreplay.replay(man_path, thresholds=[0.6, 0.55], shuffles=20, embed=fake_embedder(lengths),
                             with_rows=True)
        assert r['warnings'] == [] and r['phrases'] == 10 and set(lengths) == {round(3.3 * 16000)}, (r['warnings'], lengths)
        at60, at55 = r['thresholds']['0.6']['in_order'], r['thresholds']['0.55']['in_order']
        assert at60['reasons'] == {'new': 3, 'match': 4, 'ambiguous': 3}, at60
        assert (at60['accuracy'], at60['coverage'], at60['accuracy_labelled'], at60['clusters']) == (60.0, 70.0, 85.7, 3)
        assert at60['split_speakers'] == {A: {0: 1, 2: 1}} and at60['merged_clusters'] == {}, at60
        assert (at55['accuracy'], at55['coverage'], at55['clusters'], at55['split_speakers']) == (100.0, 100.0, 2, {})
        rows = r['thresholds']['0.6']['assignments']
        assert [x['spk'] for x in rows] == [0, 1, 2, 1, -1, 1, -1, 1, -1, 1], rows
        assert rows[2]['created'] and rows[2]['best'] == 0 and abs(rows[2]['best_sim'] - 0.558) < 1e-3, rows[2]
        shuf = r['thresholds']['0.6']['shuffled']
        assert shuf['orders'] == 20 and shuf['clusters']['min'] >= 2 and shuf['accuracy']['max'] <= 100, shuf
        sim = r['similarity']
        assert (sim['same']['n'], sim['different']['n']) == (20, 25), sim
        first = r['first_phrases']
        assert first['anchor_ids'] == {A: 0, X: 1} and first['to_first'][A][0] == {'id': 2, 'sim': 0.558}, first
        assert first['between_first'] == {f'{A}/{X}': 0.0}, first

        # Session mode: the device's labelled phrases at their played spans, with its logged decisions.
        plan, profiles = [], 0
        for i, kind in enumerate(['new', 'new', 'new', 'match', 'ambiguous', 'match', 'ambiguous', 'match',
                                  'ambiguous', 'match']):
            label = {'new': profiles, 'match': i % 2, 'ambiguous': -1}[kind]
            plan.append(([i], logs.decision(0, kind, label, profiles, samples=48000), True))
            profiles += kind == 'new'
        session = logs.write_session(root, '2026-device', man_path, man, plan, True,
                                     'submitted=10 labelled=10 skipped=0')
        lengths.clear()
        d = spkreplay.replay(man_path, session=session, thresholds=[0.6], embed=fake_embedder(lengths))
        dev = d['thresholds']['0.6']['device']
        assert d['segments'] == 'session' and set(lengths) == {48000}, lengths
        assert (dev['decisions'], dev['agree'], dev['first_divergence_seq']) == (10, 10, None), dev
        assert d['session_input']['tail_trimmed_phrases']==10
        assert d['session_input']['removed_tail_ms_total']==5000
        assert spkreplay.session_span({'span_play_s':[1,4.5],'samples':48000})==(1,4)
        try:spkreplay.session_span({'span_play_s':[1,2],'samples':32000})
        except ValueError:pass
        else:raise AssertionError('impossible input length accepted')
        # Without --thresholds the session's logged threshold (0.50 in the log writer) is replayed.
        d = spkreplay.replay(man_path, session=session, embed=fake_embedder([]))
        dev = d['thresholds']['0.5']['device']
        assert dev['first_divergence_seq'] == 3 and dev['at_first_divergence']['replay']['reason'] == 'match', dev
        assert dev['at_first_divergence']['device']['reason'] == 'new', dev
    print('spkreplay: tone playlist ok')


if __name__ == '__main__':
    main()
