#!/usr/bin/env python3
"""Why speaker labels came out as they did: per-session decisions and a clip-by-clip run comparison.

  spkdiag.py SESSION_DIR [...]               one JSON summary per session
  spkdiag.py --phrases SESSION_DIR [...]     the same, plus one row per text phrase
  spkdiag.py --compare RUN_A RUN_B           two runs of one playlist, clip by clip

Reads lines.tsv, analysis.json and the manifest as spkeval.py does. Every phrase that produced text (TL
pub, or any speaker line for its sequence) is joined with its speaker pipeline lines:
  TL spk          label, sim, samples, lag (or fail=1; skipped=1 before 0.99.99)
  TL spk_match    clustering reason, best/second profile and similarity, matches, centroid update
  TL spk_submit   admitted=0: refused before embedding, with its reason
  TL spk_result_lost, TL tsave (the label the saved transcript line carried)
  TL spk_load (threshold), TL spk_drain, TL spk_end, TL boundary (end kind, continuation, voiced samples)
Without TL spk_match lines the reason is derived from TL spk: an unknown whose sim reaches the load
threshold had two or more matches (ambiguous); below it, a phrase shorter than --min-new-ms is
no_match_short, else capacity. Derived reasons are marked, and sim/th are printed rounded.

The reference speaker follows spkeval.py (the clip holding the phrase midpoint). analysis.json's member
clips give every speaker a phrase overlaps; a phrase spanning a turn change is flagged mixed. Scores over
phrases with a reference:
  accuracy_scored    spkeval.py's number: TL spk label lines only, unknown counted wrong
  coverage           share of those with a real label
  accuracy_labelled  share of the labelled ones that are right (same best mapping)
  accuracy_text      every text phrase; refused, failed and missing ones count as unknown
  accuracy_saved     the saved transcript's labels (TL tsave; unlabelled lines count as unknown)
--compare judges each playlist clip by the phrase covering it, against that clip's own speaker, using
each run's own mapping. Numbers and IDs only: no recognised or reference text is read or printed.
"""
import argparse
import collections
import json
import re
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyse  # noqa: E402
from tl_parse import parse_line  # noqa: E402
from spkeval import best_mapping, reference_clip  # noqa: E402

WORDS = re.compile(r'\b(reason|why|outcome)=(\S+)')
LABEL_KEYS = ('spk', 'sim', 'new', 'tent', 'samples', 'lag_ms', 'us')
MATCH_KEYS = ('profiles_before', 'profiles_after', 'best', 'best_sim', 'second', 'second_sim', 'matches',
              'updated', 'phrase_samples')
NEAR = 0.05   # similarity distance from the threshold reported as a near decision
# Serial capture can join a prefix to an otherwise complete ESP-IDF log entry.
EMBEDDED_TL = re.compile(r'[IWEDV] \(\d+\) [^:\r\n]{1,32}: TL (?:spk(?:_[a-z]+)?|tsave|pub|boundary)(?:\s|=)')


def words(msg):
    return dict(WORDS.findall(msg))


