#!/usr/bin/env python3
"""Re-read every store's audio.bin from the disk and compare it with the
SHA-256 its writer recorded (index.json "audio_sha256"). Run after a remount
of the data drive so no cached copy can stand in for a bad write.
  verify_stores.py [store ...]     (default: every store that recorded a hash)
"""
import json
import sys

from data import STORES
from nocache_sha256 import sha256

names = sys.argv[1:] or sorted(p.parent.name for p in STORES.glob('*/index.json'))
bad = checked = 0
for name in names:
    index = json.loads((STORES / name / 'index.json').read_text())
    want = index.get('audio_sha256')
    if not want:
        continue
    checked += 1
    got = sha256(STORES / name / 'audio.bin')
    print(('ok ' if got == want else 'BAD'), name, flush=True)
    bad += got != want
print(f'{checked} stores checked, {bad} bad')
sys.exit(1 if bad else 0)
