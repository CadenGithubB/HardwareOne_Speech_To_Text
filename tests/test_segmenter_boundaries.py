#!/usr/bin/env python3
"""Audit actual portable cuts and PCM conservation under ASan/UBSan."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="segmenter-boundaries-") as tmp:
    binary = Path(tmp) / "audit"
    subprocess.run([
        os.environ.get("CXX", "c++"), "-std=c++17", "-O1", "-g",
        "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
        "-fno-omit-frame-pointer", "-I" + str(root / "firmware/components/hw1_stt"),
        str(root / "tests/segmenter_boundary_test.cpp"), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
