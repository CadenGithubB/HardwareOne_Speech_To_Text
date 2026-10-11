"""Model time by layer type for a 5 s phrase (250 output frames), seconds, per firmware version."""
import glob, json, os, re
from pathlib import Path
SESS = str(Path(os.environ.get('HW1_STT_SESSIONS', Path(__file__).resolve().parents[1] / 'device_tests' / 'speaker' / 'sessions')))
NODES = json.load(open(Path(__file__).with_name('graph_nodes.json')))   # the 15x5 graph's layers (graph_ops)
def cat(n):
    if n['op'] in ('Add', 'Relu'): return 'addrelu'
    if n['kind'] == 'pw':
        return {(512, 512): 'pw512', (256, 256): 'pw256'}.get((n['Cin'], n['Cout']), 'pwhead')
    return {75: 'dw75', 63: 'dw63', 51: 'dw51', 87: 'dw87'}.get(n['K'], 'dw39_33')
KEYS = ['pw512', 'pw256', 'pwhead', 'dw75', 'dw63', 'dw51', 'dw87', 'dw39_33', 'addrelu']
def from_fit(raw_path, F=250):
    raw = open(raw_path, errors='replace').read()
    t = dict.fromkeys(KEYS, 0.0)
    for m in re.finditer(r'TL stg i=(\d+) n=\d+ fr=\d+ us=\d+ b100=(-?[\d.]+) a=(-?[\d.]+)', raw):
        t[cat(NODES[int(m.group(1))])] += max(0.0, float(m.group(3)) + float(m.group(2)) * F / 100) / 1e6
    return t
# current firmware: the 09-29 per-type profile (older build of the same graph, ms per segment at F=278),
# scaled to the current firmware's measured 5 s model time (2.055 s, fit over 91 e0n phrases)
old_ms = dict(pw512=1354.5, pw256=178.7, pwhead=91.9, dw75=352.6, dw63=203.6, dw51=145.1, dw87=104.7, dw39_33=90.9, addrelu=88.6)
k = 2.055 / (sum(old_ms.values()) / 1000)
out = {'old': {x: v / 1000 * k for x, v in old_ms.items()},
       'design': from_fit(glob.glob(SESS + '/b7-prn/2026*/raw.log')[0]),
       'today': from_fit(glob.glob(SESS + '/b10-c4an-prof/2026*/raw.log')[0]),
       # 1.5-1.8 share one ESP-DL build (prepared layer setups); its profile is in the c12 sessions
       'c12': from_fit(sorted(glob.glob(SESS + '/b26-c12n-lm16/2026*/raw.log'))[0])}
json.dump(out, open(Path(__file__).with_name('layers.json'), 'w'), indent=1)
for v, t in out.items(): print(f"{v:7} total {sum(t.values()):.3f} s | " + ' '.join(f"{x}={t[x]*1000:.0f}" for x in KEYS))
