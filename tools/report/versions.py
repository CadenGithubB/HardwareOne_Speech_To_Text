#!/usr/bin/env python3
"""Per-version numbers for stt_progress.html, computed from the speaker-session analyses.

Each report version (made-up numbers for test builds) maps to the session labels that tested it on the
standard 27-clip playlist (P4 mic, quiet room). Caption delay = speech end -> caption ready (L_speech),
pooled over that version's phrases, skipping phrases whose console text line was lost or that the analyser
misassigned (same rule as breakdown.py). WER is pooled over sessions (errors / words). Memory = the lowest
free PSRAM / internal RAM seen in any of the version's sessions. Writes versions.json next to this file.
"""
import os
import glob
import json
import re
import statistics as st
from pathlib import Path

SESS = Path(os.environ.get('HW1_STT_SESSIONS', Path(__file__).resolve().parents[1] / 'device_tests' / 'speaker' / 'sessions'))
STANDARD = {
    '1.1': ['e0n'],
    '1.2': ['b6-c3xn'],
    '1.3': ['b9-c4an', 'b10-c4an-prof'],
    '1.4': ['b11-c5n'],
    '1.5': ['b14-t200', 'b15-t200', 'b16-c7t200n'],
    '1.6': ['b16-c9n', 'b17-c9n'],
    '1.7': ['b18-c11n', 'b19-c12n'],      # b19: the same build plus the LM probe (logging only)
    '1.8': ['b26-c12n-lm16'],
}


def sessions(labels):
    for lab in labels:
        for d in sorted(glob.glob(str(SESS / lab / '2026*'))):
            if '/._' not in d and Path(d, 'analysis.json').exists():
                yield Path(d)


def stats(labels):
    L, short, longer, d_lm, n_per_s = [], [], [], [], []
    err = words = 0
    psram, internal, warm = [], [], []
    count = 0
    sess_wer = []
    for d in sessions(labels):
        a = json.load(open(d / 'analysis.json'))
        raw = open(d / 'raw.log', errors='replace').read()
        if a['health'].get('seg_lm0'):
            continue                              # LM failed to load in this session: not representative
        count += 1
        txt = {int(x) for x in re.findall(r'TL txt seq=(\d+)', raw)}
        for p in a['phrases']:
            v = p.get('L_speech')
            if v is None or p['seq'] not in txt or (p.get('text_sim') or 0) < 0.15:
                continue
            L.append(v)
            (short if p.get('bin') == 'short' else longer).append(v)
        err += a['accuracy']['errors']
        words += a['accuracy']['words']
        sess_wer.append(round(a['accuracy']['wer'], 1))
        s = a['summary']
        d_lm.append(s['d']['median'] if isinstance(s['d'], dict) else s['d'])
        n_per_s.append(s['n_per_s']['median'] if isinstance(s['n_per_s'], dict) else s['n_per_s'])
        psram.append(a['health'].get('psram_min_min'))
        im = a['health'].get('internal_heap_min') or {}
        internal.append(im.get('seg.int_min') if isinstance(im, dict) else im)
        m = re.search(r'TL warm .*?psram_free=(\d+)', raw)
        if m:
            warm.append(int(m.group(1)))
    med = lambda x: round(st.median(x) / 1000, 3) if x else None
    return {'labels': labels, 'sessions': count, 'phrases': len(L), 'all': med(L), 'short': med(short),
            'longer': med(longer), 'wer': round(100 * err / words, 2) if words else None, 'words': words,
            'session_wer': sess_wer, 'session_wer_median': st.median(sess_wer) if sess_wer else None,
            'lm_ms': round(st.median(d_lm), 1) if d_lm else None,
            'model_ms_per_audio_s': round(st.median(n_per_s), 1) if n_per_s else None,
            'psram_low_mb': round(min(psram) / 1e6, 2) if psram else None,
            'psram_warm_mb': round(st.median(warm) / 1e6, 2) if warm else None,
            'internal_low_kb': round(min(internal) / 1000, 1) if internal else None}


