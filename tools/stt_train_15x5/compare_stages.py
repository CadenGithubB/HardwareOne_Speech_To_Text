#!/usr/bin/env python3
"""Pair the SAME audio through float, frozen int8, LM and measured streaming.

Inputs are stage JSON reports with schema=1, stage, provenance, records. Missing
stages require --allow-incomplete. A streaming report must identify its capture
and reference alignment; concatenating unrelated device captions is not valid.
"""
import argparse
import json
from pathlib import Path
from diagnostics import atomic_json, error_counts, summarize, paired_changes

STAGES = ('float', 'int8', 'lm', 'streaming')


def stage_report(stage, provenance, records):
    if stage not in STAGES:
        raise ValueError('Unknown recognition stage')
    if not provenance.get('weights_sha256'):
        raise ValueError('Stage needs acoustic weights identity')
    if stage != 'float' and not provenance.get('espdl_sha256'):
        raise ValueError('Quantized stages need exported model identity')
    if stage in ('lm', 'streaming') and not provenance.get('lm_sha256'):
        raise ValueError('Decoder stages need LM identity')
    seen = set()
    normalized = []
    for row in records:
        if row['id'] in seen or not row.get('pcm_sha256') or not row.get('seconds', 0) > 0:
            raise ValueError('Missing audio identity/duration or duplicate utterance')
        if stage == 'streaming' and (not row.get('capture_sha256') or row.get('alignment_passed') is not True):
            raise ValueError('Streaming records need a capture hash and passed reference alignment')
        seen.add(row['id'])
        normalized.append({**row, **error_counts(row['ref'], row['hyp'])})
    if not normalized:
        raise ValueError('Empty stage report')
    return {'schema': 1, 'stage': stage, 'provenance': provenance, 'records': normalized,
            'summary': summarize(normalized)}


def compare(reports, allow_incomplete=False):
    by_stage = {}
    for report in reports:
        validated = stage_report(report['stage'], report['provenance'], report['records'])
        stage = validated['stage']
        if stage in by_stage:
            raise ValueError('Duplicate stage: ' + stage)
        by_stage[stage] = validated
    missing = [s for s in STAGES if s not in by_stage]
    if missing and not allow_incomplete:
        raise ValueError('Missing stages: ' + ', '.join(missing))
    if not by_stage:
        raise ValueError('No stage reports')
    for field in ('weights_sha256', 'espdl_sha256', 'lm_sha256', 'frontend_sha256'):
        values = {r['provenance'][field] for r in by_stage.values() if r['provenance'].get(field)}
        if len(values) > 1:
            raise ValueError('Stage provenance differs: ' + field)
    first = next(iter(by_stage.values()))
    for r in by_stage.values():
        paired_changes(first['records'], r['records'])
    transitions = {}
    for before, after in zip(STAGES, STAGES[1:]):
        if before in by_stage and after in by_stage:
            a, b = by_stage[before], by_stage[after]
            transitions[f'{before}->{after}'] = {
                **paired_changes(a['records'], b['records']),
                'errors_delta': b['summary']['errors']-a['summary']['errors']}
    return {'schema': 1, 'complete': not missing, 'missing_stages': missing,
            'scope': 'Paired observations; deltas localize changes, not causal proof or device qualification',
            'stages': by_stage, 'transitions': transitions}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage', type=Path, action='append', required=True)
    p.add_argument('--allow-incomplete', action='store_true')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    report = compare([json.loads(p.read_text()) for p in a.stage], a.allow_incomplete)
    atomic_json(a.output, report)
    print(json.dumps({'complete': report['complete'], 'missing_stages': report['missing_stages'],
                      'summaries': {k:v['summary'] for k,v in report['stages'].items()}}))


if __name__ == '__main__':
    main()
