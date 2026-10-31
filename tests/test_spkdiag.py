#!/usr/bin/env python3
"""Run spkeval.py and spkdiag.py on synthetic sessions shaped like the repeated conversation.

Two speakers alternate over 43 clips. Run A merges a short turn with the next speaker's turn; that mixed
phrase starts a third cluster and 16 later phrases of the second speaker are ambiguous between it and
their own cluster; the last phrase is refused for audio pressure and the last three saved lines carry no
label. Run B merges a different pair without a new cluster, has two short no-match unknowns and an embed
failure, and has no TL spk_match lines (reasons are derived). Log lines use the HardwareOne 0.99.99
formats. This checks the scorers' bookkeeping, not the device or the model.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools/device_tests/speaker'
sys.path.insert(0, str(TOOLS))
import spkdiag  # noqa: E402
import spkeval  # noqa: E402

A_SPK, X_SPK = 101, 202
TH = 0.50


def playlist(n=43, short=(4, 30)):
    clips, t = [], 6.0
    for i in range(n):
        d = 1.2 if i in short else 3.0
        clips.append({'i': i, 'speaker': (A_SPK, X_SPK)[i % 2], 'start_s': round(t, 3), 'end_s': round(t + d, 3),
                      'speech_start_s': round(t + 0.1, 3), 'speech_end_s': round(t + d - 0.1, 3)})
        t += d + 1.5
    return {'wav_sha256': 'f' * 64, 'clips': clips}


def spk(seq, label, sim, new, samples, lag=1800):
    return (f'TL spk seq={seq} spk={label} sim={sim:.3f} new={new} tent={int(label < 0)} samples={samples} '
            f'fe_us=20000 nn_us=1500000 head_us=3000 us=1700000 lag_ms={lag}')


def match(seq, before, after, best, bsim, second, ssim, matches, updated, reason, samples):
    return (f'TL spk_match seq={seq} profiles_before={before} profiles_after={after} best={best} '
            f'best_sim={bsim:.3f} second={second} second_sim={ssim:.3f} matches={matches} updated={updated} '
            f'reason={reason} phrase_samples={samples}')


def decision(seq, kind, label, profiles, samples=60800):
    """(TL spk, TL spk_match) for one clustering decision."""
    if kind == 'new':
        best, bsim = (0, 0.41) if profiles else (-1, 0.0)
        return spk(seq, label, 1.0, 1, samples), match(seq, profiles, profiles + 1, best, bsim, -1, 0.0, 0, 0,
                                                        'new', samples)
    if kind == 'match':
        return spk(seq, label, 0.78, 0, samples), match(seq, profiles, profiles, label, 0.78, 0 if label else 1,
                                                         0.30, 1, 1, 'match', samples)
    if kind == 'ambiguous':
        return spk(seq, -1, 0.74, 0, samples), match(seq, profiles, profiles, 1, 0.74, 2, 0.69, 2, 0,
                                                      'ambiguous', samples)
    if kind == 'no_match_short':
        return spk(seq, -1, 0.44, 0, 28000), match(seq, profiles, profiles, 1, 0.44, 0, 0.20, 0, 0,
                                                    'no_match_short', 28000)
    raise ValueError(kind)


def write_session(root, name, man_path, man, plan, keep_match, end):
    """plan: (clip indices, outcome) per phrase in order; outcome is a decision tuple or a pipeline event."""
    d = root / name
    d.mkdir()
    clips = man['clips']
    lines = [(0, 'rst:0x17 (CHIP_USB_UART_RESET),boot:0x308 (SPI_FAST_FLASH_BOOT)'),
             (900, f'I (900) STT: TL spk_load ok=1 why=none bytes=3000000 psram_used=3348240 int_used=12288 '
                   f'ms=900 th={TH:.2f} fixture_cos=-2.0000 psram_free=6000000')]
    phrases = []
    for seq, (members, outcome, saved) in enumerate(plan, start=1):
        s0, s1 = clips[members[0]]['start_s'] - 0.3, clips[members[-1]]['end_s'] + 0.7
        a0, a1 = round(10000 + 1000 * s0), round(10000 + 1000 * s1)
        phrases.append({'seq': seq, 'span_play_s': [round(s0, 3), round(s1, 3)], 'clips': list(members),
                        'a0': a0, 'a1': a1, 'kind': 'pause', 'audio_s': round(s1 - s0, 3)})
        t = a1 + 1300
        emit = [f'TL pub seq={seq} t={t}']
        if outcome == 'refused':
            emit.append(f'TL spk_submit seq={seq} admitted=0 spk=-1 wait_ms=0 reason=audio_pressure')
        elif outcome == 'failed':
            emit.append(f'TL spk seq={seq} spk=-1 fail=1')
        else:
            emit.append(f'TL spk_submit seq={seq} admitted=1 wait_ms=0 backlog=1')
            spk_line, match_line = outcome
            emit.append(spk_line.replace('seq=0 ', f'seq={seq} '))
            if keep_match:
                emit.append(match_line.replace('seq=0 ', f'seq={seq} '))
        label = int(outcome[0].split(' spk=')[1].split()[0]) if isinstance(outcome, tuple) else -1
        emit.append(f'TL tsave seq={seq} spk={label} labelled={int(saved)} wait_ms=1900')
        for k, text in enumerate(emit):
            tick = t + (1800 if 'spk' in text and 'submit' not in text else 0) + k
            lines.append((tick, f'I ({tick}) STT: {text}'))
    tick = lines[-1][0] + 2000
    lines.append((tick, f'I ({tick}) STT: TL spk_drain wait_ms=0 outcome=complete pending=0'))
    lines.append((tick + 1, f'I ({tick + 1}) STT: TL spk_end {end}'))
    lines.sort(key=lambda x: x[0])
    with open(d / 'lines.tsv', 'w') as fh:
        for tick, text in lines:
            fh.write(f'{tick / 1000:.4f}\t{1.7e9 + tick / 1000:.4f}\t{text}\n')
    (d / 'session.json').write_text(json.dumps({'manifest': str(man_path), 'status': 'ok', 'label': 'synthetic'}))
    (d / 'analysis.json').write_text(json.dumps({
        'phrases': phrases, 'clock': {'tick_minus_esp_ms': 0},
        'alignment': {'delta_ms': 0, 'text_sim_median': 0.9, 'low_sim_phrases': 0, 'split_phrases': 2,
                      'noise_phrases': 0}}))
    return d


def groups(n, merged):
    out, i = [], 0
    while i < n:
        out.append([i, i + 1] if i == merged else [i])
        i += 2 if i == merged else 1
    return out


def run_a_plan():
    plan, profiles = [], 0
    for members in groups(43, 4):
        first, who = members[0], (A_SPK, X_SPK)[members[-1] % 2] if len(members) > 1 else (A_SPK, X_SPK)[members[0] % 2]
        if first == 42:
            plan.append((members, 'refused', False))
            continue
        if first in (0, 1):
            out = decision(0, 'new', first, profiles); profiles += 1
        elif members == [4, 5]:
            out = decision(0, 'new', 2, profiles); profiles += 1
        elif who == A_SPK:
            out = decision(0, 'match', 0, profiles)
        elif 7 <= first <= 37:
            out = decision(0, 'ambiguous', -1, profiles)
        else:
            out = decision(0, 'match', 1, profiles)
        plan.append((members, out, first not in (40, 41)))
    return plan


def run_b_plan():
    plan, profiles = [], 0
    for members in groups(43, 30):
        first, last = members[0], members[-1]
        if first == 42:
            plan.append((members, 'failed', False))
            continue
        if first in (0, 1):
            out = decision(0, 'new', first, profiles); profiles += 1
        elif first in (7, 9):
            out = decision(0, 'no_match_short', -1, profiles)
        else:
            out = decision(0, 'match', last % 2, profiles)
        plan.append((members, out, True))
    return plan


def main():
    with tempfile.TemporaryDirectory(prefix='hw1-spkdiag-') as tmp:
        root = Path(tmp)
        man = playlist()
        man_path = root / 'manifest.json'
        man_path.write_text(json.dumps(man))
        a = write_session(root, '2026-a', man_path, man, run_a_plan(), True, 'submitted=42 labelled=41 skipped=1')
        b = write_session(root, '2026-b', man_path, man, run_b_plan(), False, 'submitted=42 labelled=41 skipped=12')

        # spkeval.py: the published numbers, now with real-cluster counts and parsed totals.
        ea, eb = spkeval.score(a), spkeval.score(b)
        assert (ea['accuracy'], ea['phrases_scored'], ea['labels_logged']) == (58.5, 41, 41), ea
        assert (eb['accuracy'], eb['phrases_scored'], eb['labels_logged']) == (95.1, 41, 41), eb
        assert (ea['speakers_found'], ea['unknown_scored'], ea['speakers_true']) == (3, 16, 2), ea
        assert (eb['speakers_found'], eb['unknown_scored']) == (2, 2), eb
        assert ea['skipped'] == 1 and eb['skipped'] == 0, (ea['skipped'], eb['skipped'])
        assert eb['spk_end'] == {'submitted': 42, 'labelled': 41, 'skipped': 12}, eb['spk_end']
        assert spkeval.spk_end('no totals') is None

        # spkdiag.py, run A: coverage, not confusion; the mixed phrase seeded the third cluster.
        sa = spkdiag.summarise(a, with_rows=True)[0]
        sc = sa['scores']
        assert (sc['accuracy_scored'], sc['coverage'], sc['accuracy_labelled']) == (58.5, 61.0, 96.0), sc
        assert sc['accuracy_text'] == round(100 * 24 / 42, 1), sc
        assert (sc['saved_lines'], sc['saved_unlabelled']) == (42, 19), sc
        assert sa['threshold'] == TH and sa['phrases']['pipeline'] == {'labelled': 41, 'refused:audio_pressure': 1}
        assert sa['unknown']['by_reason'] == {'ambiguous': {X_SPK: 16}, 'refused:audio_pressure': {A_SPK: 1}}, sa
        assert sa['unknown']['ambiguous_pairs'] == {'1/2': 16} and sa['unknown']['first_ambiguous_seq'] == 7
        third = sa['clusters'][2]
        assert third['maps_to'] is None and third['phrases'] == 1, third
        assert third['created']['clips'] == [4, 5] and third['created']['mixed'], third
        assert third['created']['below_threshold_by'] == round(TH - 0.41, 3), third
        assert sa['phrases']['reason_source'] == {'spk_match': 41} and sa['phrases']['mixed'] == 1
        assert sa['firmware']['drain']['outcome'] == 'complete'
        assert sa['lag_ms']['submit_to_label_median'] == 1800

        # Run B: reasons derived from TL spk and the load threshold; the failure is not a decision.
        sb = spkdiag.summarise(b)[0]
        assert (sb['scores']['coverage'], sb['scores']['accuracy_labelled']) == (95.1, 100.0), sb['scores']
        assert sb['unknown']['by_reason'] == {'no_match_short': {X_SPK: 2}, 'failed': {A_SPK: 1}}, sb['unknown']
        assert sb['phrases']['reason_source'] == {'derived': 41}
        assert [c['created']['clips'] for c in sb['clusters']] == [[0], [1]]

        # Clip by clip: the runs part at the merged turn, and the creation is located on the playlist.
        cmp = spkdiag.compare(a, b)
        assert cmp['first_outcome_divergence_clip'] == 4, cmp['first_outcome_divergence_clip']
        assert cmp['segmentation_differs_clips'] == [4, 5, 30, 31], cmp['segmentation_differs_clips']
        assert cmp['outcome_pairs_a_b']['unknown/right'] == 14, cmp['outcome_pairs_a_b']
        assert cmp['outcome_pairs_a_b']['unknown/unknown'] == 3, cmp['outcome_pairs_a_b']
        assert [c['clips'] for c in cmp['creations']['a']] == [[0], [1], [4, 5]] and not cmp['warnings']

        # The command line prints JSON only.
        out = subprocess.run([sys.executable, str(TOOLS / 'spkdiag.py'), '--compare', str(a), str(b)],
                             check=True, capture_output=True, text=True).stdout
        assert json.loads(out)['first_outcome_divergence_clip'] == 4
        out = subprocess.run([sys.executable, str(TOOLS / 'spkdiag.py'), '--phrases', str(a), str(b)],
                             check=True, capture_output=True, text=True).stdout.splitlines()
        assert len(out) == 2 and len(json.loads(out[0])['rows']) == 42
    print('spkdiag: synthetic sessions ok')


if __name__ == '__main__':
    main()
