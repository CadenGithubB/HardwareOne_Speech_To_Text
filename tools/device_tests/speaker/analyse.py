#!/usr/bin/env python3
"""Analyse speaker-to-P4 STT sessions (stdlib only; any python >= 3.9).

  analyse.py SESSION_DIR [...]            per-session analysis
  analyse.py --label NAME [--root DIR]    every session of a label, plus pooled summary
  analyse.py --compare A B [--root DIR]   paired per-phrase deltas B - A

Per final phrase (TL seg, joined with TL pub / read / txt / draft by sequence):
  L_close   = pub.t - q                          (P4 esp_timer ms)
  split     = wait (s-q), m, f, n, d, pub_rest (pub - (s+m+f+n+d)),
              pump (read.t - pub.t), cap_lag (q - a1)
  n_per_s   = n / audio seconds ((a1-a0)/1000)
  L_speech  = Mac arrival (monotonic) of the TL pub line - (Mac playback start
              + end offset of the phrase's anchor clip); the anchor clip is the
              last playlist clip whose speech end falls inside the phrase.
              Also L_speech_vad (clip's energy speech end instead of clip end)
              and L_speech_p4 (both ends on the P4 clock, via the clock map).
Mapping phrases to clips: the P4 clock is mapped to the Mac clock from the
lower envelope of (line arrival - ESP log tick) and the tick-vs-esp_timer
offset of lines printed at their event time (pub/read/warm/draft/seg). The
playback start then gives a predicted a-clock position for every clip; a shift
delta (+-1.5 s) is searched on phrase-end vs clip-end agreement, and among the
best candidates the one with the highest text similarity (hypothesis vs the
assigned clips' references) wins.
Accuracy: the concatenated normalised hypothesis (phrases overlapping the
playback) against the concatenated references; only words / errors / WER are
printed. Texts stay in <session>/phrases.json (0600).
"""
import argparse
import ast
import hashlib
import json
import math
import os
import random
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tl_parse import ROM_BOOT, parse_line, read_lines_tsv  # noqa: E402

COMMON = HERE.parents[1] / 'stt_train_15x5' / 'common.py'
DEFAULT_ROOT = HERE / 'sessions'
BIN_ORDER = ['short', 'mid', 'long']


def _load_common():
    """Take normalize_text and word_errors from common.py without importing torch."""
    src = COMMON.read_text()
    tree = ast.parse(src)
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('normalize_text', 'word_errors')]
    mod = ast.Module(body=keep, type_ignores=[])
    ns = {'re': re}
    exec(compile(mod, str(COMMON), 'exec'), ns)
    return ns['normalize_text'], ns['word_errors']


normalize_text, word_errors = _load_common()


def med(v):
    v = [x for x in v if x is not None]
    return round(statistics.median(v), 2) if v else None


