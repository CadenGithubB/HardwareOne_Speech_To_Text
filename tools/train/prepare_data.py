#!/usr/bin/env python3
"""Convert downloaded corpora into flat int16 stores for fast random access.

Store layout (one directory per corpus split):
  audio.bin   concatenated 16 kHz mono int16 PCM
  index.json  {"offsets": [...], "lengths": [...], "texts": [...], "speakers": [...]}

Usage:
  prepare_data.py ami --mic sdm|ihm --split train|validation|test
  prepare_data.py librispeech --name train-clean-100|train-clean-360|dev-clean|test-clean [--fraction F]
  prepare_data.py voxpopuli --split train [--shards 8-11 --store voxpopuli-train-b]
  prepare_data.py peoples [--max-hours H]
  prepare_data.py commonvoice --split train|dev [--max-hours H]
  prepare_data.py musan
  prepare_data.py rirs
"""
import argparse
import io
import json
import hashlib
import random
import tarfile
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from common import SAMPLE_RATE, normalize_text, encode, ctc_min_frames, HOP
import os
STT_ROOT = Path(os.environ.get('STT_ROOT', 'stt-data'))  # data root: set STT_ROOT

USB = STT_ROOT
DATA = STT_ROOT
STORES = DATA / 'stores'
MIN_SECONDS, MAX_SECONDS = 0.5, 20.0


class StoreWriter:
    def __init__(self, directory):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.bin = open(self.dir / 'audio.bin.tmp', 'wb')
        self.sha = hashlib.sha256()  # of exactly what was written; verify_stores.py re-reads it from disk
        self.offsets, self.lengths, self.texts, self.speakers = [], [], [], []
        self.position = 0

    def add(self, samples, text='', speaker=''):
        pcm = np.clip(np.round(samples * 32767.0), -32768, 32767).astype('<i2')
        data = pcm.tobytes()
        self.bin.write(data)
        self.sha.update(data)
        self.offsets.append(self.position)
        self.lengths.append(len(pcm))
        self.texts.append(text)
        self.speakers.append(speaker)
        self.position += len(pcm)

    def close(self):
        self.bin.flush()
        os.fsync(self.bin.fileno())
        self.bin.close()
        (self.dir / 'audio.bin.tmp').replace(self.dir / 'audio.bin')
        (self.dir / 'index.json').write_text(json.dumps({
            'offsets': self.offsets, 'lengths': self.lengths,
            'audio_sha256': self.sha.hexdigest(),
            'texts': self.texts, 'speakers': self.speakers}))
        hours = self.position / SAMPLE_RATE / 3600
        print(f'{self.dir}: {len(self.lengths)} items, {hours:.1f} h')


