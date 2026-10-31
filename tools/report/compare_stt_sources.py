"""Compare standalone and HardwareOne STT sources without changing either tree.

Usage: python3 tools/report/compare_stt_sources.py --hardwareone-root /path/to/hardwareone-idf
Optional: --output docs/stt-source-parity.json
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def compare(hardwareone):
    standalone = ROOT / 'firmware/components/hw1_stt/stt'
    integrated = hardwareone / 'components/hardwareone/stt'
    if not integrated.is_dir():
        raise ValueError('HardwareOne root must contain components/hardwareone/stt')
    rows = []
    names = sorted({p.name for p in standalone.iterdir() if p.is_file()} |
                   {p.name for p in integrated.iterdir() if p.is_file()})
    for name in names:
        a, b = digest(standalone / name), digest(integrated / name)
        status = ('only_integrated' if a is None else 'only_standalone' if b is None
                  else 'identical' if a == b else 'different')
        rows.append(dict(file=name, status=status, standalone_sha256=a, integrated_sha256=b))
    revision = subprocess.check_output(['git', '-C', str(hardwareone), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(hardwareone), 'status', '--porcelain', '--',
                                    'components/hardwareone/System_STT.cpp',
                                    'components/hardwareone/System_STTLocal.cpp',
                                    'components/hardwareone/System_STTLocal.h',
                                    'components/hardwareone/stt', 'tools/p4/prepare_esp_dl.py',
                                    'tools/p4/esp-dl-3.3.12-hw1.patch'], text=True).splitlines()
    return dict(schema=1, compared_date='2026-10-31',
                integrated_head=revision, integrated_stt_worktree_changes=dirty,
                scope='Current filesystem sources; not proof of installed firmware equivalence',
                summary=dict(Counter(row['status'] for row in rows)), files=rows,
                esp_dl_patch=dict(
                    standalone_sha256=digest(ROOT / 'firmware/tools/esp-dl-3.3.12-hw1.patch'),
                    integrated_sha256=digest(hardwareone / 'tools/p4/esp-dl-3.3.12-hw1.patch')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hardwareone-root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = json.dumps(compare(args.hardwareone_root.resolve()), indent=2) + '\n'
    if args.output:
        args.output.write_text(result)
        print(args.output)
    else:
        print(result, end='')
