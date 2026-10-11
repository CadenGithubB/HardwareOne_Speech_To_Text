"""G2 glasses microphone channel: LC3 encode/decode with the glasses' settings.

The glasses stream their mic as LC3 at 16 kHz, 10 ms frames, 40 bytes/frame
(32 kbps), five frames per BLE packet (components/hardwareone/G2_Glasses.cpp,
kMicLc3*). A lost or corrupt frame is concealed by LC3 packet-loss concealment
(PLC), which the firmware's decoder does on decode error.

This wraps the repo's vendored reference liblc3 (components/hardwareone_libs/
liblc3, Apache-2.0) through ctypes. The shared library is compiled on first
use into build/ next to this file (ignored by git), or into $HW1_LC3_BUILD when
set (the Ubuntu kit keeps it on the PC's own disk), with the same LC3_PLUS=0 /
LC3_PLUS_HR=0 baseline configuration as the firmware.
"""
import ctypes
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LIBLC3 = HERE.parents[1] / 'components/hardwareone_libs/liblc3'
BUILD = Path(os.environ.get('HW1_LC3_BUILD') or HERE / 'build')
DYLIB = BUILD / ('liblc3.dylib' if sys.platform == 'darwin' else 'liblc3.so')  # macOS / Linux

FRAME_US = 10000
SAMPLE_RATE = 16000
FRAME_SAMPLES = SAMPLE_RATE * FRAME_US // 1_000_000   # 160
FRAME_BYTES = 40                                      # 32 kbps, as the glasses send
S16 = 0                                               # LC3_PCM_FORMAT_S16


def _build():
    # Safe when several processes build at once (DataLoader workers): each
    # writes its own temporary file and swaps it in atomically; a process whose
    # compile fails still uses a library that another one finished.
    DYLIB.parent.mkdir(parents=True, exist_ok=True)
    # Skip dotfiles: macOS leaves "._name.c" metadata files on exFAT drives.
    sources = sorted(str(p) for p in (LIBLC3 / 'src').glob('*.c') if not p.name.startswith('.'))
    tmp = DYLIB.with_name(f'{DYLIB.name}.{os.getpid()}.tmp')
    try:
        subprocess.run(['cc', '-O2', '-shared', '-fPIC', '-DLC3_PLUS=0', '-DLC3_PLUS_HR=0',
                        '-I', str(LIBLC3 / 'include'), *sources, '-o', str(tmp), '-lm'], check=True)
        os.replace(tmp, DYLIB)
    except subprocess.CalledProcessError:
        if not DYLIB.exists():
            raise
    finally:
        tmp.unlink(missing_ok=True)


_lib = None


def _load():
    global _lib
    if _lib is None:
        if not DYLIB.exists():
            _build()
        lib = ctypes.CDLL(str(DYLIB))
        lib.lc3_encoder_size.restype = ctypes.c_uint
        lib.lc3_encoder_size.argtypes = [ctypes.c_int, ctypes.c_int]
        lib.lc3_decoder_size.restype = ctypes.c_uint
        lib.lc3_decoder_size.argtypes = [ctypes.c_int, ctypes.c_int]
        lib.lc3_setup_encoder.restype = ctypes.c_void_p
        lib.lc3_setup_encoder.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        lib.lc3_setup_decoder.restype = ctypes.c_void_p
        lib.lc3_setup_decoder.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        lib.lc3_encode.restype = ctypes.c_int
        lib.lc3_encode.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_void_p]
        lib.lc3_decode.restype = ctypes.c_int
        lib.lc3_decode.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_void_p, ctypes.c_int]
        _lib = lib
    return _lib


class G2Channel:
    """One encoder/decoder pair; create one per process (not thread-safe)."""

    def __init__(self):
        lib = _load()
        self._lib = lib
        self._enc_mem = ctypes.create_string_buffer(lib.lc3_encoder_size(FRAME_US, SAMPLE_RATE))
        self._dec_mem = ctypes.create_string_buffer(lib.lc3_decoder_size(FRAME_US, SAMPLE_RATE))
        self._frame = (ctypes.c_uint8 * FRAME_BYTES)()

    def __call__(self, x, loss_rate=0.0, rng=None):
        """float32 [-1, 1] at 16 kHz -> the same audio after the glasses' codec.

        loss_rate: probability that each 10 ms frame is lost and concealed (PLC).
        Encoder/decoder state is reset per call, like a fresh stream.
        """
        lib = self._lib
        enc = lib.lc3_setup_encoder(FRAME_US, SAMPLE_RATE, 0, self._enc_mem)
        dec = lib.lc3_setup_decoder(FRAME_US, SAMPLE_RATE, 0, self._dec_mem)
        n = len(x)
        frames = -(-n // FRAME_SAMPLES)
        pcm = np.zeros(frames * FRAME_SAMPLES, dtype=np.int16)
        pcm[:n] = np.clip(np.round(x * 32767), -32768, 32767).astype(np.int16)
        out = np.empty_like(pcm)
        for f in range(frames):
            src = pcm[f * FRAME_SAMPLES:(f + 1) * FRAME_SAMPLES]
            dst = out[f * FRAME_SAMPLES:(f + 1) * FRAME_SAMPLES]
            lib.lc3_encode(enc, S16, src.ctypes.data, 1, FRAME_BYTES, self._frame)
            lost = loss_rate > 0 and rng is not None and rng.random() < loss_rate
            # A NULL frame asks the decoder for packet-loss concealment.
            lib.lc3_decode(dec, None if lost else self._frame, FRAME_BYTES, S16, dst.ctypes.data, 1)
        return (out[:n].astype(np.float32) / 32768.0)


def agc(x, rng, target_db=None, max_gain_db=24.0, window_s=0.5):
    """Slow automatic gain control, like a headset mic raising gain in quiet.

    Gain follows the inverse of a smoothed level toward target_db, capped at
    max_gain_db of boost: quiet stretches get louder (noise floor rises), loud
    speech is pulled down. Mirrors the jittery quiet floor measured from the
    G2 mic (2026-09-30), not an exact model of the glasses' AGC.
    """
    if target_db is None:
        target_db = rng.uniform(-30, -18)
    hop = int(window_s * SAMPLE_RATE / 4)
    if len(x) < hop:
        return x
    frames = len(x) // hop
    level = np.sqrt(np.mean(np.square(x[:frames * hop]).reshape(frames, hop), axis=1) + 1e-10)
    smooth = np.empty_like(level)
    acc = level[0]
    for i, v in enumerate(level):          # attack fast, release slow
        acc = v if v > acc else 0.9 * acc + 0.1 * v
        smooth[i] = acc
    gain_db = np.clip(target_db - 20 * np.log10(smooth + 1e-10), -12.0, max_gain_db)
    gain = 10 ** (np.repeat(gain_db, hop) / 20)
    gain = np.concatenate([gain, np.full(len(x) - len(gain), gain[-1])])
    return (x * gain).astype(np.float32)