def to_mono16k(data, rate):
    if data.ndim > 1:
        data = data[:, 0]
    data = data.astype(np.float32)
    if rate != SAMPLE_RATE:
        g = np.gcd(rate, SAMPLE_RATE)
        data = resample_poly(data, SAMPLE_RATE // g, rate // g).astype(np.float32)
    return data


def usable(samples, text):
    seconds = len(samples) / SAMPLE_RATE
    if not text or not (MIN_SECONDS <= seconds <= MAX_SECONDS):
        return False
    # Model emits one frame per 2 feature frames; CTC needs room for labels.
    return ctc_min_frames(encode(text)) <= (len(samples) // HOP) // 2 - 1


def prepare_ami(mic, split):
    import pyarrow.parquet as pq
    files = sorted((USB / 'ami' / mic).glob(f'{split}-*.parquet'))
    if not files:
        raise SystemExit(f'no AMI {mic}/{split} parquet files yet')
    writer = StoreWriter(STORES / f'ami-{mic}-{split}')
    kept = dropped = 0
    for path in files:
        pf = pq.ParquetFile(path)
        for batch in pf.iter_batches(batch_size=256, columns=['text', 'audio', 'speaker_id']):
            for row in batch.to_pylist():
                data, rate = sf.read(io.BytesIO(row['audio']['bytes']), dtype='float32')
                samples = to_mono16k(data, rate)
                text = normalize_text(row['text'])
                if usable(samples, text):
                    writer.add(samples, text, row['speaker_id'])
                    kept += 1
                else:
                    dropped += 1
    writer.close()
    print(f'kept {kept}, dropped {dropped}')


LIBRI_PARTS = {'train-clean-100': 'train.100', 'train-clean-360': 'train.360',
               'dev-clean': 'validation', 'test-clean': 'test'}


def prepare_librispeech(name, fraction=1.0):
    """From the Hugging Face parquet mirror (openslr/librispeech_asr, clean).

    fraction < 1 keeps a seeded random share of utterances from EVERY shard,
    so a subset still covers all speakers (store name gets the share, e.g.
    librispeech-train-clean-360-p28)."""
    import pyarrow.parquet as pq
    part = LIBRI_PARTS[name]
    files = sorted((USB / 'librispeech').glob(f'clean_{part}_*.parquet'))
    if not files:
        return prepare_librispeech_tar(name)
    suffix = '' if fraction >= 1.0 else f'-p{round(fraction * 100)}'
    writer = StoreWriter(STORES / f'librispeech-{name}{suffix}')
    pick = random.Random(360)
    for path in files:
        for batch in pq.ParquetFile(path).iter_batches(batch_size=128, columns=['audio', 'text', 'speaker_id']):
            for row in batch.to_pylist():
                if fraction < 1.0 and pick.random() >= fraction:
                    continue
                data, rate = sf.read(io.BytesIO(row['audio']['bytes']), dtype='float32')
                samples = to_mono16k(data, rate)
                text = normalize_text(row['text'])
                if usable(samples, text):
                    writer.add(samples, text, str(row['speaker_id']))
    writer.close()


def prepare_librispeech_tar(name):
    archive = USB / 'librispeech' / f'{name}.tar.gz'
    writer = StoreWriter(STORES / f'librispeech-{name}')
    transcripts, pending = {}, {}
    with tarfile.open(archive, 'r|gz') as tar:
        for member in tar:
            if not member.isfile():
                continue
            data = tar.extractfile(member).read()
            if member.name.endswith('.trans.txt'):
                for line in data.decode().splitlines():
                    uid, text = line.split(' ', 1)
                    transcripts[uid] = normalize_text(text)
                    if uid in pending:
                        samples = pending.pop(uid)
                        if usable(samples, transcripts[uid]):
                            writer.add(samples, transcripts[uid], uid.split('-')[0])
            elif member.name.endswith('.flac'):
                uid = Path(member.name).stem
                audio, rate = sf.read(io.BytesIO(data), dtype='float32')
                samples = to_mono16k(audio, rate)
                if uid in transcripts:
                    if usable(samples, transcripts[uid]):
                        writer.add(samples, transcripts[uid], uid.split('-')[0])
                else:
                    pending[uid] = samples
    writer.close()


def prepare_voxpopuli(split, max_hours, shards=None, store=None):
    """VoxPopuli English parliament speech (HF parquet conversion, CC0).

    raw_text keeps digits and acronyms ("EU", "2019") that are spoken
    differently from how they are written, so those utterances are skipped
    rather than trained on wrong letters."""
    import re
    import pyarrow.parquet as pq
    files = sorted(p for p in (USB / 'voxpopuli').glob(f'{split}_*.parquet')
                   if Path(str(p) + '.done').exists())
    if shards:  # e.g. "8-11": only those shard numbers (a new store beside the old one)
        lo, hi = (int(x) for x in shards.split('-'))
        files = [p for p in files if lo <= int(p.stem.split('_')[-1]) <= hi]
    if not files:
        raise SystemExit(f'no VoxPopuli {split} parquet files yet')
    writer = StoreWriter(STORES / (store or f'voxpopuli-{split}'))
    budget = max_hours * 3600 * SAMPLE_RATE
    kept = dropped = 0
    unspoken = re.compile(r'[0-9]|[A-Z]{2,}|[%&@/$€£+=]')
    for path in files:
        for batch in pq.ParquetFile(path).iter_batches(
                batch_size=64, columns=['audio', 'raw_text', 'speaker_id', 'is_gold_transcript']):
            for row in batch.to_pylist():
                raw = row['raw_text'] or ''
                if not row['is_gold_transcript'] or unspoken.search(raw):
                    dropped += 1
                    continue
                data, rate = sf.read(io.BytesIO(row['audio']['bytes']), dtype='float32')
                samples = to_mono16k(data, rate)
                text = normalize_text(raw)
                if usable(samples, text):
                    writer.add(samples, text, str(row['speaker_id']))
                    kept += 1
                else:
                    dropped += 1
                if writer.position >= budget:
                    break
            if writer.position >= budget:
                break
        if writer.position >= budget:
            break
    writer.close()
    print(f'kept {kept}, dropped {dropped}')


def prepare_musan():
    archive = DATA / 'musan' / 'musan.tar.gz'
    noise = StoreWriter(STORES / 'musan-noise')   # noise + music
    speech = StoreWriter(STORES / 'musan-speech')  # babble source
    with tarfile.open(archive, 'r|gz') as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith('.wav'):
                continue
            kind = member.name.split('/')[1]
            audio, rate = sf.read(io.BytesIO(tar.extractfile(member).read()), dtype='float32')
            samples = to_mono16k(audio, rate)
            # Keep at most 60 s per file so no single recording dominates.
            samples = samples[:60 * SAMPLE_RATE]
            if len(samples) < SAMPLE_RATE:
                continue
            (speech if kind == 'speech' else noise).add(samples, kind)
    noise.close()
    speech.close()


def prepare_rirs(limit=4000):
    archive = DATA / 'rirs' / 'rirs_noises.zip'
    writer = StoreWriter(STORES / 'rirs')
    rng = random.Random(0)
    with zipfile.ZipFile(archive) as zf:
        names = [n for n in zf.namelist() if n.endswith('.wav') and
                 ('simulated_rirs/' in n or ('real_rirs_isotropic_noises/' in n and 'rir' in Path(n).name.lower()))]
        sim = [n for n in names if 'simulated_rirs/' in n]
        real = [n for n in names if 'simulated_rirs/' not in n]
        chosen = real + rng.sample(sim, min(limit, len(sim)))
        for name in chosen:
            audio, rate = sf.read(io.BytesIO(zf.read(name)), dtype='float32')
            samples = to_mono16k(audio, rate)
            peak = np.abs(samples).max()
            if peak <= 0:
                continue
            samples = samples / peak * 0.99
            writer.add(samples[:2 * SAMPLE_RATE], 'real' if name in real else 'sim')
    writer.close()


def prepare_peoples(max_hours, split='train', fraction=1.0, store=None, shards=None):
    """People's Speech "clean" (MLCommons, CC-BY/CC-BY-SA): mostly public
    meetings, interviews and talks. Text is already lowercase with numbers
    spelled out; anything else outside the alphabet is skipped, not mapped."""
    import re
    import pyarrow.parquet as pq
    files = sorted(p for p in (USB / 'peoples_speech').glob(f'clean_{split}_*.parquet')
                   if Path(str(p) + '.done').exists())
    if shards == 'new':  # download.sh peoples2: everything except the first 30 (k*804/30)
        first = {k * 804 // 30 for k in range(30)}
        files = [p for p in files if int(p.stem.split('_')[-1]) not in first]
    if not files:
        raise SystemExit('no People\'s Speech parquet files yet')
    out = STORES / (store or f'peoples-clean-{split}')
    if (out / 'index.json').exists():
        raise SystemExit(f'{out.name} exists; refusing to overwrite it (keep.json, held-out dev views)')
    writer = StoreWriter(out)
    pick = random.Random(31)  # fraction < 1: a seeded share of every shard
    budget = max_hours * 3600 * SAMPLE_RATE
    kept = dropped = 0
    foreign = re.compile(r"[^a-z' ]")
    for path in files:
        for batch in pq.ParquetFile(path).iter_batches(batch_size=64, columns=['id', 'audio', 'text']):
            for row in batch.to_pylist():
                if fraction < 1.0 and pick.random() >= fraction:
                    continue
                raw = (row['text'] or '').strip()
                if not raw or foreign.search(raw):
                    dropped += 1
                    continue
                data, rate = sf.read(io.BytesIO(row['audio']['bytes']), dtype='float32')
                samples = to_mono16k(data, rate)
                text = normalize_text(raw)
                if usable(samples, text):
                    writer.add(samples, text, row['id'].rsplit('_', 1)[0])  # source recording as "speaker"
                    kept += 1
                else:
                    dropped += 1
                if writer.position >= budget:
                    break
            if writer.position >= budget:
                break
        if writer.position >= budget:
            break
    writer.close()
    print(f'kept {kept}, dropped {dropped}')


def prepare_commonvoice(split, max_hours):
    """Common Voice 17 English (CC0; unofficial HF mirror fsicoli/common_voice_17_0,
    as downloaded by download.sh cv): tar shards of 48 kHz MP3 + {split}.tsv.
    Thousands of speakers reading on their own phones/laptops. Sentences with
    digits or non-ASCII letters are skipped (normalisation would turn "1990"
    into nothing and "cafe" with an accent into "caf"); curly apostrophes are
    straightened. Store: commonvoice-en-train, or commonvoice-en-test for the
    dev split (never trained on; a held-out accent/microphone test)."""
    import csv
    import re
    root = USB / 'common_voice' / 'en'
    tars = sorted(p for p in root.glob(f'en_{split}_*.tar') if Path(str(p) + '.done').exists())
    if not tars:
        raise SystemExit(f'no Common Voice {split} tars yet')
    rows = {}
    with open(root / f'{split}.tsv', newline='') as f:
        for r in csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE):
            rows[r['path']] = (r['sentence'], r['client_id'])
    name = 'commonvoice-en-train' if split == 'train' else 'commonvoice-en-test'
    writer = StoreWriter(STORES / name)
    budget = max_hours * 3600 * SAMPLE_RATE
    bad = re.compile(r'[0-9]|[^\x00-\x7f]')
    kept = dropped = 0
    for t in tars:
        with tarfile.open(t) as tf:
            for m in tf:
                if not m.isfile() or not m.name.endswith('.mp3'):
                    continue
                row = rows.get(Path(m.name).name)
                if row is None:
                    dropped += 1
                    continue
                raw = row[0].replace('\u2019', "'").replace('\u2018', "'")
                if bad.search(raw):
                    dropped += 1
                    continue
                data, rate = sf.read(io.BytesIO(tf.extractfile(m).read()), dtype='float32')
                samples = to_mono16k(data, rate)
                text = normalize_text(raw)
                if usable(samples, text):
                    writer.add(samples, text, row[1][:16])
                    kept += 1
                else:
                    dropped += 1
                if writer.position >= budget:
                    break
        if writer.position >= budget:
            break
    writer.close()
    print(f'kept {kept}, dropped {dropped}')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('corpus', choices=['ami', 'librispeech', 'voxpopuli', 'peoples', 'commonvoice', 'musan', 'rirs'])
    p.add_argument('--fraction', type=float, default=1.0, help='librispeech: share of utterances to keep')
    p.add_argument('--shards', help="voxpopuli: shard range, e.g. 8-11; peoples: 'new' = the peoples2 shards")
    p.add_argument('--store', help='voxpopuli / peoples: output store name')
    p.add_argument('--max-hours', type=float, default=120.0)
    p.add_argument('--mic')
    p.add_argument('--split')
    p.add_argument('--name')
    a = p.parse_args()
    if a.corpus == 'ami':
        prepare_ami(a.mic, a.split)
    elif a.corpus == 'librispeech':
        prepare_librispeech(a.name, a.fraction)
    elif a.corpus == 'voxpopuli':
        prepare_voxpopuli(a.split, a.max_hours, a.shards, a.store)
    elif a.corpus == 'commonvoice':
        prepare_commonvoice(a.split or 'train', a.max_hours)
    elif a.corpus == 'peoples':
        prepare_peoples(a.max_hours, a.split or 'train', a.fraction, a.store, a.shards)
    elif a.corpus == 'musan':
        prepare_musan()
    else:
        prepare_rirs()


if __name__ == '__main__':
    main()
