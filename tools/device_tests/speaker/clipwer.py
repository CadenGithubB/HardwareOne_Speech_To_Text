#!/usr/bin/env python3
"""WER, arm A vs arm B, robust to console line drops.

The playlist is cut into runs of consecutive clips. A clip is dropped (in every session of both arms,
so the comparison is matched) if, in any session, a final phrase overlapping it lost its TL txt line.
Each run's hypothesis is the text of the phrases whose span midpoint lies inside the run, so phrases
straddling clip boundaries inside a run do not matter. Pooled WER per arm, and the difference B-A
with a bootstrap 95% CI over runs. Numbers only (no transcript text).
usage: clipwer.py LABEL_A LABEL_B
"""
import json, random, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import analyse
ROOT = Path(__file__).parent / 'sessions'
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
    raw = open(sdir / 'raw.log', errors='replace').read()
    txt = {}
    for line in raw.splitlines():
        m = re.search(r'TL txt seq=(\d+) ?(.*)$', line)
        if m: txt[int(m.group(1))] = analyse.normalize_text(m.group(2).replace('\r', ''))
    segs = {int(x) for x in re.findall(r'TL seg=(\d+) a0', raw)}
    phr = [(p['seq'], p['span_play_s']) for p in a['phrases'] if p.get('span_play_s')]
    bad = set()
    for seq, (s0, s1) in phr:
        if seq in segs and seq not in txt:
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
def wer(rr, idx): return 100 * sum(rr[i][0] for i in idx) / sum(rr[i][1] for i in idx)
idx = list(range(len(R))); base = wer(per[1], idx) - wer(per[0], idx)
rnd = random.Random(0); d = sorted(wer(per[1], k) - wer(per[0], k) for k in ([rnd.randrange(len(R)) for _ in R] for _ in range(5000)))
print(f'B - A: {base:+.2f} WER points, 95% CI [{d[125]:+.2f}, {d[4875]:+.2f}] (bootstrap over runs)')
