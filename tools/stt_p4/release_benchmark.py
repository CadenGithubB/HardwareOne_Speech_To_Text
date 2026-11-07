#!/usr/bin/env python3
"""Compare two local speech exports on a frozen, labeled PCM development suite."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

import numpy as np
import torch

from export_quartznet import as_runtime, sha
from quantization_probe import Probe
from quartznet_graph import QuartzNet, WEIGHTS_OVERRIDE_ENV, checkpoint_hashes, load_checkpoint

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE.parent / 'stt_train_15x5'), str(HERE.parent / 'stt_train/lm'),
                str(ROOT / 'tools/device_tests/bench')]
from diagnostics import atomic_json, error_counts, paired_changes, summarize
from score_experiments import word_error_details
import hw1lm


def read_json(path):
    return json.loads(path.read_text())


def load_float_checkpoint(checkpoint, expected_digest):
    if expected_digest is None:
        return load_checkpoint(checkpoint)
    previous = os.environ.get(WEIGHTS_OVERRIDE_ENV)
    os.environ[WEIGHTS_OVERRIDE_ENV] = expected_digest
    try:
        return load_checkpoint(checkpoint)
    finally:
        if previous is None:
            del os.environ[WEIGHTS_OVERRIDE_ENV]
        else:
            os.environ[WEIGHTS_OVERRIDE_ENV] = previous


def load_export(directory, checkpoint, allow_native, expected_digest=None):
    manifest = read_json(directory / 'manifest.json')
    identity = manifest['model']['sha256']
    if sha(directory / manifest['model']['file']) != identity:
        raise ValueError(f'Export digest differs in {directory}')
    actual_digest = checkpoint_hashes(checkpoint)['weights_sha256']
    if expected_digest is not None and expected_digest != actual_digest:
        raise ValueError('Explicit checkpoint digest differs')
    if actual_digest != manifest['checkpoint']['weights_sha256']:
        raise ValueError(f'Checkpoint differs in {directory}')
    meta = manifest['runtime']['outputs'][0]
    if meta['dtype'] != 3 or len(meta['exponents']) != 1:
        raise ValueError('An INT8 output with a single exponent is required')
    if manifest.get('native_graph'):
        if not allow_native:
            raise ValueError('Use --trusted-local-native only for your own PPQ native graphs')
        from esp_ppq import TorchExecutor
        from esp_ppq.api import load_native_graph
        native = directory / manifest['native_graph']['file']
        if sha(native) != manifest['native_graph']['sha256']:
            raise ValueError('Native graph digest differs')
        executor = TorchExecutor(graph=load_native_graph(str(native)), device='cpu')

        def forward(features):
            return executor.forward(inputs=features)[0]
    else:
        cfg, state = load_float_checkpoint(checkpoint, expected_digest)
        forward = Probe(directory, QuartzNet(cfg, state).eval()).run
    if not manifest['cases']:
        raise ValueError('Export has no reference fixture')
    with torch.inference_mode():
        for case in manifest['cases']:
            files = case['files']
            feature_path = directory / files['features']['file']
            expected = directory / files['output']['file']
            if sha(feature_path) != files['features']['sha256'] or sha(expected) != files['output']['sha256']:
                raise ValueError('Reference fixture digest differs')
            features = np.fromfile(feature_path, '<f4').reshape(case['runtime_input_shape'])
            x = torch.from_numpy(features.transpose(0, 3, 1, 2).copy())
            if as_runtime(forward(x).numpy(), dict(meta)).tobytes() != expected.read_bytes():
                raise ValueError(f'Fixture mismatch in {directory}: {case["fixture"]}')
    calibration = {r['pcm_sha256'] for r in (manifest.get('calibration_stores') or {}).get('clips', [])}
    for case in manifest['cases']:
        source = checkpoint / 'fixtures' / case['fixture']
        if sha(source) != case['wav_sha256']:
            raise ValueError('Original calibration fixture WAV digest differs')
        with wave.open(str(source)) as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
                raise ValueError('Expected uncompressed mono PCM16 fixture at 16 kHz')
            calibration.add(hashlib.sha256(wav.readframes(wav.getnframes())).hexdigest())
    return forward, meta['exponents'][0], identity, calibration


def validate_case(case, suite_root, excluded):
    if case['partition'] != 'dev' or case['kind'] not in ('speech', 'silence'):
        raise ValueError('Cases must be labeled speech or silence from development')
    path = (suite_root / case['pcm']).resolve()
    if not path.is_relative_to(suite_root) or sha(path) != case['pcm_sha256']:
        raise ValueError(f'Invalid PCM path or digest for {case["id"]}')
    pcm = np.fromfile(path, dtype='<i2')
    if path.stat().st_size != 2 * len(pcm) or not len(pcm):
        raise ValueError('Expected nonempty little-endian mono PCM16')
    sources = case['source_hashes']
    if not isinstance(sources, list) or not sources or any(
        not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)
        for digest in sources
    ):
        raise ValueError('Each case requires original PCM digests')
    if {case['pcm_sha256'], *sources} & excluded:
        raise ValueError('Suite overlaps export calibration or fixtures')
    groups = case['reference_groups']
    if (case['kind'] == 'speech') != bool(groups) or any(not text.strip() for text in groups):
        raise ValueError('Speech requires reference text and silence requires an empty reference')
    last = 0
    for start, stop in case['spans']:
        if not last <= start < stop <= len(pcm) or not 320 <= stop-start <= 480000:
            raise ValueError('Invalid segment extents for the current zero-overlap profile')
        last = stop
    return pcm


def cpp_driver(tmp):
    src = ROOT / 'firmware/components/hw1_stt/stt'
    driver = tmp / 'frontend'
    sources = [src / 'quartznet_frontend.cpp', HERE / 'frontend/test_driver.cpp']
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-I'+str(src),
                    *map(str, sources), '-o', str(driver)], check=True)
    hashes = {p.name: sha(p) for p in [*sources, src/'quartznet_frontend.h', src/'quartznet_constants.h']}
    return driver, hashes


@torch.inference_mode()
def recognize(graph, exponent, features, lm, params):
    scores = graph(features)[0, :, :, 0].T.numpy()
    q = np.rint(scores / 2.**exponent).astype(np.int8)
    if not np.array_equal(q.astype(np.float32)*2.**exponent, scores):
        raise ValueError('Output differs from declared INT8 grid')
    return hw1lm.decode_int8(q, -exponent, lm, None, **params)


def score_case(case, segments, seconds):
    text = ' '.join(s for s in segments if s).strip()
    reference = ' '.join(case['reference_groups'])
    row = {'id': case['id'], 'condition': case['condition'], 'kind': case['kind'],
           'pcm_sha256': case['pcm_sha256'], 'seconds': seconds, 'ref': reference,
           'hyp': text, **error_counts(reference, text)}
    edge = word_error_details([{'text_norm': g} for g in case['reference_groups']],
                              [{'sequence': 0, 'sttText': text}])
    if edge['edits'] != row['errors']:
        raise ValueError('Expected normalized references in benchmark alphabet')
    row['first_words'] = edge['first_words']
    row['last_words'] = edge['last_words']
    words = [s.split() for s in segments if s.split()]
    row['repeated_join_words'] = sum(a[-1] == b[0] for a, b in zip(words, words[1:]))
    return row


def aggregate(rows):
    totals = summarize(rows)
    for edge in ('first_words', 'last_words'):
        totals[edge] = {k: sum(r[edge][k] for r in rows)
                        for k in ('words', 'matched', 'substituted', 'deleted')}
    totals['repeated_join_words'] = sum(r['repeated_join_words'] for r in rows)
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('suite', 'baseline', 'candidate', 'baseline-checkpoint', 'candidate-checkpoint', 'lm', 'output'):
        parser.add_argument('--'+option, type=Path, required=True)
    for arm in ('baseline', 'candidate'):
        parser.add_argument('--'+arm+'-weights-sha256', help='Explicit checkpoint digest for this arm')
    parser.add_argument('--trusted-local-native', action='store_true')
    parser.add_argument('--threads', type=int, default=2)
    args = parser.parse_args()
    suite = read_json(args.suite)
    cases = suite['cases']
    if suite['sample_rate'] != 16000 or not cases or len({c['id'] for c in cases}) != len(cases):
        parser.error('Expected a 16 kHz suite with unique case IDs')
    if {r['kind'] for r in cases} != {'speech', 'silence'}:
        parser.error('Both speech and labeled silence cases are required')
    if args.output.exists():
        parser.error('Use a new output directory')
    args.output.mkdir(parents=True)
    torch.set_num_threads(args.threads)
    lm = hw1lm.read_lm(args.lm)
    params = dict(lm.params)
    params['beam_width'] = int(params['beam_width'])
    models = {name: load_export(getattr(args, name), getattr(args, name+'_checkpoint'), args.trusted_local_native,
                                  getattr(args, name+'_weights_sha256'))
              for name in ('baseline', 'candidate')}
    excluded = set.union(*(m[3] for m in models.values()))
    rows = {name: [] for name in models}
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        driver, sources = cpp_driver(tmp)
        for case in cases:
            pcm = validate_case(case, args.suite.resolve().parent, excluded)
            texts = {name: [] for name in models}
            for start, stop in case['spans']:
                pcm[start:stop].tofile(tmp/'input.pcm')
                subprocess.run([driver, tmp/'input.pcm', tmp/'features.bin', 'no_dither'],
                               check=True, stdout=subprocess.DEVNULL)
                f = np.fromfile(tmp/'features.bin', '<f4').reshape(-1, 64)
                features = torch.from_numpy(f.T.copy())[None, :, :, None]
                for name, (graph, exponent, _, _) in models.items():
                    texts[name].append(recognize(graph, exponent, features, lm, params))
            for name in models:
                rows[name].append(score_case(case, texts[name], len(pcm)/16000))
            atomic_json(args.output/'progress.json', {'completed': len(rows['baseline']), 'total': len(cases)})
    groups = sorted({c['condition'] for c in cases})
    report = {'scope': 'Paired host development evaluation', 'suite_sha256': sha(args.suite),
              'exports': {k: v[2] for k,v in models.items()}, 'lm_sha256': lm.sha256,
              'decoder': params, 'frontend_sources': sources, 'evaluator_sha256': sha(__file__), 'models': {}}
    for name, arm in rows.items():
        report['models'][name] = {'speech': aggregate([r for r in arm if r['kind']=='speech']),
                                  'silence': aggregate([r for r in arm if r['kind']=='silence']),
                                  'conditions': {k: aggregate([r for r in arm if r['condition']==k]) for k in groups}}
        atomic_json(args.output/(name+'.json'), arm)
    def difference(control, candidate):
        delta = {key: candidate[key] - control[key]
                 for key in ('errors', 'deletions', 'substitutions', 'insertions', 'repeated_join_words')}
        if control['words']:
            delta['wer_percentage_points'] = 100 * delta['errors'] / control['words']
        elif control['phantom_words_per_minute'] is not None:
            delta['false_words_per_minute'] = candidate['phantom_words_per_minute'] - control['phantom_words_per_minute']
        for edge in ('first_words', 'last_words'):
            delta[edge + '_deleted'] = candidate[edge]['deleted'] - control[edge]['deleted']
        return delta

    control = report['models']['baseline']
    candidate = report['models']['candidate']
    report['candidate_minus_baseline'] = {
        'speech': difference(control['speech'], candidate['speech']),
        'silence': difference(control['silence'], candidate['silence']),
        'conditions': {k: difference(control['conditions'][k], candidate['conditions'][k]) for k in groups},
    }
    report['paired'] = paired_changes(rows['baseline'], rows['candidate'])
    atomic_json(args.output/'comparison.json', report)
    print(json.dumps({name: {k: v[k]['errors'] for k in ('speech','silence')}
                      for name,v in report['models'].items()}))


if __name__ == '__main__':
    main()
