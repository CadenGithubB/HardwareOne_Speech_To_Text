#!/usr/bin/env python3
"""One table of every model version on the same full test sets.

benchmark.py [--run] [--import-existing]

Models are listed in benchmark_models.json (name, checkpoint dir, note), in
the order they were made. Results are cached per (weights SHA-256, test set)
in $STT_ROOT/work/benchmark/, so a model is only scored on sets it has
not been scored on yet and a renamed or moved checkpoint is not re-run.

  --import-existing  seed the cache from final.json / baseline.json files the
                     training runs already wrote (same evaluate.py, greedy)
  --run              score every missing (model, set) pair (MPS, ~3 min/set)

Writes BENCHMARK.md next to this file: greedy WER (no language model), which
is what training changes; the device's LM decoding is tuned per checkpoint
separately (stt_train/lm/tune.py) and is not part of this table.
"""
import argparse
import hashlib
import json
from pathlib import Path
import os
import re
STT_ROOT = Path(os.environ.get('STT_ROOT', 'stt-data'))  # data root: set STT_ROOT

HERE = Path(__file__).resolve().parent
CACHE = (STT_ROOT / 'work/benchmark')
# The Broad score is defined on exactly these ten sets (rows stay comparable).
BROAD_SETS = ['ami-sdm-test', 'ami-ihm-test', 'librispeech-test-clean', 'ami-sdm-test-g2', 'ami-ihm-test-g2',
              'peoples-clean-test', 'peoples-clean-test-g2', 'voxpopuli-validation', 'voxpopuli-validation-g2',
              'librispeech-test-clean-g2']
# Extra columns (2026-10-03): Common Voice (accents, own phones/laptops; its dev
# split, never trained on), speech under held-out everyday noise at 0-10 dB SNR
# (make_noisy_stores.py), and held-out pure noise, reported as phantom words per
# minute (anything written there is invented; 0 is ideal).
EXTRA_SETS = ['commonvoice-en-test', 'librispeech-test-clean-noisy', 'peoples-clean-test-noisy']
PHANTOM_SETS = ['demand-noise-test', 'demand-noise-test-g2']
SETS = BROAD_SETS + EXTRA_SETS + PHANTOM_SETS
LABELS = {'ami-sdm-test': 'AMI far', 'ami-ihm-test': 'AMI headset', 'librispeech-test-clean': 'Libri clean',
          'ami-sdm-test-g2': 'AMI far (G2 sim)', 'ami-ihm-test-g2': 'AMI headset (G2 sim)',
          'peoples-clean-test': "People's Speech", 'peoples-clean-test-g2': "People's Speech (G2 sim)",
          'voxpopuli-validation': 'VoxPopuli', 'voxpopuli-validation-g2': 'VoxPopuli (G2 sim)',
          'librispeech-test-clean-g2': 'Libri clean (G2 sim)',
          'commonvoice-en-test': 'Common Voice', 'librispeech-test-clean-noisy': 'Libri + noise',
          'peoples-clean-test-noisy': "People's Speech + noise",
          'demand-noise-test': 'Phantom words/min (noise)', 'demand-noise-test-g2': 'Phantom words/min (noise, G2 sim)'}


def resolve_ckpt(path):
    """Checkpoint paths in benchmark_models.json are relative to STT_ROOT
    (absolute paths under an old drive's stt/ folder are mapped onto it)."""
    for old in (os.environ.get('STT_ROOT', 'stt-data'), os.environ.get('STT_ROOT', 'stt-data')):
        if path.startswith(old):
            path = path[len(old):]
    return str(STT_ROOT / path) if not path.startswith('/') else path


def store_minutes(name):
    from data import Store
    try:
        return float(Store(name).lengths.sum()) / 16000 / 60
    except FileNotFoundError:
        return 0.0
# Result files written by earlier runs: (checkpoint dir, result json)
EXISTING = [
    (str(STT_ROOT / 'models/quartznet15x5'), str(STT_ROOT / 'work/run15x5/baseline.json')),
    (str(STT_ROOT / 'work/run15x5/best'), str(STT_ROOT / 'work/run15x5/final.json')),
    (str(STT_ROOT / 'work/run15x5/best'), str(STT_ROOT / 'work/run15x5/final-g2.json')),
    (str(STT_ROOT / 'work/run15x5b/full/best'), str(STT_ROOT / 'work/run15x5b/full/final.json')),
    (str(STT_ROOT / 'models/citrinet384_ls'), str(STT_ROOT / 'work/citrinet384-ls-ami.json')),
    (str(STT_ROOT / 'models/citrinet384_ls'), str(STT_ROOT / 'work/citrinet384-ls-libri.json')),
    (str(STT_ROOT / 'work/citrinet384/full/best'), str(STT_ROOT / 'work/citrinet384/full/final.json')),
    (str(STT_ROOT / 'work/expanded/citrinet384/best'), str(STT_ROOT / 'work/expanded/citrinet384/final.json')),
    (str(STT_ROOT / 'work/expanded/quartznet15x5/best'), str(STT_ROOT / 'work/expanded/quartznet15x5/final.json')),
]


