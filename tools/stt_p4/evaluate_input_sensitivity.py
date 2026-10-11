#!/usr/bin/env python3
"""Frozen-model diagnostic for raw PCM amplitude and trailing silence.

Reuses the four saved synthetic heldout fixtures and original PPQ parity clips.
No audio playback/capture, checkpoint export, calibration or device access occurs.
This tiny matrix is not a representative accuracy benchmark or P4 latency test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch

from evaluate_heldout import FrozenQuantized
from export_quartznet import as_runtime, features
from quartznet_graph import QuartzNet, greedy, load_checkpoint, word_errors

HERE = Path(__file__).resolve().parent
SCALES = (1.0, 1 / 16, 1 / 64)
SILENCES = (0, 2, 4)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_sha(array):
    return hashlib.sha256(array.tobytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, default=HERE / 'private/full-portable-v2')
    parser.add_argument('--fixtures', type=Path, default=HERE / 'private/heldout-tts-v1')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('Use a new empty output directory')
    args.output.mkdir(parents=True, exist_ok=True)
    baseline = json.loads((HERE / 'heldout-provenance.json').read_text())
    manifest = json.loads((args.model_dir / 'manifest.json').read_text())
    for name, key in [('quartznet.espdl', 'model_sha256'),
                      ('quartznet.onnx', 'onnx_sha256'),
                      ('quartznet.json', 'quantization_metadata_sha256')]:
        if sha(args.model_dir / name) != baseline[key]:
            raise ValueError('Pinned artifact mismatch: ' + name)
    if manifest['frontend_contract_sha256'] != baseline['frontend_sha256']:
        raise ValueError('Frontend manifest mismatch')
    if sha(HERE / 'frontend/frontend-contract.json') != baseline['frontend_sha256']:
        raise ValueError('Frontend contract mismatch')
    torch.set_num_threads(4)
    config, state = load_checkpoint()
    floating = QuartzNet(config, state).eval()
    quantized = FrozenQuantized(args.model_dir, floating)
    vocab = config['decoder']['params']['vocabulary']
    parity = []
    for case in manifest['cases']:
        rows = np.fromfile(args.model_dir / case['files']['features']['file'], dtype='<f4').reshape(case['runtime_input_shape'])
        x = torch.from_numpy(rows.transpose(0, 3, 1, 2).copy())
        with torch.inference_mode():
            actual = as_runtime(quantized(x).numpy(), manifest['runtime']['outputs'][0])
        expected = (args.model_dir / case['files']['output']['file']).read_bytes()
        if actual.tobytes() != expected:
            raise ValueError('Original frozen PPQ fixture is not byte-exact')
        parity.append({'fixture': case['fixture'], 'output_byte_exact': True,
                       'sha256': hashlib.sha256(expected).hexdigest()})
    cases = []
    for index, original in enumerate(baseline['cases']):
        wav = args.fixtures / original['file']
        pcm_path = wav.with_suffix('.pcm')
        if sha(wav) != original['wav_sha256'] or sha(pcm_path) != original['pcm_sha256']:
            raise ValueError('Saved synthetic fixture mismatch')
        pcm = np.fromfile(pcm_path, dtype='<i2')
        if len(pcm) != original['samples']:
            raise ValueError('Saved sample count mismatch')
        for scale in SCALES:
            rounded = np.rint(pcm.astype(np.float64) * scale)  # Nearest-even int16 quantization.
            clipped = int(np.count_nonzero((rounded < -32768) | (rounded > 32767)))
            scaled = np.clip(rounded, -32768, 32767).astype('<i2')
            for seconds in SILENCES:
                audio = np.pad(scaled, (0, seconds * 16000))
                if not 320 <= len(audio) <= 20 * 16000:
                    raise ValueError('Diagnostic audio exceeds bounded twenty-second capture')
                start = time.perf_counter()
                x = features(audio, None, state, 'portable')
                frontend_seconds = time.perf_counter() - start
                with torch.inference_mode():
                    yf = floating(x)
                    yq = quantized(x)
                ft, qt = greedy(yf, vocab), greedy(yq, vocab)
                if scale == 1 and seconds == 0:
                    if ft != original['portable_float'] or qt != original['frozen_int8']:
                        raise ValueError('Saved heldout greedy baseline did not replay')
                rows = x.numpy().transpose(0, 2, 3, 1).astype('<f4')
                output = as_runtime(yq.numpy(), manifest['runtime']['outputs'][0])
                cases.append({'fixture': original['file'], 'reference': original['reference'],
                    'word_count': original['word_count'], 'scale': scale,
                    'trailing_silence_seconds': seconds, 'samples': len(audio),
                    'original_samples': len(pcm), 'seconds': len(audio) / 16000,
                    'peak_absolute_pcm': int(np.abs(scaled.astype(np.int32)).max()),
                    'rms_pcm': float(np.sqrt(np.mean(scaled.astype(np.float64) ** 2))),
                    'clipped_samples': clipped, 'nonzero_samples': int(np.count_nonzero(scaled)),
                    'nonzero_fraction_original_span': float(np.count_nonzero(scaled) / len(scaled)),
                    'pcm_sha256': array_sha(audio), 'features_sha256': array_sha(rows),
                    'runtime_feature_shape': list(rows.shape), 'runtime_output_shape': list(output.shape),
                    'frozen_int8_output_sha256': array_sha(output),
                    'portable_float': ft, 'frozen_int8': qt,
                    'portable_float_word_errors': word_errors(original['reference'], ft),
                    'frozen_int8_word_errors': word_errors(original['reference'], qt),
                    'host_frontend_seconds': frontend_seconds})
            print(f'Completed fixture {index}, scale {scale:g}', flush=True)
    aggregate = []
    for scale in SCALES:
        for seconds in SILENCES:
            group = [case for case in cases if case['scale'] == scale and case['trailing_silence_seconds'] == seconds]
            aggregate.append({'scale': scale, 'trailing_silence_seconds': seconds,
                'sentences': len(group), 'words': sum(case['word_count'] for case in group),
                'portable_float_word_errors': sum(case['portable_float_word_errors'] for case in group),
                'frozen_int8_word_errors': sum(case['frozen_int8_word_errors'] for case in group)})
    report = {'scope': 'Four existing synthetic sentences; diagnostic amplitude/padding matrix, not a WER benchmark, microphone test, P4 timing test or new calibration.',
        'method': 'Scale saved mono16k int16 PCM, nearest-even round and clip back to int16; append exact digital zeros. Unchanged portable frontend, frozen float weights and exported int8 scales; greedy CTC. All captures <=20s.',
        'script_sha256': sha(__file__), 'baseline_provenance_sha256': sha(HERE / 'heldout-provenance.json'),
        'model_sha256': baseline['model_sha256'], 'frontend_sha256': baseline['frontend_sha256'],
        'onnx_sha256': baseline['onnx_sha256'], 'quantization_metadata_sha256': baseline['quantization_metadata_sha256'],
        'versions': {'torch': torch.__version__, 'numpy': np.__version__},
        'frozen_fixture_parity': parity, 'aggregate': aggregate, 'cases': cases}
    (args.output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(aggregate, indent=2))
    print('REPORT', args.output / 'results.json')


if __name__ == '__main__':
    main()