# Clip-matched WER (clipwer.py's rule): a clip is dropped for every version if any session of any version lost
# the console text line of a phrase overlapping it, so every version is scored on the same clips.
import sys
sys.path.insert(0, str(SESS.parent))
import analyse  # noqa: E402
CLIPS = json.load(open(SESS.parent / 'playlist' / 'manifest.json'))['clips']


def clip_load(sdir):
    a = json.load(open(sdir / 'analysis.json'))
    raw = open(sdir / 'raw.log', errors='replace').read()
    txt = {}
    for line in raw.splitlines():
        m = re.search(r'TL txt seq=(\d+) ?(.*)$', line)
        if m:
            txt[int(m.group(1))] = analyse.normalize_text(m.group(2).replace('\r', ''))
    segs = {int(x) for x in re.findall(r'TL seg=(\d+) a0', raw)}
    phr = [(p['seq'], p['span_play_s']) for p in a['phrases'] if p.get('span_play_s')]
    bad = set()
    for seq, (s0, s1) in phr:
        if seq in segs and seq not in txt:
            bad |= {i for i, c in enumerate(CLIPS) if c['start_s'] < s1 and c['end_s'] > s0}
    return dict(txt=txt, phr=phr, bad=bad)


def clip_runs(good):
    out, cur = [], []
    for i in range(len(CLIPS)):
        if i in good:
            cur.append(i)
        elif cur:
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out


def run_errors(sess, run):
    lo = CLIPS[run[0]]['start_s'] - (CLIPS[run[0] - 1]['gap_after_s'] / 2 if run[0] else 1.0)
    hi = CLIPS[run[-1]]['end_s'] + CLIPS[run[-1]]['gap_after_s'] / 2
    ref = ' '.join(CLIPS[i]['text_norm'] for i in run)
    hyp = ' '.join(sess['txt'][q] for q, (s0, s1) in sess['phr'] if q in sess['txt'] and lo <= (s0 + s1) / 2 < hi)
    return analyse.word_errors(ref, hyp), len(ref.split())


loaded = {v: [clip_load(d) for d in sessions(labs)] for v, labs in STANDARD.items()}
out = {v: stats(labs) for v, labs in STANDARD.items()}
for v, arm in loaded.items():
    # per version: drop the clips that lost a console line in any of that version's sessions
    runs_v = clip_runs(set(range(len(CLIPS))) - set().union(*[x['bad'] for x in arm]))
    e = w = 0
    each = []
    for x in arm:
        ew = [run_errors(x, r) for r in runs_v]
        e += sum(a for a, _ in ew); w += sum(b for _, b in ew)
        each.append(round(100 * sum(a for a, _ in ew) / sum(b for _, b in ew), 1))
    out[v]['clip_wer'] = round(100 * e / w, 2)
    out[v]['clip_wer_sessions'] = each
    out[v]['clip_wer_clips'] = sum(len(r) for r in runs_v)
out['clips_total'] = len(CLIPS)
# Long unbroken speech (14 utterances of 12-17 s) and the parliament conversation (speaker-label check)
out['long'] = {'1.6': stats(['b18L-c9n']), '1.7': stats(['b18L-c11n'])}
out['conv4'] = {'1.7': stats(['b25C-c11n-nospk']), '2.0': stats(['b25C-c13n-async'])}
# speaker labels in the background with the 2.5 MB LM (b24, b25) and with the 1.6 MB LM (b26, diagnostics off)
out['speaker_sessions'] = {'2.5M LM': stats(['b24C-c13n-async-idfpatch', 'b25C-c13n-async']),
                           '1.6M LM': stats(['b26-c13n-transcript'])}
Path(__file__).with_name('versions.json').write_text(json.dumps(out, indent=1))
for k, v in out.items():
    print(k, json.dumps(v)[:400])
