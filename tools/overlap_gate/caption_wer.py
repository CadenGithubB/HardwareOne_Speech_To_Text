"""Caption accuracy on the P4: the device's own captions from the replay sessions vs the clip text,
against the same recognizer on the clean source audio.

For every playlist clip with a reference (night 1: AMI validation/test, LibriSpeech test, synthetic
suite, real AMI pairs; night 2: AMI train only, since its other clips are crops without text):
  device  the rawText of every final the P4 produced whose span lands on the clip (device stream
          samples -> WAV samples through the per-run alignment of replay_store.py), joined in order
  clean   the deployed int8 recognizer on the host, greedy CTC, on the clip exactly as played
          (before the speaker and room), in 20 s pieces like the device
Text is lower-cased, punctuation except apostrophes removed, and the fillers uh/um/hmm/mm/mhm/ah
removed on both sides. Word errors are counted as substitutions, deletions and insertions.
  p4pcm   the same host decoder on the P4's own saved segment PCM, mapped to clips like the device
          finals, so "clean" vs "p4pcm" differs only in the audio (same decoder, same LM)
Clean and p4pcm are decoded twice: greedy, and with the P4's word LM (meeting.lm, header params,
sentence-start context), the HW1LM1 host reference. The device itself decodes in streaming mode and
promotes most finals from a speculative draft, so its rawText is not bit-identical to an offline
host decode of the saved PCM; the host check (200 segments) measures that gap.
Writes phase4/caption-wer.json.
"""
from __future__ import annotations

import json
import random
import re
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overlap_gate import g2_common as g2  # noqa: E402

P4 = g2.LABELS / 'phase4'
FILLERS = {'uh', 'um', 'hmm', 'mm', 'mhm', 'ah', 'uhm', 'mmm', 'hm'}
LM_PATH = '/Volumes/Audiodrive/stt/overlap-gate/device-models/meeting.lm'
VOCAB = json.loads(Path('/Volumes/Audiodrive/stt/work/deploy15/export-gen2-25397/manifest.json').read_text())['vocabulary']
NIGHTS = {
    'night1': dict(runs=P4 / 'night1-runs', manifests=P4 / 'night1', split=g2.LABELS / 'phase5' / 'replay-split.json', card=P4 / 'night1-card' / 'pcm',
                   arms=('off', 'on')),
    'night2': dict(runs=P4 / 'night2-runs', manifests=P4 / 'night2', split=g2.LABELS / 'phase5' / 'replay2-split.json', card=P4 / 'night2-card' / 'pcm',
                   arms=('on',)),
}


def norm(text: str) -> list[str]:
    text = re.sub(r"[^a-z' ]", ' ', text.lower().replace('-', ' '))
    return [w for w in text.split() if w.strip("'") and w not in FILLERS]


def edit_ops(ref: list[str], hyp: list[str]):
    """(substitutions, deletions, insertions) of a minimum edit alignment."""
    n, m = len(ref), len(hyp)
    d = np.zeros((n + 1, m + 1), np.int32)
    d[:, 0] = np.arange(n + 1)
    d[0, :] = np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (ref[i - 1] != hyp[j - 1]))
    s = de = ins = 0
    i, j = n, m
    while i or j:
        if i and j and d[i, j] == d[i - 1, j - 1] + (ref[i - 1] != hyp[j - 1]):
            s += ref[i - 1] != hyp[j - 1]
            i, j = i - 1, j - 1
        elif i and d[i, j] == d[i - 1, j] + 1:
            de += 1
            i -= 1
        else:
            ins += 1
            j -= 1
    return int(s), int(de), int(ins)


def greedy(q: np.ndarray) -> str:
    blank = len(VOCAB)
    out, prev = [], None
    for t in q.argmax(axis=1):
        if t != prev and t < blank:
            out.append(VOCAB[t])
        prev = t
    return re.sub(' +', ' ', ''.join(out)).strip()


def device_finals(log: Path):
    finals, pcm = [], {}
    for l in log.read_text(errors='replace').splitlines():
        p = l.split('\t', 2)
        line = p[2] if len(p) == 3 else l
        if line.startswith('STT_EVENT ') and '"type":"final"' in line:
            j = json.loads(line[10:])
            finals.append(dict(seq=j['sequence'], raw=j.get('rawText', ''), s0=int(j['startSample']), s1=int(j['endSample'])))
        elif line.startswith('STT_PCM '):
            j = json.loads(line[8:])
            if j['captioned']:
                pcm[j['caption_sequence']] = j['file']
    return finals, pcm


