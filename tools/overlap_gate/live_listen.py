"""Listening page for the live session: random saved P4 segments per trial type, with their levels.

Copies the session's PCM from the card to the Audiodrive (once), maps each segment to its trial
(rough log-time mapping; good enough to pick examples), and writes WAVs: each segment as captured,
plus a copy normalised to -26 dBFS so its content can be heard even if the capture is quiet. For
reference it adds one of night 1's replay segments and the source voice clip of one voice trial.
Serves the page on http://127.0.0.1:8770.
"""
from __future__ import annotations

import http.server
import json
import random
import shutil
import subprocess
import sys
import wave
from functools import partial
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / 'private/training-track/overlap-gate/phase4/live1-runs'
CARD_SRC = Path('/Volumes/NO NAME/STT PCM')
COPY = Path('/Volumes/Audiodrive/stt/overlap-gate/live1-card/pcm')
LISTEN = Path('/Volumes/Audiodrive/stt/overlap-gate/live1-listen')
NIGHT1 = Path('/Volumes/Audiodrive/stt/overlap-gate/night1-card/pcm/b000074')


def dbfs(x):
    return 20 * np.log10(np.sqrt(np.mean((x / 32768.0) ** 2)) + 1e-12)


def write(path, x):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(np.clip(x, -32768, 32767).astype('<i2').tobytes())


def main():
    folder = json.loads([l for l in (RUNS / 'events.jsonl').read_text().splitlines() if '"armed"' in l][0])['pcm_ack'].split('folder=/sd/STT PCM/')[1].split()[0]
    if not (COPY / folder).exists():
        COPY.mkdir(parents=True, exist_ok=True)
        subprocess.run(['rsync', '-a', '--exclude', '._*', f'{CARD_SRC / folder}/', f'{COPY / folder}/'], check=True)
        subprocess.run(['diff', '-rq', '-x', '._*', str(CARD_SRC / folder), str(COPY / folder)], check=True)
    trials = [json.loads(l) for l in (RUNS / 'events.jsonl').read_text().splitlines() if '"kind": "trial"' in l]
    segs = []
    for l in (RUNS / 'serial.log').read_text(errors='replace').splitlines():
        p = l.split('\t', 2)
        if len(p) == 3 and p[2].startswith('STT_PCM '):
            j = json.loads(p[2][8:])
            j['mono'] = float(p[1])
            segs.append(j)
    rows = []
    for j in segs:
        t0 = j['mono'] - j['samples'] / 16000 - 1.5
        best = max(trials, key=lambda t: min(t['go_end_mono'] + 1, j['mono']) - max(t['go_mono'] - 0.5, t0))
        ov = min(best['go_end_mono'] + 1, j['mono']) - max(best['go_mono'] - 0.5, t0)
        x = np.fromfile(COPY / folder / j['file'], dtype='<i2').astype(np.float64)
        rows.append(dict(file=j['file'], kind=best['trial_kind'] if ov > 0 else 'between trials', trial=best['index'] + 1, seconds=round(x.size / 16000, 1),
                         rms=round(dbfs(x), 1), peak=round(20 * np.log10(np.abs(x).max() / 32768 + 1e-12), 1), x=x))
    if LISTEN.exists():
        shutil.rmtree(LISTEN)
    LISTEN.mkdir(parents=True)
    rng = random.Random()
    picks = []
    for kind in ('both', 'you', 'voice'):
        pool = [r for r in rows if r['kind'] == kind]
        picks += rng.sample(pool, min(3, len(pool)))
    cards = []
    for r in picks:
        x = r['x']
        write(LISTEN / f"{r['file']}.wav", x)
        g = 10 ** ((-26 - r['rms']) / 20)
        write(LISTEN / f"{r['file']}-loud.wav", np.clip(x * g, -32767, 32767))
        cards.append(r)
    ref = sorted(NIGHT1.glob('s*.pcm'))[5]
    xr = np.fromfile(ref, dtype='<i2').astype(np.float64)
    write(LISTEN / 'night1.wav', xr)
    voice = next(t for t in trials if t['trial_kind'] == 'voice')['voice']
    shutil.copy(voice, LISTEN / 'source-voice.wav')
    with wave.open(voice) as w:
        xs = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(np.float64)
    names = {'both': 'You reading over the Mac voice (overlap)', 'you': 'You reading alone', 'voice': 'Mac voice alone (you quiet)'}
    levels = np.array([r['rms'] for r in rows])
    html = ['<!doctype html><meta charset=utf-8><title>Live session: listen</title><style>body{font-family:-apple-system,system-ui;margin:28px;max-width:860px}'
            '@media(prefers-color-scheme:dark){body{background:#1a1a19;color:#f0efec}}h2{font-weight:500;font-size:19px;margin:26px 0 8px}'
            '.r{display:grid;grid-template-columns:150px 1fr 1fr;gap:12px;align-items:center;margin:8px 0;font-size:14px}.m{color:#898781;font-size:13px}audio{width:100%}</style>',
            f'<p class=m>All {len(rows)} saved segments: median level {np.median(levels):.1f} dBFS (quietest {levels.min():.1f}, loudest {levels.max():.1f}). '
            f'Night 1 replay segments were about -61 dBFS; the AMI recordings the gate learned from are about -43; a clean close recording is about -26.</p>',
            '<div class="r m"><span></span><span>As the P4 captured it</span><span>Boosted to -26 dBFS (to hear the content)</span></div>']
    for kind in ('both', 'you', 'voice'):
        html.append(f'<h2>{names[kind]}</h2>')
        for r in [c for c in cards if c['kind'] == kind]:
            html.append(f"<div class=r><span>Trial {r['trial']} · {r['seconds']} s<br><span class=m>{r['rms']} dBFS, peak {r['peak']}</span></span>"
                        f"<audio controls preload=none src='{r['file']}.wav'></audio><audio controls preload=none src='{r['file']}-loud.wav'></audio></div>")
    html.append('<h2>For comparison</h2>')
    html.append(f"<div class=r><span>Night 1 replay segment<br><span class=m>{dbfs(xr):.1f} dBFS</span></span><audio controls preload=none src='night1.wav'></audio><span></span></div>")
    html.append(f"<div class=r><span>Original voice file the Mac played<br><span class=m>{dbfs(xs):.1f} dBFS</span></span><audio controls preload=none src='source-voice.wav'></audio><span></span></div>")
    (LISTEN / 'index.html').write_text('\n'.join(html))
    summary = {k: dict(n=sum(1 for r in rows if r['kind'] == k), median_dbfs=float(np.median([r['rms'] for r in rows if r['kind'] == k])))
               for k in ('both', 'you', 'voice', 'between trials') if any(r['kind'] == k for r in rows)}
    print(json.dumps(dict(folder=folder, segments=len(rows), median_dbfs=float(np.median(levels)), by_kind=summary)), flush=True)
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(LISTEN))
    http.server.ThreadingHTTPServer(('127.0.0.1', 8770), handler).serve_forever()


if __name__ == '__main__':
    sys.exit(main())
