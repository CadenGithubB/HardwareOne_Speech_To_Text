#!/usr/bin/env python3
"""Decode sttperf mmlog DMA-ring dumps that carry SDMMC controller state (x2f-st / x2f-fix arms).

  mmstate.py MMLOG.txt [...] [--tail N]

Prints the anomaly list and the last N ring entries (default 40), with time relative to the last entry,
the transaction (slot, opcode, read/write, error), buffer/length, and decoded registers:
  STATUS  fifo=<words> busy (data_busy) cmdfsm=<n>
  IDSTS   ti ri fbe du ces nis ais eb=<n> fsm=<n>   (internal DMA)
  RINTSTS cd dto rto dcrc drto hto frun hle sbe acd ebe sdio=<mask>
  buf     BUFADDR (current DMA buffer address) and cnt (TBBCNT, bytes moved host side)
ESP-Hosted notes: 16 sdio_read (a=len, b=buf), 17 sdio_done, 18 sdio_buf, 19 sdio_bad, 20 sdio_reg.
"""
import re, sys

KINDS = {16: 'sdio_read', 17: 'sdio_done', 18: 'sdio_buf', 19: 'sdio_bad', 20: 'sdio_reg', 23: 'txn_start', 24: 'txn_end'}


def flags(v, names):
    return ' '.join(n for b, n in names if v >> b & 1)


def status(st):
    return f"fifo={(st >> 17) & 0x1fff}{' busy' if st >> 9 & 1 else ''} cmdfsm={(st >> 4) & 0xf}"


def idsts(v):
    f = flags(v, [(0, 'ti'), (1, 'ri'), (2, 'fbe'), (4, 'du'), (5, 'ces'), (8, 'nis'), (9, 'ais')])
    return f"{f} eb={(v >> 10) & 7} fsm={(v >> 13) & 0xf}".strip()


def rintsts(v):
    f = flags(v, [(2, 'cd'), (3, 'dto'), (8, 'rto'), (7, 'dcrc'), (9, 'drto'), (10, 'hto'), (11, 'frun'),
                  (12, 'hle'), (13, 'sbe'), (14, 'acd'), (15, 'ebe')])
    sd = v >> 16
    return f + (f' sdio={sd:#x}' if sd else '')


def line(x, t1):
    k = x['kind']
    rel = (x['t'] - t1) / 1000
    if k in (23, 24):
        a = x['a']
        txn = f"slot {a & 15} op {(a >> 8) & 255} {'rd' if a >> 4 & 1 else 'wr'} err {a >> 16:#x}"
        regs = (f"| {status(x['st'])} | ids {idsts(x['ids'])} | rint {rintsts(x['rint'])} | "
                f"buf {x['buf']:#x} cnt {x['cnt']}")
        return f"{rel:9.3f} {KINDS[k]:9s} {txn} b {x['b']:#x} len {x['c']} {regs}"
    return f"{rel:9.3f} {KINDS.get(k, k):9s} a {x['a']} b {x['b']:#x}"


def main():
    args = sys.argv[1:]
    tail = 40
    if '--tail' in args:
        i = args.index('--tail')
        tail = int(args[i + 1])
        del args[i:i + 2]
    for f in args:
        L = open(f, errors='replace').read().splitlines()
        parse = lambda tag: [dict((k, int(v)) for k, v in re.findall(r'(\w+)=(\d+)', l.split(f'TL {tag} ', 1)[1]))
                             for l in L if f'TL {tag} t=' in l]
        head = [re.sub(r'.*TL mmdma ', '', l) for l in L if 'TL mmdma' in l]
        an, d = parse('mmanom'), parse('mmd')
        print('=====', f, head)
        t1 = d[-1]['t'] if d else 0
        print('-- anomalies (first 16)')
        for x in an:
            print('  ', line(x, t1))
        print(f'-- last {tail} entries')
        for x in d[-tail:]:
            print('  ', line(x, t1))


if __name__ == '__main__':
    main()