def main():
    from overlap_gate.g0_extract import Recognizer
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'stt_train' / 'lm'))
    import hw1lm
    rec = Recognizer(g2.LABELS / 'phase4' / 'caption-cache')
    lm = hw1lm.read_lm(LM_PATH)

    def both(x):
        q = rec.logits(x)
        return greedy(q), hw1lm.decode_int8(q, rec.exponent, lm)
    rows, checks = [], []
    rng = random.Random(7)
    for night, cfg in NIGHTS.items():
        align = json.loads(cfg['split'].read_text())['alignment']
        events = [json.loads(l) for l in (cfg['runs'] / 'events.jsonl').read_text().splitlines() if '"run-done"' in l]
        clean_cache = {}
        for e in events:
            if e['arm'] not in cfg['arms'] or e['run'] not in align:
                continue
            m = json.loads((cfg['manifests'] / f"block{e['block']:02d}.json").read_text())
            with wave.open(m['wav']) as w:
                src = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2')
            shift = align[e['run']]['offset'] - align[e['run']]['lag']        # wav = device - shift
            finals, pcm_of = device_finals(cfg['runs'] / 'runs' / e['run'] / 'serial.log')
            folder = re.search(r'b0+\d+', e['pcm_ack'])[0]
            clips = [c for c in m['clips'] if c['category'] != 'noise-train' and (c.get('reference') or c['category'] == 'noise')]
            if night == 'night2':
                clips = [c for c in clips if c['category'] == 'ami-train']
            hyp = {c['index']: [] for c in clips}
            hostg = {c['index']: [] for c in clips}
            hostl = {c['index']: [] for c in clips}
            for f in finals:
                a, b = f['s0'] - shift, f['s1'] - shift
                best, cover = None, 0
                for c in clips:
                    ov = min(b, c['end_sample'] + 8000) - max(a, c['start_sample'] - 8000)
                    if ov > cover:
                        best, cover = c, ov
                hg = hl = ''
                if f['seq'] in pcm_of:
                    hg, hl = both(np.fromfile(cfg['card'] / folder / pcm_of[f['seq']], dtype='<i2'))
                    if len(checks) < 200 and rng.random() < 0.1:
                        checks.append(dict(device=f['raw'], host=hl, host_greedy=hg))
                if best is not None:
                    hyp[best['index']].append(f['raw'])
                    hostg[best['index']].append(hg)
                    hostl[best['index']].append(hl)
            for c in clips:
                key = (e['block'], c['index'])
                if key not in clean_cache:
                    clean_cache[key] = both(src[c['start_sample']:c['end_sample']])
                ref = norm(c.get('reference', ''))
                dev = norm(' '.join(hyp[c['index']]))
                cln, clm = norm(clean_cache[key][0]), norm(clean_cache[key][1])
                pg, pl = norm(' '.join(hostg[c['index']])), norm(' '.join(hostl[c['index']]))
                rows.append(dict(night=night, run=e['run'], arm=e['arm'], block=e['block'], clip=c['index'], category=c['category'], overlap=bool(c['label']),
                                 ref_words=len(ref), device=edit_ops(ref, dev), clean=edit_ops(ref, cln), clean_lm=edit_ops(ref, clm),
                                 p4pcm=edit_ops(ref, pg), p4pcm_lm=edit_ops(ref, pl), device_words=len(dev), clean_words=len(cln),
                                 device_empty=not dev, ref=' '.join(ref), device_text=' '.join(dev), clean_text=' '.join(cln),
                                 clean_lm_text=' '.join(clm), p4pcm_lm_text=' '.join(pl)))
            print(night, e['run'], 'clips', len(clips), flush=True)
    def gap(k):
        return dict(identical=sum(norm(c['device']) == norm(c[k]) for c in checks),
                    word_difference=sum(sum(edit_ops(norm(c['device']), norm(c[k]))) for c in checks) / max(1, sum(len(norm(c['device'])) for c in checks)))
    out = dict(host_device_check=dict(segments=len(checks), lm=gap('host'), greedy=gap('host_greedy'), examples=checks[:40]), rows=rows)
    (P4 / 'caption-wer.json').write_text(json.dumps(out) + '\n')
    print(json.dumps({k: v for k, v in out['host_device_check'].items() if k != 'examples'}))


if __name__ == '__main__':
    main()
