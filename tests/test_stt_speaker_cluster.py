#!/usr/bin/env python3
"""Compile/run speaker attribution regressions against the production header.

Uses synthetic embeddings only; verifies abstention/state invariants, not model
accuracy. --sanitize enables AddressSanitizer and UndefinedBehaviorSanitizer.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='hw1-stt-speaker-') as temporary:
        binary = Path(temporary) / 'speaker-cluster'
        command = [
            'clang++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
            str(HERE / 'stt_speaker_cluster_harness.cpp'),
            '-I' + str(HERE.parent / 'firmware/components/hw1_stt/stt'), '-o', str(binary),
        ]
        if args.sanitize:
            command[1:1] = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run(command, check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    main()
