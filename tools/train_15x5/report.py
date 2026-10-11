#!/usr/bin/env python3
"""Write run15x5/REPORT.md: QuartzNet15x5 before/after vs the 5x5 (run2)."""
import json
import os
from pathlib import Path
STT_ROOT = Path(os.environ.get('STT_ROOT', 'stt-data'))  # data root: set STT_ROOT

WORK = (STT_ROOT / 'work')
RUN = Path(os.environ.get('RUN15X5', WORK / 'run15x5'))
MODEL = (STT_ROOT / 'models/quartznet15x5')
LITTLEFS_BYTES = 9.86e6
LM_BYTES = 2.5e6


def load(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def events(path):
    out = []
    try:
        for line in Path(path).read_text().splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    except OSError:
        pass
    return out


def pct(results, key):
    if not results or key not in results.get('results', {}):
        return '-'
    return f"{results['results'][key]['wer'] * 100:.1f}%"


def main():
    b5, f5 = load(WORK / 'baseline.json'), load(WORK / 'final.json')
    b15, f15 = load(RUN / 'baseline.json'), load(RUN / 'final.json')
    speed = load(RUN / 'speed.json')
    dl = load(MODEL / 'download.json') or {}
    ev15 = events(RUN / 'train.jsonl')
    ev5 = events(WORK / 'run2' / 'train.jsonl')

    lines = ['# QuartzNet15x5 vs QuartzNet5x5: like-for-like fine-tuning (run2 recipe)', '']
    lines += ['Greedy CTC WER on the full held-out test sets (no LM).', '',
              '| Test set | 5x5 original | 5x5 run2 (on P4) | 15x5 original | 15x5 fine-tuned |',
              '|---|---:|---:|---:|---:|']
    keys = list((f15 or b15 or f5 or {}).get('results', {}).keys()) or \
        ['ami-sdm-test', 'ami-ihm-test', 'librispeech-test-clean']
    for k in keys:
        lines.append(f'| {k} | {pct(b5, k)} | {pct(f5, k)} | {pct(b15, k)} | {pct(f15, k)} |')

    lines += ['', '## Training', '']
    fin15 = [e for e in ev15 if e.get('event') == 'finished']
    cfg15 = [e for e in ev15 if e.get('event') == 'config']
    evals15 = [e for e in ev15 if e.get('event') == 'eval']
    stops = [e for e in ev15 if e.get('event') in ('target_reached', 'deadline')]
    if cfg15:
        c = cfg15[-1]
        lines.append(f"- Recipe: run2's mix {c['mix']}, AdamW lr {c['lr']}, warmup 300, frozen BN stats, "
                     f"effective batch 110 s / 32 items as {c['accum']} micro-batches of "
                     f"{c['micro_seconds']:.1f} s / {c['micro_items']} items, target {c['target_hours']} audio hours.")
    if stops:
        lines.append(f"- Stopped by: {stops[-1]['event']} at step {stops[-1]['step']}, "
                     f"{stops[-1]['audio_hours']} audio hours.")
    if fin15:
        best = fin15[-1]['best']
        lines.append(f"- Best dev checkpoint: step {best['step']} (score {best['score']:.4f}); "
                     f"finished {fin15[-1]['time']} after {fin15[-1]['step']} optimizer steps.")
    rs = [e for e in ev15 if e.get('event') in ('rollback', 'memory_restart')]
    lines.append(f"- Rollbacks: {sum(e['event'] == 'rollback' for e in rs)}, "
                 f"memory restarts: {sum(e['event'] == 'memory_restart' for e in rs)}.")
    lines += ['', '### Dev curve (400 utts per set; score = mean WER)', '',
              '| Model | step | audio h | ami-sdm-val | ami-ihm-val | libri-dev-clean | score |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for tag, evs in (('5x5 run2', [e for e in ev5 if e.get('event') == 'eval']), ('15x5', evals15)):
        seen = set()
        for e in evs:
            if e['step'] in seen:
                continue
            seen.add(e['step'])
            cells = [f"{e[k] * 100:.1f}%" if k in e else '-' for k in
                     ('ami-sdm-validation', 'ami-ihm-validation', 'librispeech-dev-clean')]
            lines.append(f"| {tag} | {e['step']} | {e.get('audio_hours', '')} | {' | '.join(cells)} | "
                         f"{e['score']:.4f} |")

    lines += ['', '## Cost', '']
    if speed:
        lines += [f"Acoustic model only, one utterance at a time on the M1 CPU "
                  f"({speed['utterances']} dev utterances, {speed['audio_seconds']} s of audio).", '',
                  '| Model | params | CPU s per audio s (1 thread) | CPU s per audio s (all threads, wall) | int8 size estimate |',
                  '|---|---:|---:|---:|---:|']
        for name, m in speed['models'].items():
            one = m.get('threads_1', {}).get('cpu_s_per_audio_s', '-')
            multi = [v for k, v in m.items() if k.startswith('threads_') and k != 'threads_1']
            multi = multi[0]['wall_s_per_audio_s'] if multi else '-'
            size = m.get('int8_bytes_estimate')
            lines.append(f"| {name} | {m['params'] / 1e6:.1f} M | {one} | {multi} | "
                         f"{size / 1e6:.1f} MB |" if size else f"| {name} | {m['params'] / 1e6:.1f} M | {one} | {multi} | - |")
        lines += ['', f"P4 fit: LittleFS is {LITTLEFS_BYTES / 1e6:.2f} MB and currently holds the 5.5 MB 5x5 "
                  f"model + {LM_BYTES / 1e6:.1f} MB LM. The int8 estimate is the deployed 5x5 file scaled by "
                  "BN-folded parameter count, so the 15x5 does not fit as is (it would need a bigger "
                  "partition/SD card or much heavier compression), and it costs ~3x the compute per second of audio."]

    lines += ['', '## Provenance', '',
              f"- Checkpoint: {dl.get('url', '?')}",
              f"- sha256 {dl.get('sha256', '?')}, {dl.get('bytes', '?')} bytes (QuartzNet15x5Base-En, NGC "
              "nvidia/nemospeechmodels 1.0.0a5, same listing as the 5x5 QuartzNet5x5LS-En; trained on "
              "LibriSpeech, Common Voice, WSJ, Fisher, Switchboard, NSC).",
              '- Code: experiments/stt_train_15x5 (copy of experiments/stt_train with run2 mix, '
              'audio-hour budget, gradient accumulation).']

    for name, res in (('15x5 fine-tuned', f15),):
        if res:
            lines += ['', f'## Example transcripts ({name})', '']
            for k, r in res['results'].items():
                lines.append(f'### {k}')
                for e in r.get('examples', []):
                    lines.append(f"- ref: {e['ref']}\n  hyp: {e['hyp']}")
    (RUN / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines[:12]))


if __name__ == '__main__':
    main()