def weights_sha(ckpt):
    h = hashlib.sha256()
    with open(Path(ckpt) / 'model_weights.ckpt', 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def cache_path(sha, name):
    return CACHE / sha[:16] / f'{name}.json'


def store(sha, name, result, source):
    path = cache_path(sha, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: result[k] for k in ('wer', 'errors', 'words', 'utterances')}
    path.write_text(json.dumps({**keep, 'source': source}, indent=1))


def import_existing():
    for ckpt, report in EXISTING:
        if not Path(report).exists() or not (Path(ckpt) / 'model_weights.ckpt').exists():
            continue
        sha = weights_sha(ckpt)
        for name, result in json.loads(Path(report).read_text())['results'].items():
            if name in SETS and not cache_path(sha, name).exists():
                store(sha, name, result, report)
                print(f'imported {name} for {ckpt} from {report}')


def run_missing(models):
    import torch
    from common import QuartzNet, load_checkpoint
    from citrinet import is_citrinet, Citrinet, load_vocab
    from evaluate import evaluate_stores
    from data import STORES
    device = torch.device('cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu')
    available = [s for s in SETS if (STORES / s / 'index.json').exists()]
    for m in models:
        missing = [s for s in available if not cache_path(m['sha'], s).exists()]
        if not missing:
            continue
        config, state = load_checkpoint(m['ckpt'])
        model = (Citrinet(config, load_vocab(m['ckpt'])) if is_citrinet(config) else QuartzNet(config))
        model = model.load_nemo(state).to(device).eval()
        for name in missing:
            print(f"scoring {m['name']} on {name}", flush=True)
            result = evaluate_stores(model, state, [(name, None)], device)[name]
            store(m['sha'], name, result, 'benchmark.py')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', action='store_true')
    p.add_argument('--import-existing', action='store_true')
    a = p.parse_args()
    if a.import_existing:
        import_existing()
    models = json.loads((HERE / 'benchmark_models.json').read_text())
    for m in models:
        m['ckpt'] = resolve_ckpt(m['ckpt'])
        m['sha'] = weights_sha(m['ckpt'])
    if a.run:
        run_missing(models)
    from train import broad_score
    lines = ['# STT model benchmark', '',
             'Greedy WER % (no language model) on the full test sets; G2 sim = the same audio through the',
             'simulated glasses mic channel (make_g2_stores.py). Lower is better. Generated by benchmark.py.',
             'Broad = mean over meetings (AMI far+headset), varied talk (People\'s Speech), read (LibriSpeech)',
             'and accented (VoxPopuli), each the mean of its plain and G2-sim sets (train.broad_score).', '',
             'Extra columns are not part of Broad: Common Voice, speech mixed with held-out everyday noise at',
             '0-10 dB SNR, and phantom words per minute on held-out pure noise (lower is better; 0 is ideal).', '',
             '| # | Model | **Broad** | ' + ' | '.join(LABELS[s] for s in SETS) + ' | Notes |',
             '|---|---|---:|' + '---:|' * len(SETS) + '---|']
    minutes = {s: store_minutes(s) for s in PHANTOM_SETS}
    for i, m in enumerate(models, 1):
        cells, wers = [], {}
        for s in SETS:
            path = cache_path(m['sha'], s)
            if not path.exists():
                cells.append('–')
            elif s in PHANTOM_SETS:
                r = json.loads(path.read_text())
                cells.append(f"{r['errors'] / minutes[s]:.1f}" if minutes[s] else '–')
            else:
                wers[s] = json.loads(path.read_text())['wer']
                cells.append(f"{wers[s] * 100:.2f}")
        broad_wers = {s: wers[s] for s in BROAD_SETS if s in wers}
        broad = f"**{broad_score(broad_wers) * 100:.2f}**" if len(broad_wers) == len(BROAD_SETS) else '–'
        lines.append(f"| {i} | {m['name']} | {broad} | " + ' | '.join(cells) + f" | {m.get('note', '')} |")
    (HERE / 'BENCHMARK.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
