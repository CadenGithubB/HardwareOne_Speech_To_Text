"""Stable receive-log timestamps around the approved Console transport.

The transport and its deadlines remain unchanged. A wall-clock anchor plus
monotonic elapsed time timestamps each log write; NTP corrections cannot move
publication time backwards. Old wall-clock logs are never rewritten.
"""
import hashlib
import json
from pathlib import Path
import re
import time

SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
STAMP = re.compile(r'^\d+\.\d+ ')


class AnchoredMonotonicClock:
    def __init__(self, wall=time.time, monotonic=time.monotonic):
        self.wall_anchor = wall()
        self.monotonic_anchor = monotonic()
        self.monotonic = monotonic
        self.last = self.monotonic_anchor

    def now(self):
        current = self.monotonic()
        if current < self.last:
            raise ValueError('Monotonic clock regressed')
        self.last = current
        return self.wall_anchor + current - self.monotonic_anchor

    def metadata(self):
        return {'domain': 'wall-anchored-monotonic-v1',
                'wall_anchor_s': self.wall_anchor,
                'monotonic_anchor_s': self.monotonic_anchor,
                'implementation_sha256': SOURCE_SHA256,
                'limitation': 'Host receive/write time, not physical display time or serial wire arrival.'}


class _ClockedWriter:
    def __init__(self, output, clock):
        self.output, self.clock = output, clock

    def write(self, line):
        match = STAMP.match(line)
        if not match:
            raise ValueError('Unexpected Console log writer format')
        return self.output.write(f'{self.clock.now():.3f} ' + line[match.end():])

    def flush(self):
        return self.output.flush()

    def __getattr__(self, name):
        return getattr(self.output, name)


def clocked_console_type(base, clock_factory=AnchoredMonotonicClock):
    """Subclass only the logger seam; preserve serial reads, scrubbing and send.

    The pinned helper's _loop writes timestamp-prefixed lines through write and
    flush. Record this adapter identity alongside the capture harness identity.
    Each fresh log gets a separate clock sidecar; never overwrite an old log's
    clock description. Use one Console/anchor for a continuous soak.
    """
    if not callable(getattr(base, '_loop', None)):
        raise TypeError('Console transport has no supported log-writer seam')

    class ClockedConsole(base):
        def __init__(self, logpath, *args, **kwargs):
            self.receive_clock = clock_factory()
            path = Path(logpath)
            with path.with_suffix(path.suffix + '.clock.json').open('x') as output:
                json.dump(self.receive_clock.metadata(), output, indent=2)
                output.write('\n')
            super().__init__(logpath, *args, **kwargs)

        def _loop(self, output, buffer):
            return super()._loop(_ClockedWriter(output, self.receive_clock), buffer)

    return ClockedConsole
