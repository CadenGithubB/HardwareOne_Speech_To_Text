"""Read-only CoreAudio queries for the default output device (ctypes, stdlib only).

Used to time when afplay's audio actually starts flowing: the default output
device's 'IsRunningSomewhere' flag goes 0 -> 1 when some client starts IO on it.
Nothing here changes any setting; it only reads properties.
"""
import ctypes
import struct
import subprocess
import threading
import time

_ca = ctypes.CDLL('/System/Library/Frameworks/CoreAudio.framework/CoreAudio')


def _fourcc(s):
    return struct.unpack('>I', s.encode())[0]


class _Addr(ctypes.Structure):
    _fields_ = [('sel', ctypes.c_uint32), ('scope', ctypes.c_uint32), ('elem', ctypes.c_uint32)]


_get = _ca.AudioObjectGetPropertyData
_get.argtypes = [ctypes.c_uint32, ctypes.POINTER(_Addr), ctypes.c_uint32, ctypes.c_void_p,
                 ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
_get.restype = ctypes.c_int32
_size = _ca.AudioObjectGetPropertyDataSize
_size.argtypes = [ctypes.c_uint32, ctypes.POINTER(_Addr), ctypes.c_uint32, ctypes.c_void_p,
                  ctypes.POINTER(ctypes.c_uint32)]
_size.restype = ctypes.c_int32

SYSTEM = 1
GLOB, OUTP = _fourcc('glob'), _fourcc('outp')


def _read(obj, sel, scope, ctype):
    a = _Addr(_fourcc(sel), scope, 0)
    v = ctype()
    n = ctypes.c_uint32(ctypes.sizeof(v))
    st = _get(obj, ctypes.byref(a), 0, None, ctypes.byref(n), ctypes.byref(v))
    if st != 0:
        raise OSError(f'AudioObjectGetPropertyData({sel}) status {st}')
    return v.value


def default_output_device():
    return _read(SYSTEM, 'dOut', GLOB, ctypes.c_uint32)


def is_running_somewhere(dev):
    return bool(_read(dev, 'gone', GLOB, ctypes.c_uint32))


def output_latency_info(dev):
    """Output-path latency terms in frames, plus the nominal rate (all read-only)."""
    info = {'device_id': dev}
    try:
        info['rate'] = _read(dev, 'nsrt', GLOB, ctypes.c_double)
    except OSError:
        info['rate'] = None
    for key, sel in (('device_latency', 'ltnc'), ('safety_offset', 'saft'), ('buffer_frames', 'fsiz')):
        try:
            info[key] = _read(dev, sel, OUTP, ctypes.c_uint32)
        except OSError:
            info[key] = None
    # first output stream's latency
    try:
        a = _Addr(_fourcc('stm#'), OUTP, 0)
        n = ctypes.c_uint32(0)
        if _size(dev, ctypes.byref(a), 0, None, ctypes.byref(n)) == 0 and n.value >= 4:
            arr = (ctypes.c_uint32 * (n.value // 4))()
            if _get(dev, ctypes.byref(a), 0, None, ctypes.byref(n), arr) == 0:
                info['stream_latency'] = _read(arr[0], 'ltnc', GLOB, ctypes.c_uint32)
    except OSError:
        pass
    info.setdefault('stream_latency', None)
    if info['rate']:
        frames = sum(info[k] or 0 for k in ('device_latency', 'safety_offset', 'buffer_frames', 'stream_latency'))
        info['pipeline_frames'] = frames
        info['pipeline_ms'] = 1000.0 * frames / info['rate']
    return info


def read_output_volume():
    """Read (never set) the system output volume and mute state via osascript."""
    try:
        out = subprocess.run(['osascript', '-e', 'get volume settings'], capture_output=True,
                             text=True, timeout=10).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return {'error': repr(exc)}
    res = {'raw': out}
    for part in out.split(','):
        if ':' in part:
            k, v = part.split(':', 1)
            res[k.strip().replace(' ', '_')] = v.strip()
    return res


class RunWatcher:
    """Polls the default output device's IsRunningSomewhere flag in a thread and
    records the monotonic time of each 0->1 / 1->0 transition."""

    def __init__(self, period_s=0.001):
        self.dev = default_output_device()
        self.period = period_s
        self.events = []          # (monotonic, running)
        self.initial = is_running_somewhere(self.dev)
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        last = self.initial
        while not self._stop.is_set():
            try:
                cur = is_running_somewhere(self.dev)
            except OSError:
                cur = last
            if cur != last:
                self.events.append((time.monotonic(), cur))
                last = cur
            time.sleep(self.period)

    def start(self):
        self._t.start()
        return self

    def stop(self):
        self._stop.set()
        self._t.join(timeout=2)

    def first_start_after(self, t):
        for ts, running in self.events:
            if running and ts >= t:
                return ts
        return None

    def first_stop_after(self, t):
        for ts, running in self.events:
            if not running and ts >= t:
                return ts
        return None


if __name__ == '__main__':
    import json
    d = default_output_device()
    print(json.dumps({'running_somewhere': is_running_somewhere(d), **output_latency_info(d),
                      'volume': read_output_volume()}, indent=1))
