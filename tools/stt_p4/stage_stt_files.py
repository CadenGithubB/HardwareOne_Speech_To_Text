"""Additively stage STT files into a LittleFS partition image; no USB IO.

stage_stt_files.py BEFORE.bin AFTER.bin RECORD.json DEST=SRC [DEST=SRC ...]
Adds or replaces only the named files (under /STT Models/); every other file
and directory must come out byte-identical, which is verified by re-reading.
DEST= with no SRC removes that file instead (it must exist).
"""
import hashlib, json, sys
from pathlib import Path
from littlefs import LittleFS
from littlefs.context import UserContext

before_path, after_path, record_path = map(Path, sys.argv[1:4])
pairs = [arg.split('=', 1) for arg in sys.argv[4:]]
assert pairs and all(dest.startswith('/STT Models/') for dest, _ in pairs)
installs = [(dest, src) for dest, src in pairs if src]
removals = {dest for dest, src in pairs if not src}
assert not after_path.exists() and not record_path.exists()
sha = lambda b: hashlib.sha256(b).hexdigest()
original = before_path.read_bytes()
assert len(original) == 0x9DB000
ctx = UserContext(len(original)); ctx.buffer[:] = original
fs = LittleFS(context=ctx, mount=False, block_size=4096, block_count=len(original) // 4096,
              read_size=128, prog_size=128, cache_size=512, lookahead_size=128)
fs.mount()


def inventory():
    files, dirs = {}, []
    for folder, _, names in fs.walk('/'):
        dirs.append(folder)
        for name in names:
            path = folder.rstrip('/') + '/' + name
            with fs.open(path, 'rb') as f:
                data = f.read()
            files[path] = {'size': len(data), 'sha256': sha(data)}
    return {'files': files, 'directories': sorted(dirs)}


before = inventory()
assert bytes(ctx.buffer) == original
if '/STT Models' not in before['directories']:
    fs.mkdir('/STT Models')
assert removals <= set(before['files']), f'not on the device: {sorted(removals - set(before["files"]))}'
for dest in removals:
    fs.remove(dest)
payload = {}
for dest, src in installs:
    data = Path(src).read_bytes()
    if dest in before['files']:
        fs.remove(dest)  # copy-on-write: old + new copy may not both fit
    payload[dest] = sha(data)
    with fs.open(dest, 'wb') as f:
        assert f.write(data) == len(data)
after = inventory()
targets = set(payload)
assert all(after['files'][p] == info for p, info in before['files'].items() if p not in targets | removals)
assert set(after['files']) == (set(before['files']) - removals) | targets
assert all(after['files'][p]['sha256'] == h for p, h in payload.items())
assert set(before['directories']) <= set(after['directories'])
assert set(after['directories']) - set(before['directories']) <= {'/STT Models'}
free_blocks = len(original) // 4096 - fs.used_block_count
fs.unmount()
with after_path.open('xb') as f:
    f.write(ctx.buffer)
record = {'installed': payload, 'replaced': sorted(targets & set(before['files'])),
          'removed': sorted(removals),
          'other_files_unchanged': len(before['files']) - len((targets | removals) & set(before['files'])),
          'free_blocks_after': free_blocks, 'before_sha256': sha(original),
          'after_sha256': sha(bytes(ctx.buffer)), 'before': before, 'after': after}
record_path.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({k: v for k, v in record.items() if k not in ('before', 'after')}, indent=1))
