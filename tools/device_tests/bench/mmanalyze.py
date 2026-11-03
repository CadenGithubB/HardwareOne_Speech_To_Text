#!/usr/bin/env python3
"""Summarize sttperf mmlog dumps (upward PSRAM memmoves) by caller.

  mmanalyze.py ELF MMLOG.txt [...]

Per file: the header line (head, armed, trapped, trap_ra...), then callers by count with the shift
(dst - src) values and length range, decoded with addr2line; and the last 12 entries with their
time relative to the last one. Numbers and code locations only.
"""
import collections, re, subprocess, sys
from pathlib import Path

A2L = sorted(Path.home().glob('.espressif/tools/riscv32-esp-elf/*/riscv32-esp-elf/bin/riscv32-esp-elf-addr2line'))[-1]


def decode(elf, addrs):
    if not addrs:
        return {}
    out = subprocess.run([str(A2L), '-pfiaC', '-e', elf] + [hex(a) for a in addrs], capture_output=True,
                         text=True).stdout
    res, cur = {}, None
    for line in out.splitlines():
        m = re.match(r'(0x[0-9a-f]+): (.*)', line)
        if m:
            cur = int(m.group(1), 16)
            res[cur] = m.group(2)
        elif cur is not None and 'inlined by' in line:
            res[cur] += ' <= ' + line.strip().replace('(inlined by) ', '')
    return {a: re.sub(r'/Users/[^ ]*/(components|esp-idf)/', r'\1/', v) for a, v in res.items()}


def main():
    elf = sys.argv[1]
    for f in sys.argv[2:]:
        lines = Path(f).read_text(errors='replace').splitlines()
        head = [l for l in lines if 'TL mmlog' in l]
        ents = [dict((k, int(v)) for k, v in re.findall(r'(\w+)=(\d+)', l.split('TL mm ', 1)[1]))
                for l in lines if 'TL mm t=' in l]
        print('==', f, len(ents), 'entries')
        if head:
            print('  ', re.sub(r'.*TL mmlog ', '', head[0]))
        by = collections.defaultdict(list)
        for e in ents:
            by[e['ra']].append(e)
        names = decode(elf, list(by) + [int(m) for m in re.findall(r'trap_ra=(\d+)', head[0] if head else '') if int(m)])
        for ra, es in sorted(by.items(), key=lambda kv: -len(kv[1])):
            shifts = collections.Counter(e['dst'] - e['src'] for e in es)
            print(f'   {len(es):4d}  shift {dict(shifts.most_common(4))} len {min(e["len"] for e in es)}..'
                  f'{max(e["len"] for e in es)}  {names.get(ra, hex(ra))[:220]}')
        if ents:
            t1 = ents[-1]['t']
            print('   last entries (ms before the last):')
            for e in ents[-12:]:
                print(f'     {(e["t"] - t1) / 1000:9.1f}  dst {e["dst"]:#x} src {e["src"]:#x} len {e["len"]} '
                      f'shift {e["dst"] - e["src"]}  {names.get(e["ra"], hex(e["ra"]))[:120]}')


if __name__ == '__main__':
    main()
