#!/usr/bin/env python3
"""Synthetic console prompt/log interleaving; no private input."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/speaker'))
from tl_parse import parse_line

line='I (1234) STT: TL seg=29 a0=100 a1=200 ok=1'
expected=parse_line(line)
for prefix in ('', '[123] ', '$ [login] ', '$ [tester] '):
    assert parse_line(prefix+line)==expected
assert parse_line('$ [tester] stt status')['tl'] is None
assert parse_line('{"text":"'+line+'"}')['tl'] is None
assert parse_line('unrelated '+line)['tl'] is None
print('tl parse: console prompt interleaving ok')
