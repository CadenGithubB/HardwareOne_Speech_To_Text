#!/usr/bin/env python3
"""Turn PCM-file benchmark runs with speaker diagnostics (TL spke2 lines) into spkrules.py voiceprint sets.

  benchsets.py MANIFEST OUT.json BENCH_DIR [BENCH_DIR ...]
  benchsets.py check OUT.json REPO      replay the production rule in device order against the device

Each run becomes one set (group "device"): every phrase the device clustered, in device order, with its
logged int8 unit voiceprint, the phrase length the clusterer saw and the reference speaker of the clip
holding the caption midpoint (mixed when it holds at least 0.3 s of two speakers' clips).
The device's own label, reason and similarity are kept per phrase (dev_spk, dev_reason, dev_sim) so a
production replay can be checked decision for decision. Numbers and IDs only; no text.
"""
import base64, json, re, sys
from pathlib import Path


def kv(line):
    return dict(re.findall(r'\b([a-z_0-9]+)=(\S+)', line))


def clip_at(clips, t):
    for c in clips:
        if float(c['start_s']) <= t < float(c['end_s']) + float(c.get('gap_after_s', 0)):
            return c
    return None


def run_set(clips, name, captions, log):
    caps = {c['sequence']: c for c in captions}
    emb, match, parts, dims = {}, {}, {}, {}
    for line in log:
        # TL spke2: int8 direction in 128-value parts (TL spke lines are cut at the log line limit).
        m = re.search(r'TL spke2 seq=(\d+) dim=(\d+) part=(\d+) e=([A-Za-z0-9+/=]+)', line)
        if m:
            q = int(m.group(1))
            dims[q] = int(m.group(2))
            parts.setdefault(q, {})[int(m.group(3))] = base64.b64decode(m.group(4))
        m = re.search(r'TL spk_match seq=(\d+) ', line)
        if m:
            match[int(m.group(1))] = kv(line[m.start():])
    for q, p in parts.items():
        raw = b''.join(p[i] for i in sorted(p))
        if sorted(p) == list(range(len(p))) and len(raw) == dims[q]:
            emb[q] = [(b - 256 if b > 127 else b) / 127.0 for b in raw]
    spk = {}
    for line in log:
        m = re.search(r'TL spk seq=(\d+) spk=(-?\d+)', line)
        if m:
            spk[int(m.group(1))] = int(m.group(2))
    phrases = []
    for q in sorted(emb):
        if q not in match:
            continue
        ref, mixed = None, False
        c = caps.get(q)
        if c:
            cs, ce = c['startSample'] / 16000, c['endSample'] / 16000
            mid = clip_at(clips, (cs + ce) / 2)
            ref = mid['speaker'] if mid else None
            # Mixed: at least 0.3 s of two speakers' clip audio (pre-roll into a gap does not count).
            heard = {k['speaker'] for k in clips
                     if min(ce, float(k['end_s'])) - max(cs, float(k['start_s'])) >= 0.3}
            mixed = len(heard) > 1
        n = sum(v * v for v in emb[q]) ** 0.5
        phrases.append({'id': q, 'ref': ref, 'mixed': mixed, 'samples': int(match[q]['phrase_samples']),
                        'e': [round(v / n, 6) for v in emb[q]], 'dev_spk': spk.get(q),
                        'dev_reason': match[q].get('reason'), 'dev_sim': float(match[q].get('best_sim', 'nan'))})
    return {'name': name, 'group': 'device', 'phrases': phrases}


def main():
    manifest = json.load(open(sys.argv[1]))
    clips = sorted(manifest['clips'], key=lambda c: float(c['start_s']))
    sets = []
    for d in map(Path, sys.argv[3:]):
        for r in json.load(open(d / 'bench.json')):
            log = (d / f"serial-{r['run']}.log").read_text(errors='replace').splitlines()
            s = run_set(clips, f"{d.name}/{r['run']}", r['captions'], log)
            sets.append(s)
            print(s['name'], 'phrases', len(s['phrases']), 'with_ref', sum(p['ref'] is not None for p in s['phrases']),
                  'mixed', sum(p['mixed'] for p in s['phrases']), file=sys.stderr)
    Path(sys.argv[2]).write_text(json.dumps({'version': 1, 'model': 'device w8a16 trunk, int8-rounded unit voiceprints',
                                             'min_new_samples': 32000, 'sets': sets}))




def check(sets_path, repo):
    """Replay the production rule in device order; report decision agreement with the device per set."""
    sys.path.insert(0, str(Path(repo) / 'tools/device_tests/speaker'))
    import tempfile
    import spkrules
    sets = json.load(open(sets_path))['sets']
    rule = spkrules.parse_rule('production', 0.6)
    with tempfile.TemporaryDirectory() as tmp:
        runner = spkrules.Runner(tmp)
        for s in sets:
            ph = s['phrases']
            labels = runner.runs(ph, [(rule, list(range(len(ph))))], 32000)[0]
            same = sum(1 for p, (spk, why) in zip(ph, labels) if p['dev_spk'] == spk and p['dev_reason'] == why)
            diff = [(p['id'], p['dev_spk'], p['dev_reason'], round(p['dev_sim'], 3), spk, why)
                    for p, (spk, why) in zip(ph, labels) if not (p['dev_spk'] == spk and p['dev_reason'] == why)]
            print(s['name'], 'agree', same, 'of', len(ph), 'first_diffs', diff[:3])


if __name__ == '__main__':
    if sys.argv[1] == 'check':
        check(sys.argv[2], sys.argv[3])
    else:
        main()
