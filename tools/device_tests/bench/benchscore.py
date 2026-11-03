#!/usr/bin/env python3
"""Score PCM-file benchmark runs (heaptw_remote.py bench). Numbers only, never transcript text.

  benchscore.py MANIFEST BENCH_DIR [BENCH_DIR ...]

Per run: pooled WER against the manifest's clip references; speaker accuracy, coverage and unknowns
(clusters mapped to reference speakers by majority); caption delay (publication minus the phrase's audio
end); speaker-label lag (label minus publication); speech-model ms per audio ms; speaker NN wall ms;
draft count and draft busy ms. Per directory: median and range across runs.
"""
import json, re, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path


def norm(text):
    return re.sub(r"[^a-z' ]+", ' ', text.lower().replace('’', "'")).split()


def edits(ref, hyp):
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1]


def kv(line):
    return {k: int(v) for k, v in re.findall(r'\b([a-z_0-9]+)=(-?\d+)\b', line)}


def score_run(clips, captions, log):
    ref = [w for c in clips for w in c['text_norm'].split()]
    caps = sorted(captions, key=lambda c: c['sequence'])
    hyp = [w for c in caps for w in norm(c.get('sttText', ''))]
    out = {'wer': round(edits(ref, hyp) / len(ref), 4), 'ref_words': len(ref), 'captions': len(caps)}

    def stamp(line):
        # Device milliseconds: the first "[123456]" field (the host log adds its own time before it).
        m = re.search(r'\[\s*(\d+)\]', line)
        return int(m.group(1)) if m else None
    seg, pub, spk_at, spk = {}, {}, {}, {}
    drafts, draft_ms = 0, 0
    for line in log:
        m = re.search(r'TL seg=(\d+) ', line)
        if m:
            seg[int(m.group(1))] = kv(line[m.start():])
        m = re.search(r'TL pub seq=(\d+) t=(\d+)', line)
        if m:
            pub[int(m.group(1))] = int(m.group(2))
        m = re.search(r'TL spk seq=(\d+) spk=(-?\d+)', line)
        if m:
            q = int(m.group(1))
            spk[q] = int(m.group(2))
            spk_at[q] = stamp(line)
        m = re.search(r'TL draft seq=\d+ [^\r\n]*', line)
        if m:
            d = kv(m.group(0))
            drafts += 1
            if 'e' in d and 's' in d:
                draft_ms += d['e'] - d['s']
    nn = [kv(l).get('nn_us', 0) / 1000 for l in log if 'TL spk seq=' in l]
    ratio = [s['n'] / (s['a1'] - s['a0']) for s in seg.values() if s.get('a1', 0) > s.get('a0', 0) and 'n' in s]
    close = [pub[q] - seg[q]['a1'] for q in pub if q in seg and 'a1' in seg[q]]
    lag = [spk_at[q] - pub[q] for q in spk_at if q in pub and spk_at[q] is not None]

    # Speaker accuracy: caption midpoint -> manifest clip -> reference speaker.
    def clip_at(t):
        for c in clips:
            if float(c['start_s']) <= t < float(c['end_s']) + float(c.get('gap_after_s', 0)):
                return c
        return None
    pairs = []
    for c in caps:
        q = c['sequence']
        if q not in spk:
            continue
        mid = (c['startSample'] + c['endSample']) / 2 / 16000
        clip = clip_at(mid)
        if clip:
            pairs.append((spk[q], clip['speaker']))
    labelled = [(k, s) for k, s in pairs if k >= 0]
    mapping = {}
    for k in {k for k, _ in labelled}:
        mapping[k] = Counter(s for kk, s in labelled if kk == k).most_common(1)[0][0]
    correct = sum(1 for k, s in labelled if mapping[k] == s)
    med = lambda v: round(statistics.median(v), 3) if v else None
    out.update({
        'spk_scored': len(pairs), 'spk_correct': correct, 'spk_unknown': len(pairs) - len(labelled),
        'spk_clusters': len(mapping), 'spk_acc': round(correct / len(pairs), 4) if pairs else None,
        'close_ms_med': med(close), 'spk_lag_ms_med': med(lag), 'spk_lag_ms_max': max(lag) if lag else None,
        'model_ms_per_audio_ms': med(ratio), 'spk_nn_ms_med': med(nn), 'drafts': drafts, 'draft_busy_ms': draft_ms,
        'watchdog': sum('Task watchdog got triggered' in l for l in log),
    })
    return out


def main():
    manifest = json.load(open(sys.argv[1]))
    clips = sorted(manifest['clips'], key=lambda c: float(c['start_s']))
    for d in map(Path, sys.argv[2:]):
        runs = json.load(open(d / 'bench.json'))
        rows = []
        for r in runs:
            log = (d / f"serial-{r['run']}.log").read_text(errors='replace').splitlines()
            row = score_run(clips, r['captions'], log)
            row['run'] = r['run']
            row['state'] = r['state']
            rows.append(row)
            print(d.name, json.dumps(row))
        keys = ['wer', 'spk_acc', 'spk_unknown', 'close_ms_med', 'spk_lag_ms_med', 'model_ms_per_audio_ms',
                'spk_nn_ms_med', 'drafts', 'draft_busy_ms', 'watchdog']
        summary = {}
        for k in keys:
            v = [r[k] for r in rows if r.get(k) is not None]
            if v:
                summary[k] = {'med': round(statistics.median(v), 4), 'min': min(v), 'max': max(v)}
        print(d.name, 'SUMMARY', len(rows), 'runs', json.dumps(summary))
        (d / 'score.json').write_text(json.dumps({'runs': rows, 'summary': summary}, indent=2))


if __name__ == '__main__':
    main()
