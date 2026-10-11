#!/usr/bin/env python3
"""Does carrying LM context across phrases help? Consecutive-segment WER.

  context_eval.py --ckpt DIR --lm meeting.lm [--meetings 4] [--segments 150]

tune.py's sets are shuffled single utterances, so they cannot show what the
device does in continuous transcription: phrase N+1 follows phrase N. This
takes runs of consecutive AMI validation segments (one timeline per meeting,
all speakers, ordered by start time; SDM = one room mic, IHM = headsets) and
decodes each run in order four ways:
  base       every phrase starts at <s> and ends with </s> (the device today)
  open       starts at <s>, no </s> at the end
  ctx        starts from the previous phrase's DECODED last two words, </s>
  ctx-open   previous decoded words, no </s>
  oracle     previous REFERENCE words, no </s> (upper bound, not achievable)
Logits (float, CPU) are cached per checkpoint under work/lm/context/.
"""
from __future__ import annotations

import argparse
import io
import json
import multiprocessing as mp
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent))
import hw1lm  # noqa: E402
from tune import ckpt_key, wer  # noqa: E402
import os
STT_ROOT = Path(os.environ.get('STT_ROOT', 'stt-data'))  # data root: set STT_ROOT

USB = STT_ROOT
WORK = (STT_ROOT / 'work/lm/context')
MODES = ['base', 'open', 'ctx', 'ctx-open', 'oracle']


def select_runs(mic, meetings, segments, seed):
    import pyarrow.parquet as pq
    from build_lm import complete_files
    files = complete_files(USB / 'ami' / mic, 'validation-*.parquet')
    rows = defaultdict(list)
    for fi, f in enumerate(files):
        pf = pq.ParquetFile(f)
        for rg in range(pf.metadata.num_row_groups):
            t = pf.read_row_group(rg, columns=['meeting_id', 'begin_time', 'end_time', 'text']).to_pydict()
            for r in range(len(t['text'])):
                text = hw1lm.normalize_text(t['text'][r] or '')
                dur = t['end_time'][r] - t['begin_time'][r]
                if text and 0.5 <= dur <= 20.0:
                    rows[t['meeting_id'][r]].append((t['begin_time'][r], fi, rg, r, text))
    chosen = sorted(rows)
    random.Random(seed).shuffle(chosen)
    runs = []
    for m in sorted(chosen[:meetings]):
        segs = sorted(rows[m])[:segments]
        runs.append((m, segs))
    return files, runs


def compute(ckpt, mic, meetings, segments, seed):
    cache = WORK / ckpt_key(ckpt) / f'{mic}-m{meetings}-s{segments}-r{seed}.npz'
    if cache.exists():
        d = np.load(cache, allow_pickle=True)
        return d['meta'].item()['runs'], [d[f'l{i}'] for i in range(len(d['meta'].item()['flat']))]
    import pyarrow.parquet as pq
    import soundfile as sf
    import torch
    from common import Frontend, QuartzNet, load_checkpoint
    from prepare_data import to_mono16k
    torch.set_num_threads(2)
    config, state = load_checkpoint(ckpt)
    model = QuartzNet(config).load_nemo(state).eval()
    frontend = Frontend(state)
    files, runs = select_runs(mic, meetings, segments, seed)
    logits, meta_runs, flat = [], [], []
    audio_cache = {}
    for m, segs in runs:
        texts = []
        for _, fi, rg, r, text in segs:
            if (fi, rg) not in audio_cache:
                audio_cache.clear()
                audio_cache[(fi, rg)] = pq.ParquetFile(files[fi]).read_row_group(rg, columns=['audio']).column('audio')
            data, rate = sf.read(io.BytesIO(audio_cache[(fi, rg)][r].as_py()['bytes']), dtype='float32')
            feats = frontend(to_mono16k(data, rate), dither=False)
            with torch.no_grad():
                out, n = model(feats[None], torch.tensor([feats.shape[1]]))
            logits.append(out[0, :int(n[0])].numpy().astype(np.float32))
            flat.append(len(flat))
            texts.append(text)
        meta_runs.append({'meeting': m, 'texts': texts})
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache, meta=np.array({'runs': meta_runs, 'flat': flat}, dtype=object),
             **{f'l{i}': x for i, x in enumerate(logits)})
    return meta_runs, logits


_W = {}


def _init(lm_path):
    _W['lm'] = hw1lm.read_lm(lm_path)


def _decode_run(job):
    mode, texts, lps = job
    lm = _W['lm']
    hyps, prev_hyp, prev_ref = [], '', ''
    for ref, lp in zip(texts, lps):
        ctx = {'base': None, 'open': None, 'ctx': prev_hyp, 'ctx-open': prev_hyp, 'oracle': prev_ref}[mode]
        end = mode in ('base', 'ctx')
        h = hw1lm.decode(lp, lm, context=ctx, end_eos=end)
        hyps.append(h)
        # A phrase that decoded to nothing keeps the earlier context.
        prev_hyp = (prev_hyp + ' ' + h).strip()[-200:] if h else prev_hyp
        prev_ref = (prev_ref + ' ' + ref).strip()[-200:]
    return mode, hyps


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ckpt', required=True)
    ap.add_argument('--lm', required=True)
    ap.add_argument('--meetings', type=int, default=4)
    ap.add_argument('--segments', type=int, default=150)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--modes', default=','.join(MODES))
    ap.add_argument('--out')
    a = ap.parse_args()
    modes = a.modes.split(',')
    report = {'ckpt': a.ckpt, 'lm': a.lm, 'params': hw1lm.read_lm(a.lm).params}
    for mic in ('sdm', 'ihm'):
        t0 = time.time()
        runs, logits = compute(a.ckpt, mic, a.meetings, a.segments, a.seed)
        lps = [hw1lm.log_softmax(x) for x in logits]
        jobs, k = [], 0
        for run in runs:
            n = len(run['texts'])
            for mode in modes:
                jobs.append((mode, run['texts'], lps[k:k + n]))
            k += n
        hyps = defaultdict(list)
        refs = [t for run in runs for t in run['texts']]
        with mp.get_context('spawn').Pool(a.workers, _init, (a.lm,)) as pool:
            # results arrive in submission order per (run, mode) via imap
            for mode, h in pool.imap(_decode_run, jobs):
                hyps[mode].extend(h)
        report[mic] = {}
        for mode in modes:
            w, e, n = wer(refs, hyps[mode])
            report[mic][mode] = {'wer': w, 'errors': e, 'words': n}
            print(f'{mic} {mode:9s} WER {w * 100:6.2f}% ({e}/{n})', flush=True)
        print(f'{mic}: {len(refs)} segments in {len(runs)} meetings, {time.time() - t0:.0f} s', flush=True)
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
