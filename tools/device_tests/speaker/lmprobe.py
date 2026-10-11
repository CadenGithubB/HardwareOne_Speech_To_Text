#!/usr/bin/env python3
"""Parse the c12 LM probe dump (TL lmp / TL lmd) of one or more sessions.

  lmprobe.py SESSION_DIR [...]     writes SESSION_DIR/lmprobe.npz + lmprobe.json, prints a summary

Each caption the device published from an LM decode has one TL lmp line (live decode time, idle replay
times with the cache evicted (cold) and warm, decoder work counters, CRC-32s of the device text, the replayed
text and the logits) and its int8 logits [frames x 29] in TL lmd lines (base64, 96 bytes per line, CRC-32 per
line, printed twice). A caption is complete when every chunk arrived intact in either pass and the whole
buffer matches dcrc. Numbers only, no transcript text.
"""
import base64
import json
import re
import sys
import zlib
from pathlib import Path

import numpy as np

LMP = re.compile(r'TL lmp seq=(\d+) k=(\w) id=(\d+) fr=(\d+) exp=(-?\d+) beam=(\d+) us=(\d+) cold_us=(\d+) '
                 r'warm_us=(\d+) nodes=(\d+) cand=(\d+) comp=(\d+) rnodes=(\d+) rcand=(\d+) rcomp=(\d+) st=(-?\d+) '
                 r'crc=([0-9a-f]{8}) rcrc=([0-9a-f]{8}) dcrc=([0-9a-f]{8})')
LMD = re.compile(r'TL lmd p=(\d) seq=(\d+) o=(\d+) ([A-Za-z0-9+/=]+) c=([0-9a-f]{8})')
LMLM = re.compile(r'TL lmp_lm (.*)$')
BEGIN = re.compile(r'TL lmp_begin (.*)$')
FIELDS = ['seq', 'kind', 'id', 'frames', 'exponent', 'beam', 'live_us', 'cold_us', 'warm_us', 'nodes', 'cand',
          'comp', 'rnodes', 'rcand', 'rcomp', 'status', 'crc', 'rcrc', 'dcrc']


def kv(text):
    out = {}
    for tok in text.split():
        if '=' in tok:
            k, v = tok.split('=', 1)
            try:
                out[k] = float(v) if '.' in v else int(v)
            except ValueError:
                out[k] = v
    return out


def parse(sdir):
    sdir = Path(sdir)
    raw = open(sdir / 'raw.log', errors='replace').read().replace('\r', '')
    heads, chunks, lm, begin = {}, {}, None, None
    bad_lines = 0
    for line in raw.splitlines():
        m = LMP.search(line)
        if m:
            g = m.groups()
            h = dict(zip(FIELDS, [int(g[0]), g[1]] + [int(x) for x in g[2:16]] + list(g[16:])))
            heads[h['seq']] = h
            continue
        m = LMD.search(line)
        if m:
            p, seq, off, b64, c = m.groups()
            try:
                data = base64.b64decode(b64, validate=True)
            except Exception:  # noqa: BLE001
                bad_lines += 1
                continue
            if f'{zlib.crc32(data):08x}' != c:
                bad_lines += 1
                continue
            chunks.setdefault(int(seq), {})[int(off)] = data
            continue
        m = LMLM.search(line)
        if m:
            lm = kv(m.group(1))
            continue
        m = BEGIN.search(line)
        if m:
            begin = kv(m.group(1))
    caps, arrays = [], {}
    for seq, h in sorted(heads.items()):
        n = h['frames'] * 29
        buf = bytearray(n)
        have = chunks.get(seq, {})
        complete = all(o in have for o in range(0, n, 96))
        if complete:
            for o, d in have.items():
                buf[o:o + len(d)] = d
            complete = f'{zlib.crc32(bytes(buf)):08x}' == h['dcrc']
        h['complete'] = complete
        h['replay_exact'] = h['crc'] == h['rcrc']
        if complete:
            arrays[f's{seq}'] = np.frombuffer(bytes(buf), dtype=np.int8).reshape(h['frames'], 29)
        caps.append(h)
    np.savez_compressed(sdir / 'lmprobe.npz', **arrays)
    info = {'begin': begin, 'lm': lm, 'bad_lines': bad_lines, 'captions': caps}
    (sdir / 'lmprobe.json').write_text(json.dumps(info, indent=1))
    return info


def main():
    for d in sys.argv[1:]:
        info = parse(d)
        caps = info['captions']
        ok = [c for c in caps if c['complete']]
        exact = sum(c['replay_exact'] for c in caps)
        print(f'{d}: begin {info["begin"]}; lm {info["lm"]}')
        print(f'  captions {len(caps)}, logits complete {len(ok)}, bad lmd lines {info["bad_lines"]}, '
              f'idle replay text identical {exact}/{len(caps)}')


if __name__ == '__main__':
    main()