def speaker_lines(records):
    """Per-sequence speaker pipeline facts and the session-level speaker lines."""
    seq = {}
    out = {'seq': seq, 'text': set(), 'boundary': {}, 'load': None, 'drain': None, 'end': None}
    for r in records:
        if r['tl'] is None:
            m = EMBEDDED_TL.search(r['msg'])
            if m:
                recovered = parse_line(r['msg'][m.start():])
                if recovered['tl'] is not None:
                    r = recovered
        tl = r['tl']
        if not tl:
            continue
        kind, f = tl['kind'], tl['f']
        row = seq.setdefault(int(f['seq']), {}) if 'seq' in f and kind.startswith(('spk', 'tsave')) else None
        if kind == 'pub' and tl['id'] is not None:
            out['text'].add(int(tl['id']))
        elif kind == 'spk' and row is not None:
            if f.get('fail'):
                row['fail'] = True
            elif f.get('skipped'):
                row['refused'] = 'backlog'
            elif 'sim' in f:
                row['label'] = {k: f.get(k) for k in LABEL_KEYS}
                row['label_tick'] = r['tick']
        elif kind == 'spk_match' and row is not None:
            row['match'] = {k: f.get(k) for k in MATCH_KEYS}
            row['match']['reason'] = words(r['msg']).get('reason')
        elif kind == 'spk_submit' and row is not None and f.get('admitted') == 0:
            row['refused'] = words(r['msg']).get('reason', 'unknown')
        elif kind == 'spk_result_lost' and row is not None:
            row['lost'] = True
        elif kind == 'tsave' and row is not None:
            row['saved'] = f.get('spk', -1) if f.get('labelled') else -1
        elif kind == 'spk_load':
            out['load'] = {'ok': f.get('ok'), 'th': f.get('th'), 'why': words(r['msg']).get('why')}
        elif kind == 'spk_drain':
            out['drain'] = {'outcome': words(r['msg']).get('outcome'), 'pending': f.get('pending'),
                            'wait_ms': f.get('wait_ms')}
        elif kind == 'spk_end':
            out['end'] = {k: f.get(k) for k in ('submitted', 'labelled', 'skipped')}
        elif kind == 'boundary' and tl['id'] is not None:
            out['boundary'][int(tl['id'])] = {'end_kind': f.get('kind'), 'continuation': f.get('continuation'),
                                              'vad_voiced': f.get('vad_voiced')}
    return out


def derived_reason(label, th, min_new):
    if label['new']:
        return 'new'
    if label['spk'] >= 0:
        return 'match' if label['samples'] >= min_new else 'short_match'
    if th is None:
        return None
    if label['sim'] >= th:
        return 'ambiguous'
    return 'no_match_short' if label['samples'] < min_new else 'capacity'


def phrase_rows(sdir, min_new):
    sdir = Path(sdir)
    meta, records = analyse.load_session(sdir)
    a = json.loads((sdir / 'analysis.json').read_text())
    man = json.loads(Path(meta['manifest']).read_text())
    clips = {c['i']: c for c in man['clips']}
    sp = speaker_lines(records)
    th = (sp['load'] or {}).get('th')
    tick_minus_esp = (a.get('clock') or {}).get('tick_minus_esp_ms') or 0
    rows = []
    for p in a['phrases']:
        n = p['seq']
        s = sp['seq'].get(n, {})
        if n not in sp['text'] and not s:
            continue
        members = p.get('clips') or []
        ref = reference_clip(man['clips'], p['span_play_s']) if p.get('span_play_s') else None
        lab, m = s.get('label'), s.get('match')
        pipeline = ('labelled' if lab else 'failed' if s.get('fail') else
                    'refused:' + s['refused'] if s.get('refused') else 'missing')
        row = {'seq': n, 'clips': members, 'speakers': sorted({clips[i]['speaker'] for i in members}),
               'ref': ref['speaker'] if ref else None, 'kind': p.get('kind'), 'audio_s': p.get('audio_s'),
               'pipeline': pipeline, 'spk': lab['spk'] if lab else -1}
        row['mixed'] = len(row['speakers']) > 1
        if lab:
            row.update(sim=lab['sim'], samples=lab['samples'], created=bool(lab['new']), lag_ms=lab['lag_ms'])
            if m:
                row.update(reason=m['reason'], reason_source='spk_match',
                           **{k: m[k] for k in ('best', 'best_sim', 'second', 'second_sim', 'matches', 'updated')})
            else:
                row.update(reason=derived_reason(lab, th, min_new), reason_source='derived')
            if s.get('label_tick') is not None and p.get('a1') is not None:
                row['label_after_capture_end_ms'] = round(s['label_tick'] - tick_minus_esp - p['a1'])
        if s.get('lost'):
            row['lost'] = True
        if 'saved' in s:
            row['saved_spk'] = s['saved']
        row.update(sp['boundary'].get(n, {}))
        rows.append(row)
    return meta, a, man, sp, rows


