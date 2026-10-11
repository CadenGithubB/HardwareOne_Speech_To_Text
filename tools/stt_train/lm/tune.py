#!/usr/bin/env python3
"""Tune HW1LM1 decoder parameters for a checkpoint and report WER.

  tune.py --ckpt DIR [--lm meeting.lm] [--out-lm tuned.lm]

1. Fixed, seeded dev/test subsets are drawn from the parquet corpora (same
   utterances on every run, so checkpoints are comparable):
     dev:  AMI sdm validation 200, AMI ihm validation 150, LibriSpeech dev 100
     test: AMI sdm test 200, AMI ihm test 150, LibriSpeech test 100
2. Float logits of the checkpoint (CPU, 2 threads, no dither) are cached under
   $STT_ROOT/work/lm/logits/<ckpt-name>-<sha12>/<set>.npz.
3. Coordinate search on dev only: alpha x beta grid, refinement, unk_log10,
   then beam_width x char_prune for the accuracy/speed trade-off.
   Objective: 0.4*WER(ami-sdm-dev) + 0.4*WER(ami-ihm-dev) + 0.2*WER(libri-dev).
4. The chosen params are written into the LM header (SHA recomputed) and the
   test sets are decoded once with them. Test data never influences a choice.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import multiprocessing as mp
import os
import random
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True  # never leave caches next to the training pipeline's modules
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent))
import hw1lm  # noqa: E402
STT_ROOT = Path(os.environ.get('STT_ROOT', 'stt-data'))  # data root: set STT_ROOT

USB = STT_ROOT
WORK = (STT_ROOT / 'work/lm')
DEFAULT_LM = WORK / 'meeting.lm'
FPS = 50.0  # model output frames per second (hop 10 ms, stride 2)

SETS = {  # name: (kind, directory, pattern, count, seed)
    'ami-sdm-dev': ('ami', USB / 'ami' / 'sdm', 'validation-*.parquet', 200, 11),
    'ami-ihm-dev': ('ami', USB / 'ami' / 'ihm', 'validation-*.parquet', 150, 12),
    'libri-dev': ('libri', USB / 'librispeech', 'clean_validation_*.parquet', 100, 13),
    'ami-sdm-test': ('ami', USB / 'ami' / 'sdm', 'test-*.parquet', 200, 21),
    'ami-ihm-test': ('ami', USB / 'ami' / 'ihm', 'test-*.parquet', 150, 22),
    'libri-test': ('libri', USB / 'librispeech', 'clean_test_*.parquet', 100, 23),
    # Held-out non-AMI conversation (2026-10-02); not part of DEV/TEST or tuning.
    'peoples-test': ('libri', USB / 'peoples_speech', 'clean_test_*.parquet', 300, 31),
    # VoxPopuli validation: never used in training (2026-10-02 broad score).
    'vox-test': ('vox', USB / 'voxpopuli', 'validation_*.parquet', 300, 41),
}
DEV = ['ami-sdm-dev', 'ami-ihm-dev', 'libri-dev']
TEST = ['ami-sdm-test', 'ami-ihm-test', 'libri-test']
WEIGHTS = {'ami-sdm-dev': 0.4, 'ami-ihm-dev': 0.4, 'libri-dev': 0.2}
TOLERANCE = 0.0005  # objective (absolute WER) treated as a tie when picking cheaper/safer settings
# hotword_bonus: real custom lists carry insertion risk that the simulated decoys
# cannot fully show, so a wider tie band steers towards the smaller bonus
HOTWORD_TOLERANCE = 0.001


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


# ------------------------------------------------------------------ subsets

def select_utterances(name):
    """Deterministic subset: [(id, text, samples16k)] in a seeded order."""
    import pyarrow.parquet as pq
    import soundfile as sf
    from build_lm import complete_files
    from prepare_data import to_mono16k, usable
    kind, directory, pattern, count, seed = SETS[name]
    files = complete_files(directory, pattern)
    rows = []
    for fi, f in enumerate(files):
        pf = pq.ParquetFile(f)
        cols = {'ami': ['audio_id', 'text', 'begin_time', 'end_time'],
                'vox': ['audio_id', 'raw_text', 'is_gold_transcript']}.get(kind, ['id', 'text'])
        start = 0
        for rg in range(pf.metadata.num_row_groups):
            t = pf.read_row_group(rg, columns=cols).to_pydict()
            if kind == 'vox':  # same filter as prepare_data.py: gold, no digits/acronyms
                import re
                bad = re.compile(r'[0-9]|[A-Z]{2,}|[%&@/$€£+=]')
                t['text'] = [x if g and not bad.search(x or '') else '' for x, g in zip(t['raw_text'], t['is_gold_transcript'])]
                t['id'] = t['audio_id']
            for r in range(len(t['text'])):
                text = hw1lm.normalize_text(t['text'][r] or '')
                if not text:
                    continue
                if kind == 'ami':
                    dur = t['end_time'][r] - t['begin_time'][r]
                    if not 0.5 <= dur <= 20.0:
                        continue
                    uid = t['audio_id'][r]
                else:
                    uid = t['id'][r]
                rows.append((fi, rg, r, uid, text))
            start += pf.metadata.row_group(rg).num_rows
    rows.sort(key=lambda x: x[3])
    random.Random(seed).shuffle(rows)
    chosen, pos = [], 0
    while len(chosen) < count and pos < len(rows):
        batch = rows[pos:pos + max(count - len(chosen), 1) * 3 // 2 + 8]
        pos += len(batch)
        groups = defaultdict(list)
        for k, row in enumerate(batch):
            groups[(row[0], row[1])].append((k, row))
        got = {}
        for (fi, rg), items in sorted(groups.items()):
            audio = pq.ParquetFile(files[fi]).read_row_group(rg, columns=['audio']).column('audio')
            for k, (_, _, r, uid, text) in items:
                data, rate = sf.read(io.BytesIO(audio[r].as_py()['bytes']), dtype='float32')
                samples = to_mono16k(data, rate)
                if usable(samples, text):
                    got[k] = (uid, text, samples)
            del audio
        for k in sorted(got):
            if len(chosen) < count:
                chosen.append(got[k])
    return chosen


# ------------------------------------------------------------------- logits

def ckpt_key(ckpt):
    h = hashlib.sha256()
    with open(Path(ckpt) / 'model_weights.ckpt', 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return f'{Path(ckpt).resolve().name}-{h.hexdigest()[:12]}'


def compute_logits(ckpt, names, cache_dir):
    todo = [n for n in names if not (cache_dir / f'{n}.npz').exists()]
    if not todo:
        return
    import torch
    torch.set_num_threads(2)
    from common import Frontend, QuartzNet, load_checkpoint
    config, state = load_checkpoint(ckpt)
    model = QuartzNet(config).load_nemo(state).eval()
    frontend = Frontend(state)
    cache_dir.mkdir(parents=True, exist_ok=True)
    for name in todo:
        t0 = time.time()
        utts = select_utterances(name)
        ids, texts, durs, chunks = [], [], [], []
        with torch.no_grad():
            for uid, text, samples in utts:
                feats = frontend(samples, dither=False)
                logits, lengths = model(feats[None], torch.tensor([feats.shape[1]]))
                chunks.append(logits[0, :int(lengths[0])].numpy().astype(np.float32))
                ids.append(uid)
                texts.append(text)
                durs.append(len(samples) / 16000.0)
        offsets = np.cumsum([0] + [len(c) for c in chunks])
        np.savez(cache_dir / f'{name}.npz', logits=np.concatenate(chunks), offsets=offsets,
                 ids=np.array(ids), texts=np.array(texts), durations=np.array(durs))
        log(f'logits {name}: {len(utts)} utts, {sum(durs):.0f} s audio, {time.time() - t0:.0f} s')


def load_set(cache_dir, name):
    d = np.load(cache_dir / f'{name}.npz')
    off = d['offsets']
    flat = d['logits']  # NpzFile re-reads on every access: load once
    logits = [flat[off[i]:off[i + 1]] for i in range(len(off) - 1)]
    return {'logits': logits, 'texts': d['texts'].tolist(), 'ids': d['ids'].tolist(),
            'durations': d['durations'].tolist()}


# ------------------------------------------------------------ WER helpers

def word_errors(ref, hyp):
    a, b = ref.split(), hyp.split()
    row = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        nxt = [i]
        for j, right in enumerate(b, 1):
            nxt.append(min(nxt[-1] + 1, row[j] + 1, row[j - 1] + (left != right)))
        row = nxt
    return row[-1]


def greedy_text(logits):
    ids = np.argmax(logits, axis=1)
    out, prev = [], -1
    for t in ids.tolist():
        if t != hw1lm.BLANK and t != prev:
            out.append(hw1lm.VOCAB[t])
        prev = t
    return ' '.join(''.join(out).split())


def wer(refs, hyps):
    e = sum(word_errors(r, h) for r, h in zip(refs, hyps))
    n = sum(len(r.split()) for r in refs)
    return e / max(n, 1), e, n


# ----------------------------------------------------------- parallel decode

_W = {}


def _init(lm_path, cache_dir, names, quantise):
    _W['lm'] = hw1lm.read_lm(lm_path)
    _W['lp'] = {}
    for n in names:
        s = load_set(Path(cache_dir), n)
        lps = []
        for x in s['logits']:
            if quantise is not None:
                x = hw1lm.dequantise(np.clip(np.rint(x * 2.0 ** quantise), -128, 127), quantise)
            lps.append(hw1lm.log_softmax(x))
        _W['lp'][n] = lps


def _job(args):
    name, i, params, custom = args
    t0 = time.process_time()
    text = hw1lm.decode(_W['lp'][name][i], _W['lm'], custom, **params)
    return name, i, text, time.process_time() - t0


class Decoder:
    def __init__(self, lm_path, cache_dir, names, workers=2, quantise=None):
        self.names = names
        self.sets = {n: load_set(cache_dir, n) for n in names}
        if workers <= 1:
            _init(str(lm_path), str(cache_dir), names, quantise)
            self.pool = None
        else:
            ctx = mp.get_context('spawn')
            self.pool = ctx.Pool(workers, _init, (str(lm_path), str(cache_dir), names, quantise))

    def run(self, params, names=None, custom=None, subset=None):
        names = names or self.names
        jobs = []
        for n in names:
            idx = range(len(self.sets[n]['texts']))
            if subset:
                idx = idx[::subset]
            jobs += [(n, i, params, custom) for i in idx]
        # longest first for load balance
        jobs.sort(key=lambda j: -len(self.sets[j[0]]['logits'][j[1]]))
        hyps = defaultdict(dict)
        cpu = 0.0
        results = map(_job, jobs) if self.pool is None else self.pool.imap_unordered(_job, jobs, chunksize=4)
        for n, i, text, secs in results:
            hyps[n][i] = text
            cpu += secs
        out = {}
        audio = 0.0
        for n in names:
            refs = [self.sets[n]['texts'][i] for i in sorted(hyps[n])]
            hs = [hyps[n][i] for i in sorted(hyps[n])]
            audio += sum(self.sets[n]['durations'][i] for i in hyps[n])
            w, e, words = wer(refs, hs)
            out[n] = {'wer': w, 'errors': e, 'words': words, 'hyps': hs}
        out['_cpu_per_audio_s'] = cpu / max(audio, 1e-9)
        return out

    def close(self):
        if self.pool is not None:
            self.pool.close()
            self.pool.join()


def objective(res):
    return sum(WEIGHTS[n] * res[n]['wer'] for n in WEIGHTS if n in res)


def fmt(p):
    return ', '.join(f'{k}={v:g}' if isinstance(v, float) else f'{k}={v}' for k, v in p.items())


# -------------------------------------------------------------------- search

def expansion_rate(sets, char_prune):
    """Mean (#non-blank labels >= char_prune) + 2 per beam and frame on dev."""
    vals = []
    for n in DEV:
        for x in sets[n]['logits']:
            lp = hw1lm.log_softmax(x)
            vals.append((lp[:, :28] >= char_prune).sum(axis=1) + 2)
    return float(np.concatenate(vals).mean())


def search(dec, base, log_rows, quick=False):
    """Search alpha, beta, unk_log10 on the dev objective at the fixed beam_width /
    char_prune in `base`, then sweep beam and prune for information only.

    Beam width is not picked by dev WER: with ~5k dev words the objective is
    noisy at the +-0.3 level, and tuning alpha/beta at one beam and then picking
    the beam fitted that noise (wider beams looked worse). Returns
    (best params, sweep rows)."""
    cache = {}

    def evaluate(p):
        key = tuple(sorted(p.items()))
        if key not in cache:
            t0 = time.time()
            r = dec.run(p, DEV)
            cache[key] = r
            row = {'params': dict(p), 'objective': objective(r),
                   **{n: r[n]['wer'] for n in DEV}, 'cpu_per_audio_s': r['_cpu_per_audio_s'],
                   'wall': time.time() - t0}
            log_rows.append(row)
            log(f"obj {row['objective'] * 100:.2f}  " + '  '.join(f'{n} {r[n]["wer"] * 100:.2f}' for n in DEV)
                + f"  {r['_cpu_per_audio_s']:.4f} cpu-s/s  [{fmt(p)}]")
        return objective(cache[key])

    def coordinate(best, steps):
        cur = evaluate(best)
        for key, step, lo in steps:
            improved = True
            while improved:
                improved = False
                for s in (-step, step):
                    p = {**best, key: round(best[key] + s, 4)}
                    if p[key] < lo:
                        continue
                    o = evaluate(p)
                    if o < cur - 1e-9:
                        best, cur, improved = p, o, True
        return best, cur

    # 1. coarse alpha x beta x unk grid (unk interacts with alpha, so it is not left to the end)
    alphas = (0.3, 0.5, 0.8) if quick else (0.3, 0.45, 0.6, 0.8, 1.0)
    betas = (0.0, 1.5, 3.0) if quick else (0.0, 1.0, 2.0, 3.0, 4.0)
    unks = (-6.0, -8.0) if quick else (-5.0, -6.5, -8.0, -10.0)
    grid = sorted((evaluate({**base, 'alpha': a, 'beta': b, 'unk_log10': u}), a, b, u)
                  for a in alphas for b in betas for u in unks)
    # 2. coordinate refinement from the best three grid points
    best, cur = None, None
    for _, a, b, u in grid[:3]:
        p, o = coordinate({**base, 'alpha': a, 'beta': b, 'unk_log10': u},
                          [('alpha', 0.1, 0.05), ('beta', 0.5, -5.0), ('unk_log10', 1.0, -20.0),
                           ('alpha', 0.05, 0.05), ('beta', 0.25, -5.0), ('unk_log10', 0.5, -20.0)])
        if cur is None or o < cur - 1e-9:
            best, cur = p, o
    # 3. information only: accuracy/cost of other beams and prune thresholds
    rates = {cp: expansion_rate(dec.sets, cp) for cp in (-5.0, -7.0, -10.0, -14.0)}
    rows = []
    for bw in ((8, 16, 32) if quick else (4, 8, 16, 24, 32, 48, 64)):
        for cp in ((best['char_prune'],) if bw != best['beam_width'] else tuple(rates)):
            p = {**best, 'beam_width': bw, 'char_prune': cp}
            rows.append({'objective': evaluate(p), 'expansions_per_frame': bw * rates.get(cp, 0.0), **p})
    return best, rows


def hotword_sim(dec, best, lm, rows):
    """Custom list = up to 128 LM-OOV words seen in dev references plus rare
    in-vocabulary decoys that never occur in dev (256 total), applied to every
    dev utterance: measures hits on the targets, false insertions of any listed
    word, and the WER effect. Returns the smallest bonus within
    TOLERANCE of the best dev objective (a large bonus risks insertions when a
    real list names words that are never spoken)."""
    from collections import Counter
    counts = Counter(w for n in DEV for t in dec.sets[n]['texts'] for w in t.split()
                     if w not in lm.word_id and len(w.encode()) <= hw1lm.MAX_CUSTOM_BYTES)
    targets = [w for w, _ in counts.most_common(hw1lm.MAX_CUSTOM_WORDS // 2)]
    # decoys: rarer in-vocabulary words that never occur in dev, filling the list to 256,
    # so a large bonus pays for the insertions it causes
    seen = {w for n in DEV for t in dec.sets[n]['texts'] for w in t.split()}
    pool = sorted((lm.uni_logp[i], w) for i, w in enumerate(lm.words)
                  if w not in seen and w not in hw1lm.SPECIALS and 4 <= len(w) <= 12)
    pool = pool[:len(pool) // 2]  # rarer half, jargon-like
    need = hw1lm.MAX_CUSTOM_WORDS - len(targets)
    decoys = [w for _, w in pool[::max(len(pool) // max(need, 1), 1)]][:need]
    custom = targets + decoys
    targets = set(targets)
    results = []
    for bonus in (0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0):
        r = dec.run({**best, 'hotword_bonus': bonus}, DEV, custom=custom)
        hits = ins = 0
        for n in DEV:
            for ref, hyp in zip(dec.sets[n]['texts'], r[n]['hyps']):
                rc, hc = Counter(ref.split()), Counter(hyp.split())
                for w in set(custom) & set(hc):
                    hits += min(rc[w], hc[w]) if w in targets else 0
                    ins += max(hc[w] - rc[w], 0)
        o = objective(r)
        rows.append({'hotword_bonus': bonus, 'objective': o, **{n: r[n]['wer'] for n in DEV},
                     'custom_words': len(custom), 'targets': len(targets), 'decoys': len(decoys),
                     'target_occurrences': sum(counts[w] for w in targets),
                     'hits': hits, 'false_insertions': ins})
        log(f'hotword {bonus:g}: obj {o * 100:.2f} hits {hits}/{sum(counts[w] for w in targets)} '
            f'false insertions {ins} ({len(targets)} targets + {len(decoys)} decoys)')
        results.append((o, bonus))
    top = min(o for o, _ in results)
    return min(b for o, b in results if o <= top + HOTWORD_TOLERANCE)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ckpt', required=True)
    ap.add_argument('--lm', default=str(DEFAULT_LM))
    ap.add_argument('--out-lm', help='write the tuned LM here (default: update --lm in place)')
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--quick', action='store_true', help='smaller grids')
    ap.add_argument('--beam-width', type=int, default=32, help='fixed search beam (1..64)')
    ap.add_argument('--char-prune', type=float, default=-7.0, help='fixed char prune (nats)')
    ap.add_argument('--no-search', action='store_true', help='evaluate the header params only')
    ap.add_argument('--compare-lms', nargs='*', default=[], help='extra LMs to score on dev with the tuned params')
    ap.add_argument('--report', help='JSON report path (default under work/lm/tune/)')
    ap.add_argument('--device-quantise', type=int, default=None,
                    help='tune on device-like int8 logits with scale 2^-N (5x5: 2, 15x5: 1)')
    a = ap.parse_args()

    key = ckpt_key(a.ckpt)
    cache_dir = WORK / 'logits' / key
    log(f'checkpoint {a.ckpt} -> {key}')
    compute_logits(a.ckpt, DEV + TEST, cache_dir)
    lm_path = Path(a.lm)
    lm = hw1lm.read_lm(lm_path)
    log(f'LM {lm_path}: {hw1lm.describe(lm)}')
    report = {'ckpt': str(a.ckpt), 'ckpt_key': key, 'lm': str(lm_path), 'lm_info': hw1lm.describe(lm)}

    sets = {n: load_set(cache_dir, n) for n in DEV + TEST}
    greedy = {}
    for n, s in sets.items():
        greedy[n] = wer(s['texts'], [greedy_text(x) for x in s['logits']])[0]
        report.setdefault('sets', {})[n] = {'utterances': len(s['texts']),
                                            'audio_s': round(sum(s['durations']), 1),
                                            'words': sum(len(t.split()) for t in s['texts'])}
    log('greedy WER: ' + '  '.join(f'{n} {w * 100:.2f}' for n, w in greedy.items()))
    report['greedy'] = greedy

    # The search always starts from the fixed defaults (not the current header) so
    # reruns are reproducible; --no-search evaluates the header params as they are.
    src = lm.params if a.no_search else hw1lm.DEFAULT_PARAMS
    base = {k: src[k] for k in hw1lm.PARAM_NAMES}
    base['beam_width'] = int(base['beam_width'])
    base['hotword_bonus'] = 0.0  # no custom words during the main search
    if not a.no_search:
        base.update(beam_width=a.beam_width, char_prune=a.char_prune)
    dec = Decoder(lm_path, cache_dir, DEV + TEST, workers=a.workers, quantise=a.device_quantise)
    rows = []
    try:
        sweep = []
        if a.no_search:
            best = base
        else:
            best, sweep = search(dec, base, rows, quick=a.quick)
        hot_rows = []
        if not a.no_search:
            best['hotword_bonus'] = hotword_sim(dec, best, lm, hot_rows)
        else:
            best['hotword_bonus'] = lm.params['hotword_bonus']
        report['hotword_sim'] = hot_rows
        log(f'chosen: {fmt(best)}')
        dev = dec.run(best, DEV)
        test = dec.run(best, TEST)
        report['search'] = rows
        report['beam_sweep'] = sweep
        report['params'] = dict(best)
        report['dev'] = {n: dev[n]['wer'] for n in DEV}
        report['test'] = {n: test[n]['wer'] for n in TEST}
        report['cpu_per_audio_s'] = {'dev': dev['_cpu_per_audio_s'], 'test': test['_cpu_per_audio_s']}
        report['examples'] = {n: [{'ref': sets[n]['texts'][i], 'greedy': greedy_text(sets[n]['logits'][i]),
                                   'lm': res[n]['hyps'][i]} for i in range(6)]
                              for res, names in ((dev, DEV), (test, TEST)) for n in names}
        # cost model: expansions per second of audio at the chosen params
        exp = []
        for n in DEV:
            for x in sets[n]['logits']:
                lp = hw1lm.log_softmax(x)
                exp.append(((lp[:, :28] >= best['char_prune']).sum(axis=1) + 2).mean())
        report['cost'] = {'frames_per_s': FPS, 'mean_candidates_plus2_per_beam_frame': float(np.mean(exp)),
                          'beam_expansions_per_audio_s': float(np.mean(exp) * best['beam_width'] * FPS)}
        # robustness: device-like int8 logits (scale 2^-2) with the same params
        dq = Decoder(lm_path, cache_dir, DEV + TEST, workers=a.workers,
                     quantise=a.device_quantise if a.device_quantise is not None else 2)
        try:
            q = dq.run(best, DEV + TEST)
            report['int8_logits'] = {n: q[n]['wer'] for n in DEV + TEST}
        finally:
            dq.close()
        for other in a.compare_lms:
            # fair comparison: each LM gets its own small alpha/beta grid around the tuned point
            d2 = Decoder(other, cache_dir, DEV, workers=a.workers)
            try:
                r2, o2 = None, None
                for fa in (0.7, 0.85, 1.0, 1.15, 1.3):
                    for db in (-1.0, 0.0, 1.0):
                        p2 = {**best, 'alpha': round(best['alpha'] * fa, 3), 'beta': best['beta'] + db,
                              'hotword_bonus': 0.0}
                        r = d2.run(p2, DEV)
                        if o2 is None or objective(r) < o2:
                            r2, o2, pb = r, objective(r), p2
                report.setdefault('compare_lms', {})[other] = {n: r2[n]['wer'] for n in DEV}
                report['compare_lms'][other].update(objective=o2, alpha=pb['alpha'], beta=pb['beta'])
            finally:
                d2.close()
            log(f"compare {other}: obj {report['compare_lms'][other]['objective'] * 100:.2f} "
                + '  '.join(f'{n} {r2[n]["wer"] * 100:.2f}' for n in DEV))
        report['compare_lms_reference_objective'] = objective(dev)
    finally:
        dec.close()

    out_lm = Path(a.out_lm) if a.out_lm else lm_path
    if out_lm != lm_path:
        shutil.copyfile(lm_path, out_lm)
    if not a.no_search:
        hw1lm.set_params(out_lm, **best)
    report['out_lm'] = str(out_lm)
    report['out_lm_sha256'] = hw1lm.read_lm(out_lm).sha256
    rpath = Path(a.report) if a.report else WORK / 'tune' / f'{key}.json'
    rpath.parent.mkdir(parents=True, exist_ok=True)
    rpath.write_text(json.dumps(report, indent=1))
    lines = ['| set | greedy WER | LM WER | int8-logit LM WER |', '|---|---:|---:|---:|']
    for n in DEV + TEST:
        lmw = report['dev'].get(n, report['test'].get(n))
        lines.append(f"| {n} | {greedy[n] * 100:.2f}% | {lmw * 100:.2f}% | {report['int8_logits'][n] * 100:.2f}% |")
    print('\n'.join(lines))
    log(f"params {fmt(report['params'])}; decoder {report['cpu_per_audio_s']['dev']:.3f} cpu-s per audio s; "
        f"report {rpath}; LM {out_lm}")


if __name__ == '__main__':
    main()