def pct(v, p):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    k = (len(v) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return round(v[lo] + (v[hi] - v[lo]) * (k - lo), 2)


def private_write(path, text):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as fh:
        fh.write(text)


# ---------------------------------------------------------------- clock map
def fit_lower_envelope(points, bin_ms=10000.0):
    """points: (tick_ms, mono_ms). Fit mono - tick = a + b*tick on per-bin minima."""
    if not points:
        return None
    bins = {}
    for t, m in points:
        k = int(t // bin_ms)
        d = m - t
        if k not in bins or d < bins[k][1]:
            bins[k] = (t, d)
    pts = sorted(bins.values())
    if len(pts) < 3:
        a = min(d for _, d in pts)
        return {'a': a, 'b': 0.0, 'bins': len(pts), 'resid_max_ms': 0.0}
    n = len(pts)
    mx = sum(t for t, _ in pts) / n
    my = sum(d for _, d in pts) / n
    sxx = sum((t - mx) ** 2 for t, _ in pts)
    b = sum((t - mx) * (d - my) for t, d in pts) / sxx if sxx else 0.0
    a = my - b * mx
    # shift down so the line is a lower envelope of the bin minima
    a += min(d - (a + b * t) for t, d in pts)
    resid = [d - (a + b * t) for t, d in pts]
    return {'a': a, 'b': b, 'bins': n, 'resid_max_ms': round(max(resid), 3), 'drift_ppm': round(b * 1e6, 2)}


class ClockMap:
    def __init__(self, env, tick_minus_esp):
        self.env, self.tme = env, tick_minus_esp

    def esp_to_mono(self, t_esp):
        tick = t_esp + self.tme
        return (tick + self.env['a'] + self.env['b'] * tick) / 1000.0

    def mono_to_esp(self, mono):
        ms = mono * 1000.0
        tick = (ms - self.env['a']) / (1.0 + self.env['b'])
        return tick - self.tme


# ---------------------------------------------------------------- one session
def load_session(sdir):
    sdir = Path(sdir)
    meta = json.loads((sdir / 'session.json').read_text())
    rows = list(read_lines_tsv(sdir / 'lines.tsv'))
    # keep only lines after the last boot banner (this session's boot)
    last_boot = 0
    for i, (_, _, l) in enumerate(rows):
        if ROM_BOOT.search(l):
            last_boot = i
    lines = []
    for mono, wall, l in rows[last_boot:]:
        p = parse_line(l)
        p['mono'], p['wall'] = mono, wall
        lines.append(p)
    return meta, lines


def by_kind(lines):
    out = {}
    for p in lines:
        if p['tl']:
            out.setdefault(p['tl']['kind'], []).append(p)
    return out


def boundary_score(phr, clips, delta, play_esp):
    s = 0.0
    for p in phr:
        x1 = (p['a1'] - play_esp - delta) / 1000.0 - 0.6
        best = 0.0
        for c in clips:
            d = (x1 - c['speech_end_s']) / 0.15
            if abs(d) < 4:
                best = max(best, math.exp(-d * d))
        s += best
    return s


def assign(phr, clips, delta, play_esp):
    """Assign each clip to the phrase with the largest overlap of its speech span."""
    spans = [((p['a0'] - play_esp - delta) / 1000.0, (p['a1'] - play_esp - delta) / 1000.0) for p in phr]
    members = [[] for _ in phr]
    clip_to = {}
    for c in clips:
        best, bj = 0.0, None
        for j, (x0, x1) in enumerate(spans):
            ov = min(x1, c['speech_end_s']) - max(x0, c['speech_start_s'])
            if ov > best:
                best, bj = ov, j
        if bj is not None:
            members[bj].append(c['i'])
            clip_to[c['i']] = bj
    anchors = []
    for j, (x0, x1) in enumerate(spans):
        # anchor: the last clip whose speech ends inside the phrase (its clip end may lie
        # just after the close when the clip carries > 0.6 s of trailing silence)
        inside = [c['i'] for c in clips if x0 < c['speech_end_s'] <= x1 + 0.05]
        anchors.append(inside[-1] if inside else None)
    return spans, members, anchors, clip_to


def text_sim(ref, hyp):
    r = ref.split()
    if not r:
        return None
    return 1.0 - word_errors(ref, hyp) / max(len(r), len(hyp.split()))


def early_exit(res, sdir, write, quiet):
    res['valid'] = False
    if write:
        (sdir / 'analysis.json').write_text(json.dumps(res, indent=1))
    if not quiet:
        print_session(res)
    return res, []


def analyse_session(sdir, write=True, quiet=False):
    sdir = Path(sdir)
    meta, lines = load_session(sdir)
    res = {'session': str(sdir), 'label': meta.get('label'), 'status': meta.get('status'), 'warnings': []}
    W = res['warnings']
    man_path = Path(meta.get('manifest') or HERE / 'playlist' / 'manifest.json')
    man = json.loads(man_path.read_text())
    if meta.get('wav_sha256') and meta['wav_sha256'] != man.get('wav_sha256'):
        W.append('wav sha256 differs from manifest')
    clips = man['clips']
    K = by_kind(lines)
    res['tl_counts'] = {k: len(v) for k, v in K.items()}

    # ---- clock map
    pts = [(p['tick'], p['mono'] * 1000.0) for p in lines if p['tick'] is not None and p['tick'] > 2000]
    env = fit_lower_envelope(pts)
    cand = []
    for kind, key in (('pub', 't'), ('read', 't'), ('warm', 'e'), ('draft', 'e'), ('seg', 'e')):
        for p in K.get(kind, []):
            t = p['tl']['f'].get(key)
            if p['tick'] is not None and t:
                cand.append((p['tick'] - t, kind))
    cand.sort()
    tme = cand[0][0] if cand else 0.0
    if not cand:
        W.append('no TL line with an event time; assuming log tick == esp_timer')
    res['clock'] = {'envelope': env, 'tick_minus_esp_ms': tme, 'tick_minus_esp_from': cand[0][1] if cand else None,
                    'tick_minus_esp_next3': [c[0] for c in cand[1:4]]}
    if env is None:
        W.append('no ESP log ticks; cannot map clocks')
        return early_exit(res, sdir, write, quiet)
    cm = ClockMap(env, tme)

    # ---- playback
    play = meta.get('afplay') or {}
    calib = meta.get('afplay_calibration') or {}
    t_play = play.get('t_audio_start')
    if t_play is None and play.get('t_launch') is not None and calib.get('launch_to_audio_ms') is not None:
        t_play = play['t_launch'] + calib['launch_to_audio_ms'] / 1000.0
        W.append('playback start from launch + calibrated latency')
    res['playback'] = {'t_audio_start_mono': t_play, 'method': play.get('audio_start_method'),
                       'launch_to_audio_ms': (meta.get('afplay_summary') or {}).get('launch_to_audio_ms')}
    if t_play is None:
        W.append('no playback timing (capture-only or aborted session)')
        return early_exit(res, sdir, write, quiet)
    play_esp = cm.mono_to_esp(t_play)
    cs = K.get('capture_start', [{}])[-1].get('tl', {}).get('f', {}).get('t') if K.get('capture_start') else None
    res['playback'].update(play_esp_ms=round(play_esp, 1),
                           capture_start_ms=cs,
                           play_pos_in_capture_ms=round(play_esp - cs, 1) if cs else None)

    # ---- phrases
    pub = {p['tl']['id']: p for p in K.get('pub', [])}
    rd = {p['tl']['id']: p for p in K.get('read', [])}
    txt = {p['tl']['id']: p['tl']['text'] for p in K.get('txt', [])}
    drafts = {}
    for p in K.get('draft', []):
        drafts.setdefault(p['tl']['id'], []).append(p['tl']['f'])
    phr = []
    seen = set()
    for p in K.get('seg', []):
        f = dict(p['tl']['f'])
        sid = p['tl']['id']
        if sid in seen:
            W.append(f'duplicate TL seg {sid}')
            continue
        seen.add(sid)
        f['seq'] = sid
        f['mono_seg_line'] = p['mono']
        if sid in pub:
            f['pub_t'] = pub[sid]['tl']['f'].get('t')
            f['mono_pub_line'] = pub[sid]['mono']
        if sid in rd:
            f['read_t'] = rd[sid]['tl']['f'].get('t')
        f['hyp'] = normalize_text(txt.get(sid, '')) if sid in txt else None
        phr.append(f)
    if not phr:
        W.append('no TL seg lines')
    if phr and not pub:
        W.append('no TL pub lines; L_close uses sv0 as the publish proxy')

    # ---- delta search (boundary agreement), then text similarity among the best candidates
    grid = [d for d in range(-1500, 1501, 10)]
    scores = [(boundary_score(phr, clips, d, play_esp), d) for d in grid] if phr else [(0.0, 0)]
    local = [(s, d) for i, (s, d) in enumerate(scores)
             if (i == 0 or s >= scores[i - 1][0]) and (i == len(scores) - 1 or s >= scores[i + 1][0])]
    local.sort(reverse=True)
    cands = [d for _, d in local[:6]] + [0]
    best = None
    have_text = any(p['hyp'] is not None for p in phr)
    for d in dict.fromkeys(cands):
        spans, members, anchors, clip_to = assign(phr, clips, d, play_esp)
        tsc = 0.0
        if have_text:
            for p, mem in zip(phr, members):
                if p['hyp'] is None:
                    continue
                ref = ' '.join(clips[i]['text_norm'] for i in mem)
                tsc += (len(ref.split()) - word_errors(ref, p['hyp'])) if ref else -len(p['hyp'].split())
        bsc = dict((dd, s) for s, dd in scores).get(d, 0.0)
        key = (tsc if have_text else 0.0, bsc)
        if best is None or key > best[0]:
            best = (key, d, spans, members, anchors, clip_to)
    (tscore, bscore), delta, spans, members, anchors, clip_to = best
    res['alignment'] = {'delta_ms': delta, 'boundary_score': round(bscore, 2), 'phrases': len(phr),
                        'text_score': round(tscore, 1) if have_text else None,
                        'clips_assigned': len(clip_to), 'clips_total': len(clips)}

    # ---- per-phrase metrics
    out = []
    for j, p in enumerate(phr):
        q, s = p.get('q'), p.get('s')
        m, f, n, d = (p.get(k) for k in ('m', 'f', 'n', 'd'))
        pub_t = p.get('pub_t') or (p.get('sv0') or None)
        T = (p['a1'] - p['a0']) / 1000.0 if p.get('a1') is not None and p.get('a0') is not None else None
        anc = anchors[j]
        mem = members[j]
        r = {'seq': p['seq'], 'ok': p.get('ok'), 'lm': p.get('lm'), 'a0': p.get('a0'), 'a1': p.get('a1'),
             'audio_s': round(T, 3) if T is not None else None,
             'span_play_s': [round(spans[j][0], 3), round(spans[j][1], 3)],
             'clips': mem, 'anchor_clip': anc, 'bin': clips[anc]['bin'] if anc is not None else None,
             'kind': 'pause' if anc is not None else ('split' if mem else 'noise'),
             'L_close': (pub_t - q) if (pub_t and q) else None,
             'wait': (s - q) if (s and q) else None, 'm': m, 'f': f, 'n': n, 'd': d,
             'pub_rest': (pub_t - (s + m + f + n + d)) if (pub_t and s and None not in (m, f, n, d)) else None,
             'pump': (p['read_t'] - pub_t) if (p.get('read_t') and pub_t) else None,
             'cap_lag': (q - p['a1']) if (q and p.get('a1')) else None,
             'n_per_s': round(n / T, 1) if (n and T) else None,
             'psram_min': p.get('psram_min'),
             'pub_source': 'pub' if p.get('pub_t') else ('sv0' if p.get('sv0') else None)}
        if anc is not None:
            c = clips[anc]
            end_mono = t_play + c['end_s']
            if p.get('mono_pub_line') is not None:
                r['L_speech'] = round((p['mono_pub_line'] - end_mono) * 1000.0, 1)
                r['L_speech_vad'] = round((p['mono_pub_line'] - (t_play + c['speech_end_s'])) * 1000.0, 1)
            if pub_t:
                r['L_speech_p4'] = round(pub_t - (play_esp + 1000.0 * c['end_s']), 1)
        # drafts
        dl = drafts.get(p['seq'], [])
        r['drafts'] = len(dl)
        r['drafts_preempted'] = sum(1 for x in dl if not x.get('ok'))
        lags = [x['e'] - (p['a0'] + x['audio_ms']) for x in dl if x.get('ok') and x.get('e') and 'audio_ms' in x]
        r['draft_lag'] = lags
        r['draft_compute'] = [x['e'] - x['s'] for x in dl if x.get('e') and x.get('s')]
        firsts = [x['e'] for x in dl if x.get('ok') and x.get('e')] + ([pub_t] if pub_t else [])
        if mem and firsts:
            r['first_text_ms'] = round(min(firsts) - (play_esp + 1000.0 * clips[mem[0]]['speech_start_s']), 1)
        if p['hyp'] is not None:
            ref = ' '.join(clips[i]['text_norm'] for i in mem)
            r['text_sim'] = round(text_sim(ref, p['hyp']), 3) if ref else None
            r['hyp_sha1'] = hashlib.sha1(p['hyp'].encode()).hexdigest()[:12]
        out.append(r)

    # ---- accuracy (concatenated)
    lo, hi = -1.0, man['duration_s'] + 3.0
    hyp_all = ' '.join(p['hyp'] for p, r in zip(phr, out)
                       if p['hyp'] and r['span_play_s'][1] > lo and r['span_play_s'][0] < hi)
    ref_all = ' '.join(c['text_norm'] for c in clips)
    acc = None
    if have_text:
        e = word_errors(ref_all, hyp_all)
        nw = len(ref_all.split())
        acc = {'words': nw, 'errors': e, 'wer': round(100.0 * e / nw, 2), 'hyp_words': len(hyp_all.split())}
    res['accuracy'] = acc

    # ---- health
    faults = K.get('fault', [])
    warm = K.get('warm', [{}])[-1].get('tl', {}).get('f', {}) if K.get('warm') else {}
    heap_keys = {}
    for kind, lst in K.items():
        for pl in lst:
            for k, v in pl['tl']['f'].items():
                if isinstance(v, (int, float)) and re.search(r'(^|_)(int|heap|dram|iram|internal)', k):
                    heap_keys.setdefault(f'{kind}.{k}', []).append(v)
    res['health'] = {
        'fatal_markers': len((meta.get('reader') or {}).get('fatal_markers') or []),
        'boot_banners': len((meta.get('reader') or {}).get('boot_banners') or []),
        'fault_lines': len(faults), 'fault_last': faults[-1]['tl']['f'] if faults else None,
        'seg_not_ok': sum(1 for p in phr if not p.get('ok')), 'seg_lm0': sum(1 for p in phr if p.get('lm') == 0),
        'psram_min_min': min((p['psram_min'] for p in phr if p.get('psram_min')), default=None),
        'warm': warm,
        'internal_heap_min': {k: min(v) for k, v in heap_keys.items()} or None,
        'level_lines': len(K.get('level', [])),
    }
    # ---- summaries
    fin = [r for r in out if r['ok']]
    res['summary'] = summarise(fin)
    res['drafts'] = {'count': sum(r['drafts'] for r in out), 'preempted': sum(r['drafts_preempted'] for r in out),
                     'lag_median_ms': med([x for r in out for x in r['draft_lag']]),
                     'compute_median_ms': med([x for r in out for x in r['draft_compute']]),
                     'first_text_median_ms': med([r.get('first_text_ms') for r in out])}
    sims = [r.get('text_sim') for r in out if r.get('text_sim') is not None]
    res['alignment'].update(text_sim_median=med(sims), low_sim_phrases=sum(1 for x in sims if x < 0.3),
                            pause_phrases=sum(1 for r in out if r['kind'] == 'pause'),
                            split_phrases=sum(1 for r in out if r['kind'] == 'split'),
                            noise_phrases=sum(1 for r in out if r['kind'] == 'noise'))
    if res['alignment']['low_sim_phrases'] > max(2, len(sims) // 4):
        W.append('many phrases have low text similarity to their mapped clips (check alignment)')
    res['valid'] = (meta.get('status') == 'ok' and res['health']['fatal_markers'] == 0 and bool(phr))
    if write:
        (sdir / 'analysis.json').write_text(json.dumps({**res, 'phrases': strip_text(out)}, indent=1))
        private_write(sdir / 'phrases.json', json.dumps(
            {'note': 'contains transcripts; do not print', 'phrases': [
                {**r, 'hyp': p['hyp'], 'ref': ' '.join(clips[i]['text_norm'] for i in r['clips'])}
                for p, r in zip(phr, out)], 'hyp_all': hyp_all, 'ref_all': ref_all}, indent=1))
    if not quiet:
        print_session(res)
    return res, out


def strip_text(rows):
    return [{k: v for k, v in r.items() if k not in ('hyp', 'ref')} for r in rows]


METRICS = ['L_close', 'L_speech', 'L_speech_vad', 'L_speech_p4', 'wait', 'm', 'f', 'n', 'd', 'pub_rest', 'pump',
           'cap_lag', 'n_per_s']


def summarise(rows):
    s = {'phrases': len(rows)}
    for k in METRICS:
        v = [r.get(k) for r in rows if r.get(k) is not None]
        if v:
            s[k] = {'median': med(v), 'p10': pct(v, 10), 'p90': pct(v, 90), 'n': len(v)}
    s['by_bin'] = {}
    for b in BIN_ORDER:
        rb = [r for r in rows if r.get('bin') == b]
        if rb:
            s['by_bin'][b] = {'n': len(rb), **{k: med([r.get(k) for r in rb]) for k in
                                               ('L_close', 'L_speech', 'n_per_s', 'audio_s')}}
    return s


def fmt(v):
    return '-' if v is None else (f'{v:.0f}' if isinstance(v, (int, float)) and abs(v) >= 100 else f'{v}')


def print_summary_block(s, indent='  '):
    keys = [k for k in METRICS if k in s]
    print(indent + ' '.join(f'{k}={fmt(s[k]["median"])}' for k in keys) + '   (medians, ms; n_per_s = ms/audio-s)')
    for b, v in s.get('by_bin', {}).items():
        print(indent + f'  {b:5s} n={v["n"]:3d} audio_s={fmt(v["audio_s"])} L_close={fmt(v["L_close"])} '
                       f'L_speech={fmt(v["L_speech"])} n_per_s={fmt(v["n_per_s"])}')


def print_session(res):
    a, h, acc = res.get('alignment', {}), res.get('health', {}), res.get('accuracy')
    print(f'== {res["session"]}  label={res["label"]} status={res["status"]} valid={res.get("valid")}')
    c = res.get('clock', {})
    env = c.get('envelope') or {}
    print(f'  clock: tick-esp={c.get("tick_minus_esp_ms")} ms (from {c.get("tick_minus_esp_from")}), '
          f'envelope bins={env.get("bins")} drift={env.get("drift_ppm")} ppm resid_max={env.get("resid_max_ms")} ms; '
          f'playback {res.get("playback", {}).get("method")}, pos in capture {res.get("playback", {}).get("play_pos_in_capture_ms")} ms')
    if a:
        print(f'  alignment: delta={a.get("delta_ms")} ms phrases={a.get("phrases")} pause/split/noise='
              f'{a.get("pause_phrases")}/{a.get("split_phrases")}/{a.get("noise_phrases")} '
              f'clips assigned {a.get("clips_assigned")}/{a.get("clips_total")} text_sim median={a.get("text_sim_median")} '
              f'low={a.get("low_sim_phrases")}')
    if res.get('summary'):
        print_summary_block(res['summary'])
    d = res.get('drafts') or {}
    if d:
        print(f'  drafts: {d.get("count")} (preempted {d.get("preempted")}), lag median {d.get("lag_median_ms")} ms, '
          f'compute median {d.get("compute_median_ms")} ms, first text median {d.get("first_text_median_ms")} ms')
    if h:
        print(f'  health: fatal={h.get("fatal_markers")} boots={h.get("boot_banners")} fault_lines={h.get("fault_lines")} '
              f'last_fault={h.get("fault_last")} seg_not_ok={h.get("seg_not_ok")} lm0={h.get("seg_lm0")} '
              f'psram_min={h.get("psram_min_min")} internal={h.get("internal_heap_min")}')
    if acc:
        print(f'  accuracy: words={acc["words"]} errors={acc["errors"]} WER={acc["wer"]}%')
    for w in res.get('warnings', []):
        print(f'  WARNING: {w}')


# ---------------------------------------------------------------- labels / compare
def label_sessions(root, label):
    d = Path(root) / label
    return sorted(p for p in d.glob('*_s*') if (p / 'session.json').exists()) if d.exists() else []


def analyse_label(root, label, quiet=False):
    sess = []
    for sd in label_sessions(root, label):
        res, rows = analyse_session(sd, write=True, quiet=quiet)
        sess.append((res, rows))
    return sess


def per_clip(sess, metric):
    """anchor clip -> mean over valid sessions of the metric (final pause phrases only)."""
    acc = {}
    for res, rows in sess:
        if not res.get('valid'):
            continue
        for r in rows:
            if r['ok'] and r['kind'] == 'pause' and r.get(metric) is not None:
                acc.setdefault(r['anchor_clip'], []).append(r[metric])
    return {k: sum(v) / len(v) for k, v in acc.items()}


def bootstrap_ci(vals, stat=statistics.median, reps=10000, seed=0):
    rng = random.Random(seed)
    n = len(vals)
    if n < 2:
        return None, None
    bs = sorted(stat([vals[rng.randrange(n)] for _ in range(n)]) for _ in range(reps))
    return round(bs[int(0.025 * reps)], 1), round(bs[int(0.975 * reps) - 1], 1)


def pooled(sess):
    rows = [r for res, rr in sess if res.get('valid') for r in rr if r['ok']]
    accs = [res['accuracy'] for res, _ in sess if res.get('valid') and res.get('accuracy')]
    w = sum(a['words'] for a in accs)
    e = sum(a['errors'] for a in accs)
    return rows, ({'words': w, 'errors': e, 'wer': round(100.0 * e / w, 2)} if w else None)


def compare(root, la, lb, reps=10000):
    A = analyse_label(root, la, quiet=True)
    B = analyse_label(root, lb, quiet=True)
    if not A or not B:
        raise SystemExit(f'need sessions for both labels (found {len(A)} for {la}, {len(B)} for {lb})')
    man = json.loads(Path(json.loads((Path(A[0][0]['session']) / 'session.json').read_text())
                          .get('manifest') or HERE / 'playlist' / 'manifest.json').read_text())
    bins = {c['i']: c['bin'] for c in man['clips']}
    print(f'compare {lb} - {la}: sessions valid {sum(1 for r, _ in A if r.get("valid"))}/{len(A)} vs '
          f'{sum(1 for r, _ in B if r.get("valid"))}/{len(B)}')
    for lab, S in ((la, A), (lb, B)):
        rows, acc = pooled(S)
        print(f'  {lab}: final phrases {len(rows)}; accuracy ' +
              (f'words={acc["words"]} errors={acc["errors"]} WER={acc["wer"]}%' if acc else 'n/a'))
    out = {'A': la, 'B': lb, 'metrics': {}}
    for metric in ('L_close', 'L_speech', 'wait', 'm', 'f', 'n', 'd', 'pub_rest', 'pump'):
        pa, pb = per_clip(A, metric), per_clip(B, metric)
        keys = sorted(set(pa) & set(pb))
        if not keys:
            continue
        res = {}
        for name, ks in [('all', keys)] + [(b, [k for k in keys if bins.get(k) == b]) for b in BIN_ORDER]:
            dl = [pb[k] - pa[k] for k in ks]
            if not dl:
                continue
            lo, hi = bootstrap_ci(dl, reps=reps)
            res[name] = {'n': len(dl), 'median_delta': round(statistics.median(dl), 1),
                         'ci95': [lo, hi], 'mean_delta': round(sum(dl) / len(dl), 1),
                         'A_median': round(statistics.median(pa[k] for k in ks), 1),
                         'B_median': round(statistics.median(pb[k] for k in ks), 1)}
        out['metrics'][metric] = res
        line = '  '.join(f'{nm}: n={v["n"]} {v["A_median"]:.0f}->{v["B_median"]:.0f} '
                         f'd={v["median_delta"]:+.0f} [{fmt(v["ci95"][0])},{fmt(v["ci95"][1])}]'
                         for nm, v in res.items())
        print(f'  {metric:8s} {line}')
    dest = Path(root) / f'compare_{la}_vs_{lb}.json'
    dest.write_text(json.dumps(out, indent=1))
    print(f'  (median of per-phrase deltas B-A, ms, with bootstrap 95% CI over phrases; saved {dest})')
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('sessions', nargs='*', type=Path)
    ap.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    ap.add_argument('--label')
    ap.add_argument('--compare', nargs=2, metavar=('A', 'B'))
    ap.add_argument('--reps', type=int, default=10000)
    a = ap.parse_args()
    if a.compare:
        compare(a.root, a.compare[0], a.compare[1], a.reps)
        return
    if a.label:
        S = analyse_label(a.root, a.label)
        rows, acc = pooled(S)
        print(f'== label {a.label}: {sum(1 for r, _ in S if r.get("valid"))}/{len(S)} valid sessions, '
              f'{len(rows)} final phrases')
        print_summary_block(summarise(rows))
        if acc:
            print(f'  pooled accuracy: words={acc["words"]} errors={acc["errors"]} WER={acc["wer"]}%')
        return
    for sd in a.sessions:
        analyse_session(sd)


if __name__ == '__main__':
    main()