def pct(n, d):
    return round(100 * n / d, 1) if d else None


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def summarise(sdir, min_new=32000, with_rows=False):
    meta, a, man, sp, rows = phrase_rows(sdir, min_new)
    th = (sp['load'] or {}).get('th')
    ref_rows = [r for r in rows if r['ref'] is not None]
    scored = [r for r in ref_rows if r['pipeline'] == 'labelled']
    right, mapping = best_mapping([r['ref'] for r in scored], [r['spk'] for r in scored])
    labelled = [r for r in scored if r['spk'] >= 0]
    text_right = best_mapping([r['ref'] for r in ref_rows], [r['spk'] for r in ref_rows])[0]
    saved = [r for r in ref_rows if 'saved_spk' in r]
    saved_right = best_mapping([r['ref'] for r in saved], [r['saved_spk'] for r in saved])[0]

    clusters, scored_seqs = {}, {r['seq'] for r in scored}
    for r in rows:
        if r['spk'] < 0:
            continue
        c = clusters.setdefault(r['spk'], {'label': r['spk'], 'maps_to': mapping.get(r['spk']), 'phrases': 0,
                                           'scored': 0, 'scored_right': 0})
        c['phrases'] += 1
        c['scored'] += r['seq'] in scored_seqs
        c['scored_right'] += r['seq'] in scored_seqs and mapping.get(r['spk']) == r['ref']
        if r.get('created'):
            c['created'] = {'seq': r['seq'], 'clips': r['clips'], 'speakers': r['speakers'], 'mixed': r['mixed'],
                            'ref': r['ref'], 'samples': r['samples'], 'best_sim_before': r.get('best_sim'),
                            'below_threshold_by': round(th - r['best_sim'], 3)
                            if th is not None and r.get('best_sim') is not None and r.get('best') is not None
                            and r['best'] >= 0 else None}

    unknown = [r for r in ref_rows if r['spk'] < 0]
    by_reason = collections.defaultdict(collections.Counter)
    for r in unknown:
        by_reason[r.get('reason') or r['pipeline']][r['ref']] += 1
    pairs = collections.Counter(f"{r['best']}/{r['second']}" for r in unknown
                                if r.get('reason') == 'ambiguous' and r.get('best') is not None)
    near = [r for r in rows if th is not None and r.get('best_sim') is not None and r.get('best', -1) >= 0
            and abs(r['best_sim'] - th) < NEAR]
    out = {
        'session': str(sdir), 'threshold': th, 'min_new_samples': min_new, 'load': sp['load'],
        'phrases': {'text': len(rows), 'with_reference': len(ref_rows), 'scored': len(scored),
                    'labelled': len(labelled), 'mixed': sum(r['mixed'] for r in rows),
                    'mixed_scored': sum(r['mixed'] for r in scored), 'lost': sum('lost' in r for r in rows),
                    'pipeline': dict(collections.Counter(r['pipeline'] for r in rows)),
                    'reasons': dict(collections.Counter(r.get('reason') for r in rows if r.get('reason'))),
                    'reason_source': dict(collections.Counter(r['reason_source'] for r in rows
                                                              if 'reason_source' in r))},
        'scores': {'accuracy_scored': pct(right, len(scored)), 'coverage': pct(len(labelled), len(scored)),
                   'accuracy_labelled': pct(right, len(labelled)), 'accuracy_text': pct(text_right, len(ref_rows)),
                   'accuracy_saved': pct(saved_right, len(saved)), 'saved_lines': len(saved),
                   'saved_unlabelled': sum(1 for r in saved if r['saved_spk'] < 0)},
        'mapping': mapping,
        'clusters': [clusters[k] for k in sorted(clusters)],
        'unknown': {'by_reason': {k: dict(v) for k, v in by_reason.items()},
                    'ambiguous_pairs': dict(pairs),
                    'first_seq': min((r['seq'] for r in unknown), default=None),
                    'first_ambiguous_seq': min((r['seq'] for r in unknown if r.get('reason') == 'ambiguous'),
                                               default=None)},
        'near_threshold': {'within': NEAR, 'decisions': len(near),
                           'seqs': [r['seq'] for r in near]},
        'lag_ms': {'submit_to_label_median': med(r.get('lag_ms') for r in rows),
                   'submit_to_label_max': max((r['lag_ms'] for r in rows if r.get('lag_ms') is not None),
                                              default=None),
                   'capture_end_to_label_median': med(r.get('label_after_capture_end_ms') for r in rows)},
        'firmware': {'spk_end': sp['end'], 'drain': sp['drain']},
        'alignment': {k: (a.get('alignment') or {}).get(k) for k in
                      ('delta_ms', 'text_sim_median', 'low_sim_phrases', 'split_phrases', 'noise_phrases')},
    }
    if with_rows:
        out['rows'] = rows
    return out, man


