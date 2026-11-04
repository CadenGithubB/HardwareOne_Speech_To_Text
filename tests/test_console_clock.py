"""No serial access: exercise the real logger adapter with a transport double."""
import importlib.util
import json
from pathlib import Path
import tempfile

SOURCE = Path(__file__).resolve().parents[1] / 'tools/device_tests/stream/console_clock.py'
spec = importlib.util.spec_from_file_location('console_clock', SOURCE)
clock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clock)


class Transport:
    def __init__(self, path):
        with Path(path).open('a') as output:
            self._loop(output, b'')

    def _loop(self, output, buffer):
        output.write('1001.000 STT_EVENT {"type":"final","rawText":"unchanged"}\n')
        output.flush()
        output.write('1000.693 STT_PERF {"type":"end"}\n')
        output.flush()


with tempfile.TemporaryDirectory(prefix='stt-clock-') as folder:
    path = Path(folder) / 'serial.log'
    def factory():
        ticks = iter([10, 10.01, 10.02])
        return clock.AnchoredMonotonicClock(wall=lambda: 1000, monotonic=lambda: next(ticks))
    Wrapped = clock.clocked_console_type(Transport, factory)
    Wrapped(path)
    lines = path.read_text().splitlines()
    assert lines == ['1000.010 STT_EVENT {"type":"final","rawText":"unchanged"}',
                     '1000.020 STT_PERF {"type":"end"}']
    metadata = json.loads(path.with_suffix('.log.clock.json').read_text())
    assert metadata['domain'] == 'wall-anchored-monotonic-v1'
    try:
        Wrapped(path)
        raise AssertionError('Overwrote an existing clock sidecar')
    except FileExistsError:
        pass
    assert path.read_text().splitlines() == lines

ticks = iter([5, 5, 4])
c = clock.AnchoredMonotonicClock(wall=lambda: 1000, monotonic=lambda: next(ticks))
assert c.now() == 1000
try:
    c.now()
    raise AssertionError('Accepted a regressing monotonic source')
except ValueError:
    pass
try:
    clock.clocked_console_type(object)
    raise AssertionError('Accepted an incompatible transport')
except TypeError:
    pass
print('Receive clock: backwards wall log, payload preservation, sidecar protection and invalid-clock/transport checks passed')
