"""Split speech-end-to-caption latency per phrase from bench serial logs.
usage: latsplit.py RUN_DIR [RUN_DIR...]"""
import re, sys, glob, statistics as st

def kv(line):
    return {k: int(v) for k, v in re.findall(r'\b([a-z_0-9]+)=(-?\d+)\b', line)}

rows = []
for d in sys.argv[1:]:
    for f in sorted(glob.glob(d + '/serial-*.log')):
        seg, trim, pub, promo, kind, drafts = {}, {}, {}, set(), {}, []
        for line in open(f, errors='replace'):
            m = re.search(r'TL (seg|trim seg|pub seq|spec_promote seg|boundary seg|draft seq)=(\d+)(.*)', line)
            if not m:
                continue
            tag, n, rest = m.group(1), int(m.group(2)), m.group(3)
            v = kv(rest)
            if tag == 'seg': seg[n] = v
            elif tag == 'trim seg': trim[n] = v
            elif tag == 'pub seq': pub[n] = v['t']
            elif tag == 'spec_promote seg': promo.add(n)
            elif tag == 'boundary seg': kind[n] = v.get('kind')
            elif tag == 'draft seq' and 's' in v and 'e' in v: drafts.append((v['s'], v['e']))
        for n, s in seg.items():
            if n not in pub or n not in trim or 'a1' not in s:
                continue
            t = trim[n]
            ve = s['a0'] + t['voiced_end'] // 16
            busy = any(ds < s['q'] < de for ds, de in drafts)
            rows.append(dict(len=s['a1'] - s['a0'], pause=s['a1'] - ve, close=pub[n] - s['a1'],
                             user=pub[n] - ve, wait=max(0, s['s'] - s['q']), nn=s.get('n', 0), dec=s.get('d', 0),
                             fe=s.get('f', 0), spec=n in promo, kind=kind.get(n), busy=busy,
                             inf=t.get('inf', 0) // 16))

def med(xs): return int(st.median(xs)) if xs else None

def show(name, rs):
    if not rs: return
    print('%-22s n=%3d len=%5s pause=%5s close=%5s user=%5s | wait=%4s nn=%5s dec=%3s fe=%3s busy=%d%%' % (
        name, len(rs), med([r['len'] for r in rs]), med([r['pause'] for r in rs]), med([r['close'] for r in rs]),
        med([r['user'] for r in rs]), med([r['wait'] for r in rs]), med([r['nn'] for r in rs]),
        med([r['dec'] for r in rs]), med([r['fe'] for r in rs]), 100 * sum(r['busy'] for r in rs) // len(rs)))

show('all', rows)
show('spec promoted', [r for r in rows if r['spec']])
show('no spec', [r for r in rows if not r['spec']])
for k in sorted({r['kind'] for r in rows}, key=str):
    show('boundary kind=%s' % k, [r for r in rows if r['kind'] == k])
for lo, hi in ((0, 4000), (4000, 6000), (6000, 8000), (8000, 99999)):
    show('len %d-%d' % (lo, hi), [r for r in rows if lo <= r['len'] < hi])
nn = [r['nn'] / r['inf'] for r in rows if r['inf']]
print('nn ms per inferred audio ms: med %.3f' % st.median(nn))
