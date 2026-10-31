#!/usr/bin/env python3
"""WER, arm A vs arm B, robust to console line drops.

The playlist is cut into runs of consecutive clips. A clip is dropped (in every session of both arms,
so the comparison is matched) if, in any session, a final phrase overlapping it lost its TL txt line.
Each run's hypothesis is the text of the phrases whose span midpoint lies inside the run, so phrases
straddling clip boundaries inside a run do not matter. Pooled WER per arm, and the difference B-A
with a bootstrap 95% CI over runs. Numbers only (no transcript text).
usage: clipwer.py LABEL_A LABEL_B
"""
import os
import json, random, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import analyse
ROOT = Path(os.environ.get('STT_SESSION_ROOT', Path(__file__).parent / 'sessions'))
def _manifest():
    # the playlist the sessions were played from (session.json), so other playlists work too
    for d in sorted((ROOT / sys.argv[1]).glob('2026*')):
        if (d / 'session.json').exists():
            m = json.load(open(d / 'session.json')).get('manifest')
            if m: return Path(m)
    return Path(__file__).parent / 'playlist' / 'manifest.json'
CLIPS = json.load(open(_manifest()))['clips']

def load(sdir):
    a = json.load(open(sdir / 'analysis.json'))
    _, records = analyse.load_session(sdir)
    raw = '\n'.join(record['msg'] for record in records)
    txt = {}
    sample_spans = {}
    for line in raw.splitlines():
        m = re.search(r'TL txt seq=(\d+) ?(.*)$', line)
        if m: txt[int(m.group(1))] = analyse.normalize_text(m.group(2).replace('\r', ''))
        # Normal firmware returns private final text in the owning CLI session.
        start = line.find('{')
        if start >= 0:
            try:
                value = json.loads(line[start:])
                if value.get('available') and isinstance(value.get('sequence'), int):
                    txt[value['sequence']] = analyse.normalize_text(value.get('sttText', ''))
                    if isinstance(value.get('startSample'), int) and isinstance(value.get('endSample'), int):
                        sample_spans[value['sequence']] = (value['startSample'], value['endSample'])
            except (ValueError, TypeError, AttributeError):
                pass
    # Empty final segments intentionally have no CLI chunk. Their boundary
    # record still identifies where the recognizer returned no text.
    empty = {int(x) for x in re.findall(r'TL empty seq=(\d+)', raw)}
    for m in re.finditer(r'TL boundary seg=(\d+) start=(\d+) end=(\d+)', raw):
        seq, start, end = map(int, m.groups())
        sample_spans.setdefault(seq, (start, end))
        if seq in empty:
            txt.setdefault(seq, '')
    meta = json.load(open(sdir / 'session.json'))
    phr_map = {p['seq']: p['span_play_s'] for p in a['phrases'] if p.get('span_play_s')}
    # The owned CLI reply carries the same sample boundaries as TL seg. Recover
    # missing serial timing lines using the capture and playback clocks.
    cs, play = a['playback'].get('capture_start_ms'), a['playback'].get('play_esp_ms')
    delta = a['alignment'].get('delta_ms')
    if cs is not None and play is not None and delta is not None:
        for seq, (start, end) in sample_spans.items():
            phr_map.setdefault(seq, [(cs + start / 16 - play - delta) / 1000,
                                     (cs + end / 16 - play - delta) / 1000])
    if meta.get('segments_completed') is not None and len(phr_map) != meta['segments_completed']:
        raise ValueError(f'{sdir}: missing segment timing; cannot score reliably')
    phr = sorted(phr_map.items())
    bad = set()
    for seq, (s0, s1) in phr:
        if seq not in txt:
            bad |= {i for i, c in enumerate(CLIPS) if c['start_s'] < s1 and c['end_s'] > s0}
    return dict(txt=txt, phr=phr, bad=bad)

def runs(good):
    out, cur = [], []
    for i in range(len(CLIPS)):
        if i in good: cur.append(i)
        elif cur: out.append(cur); cur = []
    if cur: out.append(cur)
    return out

def run_errors(sess, run):
    lo = CLIPS[run[0]]['start_s'] - (CLIPS[run[0] - 1]['gap_after_s'] / 2 if run[0] else 1.0)
    hi = CLIPS[run[-1]]['end_s'] + CLIPS[run[-1]]['gap_after_s'] / 2
    ref = ' '.join(CLIPS[i]['text_norm'] for i in run)
    hyp = ' '.join(sess['txt'][q] for q, (s0, s1) in sess['phr'] if q in sess['txt'] and lo <= (s0 + s1) / 2 < hi)
    return analyse.word_errors(ref, hyp), len(ref.split())

arms = [[load(d) for d in sorted((ROOT / lab).glob('2026*')) if (d / 'analysis.json').exists()] for lab in sys.argv[1:3]]
bad = set().union(*[s['bad'] for arm in arms for s in arm])
R = runs(set(range(len(CLIPS))) - bad)
print(f'clips dropped for console line loss (any session): {sorted(bad)}; {len(R)} runs, {sum(len(r) for r in R)} of {len(CLIPS)} clips kept')
per = []   # per arm: list over runs of (errors, words) summed over its sessions
for lab, arm in zip(sys.argv[1:3], arms):
    rr = [tuple(map(sum, zip(*[run_errors(s, r) for s in arm]))) for r in R]
    per.append(rr)
    e = sum(x[0] for x in rr); w = sum(x[1] for x in rr)
    each = [100 * sum(run_errors(s, r)[0] for r in R) / sum(run_errors(s, r)[1] for r in R) for s in arm]
    print(f'{lab}: {len(arm)} sessions, WER {100*e/w:.2f}% ({e}/{w}); per session ' + ', '.join(f'{x:.1f}' for x in each))
# Resample matched sessions, not clips pooled across all sessions. The same
# reference runs are scored in each pair, preserving within-session dependence.
if len(arms[0]) != len(arms[1]) or len(arms[0]) < 5:
    raise SystemExit('need at least five matched sessions per arm')
def session_wer(sess):
    e, w = map(sum, zip(*(run_errors(sess, r) for r in R)))
    return 100 * e / w
paired = [session_wer(b) - session_wer(a) for a, b in zip(*arms)]
rnd = random.Random(0)
d = sorted(sum(rnd.choices(paired, k=len(paired))) / len(paired) for _ in range(10000))
print(f'B - A: {sum(paired)/len(paired):+.2f} WER points, 95% CI [{d[250]:+.2f}, {d[9750]:+.2f}] (bootstrap over matched sessions)')
