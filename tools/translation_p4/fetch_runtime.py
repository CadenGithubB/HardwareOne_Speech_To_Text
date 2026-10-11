#!/usr/bin/env python3
"""Fetch a checksummed host-only Bergamot WASM runtime; run no npm scripts."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent
URL = ('https://registry.npmjs.org/@browsermt/bergamot-translator/-/'
       'bergamot-translator-0.4.9.tgz')
SHA512 = ('bNuuCwM/JnsIYQCKXcYKFT4Qc5vLMoB8Nbvz8ReIgs7xzebK8Sa+'
          'R8iEK8mLvNBe/WaZ6zrPaUQilLsRT/ea8Q==')
MAX_BYTES = 16 * 1024 * 1024


def main():
    target = HERE / 'private' / 'runtime'
    archive = HERE / 'private' / 'bergamot-translator-0.4.9.tgz'
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        payload = archive.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=60) as response:
            payload = response.read(MAX_BYTES + 1)
    actual = base64.b64encode(hashlib.sha512(payload).digest()).decode('ascii')
    if len(payload) > MAX_BYTES or actual != SHA512:
        raise SystemExit('Runtime archive does not match the pinned size limit/checksum')
    files = []
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as tar:
        members = tar.getmembers()
        if sum(m.size for m in members) > MAX_BYTES:
            raise SystemExit('Runtime archive expands beyond the expected bound')
        for member in members:
            rel = Path(member.name)
            if rel.is_absolute() or '..' in rel.parts or rel.parts[0] != 'package':
                raise SystemExit('Unsafe archive path')
            if member.isdir():
                continue
            if not member.isfile():
                raise SystemExit('Unexpected archive member type')
            destination = target / rel
            data = tar.extractfile(member).read()
            if destination.exists() and destination.read_bytes() != data:
                raise SystemExit(f'Refusing to overwrite changed file: {destination}')
            files.append((destination, data, member.name))
    if not archive.exists():
        archive.write_bytes(payload)
    manifest = {
        'name': '@browsermt/bergamot-translator', 'version': '0.4.9',
        'url': URL, 'integrity': 'sha512-' + SHA512,
        'archive_bytes': len(payload), 'files': [],
    }
    for destination, data, name in files:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        manifest['files'].append({
            'path': name, 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(),
        })
    (HERE / 'private' / 'runtime-provenance.json').write_text(
        json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
