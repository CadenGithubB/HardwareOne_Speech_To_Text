"""Parse P4 console lines (stdlib only, Python 3.9+).

ESP-IDF log lines look like  'I (50407) STT: TL seg=1 a0=43527 a1=48637 ...'
(optionally wrapped in ANSI colour codes). '(N)' is the FreeRTOS tick at print
time (ms), not the event time; event times are the t=/q=/s=/e= fields
(esp_timer ms since boot).

TL line naming: the first token after 'TL' is the line kind. If it is a
key=value token (TL seg=3 ...) the kind is the key and its value is kept as
'id'. 'TL txt seq=<n> <text>' keeps the text separately (never printed).
"""
import re

ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
LOG = re.compile(r'^([IWEDV]) \((\d+)\) ([^:]{1,32}): (.*)$')
KV = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)=(-?\d+(?:\.\d+)?)([A-Za-z%]*)$')
ROM_BOOT = re.compile(r'rst:0x[0-9a-f]+ \(')  # one ROM reset-reason line per boot
FATAL = re.compile(r'Guru Meditation|panic\'ed|abort\(\) was called|Brownout|Task watchdog got triggered|'
                   r'stack overflow|LoadProhibited|StoreProhibited|IllegalInstruction|assert failed')


def clean(text):
    return ANSI.sub('', text).rstrip('\r\n')


def num(v):
    try:
        return int(v)
    except ValueError:
        return float(v)


def parse_line(text):
    """Return a dict: {'tick', 'level', 'tag', 'msg'} for ESP log lines (else
    tick None), plus 'tl' = {'kind', 'id', 'f': {key: number}, 'text'} for TL lines."""
    t = clean(text)
    out = {'tick': None, 'level': None, 'tag': None, 'msg': t, 'tl': None}
    m = LOG.match(t)
    if m:
        out.update(level=m.group(1), tick=int(m.group(2)), tag=m.group(3).strip(), msg=m.group(4))
    body = out['msg']
    i = body.find('TL ')
    if i < 0 or (i > 0 and not body[:i].isspace()):
        return out
    toks = body[i + 3:].split(' ')
    if not toks or not toks[0]:
        return out
    first = toks[0]
    tl = {'kind': None, 'id': None, 'f': {}, 'text': None}
    km = KV.match(first)
    if km:
        tl['kind'] = km.group(1)
        tl['id'] = num(km.group(2))
        tl['f'][km.group(1)] = num(km.group(2))
        rest = toks[1:]
    else:
        tl['kind'] = first
        rest = toks[1:]
    if tl['kind'] == 'txt':
        # TL txt seq=<n> <text...>
        j = 0
        while j < len(rest):
            kv = KV.match(rest[j])
            if not kv:
                break
            tl['f'][kv.group(1)] = num(kv.group(2))
            j += 1
        tl['text'] = ' '.join(rest[j:]).strip()
        if tl['id'] is None:
            tl['id'] = tl['f'].get('seq', tl['f'].get('seg'))
        out['tl'] = tl
        return out
    for tok in rest:
        kv = KV.match(tok)
        if kv:
            tl['f'][kv.group(1)] = num(kv.group(2))
            if kv.group(3):
                tl['f'][kv.group(1) + '_unit'] = kv.group(3)
    if tl['id'] is None:
        for k in ('seq', 'seg'):
            if k in tl['f']:
                tl['id'] = tl['f'][k]
                break
    out['tl'] = tl
    return out


def read_lines_tsv(path):
    """lines.tsv rows: mono<TAB>wall<TAB>line. Yields (mono, wall, line)."""
    with open(path, encoding='utf-8', errors='replace') as fh:
        for row in fh:
            row = row.rstrip('\n')
            if not row or row.startswith('#'):
                continue
            parts = row.split('\t', 2)
            if len(parts) < 3:
                continue
            yield float(parts[0]), float(parts[1]), parts[2]
