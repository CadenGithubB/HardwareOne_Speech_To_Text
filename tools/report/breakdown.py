"""Speech end -> caption, split into sequential pieces per phrase, averaged per version and phrase type.
Start = the clip's true speech end on the device clock (read time - L_speech), so each bar sums to the
measured L_speech. Model time n is split by layer type with that version's per-layer profile."""
import glob, json, os, re, statistics as st, sys
from pathlib import Path
SESS = str(Path(os.environ.get('HW1_STT_SESSIONS', Path(__file__).resolve().parents[1] / 'device_tests' / 'speaker' / 'sessions')))
NODES = json.load(open(Path(__file__).with_name('graph_nodes.json')))   # the 15x5 graph's layers (graph_ops)
def kind(n):
    if n['op'] != 'Conv': return 'other'
    return 'dw' if n['kind'] == 'dw' else 'pw'
def fit_split(raw_path):
    raw = open(raw_path, errors='replace').read()
    fits = {int(m.group(1)): (float(m.group(3)), float(m.group(2))) for m in re.finditer(r'TL stg i=(\d+) n=\d+ fr=\d+ us=\d+ b100=(-?[\d.]+) a=(-?[\d.]+)', raw)}
    if not fits: return None
    def split(frames):
        t = {'pw': 0.0, 'dw': 0.0, 'other': 0.0}
        for i, (a, b100) in fits.items():
            t[kind(NODES[i])] += max(0.0, a + b100 * frames / 100)
        s = sum(t.values()); return {k: v / s for k, v in t.items()}
    return split
OLD_SHARES = {'pw': 0.624, 'dw': 0.343, 'other': 0.034}   # 09-29 per-stage profile (older build of the same 15x5 graph)
PROFILES = {
    'e0n': lambda f: OLD_SHARES,
    'b6-c3xn': fit_split(glob.glob(SESS + '/b7-prn/2026*/raw.log')[0]),
    'b9-c4an': fit_split(glob.glob(SESS + '/b10-c4an-prof/2026*/raw.log')[0]) if glob.glob(SESS + '/b10-c4an-prof/2026*/raw.log') else None,
}
# Later report versions. 1.4 (c5) changed only the LM decoder, so its layers are 1.3's. 1.5-1.8 (c7-c12) share one
# ESP-DL build (prepared layer setups); the c12 sessions logged its per-layer profile (TL stg).
C12 = fit_split(sorted(glob.glob(SESS + '/b26-c12n-lm16/2026*/raw.log'))[0])
PROFILES.update({'v1.4': PROFILES['b9-c4an'], 'v1.5': C12, 'v1.6': C12, 'v1.7': C12, 'v1.8': C12})
if PROFILES['b9-c4an'] is None:
    print('NOTE: no c4an per-layer profile yet; using the design split as a placeholder', file=sys.stderr)
    PROFILES['b9-c4an'] = PROFILES['b6-c3xn']
KEYS = ['wait', 'trigger', 'queue', 'rebuild', 'features', 'pw', 'dw', 'other', 'lm', 'delivery']
GROUPS = {'e0n': ['e0n'], 'b6-c3xn': ['b6-c3xn'], 'b9-c4an': ['b9-c4an', 'b10-c4an-prof'],
          'v1.4': ['b11-c5n'], 'v1.5': ['b14-t200', 'b15-t200', 'b16-c7t200n'], 'v1.6': ['b16-c9n', 'b17-c9n'],
          'v1.7': ['b18-c11n', 'b19-c12n'], 'v1.8': ['b26-c12n-lm16']}   # same sessions as versions.py
