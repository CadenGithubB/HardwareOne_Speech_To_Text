#!/usr/bin/env python3
"""Float vs frozen-int8 greedy WER of exported models on seeded dev-store subsets.

  evaluate_dev_int8.py --model NAME=CHECKPOINT_DIR:EXPORT_DIR [...] --output DIR

Each export directory must hold quartznet.onnx, quartznet.json and manifest.json
from export_quartznet.py. Int8 inference is evaluate_heldout.FrozenQuantized,
which is first required to reproduce every exported fixture output byte-exactly
(the same bytes embedded in the ESPDL test values). Utterances come from the
read-only experiments/stt_train stores; *-test stores are refused and any clip a
listed manifest used for calibration is excluded. Features use the portable
deployment frontend. Per-utterance int8 logits are saved for later LM decoding.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys
import time
import numpy as np
import torch
from quartznet_graph import QuartzNet, load_checkpoint, checkpoint_hashes, greedy, word_errors
from export_quartznet import features, as_runtime
from evaluate_heldout import FrozenQuantized

HERE = Path(__file__).resolve().parent
DEV = ['ami-sdm-validation', 'ami-ihm-validation', 'librispeech-dev-clean']


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select(store, count, excluded, seed):
    order = list(range(len(store))); random.Random(f'{seed}:{store.name}').shuffle(order)
    chosen = [i for i in order if (store.name, i) not in excluded
              and 320 <= store.lengths[i] <= 480000 and store.texts[i].strip()]
    return chosen[:count]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--model', action='append', required=True, metavar='NAME=CKPT:EXPORT')
    p.add_argument('--sets', nargs='*', default=DEV)
    p.add_argument('--count', type=int, default=150)
    p.add_argument('--seed', default='hw1-dev-int8')
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--frontend-max-abs-diff', type=float, default=0.0,
                   help='accept models whose window/fb differ from the first model by at most this '
                        '(all models always use the first model\'s frontend tensors)')
    args = p.parse_args()
    if any('test' in s.split('-') for s in args.sets): p.error('Test stores are not used here')
    if args.output.exists() and any(args.output.iterdir()): p.error('Use a new empty output directory')
    args.output.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(args.threads)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(HERE.parent/'stt_train'))
    from data import Store

    models, excluded, frontend_diffs = {}, set(), {}
    for spec in args.model:
        name, rest = spec.split('=', 1); ckpt, export = (Path(x) for x in rest.split(':', 1))
        manifest = json.loads((export/'manifest.json').read_text())
        if sha(export/'quartznet.espdl') != manifest['model']['sha256']: raise ValueError('Model hash differs: '+name)
        config, state = load_checkpoint(ckpt)
        if manifest['checkpoint']['weights_sha256'] != checkpoint_hashes(ckpt)['weights_sha256']:
            raise ValueError('Export was made from other weights: '+name)
        frontend = {k: state[k] for k in ('preprocessor.featurizer.window', 'preprocessor.featurizer.fb')}
        if models and any(not torch.equal(v, next(iter(models.values()))['frontend'][k]) for k, v in frontend.items()):
            first = next(iter(models.values()))['frontend']
            diff = max(float((v.double()-first[k].double()).abs().max()) for k, v in frontend.items())
            if not diff <= args.frontend_max_abs_diff: raise ValueError('Frontend tensors differ between models: '+name)
            frontend_diffs[name] = diff
        full = QuartzNet(config, state).eval(); quantized = FrozenQuantized(export, full)
        parity = []
        for case in manifest['cases']:
            rows = np.fromfile(export/case['files']['features']['file'], dtype='<f4').reshape(case['runtime_input_shape'])
            x = torch.from_numpy(rows.transpose(0, 3, 1, 2).copy())
            values = as_runtime(quantized(x).numpy(), dict(manifest['runtime']['outputs'][0]))
            if values.tobytes() != (export/case['files']['output']['file']).read_bytes():
                raise ValueError('Frozen int8 reconstruction differs from exported fixture: '+name)
            parity.append(case['fixture'])
        for clip in (manifest.get('calibration_stores') or {}).get('clips', []):
            excluded.add((clip['store'], clip['index']))
        models[name] = {'full': full, 'quantized': quantized, 'frontend': frontend, 'manifest': manifest,
                        'vocab': config['decoder']['params']['vocabulary'],
                        'out': dict(manifest['runtime']['outputs'][0]), 'parity': parity,
                        'checkpoint': str(ckpt), 'export': str(export)}
        print(name, 'fixture parity byte-exact:', parity, flush=True)

    report = {'scope': 'Seeded dev-store subsets, portable frontend, greedy CTC; calibration clips excluded',
              'seed': args.seed, 'count': args.count, 'script_sha256': sha(__file__),
              'models': {n: {'checkpoint': m['checkpoint'], 'export': m['export'],
                             'weights_sha256': m['manifest']['checkpoint']['weights_sha256'],
                             'espdl_sha256': m['manifest']['model']['sha256'],
                             'input_exponent': m['manifest']['runtime']['inputs'][0]['exponents'][0],
                             'output_exponent': m['out']['exponents'][0],
                             'node_count': m['manifest']['runtime']['node_count'],
                             'fixture_parity_byte_exact': m['parity']} for n, m in models.items()},
              'sets': {}}
    if frontend_diffs: report['frontend_max_abs_diff_vs_first_model'] = frontend_diffs
    for set_name in args.sets:
        store = Store(set_name); items = select(store, args.count, excluded, args.seed)
        started = time.time()
        words = 0; tallies = {n: {'float': 0, 'int8': 0, 'agree': 0, 'hi': 0, 'lo': 0, 'values': 0,
                                  'float_over': 0, 'max_abs_float': 0.0, 'in_sat': 0, 'in_values': 0} for n in models}
        saved = {n: {'q': [], 'offsets': [0]} for n in models}
        examples = []
        for k, i in enumerate(items):
            o, count = int(store.offsets[i]), int(store.lengths[i])
            pcm = np.array(store.audio[o:o+count], dtype=np.int16); ref = store.texts[i]
            words += len(ref.split()); row = {'index': i, 'ref': ref}
            x = features(pcm, None, next(iter(models.values()))['frontend'], 'portable')
            for n, m in models.items():
                with torch.inference_mode():
                    fl = m['full'](x); qt = m['quantized'](x)
                q = as_runtime(qt.numpy(), dict(m['out']))[0, :, 0, :]  # [T,29] int8
                xi = as_runtime(x.numpy(), dict(m['manifest']['runtime']['inputs'][0]))
                limit = 127 * 2.0 ** m['out']['exponents'][0]
                t = tallies[n]; ft, it = greedy(fl, m['vocab']), greedy(qt, m['vocab'])
                t['float'] += word_errors(ref, ft); t['int8'] += word_errors(ref, it); t['agree'] += ft == it
                t['hi'] += int((q == 127).sum()); t['lo'] += int((q == -128).sum()); t['values'] += q.size
                t['in_sat'] += int(((xi == 127) | (xi == -128)).sum()); t['in_values'] += xi.size
                t['float_over'] += int((fl.abs() > limit).sum()); t['max_abs_float'] = max(t['max_abs_float'], float(fl.abs().max()))
                saved[n]['q'].append(q); saved[n]['offsets'].append(saved[n]['offsets'][-1] + len(q))
                row[n] = {'float': ft, 'int8': it}
            if k < 8: examples.append(row)
        entry = {'utterances': len(items), 'words': words, 'audio_s': round(float(store.lengths[items].sum()) / 16000, 1),
                 'seconds': round(time.time() - started, 1), 'examples': examples}
        for n, t in tallies.items():
            entry[n] = {'float_wer': t['float'] / words, 'int8_wer': t['int8'] / words,
                        'float_errors': t['float'], 'int8_errors': t['int8'], 'identical_text': t['agree'],
                        'int8_at_127': t['hi'] / t['values'], 'int8_at_-128': t['lo'] / t['values'],
                        'float_beyond_int8_range': t['float_over'] / t['values'],
                        'input_at_int8_limits': t['in_sat'] / t['in_values'], 'max_abs_float_logit': t['max_abs_float']}
            np.savez(args.output/f'{n}-{set_name}.npz', q=np.concatenate(saved[n]['q']).astype(np.int8),
                     offsets=np.array(saved[n]['offsets']), indices=np.array(items),
                     texts=np.array([store.texts[i] for i in items]), exponent=models[n]['out']['exponents'][0])
        report['sets'][set_name] = entry
        print(set_name, json.dumps({n: {k: round(v, 4) if isinstance(v, float) else v for k, v in entry[n].items()}
                                     for n in models}), flush=True)
    (args.output/'results.json').write_text(json.dumps(report, indent=2)+'\n')
    lines = ['| set | utts/words | ' + ' | '.join(f'{n} float | {n} int8' for n in models) + ' |']
    for s, e in report['sets'].items():
        lines.append(f"| {s} | {e['utterances']}/{e['words']} | " +
                     ' | '.join(f"{e[n]['float_wer']*100:.2f} | {e[n]['int8_wer']*100:.2f}" for n in models) + ' |')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
