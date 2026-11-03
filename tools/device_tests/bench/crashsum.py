#!/usr/bin/env python3
"""One line per serial log: how each run ended and the crash signature. Numbers and PCs only.

  crashsum.py DIR [DIR ...] > night-summary.txt

Outcome: clean, or the first crash marker (Guru kind, CORRUPT HEAP, abort, watchpoint/breakpoint,
reset without panic). For a Guru: core, MEPC, RA, A0, A1, A2, MTVAL, MCAUSE, plus the last TL spk_end /
TL fe_end and stt start device times (ms) to place the crash in the session, and any TL watchhdr line.
A tripwire capture-N.txt in the folder is noted.
"""
import re, sys
from pathlib import Path

REG = re.compile(r'\b(MEPC|RA|A0|A1|A2|MTVAL|MCAUSE)\s*:\s*(0x[0-9a-f]+)')


def stamp(line):
    m = re.search(r'\[\s*(\d+)\]', line)
    return int(m.group(1)) if m else None


def summarize(path):
    lines = path.read_text(errors='replace').splitlines()
    out = {'file': f'{path.parent.name}/{path.name}'}
    start = end_marks = None
    for i, l in enumerate(lines):
        if 'stt start -> OK' in l and start is None:
            out['stt_start'] = stamp(l)
        if 'TL spk_end' in l or 'TL fe_end' in l:
            out['teardown'] = stamp(l)
        if 'TL watchhdr' in l:
            out['watchhdr'] = re.sub(r'.*TL watchhdr ', '', l).strip()
        if 'CORRUPT HEAP' in l and 'event' not in out:
            out['event'] = 'CORRUPT HEAP ' + re.sub(r'.*CORRUPT HEAP: ', '', l).strip()
        m = re.search(r"Guru Meditation Error: Core\s+(\d) panic'ed \(([^)]*)\)", l)
        if m and 'guru' not in out:
            out['guru'] = f'core{m.group(1)} {m.group(2)}'
            regs = {}
            for l2 in lines[i:i + 14]:
                for k, v in REG.findall(l2):
                    regs.setdefault(k, v)
            out['regs'] = ' '.join(f'{k}={v}' for k, v in regs.items())
        if 'abort() was called' in l and 'abort' not in out:
            out['abort'] = re.sub(r'.*abort\(\) was called', 'abort()', l).strip()
        if 'no panic record' in l:
            out.setdefault('note', []).append('no-panic-record line at boot')
    caps = sorted(p.name for p in path.parent.glob('capture-*.txt'))
    if caps:
        out['captures'] = caps
    if not any(k in out for k in ('guru', 'abort', 'event')):
        out['outcome'] = 'no crash marker'
    return out


for d in map(Path, sys.argv[1:]):
    for f in sorted(d.glob('serial-*.log')):
        print(summarize(f))
