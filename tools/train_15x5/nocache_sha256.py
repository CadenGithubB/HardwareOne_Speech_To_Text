#!/usr/bin/env python3
"""SHA-256 of files read from the disk itself, bypassing the macOS page cache
(F_NOCACHE), so a bad write cannot hide behind a cached good copy.
  nocache_sha256.py FILE...    prints "<sha256>  <path>" like shasum -a 256
"""
import fcntl
import hashlib
import os
import sys


def sha256(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        if hasattr(fcntl, 'F_NOCACHE'):
            fcntl.fcntl(fd, fcntl.F_NOCACHE, 1)
        h = hashlib.sha256()
        while True:
            block = os.read(fd, 8 << 20)
            if not block:
                return h.hexdigest()
            h.update(block)
    finally:
        os.close(fd)


if __name__ == '__main__':
    for p in sys.argv[1:]:
        print(f'{sha256(p)}  {p}', flush=True)
