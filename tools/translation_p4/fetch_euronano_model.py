#!/usr/bin/env python3
"""Download only the pinned EuroNano Tiny English-to-European INTGEMM pack."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request

HERE = Path(__file__).resolve().parent
REVISION = '3a5e1e4e2f7001ff5cfd79785bef03cf19281b73'
PREFIX = ('https://huggingface.co/qvac/TranslatePsy-EuroNano/resolve/'
          f'{REVISION}/en-xx/Tiny/intgemm/')
FILES = [
    ('model.intgemm.alphas.bin', 17141227,
     '646c87844fd9917e929feed627ec7f21b245f7bfded5442b61dc8b4b1b1e68dd'),
    ('lex.50.50.enxx.s2t.bin', 614636,
     '9e0c8b830ef2ac6eecc56c54c974d81b7610aa1d5b32063a1c27e8d27b6c630c'),
    ('vocab.spm', 805231,
     'f76ce75a335872f27c812c7d122051f923565b5111adc36f207a15be4cbc9a51'),
]


def fetch(entry):
    filename, expected_bytes, expected_hash = entry
    target = HERE / 'private' / 'euronano-enxx'
    target.mkdir(parents=True, exist_ok=True)
    destination = target / filename
    if destination.exists():
        data = destination.read_bytes()
    else:
        with urllib.request.urlopen(PREFIX + filename, timeout=60) as response:
            data = response.read(expected_bytes + 1)
    actual_hash = hashlib.sha256(data).hexdigest()
    if len(data) != expected_bytes or actual_hash != expected_hash:
        raise ValueError(f'Pinned checksum or size mismatch: {filename}')
    if not destination.exists():
        destination.write_bytes(data)
    return {'path': filename, 'url': PREFIX + filename,
            'bytes': len(data), 'sha256': actual_hash}


def main():
    with ThreadPoolExecutor(max_workers=3) as executor:
        files = list(executor.map(fetch, FILES))
    manifest = {'repository': 'qvac/TranslatePsy-EuroNano', 'revision': REVISION,
                'architecture': 'Tiny', 'pack': 'en-xx/Tiny/intgemm', 'files': files}
    (HERE / 'private' / 'euronano-model-provenance.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
