#!/usr/bin/env python3
"""Re-decode the device's own logits (c12 LM probe) with other decoder settings and LMs, scored as clipwer does.

  lmsweep.py verify LABEL [...]                       device settings must reproduce every device caption
  lmsweep.py sweep --labels LABEL [...] --plan PLAN.json [--out RESULT.json] [--workers 4]

Sessions are sessions/<LABEL>/2026*/ with lmprobe.npz/json (lmprobe.py). PLAN.json is a list of configs
{"name": ..., "lm": path, "params": {alpha, beta, unk_log10, beam_width, char_prune, hotword_bonus}} (missing
params come from that LM's header; "greedy": true decodes greedily). The first config is the baseline: every
other one gets a paired bootstrap CI over clip runs. A clip is scored only if every phrase overlapping it, in
every session of its playlist, has complete logits (so all configs see the same audio). Prints numbers only.
"""
import os
import argparse
import json
import random
import re
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'stt_train' / 'lm'))
import analyse  # noqa: E402
import hw1lm  # noqa: E402

ROOT = HERE / 'sessions'


def load_session(sdir):
    a = json.load(open(sdir / 'analysis.json'))
    meta = json.load(open(sdir / 'session.json'))
    man = meta.get('manifest') or str(HERE / 'playlist' / 'manifest.json')
    raw = open(sdir / 'raw.log', errors='replace').read()
    txt = {}
    for line in raw.splitlines():
        m = re.search(r'TL txt seq=(\d+) ?(.*)$', line)
        if m:
            txt[int(m.group(1))] = analyse.normalize_text(m.group(2).replace('\r', ''))
    info = json.load(open(sdir / 'lmprobe.json'))
    arr = np.load(sdir / 'lmprobe.npz')
    caps = {c['seq']: c for c in info['captions'] if c['complete']}
    logits = {seq: arr[f's{seq}'] for seq in caps}
    phr = [(p['seq'], p['span_play_s']) for p in a['phrases'] if p.get('span_play_s')]
    return dict(dir=str(sdir), manifest=man, txt=txt, caps=caps, logits=logits, phr=phr, lm=info['lm'])


def sessions_for(labels):
    out = []
    for lab in labels:
        for d in sorted((ROOT / lab).glob('2026*')):
            if (d / 'lmprobe.json').exists() and (d / 'analysis.json').exists():
                out.append(load_session(d))
    return out


_LM = {}


def get_lm(path):
    if path not in _LM:
        _LM[path] = hw1lm.read_lm(open(path, 'rb').read())
    return _LM[path]


def decode_one(q, exponent, cfg):
    if cfg.get('greedy'):
        return hw1lm.greedy_device(q) if hasattr(hw1lm, 'greedy_device') else ''
    lm = get_lm(cfg['lm'])
    return hw1lm.decode_int8(q, -exponent, lm, None, **cfg.get('params', {}))


def decode_session(args):
    s, cfg = args
    out = {}
    for seq, q in s['logits'].items():
        text = decode_one(q, s['caps'][seq]['exponent'], cfg)
        out[seq] = analyse.normalize_text(text if isinstance(text, str) else text[0])
    return out


def build_runs(sess):
    """Per playlist: clips, the runs of scoreable clips."""
    groups = {}
    for s in sess:
        groups.setdefault(s['manifest'], []).append(s)
    plan = []
    for man, ss in groups.items():
        clips = json.load(open(man))['clips']
        bad = set()
        for s in ss:
            for seq, (s0, s1) in s['phr']:
                if seq not in s['logits']:
                    bad |= {i for i, c in enumerate(clips) if c['start_s'] < s1 and c['end_s'] > s0}
        # A run ends at every clip boundary that no phrase (in any session) straddles, so the bootstrap
        # resamples small independent units, and a phrase's text always lands in one run.
        joined = set()
        for s in ss:
            for seq, (s0, s1) in s['phr']:
                over = [i for i, c in enumerate(clips) if c['start_s'] < s1 and c['end_s'] > s0]
                joined |= {i for i in over[:-1]}          # i joined to i+1
        runs, cur = [], []
        for i in range(len(clips)):
            if i in bad:
                if cur:
                    runs.append(cur); cur = []
                continue
            cur.append(i)
            if i not in joined:
                runs.append(cur); cur = []
        if cur:
            runs.append(cur)
        plan.append((man, clips, ss, runs, bad))
    return plan


UNKNOWN = set()   # reference words the base LM does not know (--new-words-lm); recall is reported for them


def run_errors(clips, s, hyp_by_seq, run):
    """(word errors, reference words, unknown-word hits, unknown words) of one run in one session."""
    lo = clips[run[0]]['start_s'] - (clips[run[0] - 1]['gap_after_s'] / 2 if run[0] else 1.0)
    hi = clips[run[-1]]['end_s'] + clips[run[-1]]['gap_after_s'] / 2
    ref = ' '.join(clips[i]['text_norm'] for i in run)
    hyp = ' '.join(hyp_by_seq[q] for q, (s0, s1) in s['phr'] if q in hyp_by_seq and lo <= (s0 + s1) / 2 < hi)
    rw, hw = ref.split(), hyp.split()
    unk = [w for w in rw if w in UNKNOWN]
    hits = sum(min(unk.count(w), hw.count(w)) for w in set(unk))
    return analyse.word_errors(ref, hyp), len(rw), hits, len(unk)


