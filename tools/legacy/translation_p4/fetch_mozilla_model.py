#!/usr/bin/env python3
"""Download pinned Mozilla EN->ES tiny weights from the official Bergamot mirror."""
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import io
import json
from pathlib import Path
import urllib.request

HERE = Path(__file__).resolve().parent
REVISION = 'e7957fc407441a5e3e35bbcbf9d60d9b35764618'
PREFIX = 'https://storage.googleapis.com/bergamot-models-sandbox/0.3.3/enes/'
FILES = [
    ('model.enes.intgemm.alphas.bin', 17140755,
     'fa7460037a3163e03fe1d23602f964bff2331da6ee813637e092ddf37156ef53'),
    ('lex.50.50.enes.s2t.bin', 3347104,
     '3a113d713dec3cf1d12bba5b138ae616e28bba4bbc7fe7fd39ba145e26b86d7f'),
    ('vocab.esen.spm', 825463,
     '909b1eea1face0d7f90a474fe29a8c0fef8d104b6e41e65616f864c964ba8845'),
]
MAX_EXPANDED_BYTES = 32 * 1024 * 1024


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def fetch(entry):
    filename, expected_bytes, expected_hash = entry
    target = HERE / 'private' / 'mozilla-enes'
    target.mkdir(parents=True, exist_ok=True)
    destination = target / filename
    if destination.exists():
        data = destination.read_bytes()
    else:
        with urllib.request.urlopen(PREFIX + filename, timeout=60) as response:
            payload = response.read(expected_bytes + 1)
        if payload[:2] == b'\x1f\x8b':
            with gzip.GzipFile(fileobj=io.BytesIO(payload)) as archive:
                data = archive.read(MAX_EXPANDED_BYTES + 1)
        else:
            data = payload
    if len(data) != expected_bytes or sha256(data) != expected_hash:
        raise ValueError(f'Pinned checksum or size mismatch: {filename}')
    if not destination.exists():
        destination.write_bytes(data)
    return {
        'path': filename, 'url': PREFIX + filename,
        'bytes': len(data), 'sha256': sha256(data),
    }


def main():
    with ThreadPoolExecutor(max_workers=3) as executor:
        files = list(executor.map(fetch, FILES))
    if files[0]['sha256'] != 'fa7460037a3163e03fe1d23602f964bff2331da6ee813637e092ddf37156ef53':
        raise SystemExit('Decompressed model differs from Mozilla metadata')
    manifest = {'revision': REVISION, 'architecture': 'tiny', 'from': 'en', 'to': 'es', 'files': files}
    (HERE / 'private' / 'mozilla-model-provenance.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
