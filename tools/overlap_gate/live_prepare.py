"""Prepare a live overlap session: cue schedule, reading prompts and the recorded voice clips.

Trials (one per cue window; 2.5 s "get ready" with the text shown, 10 s "go", 3.5 s quiet so the
P4 closes a segment):
  solo mode  you     you read the prompt aloud                         label: one speaker
             voice   the Mac plays a recorded voice, you stay quiet    label: one speaker (alignment anchor)
             both    the Mac plays a voice and you read over it        label: overlap
  pair mode  a, b    person A or B reads                               label: one speaker
             both    A and B read different prompts at the same time   label: overlap
             voice   a few recorded-voice anchors for clock alignment  label: one speaker
Recorded voices are LibriSpeech test-clean utterances of 6-10 s (evaluation material, never trained),
levelled to -26 dBFS. Prompts are transcripts of other test-clean utterances, 18-32 words.

  live_prepare.py --mode solo|pair    writes /Volumes/Audiodrive/stt/overlap-gate/live1/ (WAVs) and
                                      phase4/live1/schedule.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overlap_gate.night_playlists import Store, level, SR  # noqa: E402

OUT = Path('/Volumes/Audiodrive/stt/overlap-gate/live1')
SCHED = Path(__file__).resolve().parents[2] / 'private/training-track/overlap-gate/phase4/live1'
SEED = 20261108
READY_S, GO_S, QUIET_S = 2.5, 10.0, 3.5
PLAN = {'solo': dict(you=24, voice=24, both=30), 'pair': dict(a=20, b=20, both=30, voice=6)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--mode', choices=sorted(PLAN), default='solo')
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    SCHED.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    ls = Store('librispeech-test-clean')
    ids = list(ls.ids)
    rng.shuffle(ids)
    plan = PLAN[args.mode]
    n_voice = plan.get('voice', 0) + plan.get('both', 0) * (args.mode == 'solo')
    voices, used_speakers = [], set()
    for i in ids:
        n = ls.index['lengths'][i]
        if 6 * SR <= n <= 10 * SR:
            voices.append(i)
            used_speakers.add(ls.index['speakers'][i])
        if len(voices) == n_voice:
            break
    taken = set(voices)
    prompts = []
    for i in ids:
        words = ls.index['texts'][i].split()
        if i not in taken and 18 <= len(words) <= 32:
            t = ls.index['texts'][i].lower()
            prompts.append(t[0].upper() + t[1:] + '.')
    clips = {}
    for i in voices:
        x, gain = level(ls.pcm(i), 'ls-test')
        p = OUT / f'voice-{i}.wav'
        with wave.open(str(p), 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype('<i2').tobytes())
        clips[i] = dict(wav=str(p), source=f'librispeech-test-clean:{i}', seconds=round(x.size / SR, 3), gain_db=round(gain, 2),
                        speaker=ls.index['speakers'][i], text=ls.index['texts'][i])
    kinds = [k for k, n in plan.items() for _ in range(n)]
    rng.shuffle(kinds)
    trials, vi, pi = [], iter(voices), iter(prompts)
    for k, kind in enumerate(kinds):
        t = dict(index=k, kind=kind)
        if kind in ('voice',) or (kind == 'both' and args.mode == 'solo'):
            t['voice'] = clips[next(vi)]
        if kind in ('you', 'a', 'both'):
            t['prompt_a'] = next(pi)
        if kind == 'b' or (kind == 'both' and args.mode == 'pair'):
            t['prompt_b'] = next(pi)
        t['label_overlap'] = kind == 'both'
        trials.append(t)
    sched = dict(mode=args.mode, seed=SEED, ready_s=READY_S, go_s=GO_S, quiet_s=QUIET_S, trials=trials,
                 minutes=round(len(trials) * (READY_S + GO_S + QUIET_S) / 60, 1))
    (SCHED / 'schedule.json').write_text(json.dumps(sched, indent=1) + '\n')
    print(json.dumps(dict(mode=args.mode, trials=len(trials), kinds={k: kinds.count(k) for k in plan}, minutes=sched['minutes'])))


if __name__ == '__main__':
    main()