def phrases(label):
    out = []
    for d in sorted(sum((glob.glob(f'{SESS}/{g}/2026*') for g in GROUPS[label]), [])):
        if '/._' in d: continue
        a = json.load(open(d + '/analysis.json')); raw = open(d + '/raw.log', errors='replace').read()
        if a['health'].get('seg_lm0'): continue   # the LM did not load in this session
        txt = {int(x) for x in re.findall(r'TL txt seq=(\d+)', raw)}
        seg = {int(m.group(1)): dict(q=int(m.group(2)), s=int(m.group(3)), m=int(m.group(4)), f=int(m.group(5)), n=int(m.group(6)), d=int(m.group(7)))
               for m in re.finditer(r'TL seg=(\d+) a0=\d+ a1=\d+ q=(\d+) s=(\d+) m=(\d+) f=(\d+) n=(\d+) d=(\d+)', raw)}
        read = {int(m.group(1)): int(m.group(2)) for m in re.finditer(r'TL read seg=(\d+) t=(\d+)', raw)}
        prom = {int(x) for x in re.findall(r'TL spec_promote seg=(\d+)', raw)}
        frames = {int(m.group(1)): int(m.group(2)) for m in re.finditer(r'TL fe seg=(\d+) frames=(\d+)', raw)}
        for p in a['phrases']:
            q = p['seq']; L = p.get('L_speech')
            # skip phrases whose console text line was dropped, and those the analyser then misassigned
            if L is None or q not in txt or q not in seg or q not in read or (p.get('text_sim') or 0) < 0.15: continue
            g = seg[q]; rd = read[q]; start = rd - L
            comp = g['m'] + g['f'] + g['n'] + g['d']
            r = dict.fromkeys(KEYS, 0.0)
            F = (frames.get(q) or int(p['audio_s'] * 100)) / 2
            sh = PROFILES[label](F) if PROFILES[label] else OLD_SHARES
            for k in ('pw', 'dw', 'other'): r[k] = g['n'] * sh[k]
            r['rebuild'], r['features'], r['lm'] = g['m'], g['f'], g['d']
            if q in prom:                       # head start: began before the close
                ready = g['s'] + comp
                r['trigger'] = g['s'] - start
                r['wait'] = max(0, g['q'] - ready)
                r['delivery'] = rd - max(g['q'], ready)
            else:
                r['wait'] = g['q'] - start
                r['queue'] = g['s'] - g['q']
                r['delivery'] = rd - (g['s'] + comp)
            # queue/delivery can only be >= 0 up to clock-alignment noise: fold that into the waiting
            # piece. trigger stays signed per phrase (negative = the P4 judged speech over before the
            # clip's measured end); its average is positive.
            for k in ('queue', 'delivery'):
                if r[k] < 0: r[('trigger' if q in prom else 'wait')] += r[k]; r[k] = 0.0
            r['L'] = L; r['cat'] = 'short' if p.get('bin') == 'short' else 'longer'
            out.append(r)
    return out
res = {}
for lab in GROUPS:
    ps = phrases(lab)
    for cat in ('short', 'longer', 'all'):
        rs = [r for r in ps if cat == 'all' or r['cat'] == cat]
        # middle half by total delay (interquartile phrases): robust to outliers and still additive
        mid = sorted(rs, key=lambda r: r['L'])[len(rs) // 4: len(rs) - len(rs) // 4]
        res[f'{lab}/{cat}'] = dict(n=len(rs), n_mid=len(mid), median_L=st.median(r['L'] for r in rs) / 1000,
                                   iqm_L=st.mean(r['L'] for r in mid) / 1000,
                                   **{k: st.mean(r[k] for r in mid) / 1000 for k in KEYS})
for v in res.values():   # a negative average head-start delay = the model started before the measured end
    if v['trigger'] < 0: v['wait'] = max(0.0, v['wait'] + v['trigger']); v['trigger'] = 0.0
    # likewise a negative average end wait (the P4 closed the phrase just before the clip's measured end): fold it
    # into the head-start piece so each bar still sums to its measured total
    if v['wait'] < 0: v['trigger'] = max(0.0, v['trigger'] + v['wait']); v['wait'] = 0.0
json.dump(res, open(sys.argv[1] if len(sys.argv) > 1 else '/dev/stdout', 'w'), indent=1)
for k, v in res.items():
    print(f"{k:16} n={v['n']:2} median {v['median_L']:.2f} iqm {v['iqm_L']:.2f} | " + ' '.join(f"{x}={v[x]:.3f}" for x in KEYS))
