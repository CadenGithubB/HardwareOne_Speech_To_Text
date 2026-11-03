"""Host access to production C++ features and experimental window selection.

Requires numpy; model/reference features additionally need proto.py's environment.
No audio, features or embeddings are printed by this module.
"""
import ctypes
import os
from pathlib import Path
import subprocess
import numpy as np

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parents[2]/'firmware/components/hw1_stt/stt'


class Native:
    def __init__(self, work):
        library = Path(work)/'speaker_audio.so'
        subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-O2','-shared','-fPIC',
                        '-I'+str(ENGINE),str(HERE/'audio_frontend_bridge.cpp'),
                        str(ENGINE/'speaker_frontend.cpp'),'-o',str(library)],check=True)
        self.lib=ctypes.CDLL(str(library))
        pcm=np.ctypeslib.ndpointer(dtype=np.int16,ndim=1,flags='C_CONTIGUOUS')
        self.lib.speaker_normalize.argtypes=[pcm,ctypes.c_size_t]
        self.lib.speaker_normalize.restype=ctypes.c_float
        floats=np.ctypeslib.ndpointer(dtype=np.float32,flags='C_CONTIGUOUS')
        self.lib.speaker_features.argtypes=[pcm,ctypes.c_size_t,floats]
        self.lib.speaker_select.argtypes=[pcm,ctypes.c_size_t,ctypes.c_uint,
                                        ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_float)]

    def normalize(self, pcm):
        """Return an owned normalized copy and applied gain; preserve caller audio."""
        out=np.array(pcm,dtype=np.int16,copy=True,order='C')
        gain=self.lib.speaker_normalize(out,len(out))
        return out,gain

    def features(self, pcm):
        pcm=np.ascontiguousarray(pcm,dtype=np.int16)
        out=np.zeros((1,1,40,300),dtype=np.float32)
        if not len(pcm) or not self.lib.speaker_features(pcm,len(pcm),out):
            raise ValueError('native frontend rejected PCM')
        return out

    def select(self, pcm, policy):
        pcm=np.ascontiguousarray(pcm,dtype=np.int16)
        result=(ctypes.c_size_t*5)();threshold=ctypes.c_float()
        if not len(pcm) or not self.lib.speaker_select(pcm,len(pcm),policy,result,ctypes.byref(threshold)):
            raise ValueError('window selection rejected PCM')
        return dict(zip(('start','samples','frames','active_frames','selected_active_frames'),result),
                    threshold_rms=threshold.value)


def int16(pcm):
    """Replay's floats are quantized back to precisely the input PCM lattice."""
    return np.ascontiguousarray(np.clip(np.rint(np.asarray(pcm)*32768),-32768,32767),dtype=np.int16)
