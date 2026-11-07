"""Oracle-gated recombination of frozen round-three outputs.

Per case: take the separator candidate's result where the *label* says overlap, the baseline
result everywhere else. This is the best any gate could deliver with that candidate; it costs no
inference. Inputs are the pinned results in experiment.json and are hash-checked before use.

Scores are the per-case oracle (source-assigned) word counts and the saved-microphone audit
counts. They are acoustic lower bounds, not stable-speaker scores, so the recombined totals are
comparable only with the baseline and candidate totals in the same view.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

OVERLAP_CONDITIONS = {'two-speakers', 'real-overlap'}


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_pinned(experiment, name, root: Path):
    pin = experiment['frozen_outputs_for_recombination'][name]
    path = root / pin['path']
    assert sha(path) == pin['sha256'], f'pinned file changed: {pin["path"]}'
    return json.loads(path.read_text())


def add(a, b):
    return {k: a.get(k, 0) + b.get(k, 0) for k in set(a) | set(b)}


def recombine_rows(baseline_rows, candidate_rows):
    """Per-case oracle gating over result rows with oracle_word_counts."""
    by_id = {r['id']: r for r in candidate_rows}
    totals = dict(baseline={}, candidate={}, oracle_gated={})
    by_condition = {}
    flagged = 0
    for b in baseline_rows:
        c = by_id[b['id']]
        assert c['condition'] == b['condition']
        overlap = b['condition'] in OVERLAP_CONDITIONS
        flagged += overlap
        chosen = c if overlap else b
        cond = by_condition.setdefault(b['condition'], dict(cases=0, baseline={}, candidate={}, oracle_gated={}))
        cond['cases'] += 1
        for key, row in (('baseline', b), ('candidate', c), ('oracle_gated', chosen)):
            totals[key] = add(totals[key], row['oracle_word_counts'])
            cond[key] = add(cond[key], row['oracle_word_counts'])
    return dict(cases=len(baseline_rows), flagged_cases=flagged, totals=totals, by_condition=by_condition)


def recombine_microphone(audit):
    """Saved-microphone audit: groups other than 'overlap' keep the baseline; 'overlap' takes the candidate."""
    out = dict(groups={}, totals={})
    for view in ('whole', 'captions'):
        base = cand = gated = 0
        words = 0
        for group, views in audit['groups'].items():
            if view not in views:
                continue
            x = views[view]
            b, c = x['baseline']['errors'], x['candidate']['errors']
            g = c if group == 'overlap' else b
            base += b
            cand += c
            gated += g
            words += x['baseline']['words']
            out['groups'].setdefault(group, {})[view] = dict(baseline=b, candidate=c, oracle_gated=g)
        out['totals'][view] = dict(words=words, baseline=base, candidate=cand, oracle_gated=gated)
    out['continuous'] = [dict(id=c['id'], baseline=c['baseline']['errors'], candidate=c['candidate']['counts']['errors']) for c in audit['continuous']]
    return out


def collateral(totals):
    """How much of the candidate's excess over baseline an oracle gate removes."""
    b, c, g = totals['baseline']['errors'], totals['candidate']['errors'], totals['oracle_gated']['errors']
    excess = c - b
    return dict(baseline=b, candidate=c, oracle_gated=g, candidate_excess=excess,
                removed_by_gate=c - g, remaining_excess=g - b,
                removed_fraction=round((c - g) / excess, 4) if excess > 0 else None)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', type=Path, default=Path('.'))
    ap.add_argument('--experiment', type=Path, default=Path('private/training-track/overlap-gate/experiment.json'))
    ap.add_argument('--out', type=Path, default=Path('private/training-track/overlap-gate/phase1/oracle-recombination.json'))
    args = ap.parse_args()
    exp = json.loads(args.experiment.read_text())
    report = dict(experiment_sha256=sha(args.experiment), candidates={}, scope=(
        'Oracle gate = label; candidate output on labelled-overlap cases, baseline elsewhere. Oracle source-assigned '
        'word counts (acoustic lower bound) for the synthetic qualification and real32 regression partitions; saved-'
        'microphone audit counts for the 163-case panel. Upper bound for gating with these candidates; not a gate result.'))
    base_q = load_pinned(exp, 'baseline_qualification', args.root)['rows']
    base_r = load_pinned(exp, 'baseline_regression', args.root)['rows']
    for cand in ('B1024', 'A4096'):
        q = recombine_rows(base_q, load_pinned(exp, f'{cand}_qualification', args.root)['rows'])
        r = recombine_rows(base_r, load_pinned(exp, f'{cand}_regression', args.root)['rows'])
        mic = recombine_microphone(load_pinned(exp, f'{cand}_saved_microphone_audit', args.root))
        report['candidates'][cand] = dict(
            qualification=dict(**q, collateral=collateral(q['totals'])),
            regression=dict(**r, collateral=collateral(r['totals'])),
            saved_microphone=dict(**mic, collateral={v: collateral({k: dict(errors=mic['totals'][v][k]) for k in ('baseline', 'candidate', 'oracle_gated')}) for v in mic['totals']}),
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    for cand, r in report['candidates'].items():
        print(cand)
        for part in ('qualification', 'regression'):
            print(f"  {part:14s}", {k: v for k, v in r[part]['collateral'].items()})
        for view, c in r['saved_microphone']['collateral'].items():
            print(f"  microphone {view:9s}", c)


if __name__ == '__main__':
    main()