def verify(labels):
    sess = sessions_for(labels)
    tot = same = 0
    for s in sess:
        lm = s['lm']
        print(f'{s["dir"]}: device LM {lm}')
    # The deployed file: the header must equal what the device printed.
    lm_path = os.path.join(os.environ.get('STT_ROOT', 'stt-data'), 'work/lm/meeting-gen2-25397.lm')
    hdr = get_lm(lm_path).params
    print(f'host LM {lm_path}: {hdr}')
    cfg = {'lm': lm_path}
    for s in sess:
        hyp = decode_session((s, cfg))
        n = sum(1 for q in hyp if q in s['txt'])
        k = sum(1 for q in hyp if q in s['txt'] and s['txt'][q] == hyp[q])
        tot += n; same += k
        print(f'  {Path(s["dir"]).parent.name}/{Path(s["dir"]).name}: captions with logits {len(hyp)}, '
              f'with a TL txt line {n}, host text identical {k}')
    print(f'host reference reproduces {same}/{tot} device captions')


def sweep(labels, plan_path, out_path, workers, new_words_lm=None):
    if new_words_lm:
        vocab = get_lm(new_words_lm).word_id
        for lab in labels:
            for d in sorted((ROOT / lab).glob('2026*')):
                if (d / 'session.json').exists():
                    man = json.load(open(json.load(open(d / 'session.json'))['manifest']))
                    UNKNOWN.update(w for c in man['clips'] for w in c['text_norm'].split() if w not in vocab)
    sess = sessions_for(labels)
    cfgs = json.load(open(plan_path))
    groups = build_runs(sess)
    for man, clips, ss, runs, bad in groups:
        print(f'{Path(man).parent.name}: {len(ss)} sessions, {sum(len(r) for r in runs)}/{len(clips)} clips scored '
              f'({len(runs)} runs)')
    jobs = [(s, c) for c in cfgs for s in sess]
    with Pool(workers) as pool:
        hyps = pool.map(decode_session, jobs, chunksize=1)
    by_cfg = {}
    for (s, c), h in zip(jobs, hyps):
        by_cfg.setdefault(c['name'], {})[s['dir']] = h
    # per config: list over all runs (all playlists) of (errors, words) summed over that playlist's sessions
    table = {}
    for c in cfgs:
        rows = []
        for man, clips, ss, runs, bad in groups:
            for r in runs:
                e = w = h = u = 0
                for s in ss:
                    de, dw, dh, du = run_errors(clips, s, by_cfg[c['name']][s['dir']], r)
                    e += de; w += dw; h += dh; u += du
                rows.append((e, w, h, u))
        table[c['name']] = rows
    base = cfgs[0]['name']
    rnd = random.Random(0)
    n = len(table[base])
    boots = [[rnd.randrange(n) for _ in range(n)] for _ in range(4000)]

    def wer(rows, idx):
        return 100 * sum(rows[i][0] for i in idx) / max(1, sum(rows[i][1] for i in idx))
    allidx = list(range(n))
    results = []
    print(f'{"config":34s} {"WER":>7s} {"vs base":>8s}  95% CI            new-word recall')
    for c in cfgs:
        rows = table[c['name']]
        w = wer(rows, allidx)
        d = sorted(wer(rows, b) - wer(table[base], b) for b in boots)
        lo, hi = d[int(0.025 * len(d))], d[int(0.975 * len(d))]
        results.append({'name': c['name'], 'lm': c.get('lm'), 'params': c.get('params', {}), 'greedy': c.get('greedy', False),
                        'wer': w, 'delta': w - wer(table[base], allidx), 'ci': [lo, hi],
                        'errors': sum(r[0] for r in rows), 'words': sum(r[1] for r in rows),
                        'new_word_hits': sum(r[2] for r in rows), 'new_words': sum(r[3] for r in rows)})
        nw = sum(r[3] for r in rows)
        rec = f'{100 * sum(r[2] for r in rows) / nw:5.1f}% of {nw}' if nw else ''
        print(f'{c["name"]:34s} {w:7.2f} {w - wer(table[base], allidx):+8.2f}  [{lo:+.2f}, {hi:+.2f}]  {rec}')
    if out_path:
        Path(out_path).write_text(json.dumps({'labels': labels, 'results': results}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    v = sub.add_parser('verify'); v.add_argument('labels', nargs='+')
    w = sub.add_parser('sweep'); w.add_argument('--labels', nargs='+', required=True); w.add_argument('--plan', required=True)
    w.add_argument('--out'); w.add_argument('--workers', type=int, default=4)
    w.add_argument('--new-words-lm', help='report recall of reference words this LM does not know')
    a = ap.parse_args()
    if a.cmd == 'verify':
        verify(a.labels)
    else:
        sweep(a.labels, a.plan, a.out, a.workers, a.new_words_lm)


if __name__ == '__main__':
    main()