def compare(dir_a, dir_b, min_new=32000):
    (A, man_a), (B, man_b) = summarise(dir_a, min_new, True), summarise(dir_b, min_new, True)
    warnings = []
    if man_a.get('wav_sha256') != man_b.get('wav_sha256'):
        warnings.append('the runs used different playlists')

    def by_clip(S):
        return {i: r for r in S['rows'] for i in r['clips']}

    def outcome(S, r, clip):
        if r is None:
            return 'no_phrase'
        if r['spk'] < 0:
            return 'unknown'
        return 'right' if S['mapping'].get(r['spk']) == clip['speaker'] else 'wrong'

    def brief(r, o):
        if r is None:
            return {'outcome': o}
        return {'outcome': o, 'seq': r['seq'], 'clips': r['clips'], 'spk': r['spk'], 'reason': r.get('reason'),
                'pipeline': r['pipeline'], 'created': r.get('created', False)}

    ca, cb = by_clip(A), by_clip(B)
    pairs, diffs, seg = collections.Counter(), [], []
    for c in man_a['clips']:
        ra, rb = ca.get(c['i']), cb.get(c['i'])
        oa, ob = outcome(A, ra, c), outcome(B, rb, c)
        pairs[f'{oa}/{ob}'] += 1
        segment_differs = (ra or {}).get('clips') != (rb or {}).get('clips')
        if segment_differs:
            seg.append(c['i'])
        if oa != ob or segment_differs:
            diffs.append({'clip': c['i'], 'speaker': c['speaker'], 'segment_differs': segment_differs,
                          'a': brief(ra, oa), 'b': brief(rb, ob)})

    def creations(S):
        return [{'label': c['label'], **c['created']} for c in S['clusters'] if 'created' in c]

    first = next((d['clip'] for d in diffs if d['a']['outcome'] != d['b']['outcome']), None)
    return {'a': A['session'], 'b': B['session'], 'warnings': warnings,
            'scores': {'a': A['scores'], 'b': B['scores']},
            'clips': len(man_a['clips']), 'outcome_pairs_a_b': dict(pairs),
            'first_outcome_divergence_clip': first, 'segmentation_differs_clips': seg,
            'creations': {'a': creations(A), 'b': creations(B)}, 'differences': diffs}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('sessions', nargs='+')
    ap.add_argument('--phrases', action='store_true', help='include one row per text phrase')
    ap.add_argument('--compare', action='store_true', help='compare exactly two runs of one playlist')
    ap.add_argument('--min-new-ms', type=int, default=2000,
                    help='minimum new-speaker phrase (speaker.spk; 2000 for export_final) for derived reasons')
    a = ap.parse_args()
    min_new = a.min_new_ms * 16
    if a.compare:
        if len(a.sessions) != 2:
            ap.error('--compare takes two session directories')
        print(json.dumps(compare(*a.sessions, min_new=min_new)))
        return
    for d in a.sessions:
        if not (Path(d) / 'analysis.json').exists():
            print(f'{d}: no analysis.json (run analyse.py first)', file=sys.stderr)
            continue
        print(json.dumps(summarise(d, min_new, a.phrases)[0]))


if __name__ == '__main__':
    main()
