#!/usr/bin/env python3
"""The device's portable overlap decision rule (C++) against the Python reference used for the
host scores (tools/overlap_gate/suppression.py: R10 at threshold 0.360 on 20 ms frames).

Builds firmware/components/hw1_stt/stt/overlap_rule.h's test with ASan/UBSan, runs its constructed
cases, then 300 random int8 logit sequences through both implementations: decisions must agree
exactly and fractions to 1e-6. Needs numpy (run with the export venv python).
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

root = Path(__file__).resolve().parents[1]
src = root / 'firmware/components/hw1_stt'
sys.path.insert(0, str(root / 'tools'))
from overlap_gate.suppression import drop_short_runs  # noqa: E402

RULE = dict(frame_threshold=0.5, min_run=10, segment_threshold=0.360, exponent=-3)


def reference(logits: np.ndarray):
    z = logits.astype(np.float64) * 2.0 ** RULE['exponent']
    z -= z.max(axis=1, keepdims=True)
    p = np.exp(z)
    p /= p.sum(axis=1, keepdims=True)
    marked = drop_short_runs(p[:, 2] >= RULE['frame_threshold'], RULE['min_run'])
    fraction = float(marked.mean()) if marked.size else 0.0
    return int(marked.sum()), fraction, bool(fraction >= RULE['segment_threshold'])


with tempfile.TemporaryDirectory(prefix='overlap-rule-') as tmp:
    exe = Path(tmp) / 'rule'
    subprocess.run([os.environ.get('CXX', 'clang++'), '-std=c++17', '-O2', '-g', '-ffp-contract=off', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-I' + str(src),
                    str(root / 'tests/overlap_rule_test.cpp'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
    rng = np.random.default_rng(20261106)
    agree = 0
    for i in range(300):
        frames = int(rng.integers(1, 700))
        # Mix of confident and borderline frames so marks form runs of varied length.
        base = rng.integers(-40, 41, size=(frames, 3)).astype(np.int8)
        if rng.random() < 0.7:
            runs = rng.integers(1, 30, size=8)
            pos = 0
            for r in runs:
                pos += int(rng.integers(0, 40))
                base[pos:pos + int(r), 2] = np.clip(base[pos:pos + int(r), 2].astype(int) + 60, -128, 127).astype(np.int8)
        f = Path(tmp) / f'case{i}.i8'
        base.tofile(f)
        out = subprocess.run([str(exe), str(f)], check=True, capture_output=True, text=True).stdout.split()
        c_frames, c_marked, c_fraction, c_flag = int(out[0]), int(out[1]), float(out[2]), out[3] == '1'
        r_marked, r_fraction, r_flag = reference(base)
        assert c_frames == frames, (c_frames, frames)
        assert c_marked == r_marked and c_flag == r_flag and abs(c_fraction - r_fraction) < 1e-6, (i, out, r_marked, r_fraction, r_flag)
        agree += 1
    print(f'{agree} random sequences agree with the Python reference')
