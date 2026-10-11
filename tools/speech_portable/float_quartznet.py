#!/usr/bin/env python3
"""Host-only float sanity decoder for the inspected QuartzNet-5x5 checkpoint.

Implements the checkpoint's fixed topology with tensor-only loading. Reference
semantics: NVIDIA NeMo v1.0.0rc1 parts/features.py and parts/jasper.py. This is
an independent experimental decoder, not a substitute for official NeMo parity
or an accuracy benchmark. Inputs must be mono 16 kHz WAV, at most 30 seconds.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import urllib.request
import numpy as np
import soundfile as sf
import torch
import torch.nn.functional as F
import yaml

HERE = Path(__file__).resolve().parent
EXPECTED_WEIGHTS = '51a92f946c8cccacb723f4291be1f3285d589e5ac84fa0f6714221dbbbf333cb'
EXPECTED_CONFIG = '1e829dd42c31d4c55d2bcf844c8abbf664ba6f1b767a9e6c8e8d26672ae5ab58'


FIXTURES = [{'name': '0.wav', 'url': 'https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-en-20M-2023-02-17/resolve/d42f2d9/test_wavs/0.wav', 'bytes': 212044, 'sha256': '6bc58a4efdf20daac252b6b1502632601a71efe0308f6757dc1eda34891a7e4f'}, {'name': '1.wav', 'url': 'https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-en-20M-2023-02-17/resolve/d42f2d9/test_wavs/1.wav', 'bytes': 534924, 'sha256': '5143a6ba93c4b274e2c4ac22deb75c2c48936c853f0519add1de828b6c79cc5a'}, {'name': 'trans.txt', 'url': 'https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-en-20M-2023-02-17/resolve/d42f2d9/test_wavs/trans.txt', 'bytes': 449, 'sha256': 'b9ac44e7b794abb1a2d5faf0005e98a665971e7ac2ed15435832cc34edaa9100'}]

class Decoder:
    def __init__(self, directory):
        for name, wanted in [('model_weights.ckpt', EXPECTED_WEIGHTS), ('model_config.yaml', EXPECTED_CONFIG)]:
            if hashlib.sha256((directory / name).read_bytes()).hexdigest() != wanted:
                raise ValueError('Inspected checkpoint mismatch: ' + name)
        self.cfg = yaml.safe_load((directory / 'model_config.yaml').read_text())
        self.state = torch.load(directory / 'model_weights.ckpt', map_location='cpu', weights_only=True)
        self.used = set()

    def tensor(self, name):
        self.used.add(name)
        return self.state[name]

    @staticmethod
    def mask(x, length):
        if length < x.shape[-1]:
            x = x.clone(); x[:, :, length:] = 0
        return x

    def conv(self, x, length, name, stride=1, dilation=1):
        x = self.mask(x, length)
        weight = self.tensor(name + '.weight')
        bias = self.tensor(name + '.bias') if name + '.bias' in self.state else None
        kernel = weight.shape[-1]
        groups = x.shape[1] if weight.shape[1] == 1 and x.shape[1] > 1 else 1
        padding = dilation * (kernel - 1) // 2
        x = F.conv1d(x, weight, bias, stride=stride, padding=padding, dilation=dilation, groups=groups)
        return x, (length + stride - 1) // stride

    def norm(self, x, name):
        return F.batch_norm(x, self.tensor(name + '.running_mean'), self.tensor(name + '.running_var'),
                            self.tensor(name + '.weight'), self.tensor(name + '.bias'), training=False, eps=1e-3)

    def features(self, samples):
        torch.manual_seed(0)
        x = torch.from_numpy(samples.copy()).unsqueeze(0)
        x = x + 1e-5 * torch.randn_like(x)
        x = torch.cat((x[:, :1], x[:, 1:] - 0.97 * x[:, :-1]), dim=1)
        length = math.ceil(x.shape[-1] / 160)
        spectrum = torch.stft(x, n_fft=512, hop_length=160, win_length=320,
                              window=self.tensor('preprocessor.featurizer.window'),
                              center=True, return_complex=True)
        mel = torch.matmul(self.tensor('preprocessor.featurizer.fb'), spectrum.abs().square())
        x = torch.log(mel + 2**-24)
        valid = x[:, :, :length]
        x = (x - valid.mean(dim=-1, keepdim=True)) / (valid.std(dim=-1, keepdim=True) + 1e-5)
        x = self.mask(x, length)
        x = F.pad(x, (0, (-x.shape[-1]) % 16))
        return x, length

    @torch.inference_mode()
    def decode(self, samples):
        x, length = self.features(samples)
        for index, block in enumerate(self.cfg['encoder']['params']['jasper']):
            prefix = f'encoder.encoder.{index}'
            residual, original_length = x, length
            repeat = block['repeat']
            separable = block.get('separable', False)
            width = 5 if separable else 4
            for iteration in range(repeat):
                offset = width * iteration
                x, length = self.conv(x, length, f'{prefix}.mconv.{offset}.conv',
                                      stride=block['stride'][0], dilation=block['dilation'][0])
                if separable:
                    x, length = self.conv(x, length, f'{prefix}.mconv.{offset + 1}.conv')
                x = self.norm(x, f'{prefix}.mconv.{offset + (2 if separable else 1)}')
                if iteration + 1 < repeat:
                    x = F.relu(x)
            if block.get('residual'):
                residual, _ = self.conv(residual, original_length, prefix + '.res.0.0.conv')
                residual = self.norm(residual, prefix + '.res.0.1')
                x = x + residual
            x = F.relu(x)
        logits, length = self.conv(x, length, 'decoder.decoder_layers.0')
        ids = logits[0, :, :length].argmax(dim=0).tolist()
        vocabulary = self.cfg['decoder']['params']['vocabulary']
        previous = None; text = []
        for value in ids:
            if value != previous and value < len(vocabulary):
                text.append(vocabulary[value])
            previous = value
        unused = [name for name in self.state if name not in self.used and not name.endswith('.num_batches_tracked')]
        if unused:
            raise ValueError('Unexpected unused checkpoint tensors: ' + str(unused))
        return ''.join(text).strip()


def distance(reference, hypothesis):
    row = list(range(len(hypothesis) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, row[j] + 1, row[j-1] + (left != right)))
        row = current
    return row[-1]


def fetch_fixtures(directory):
    destination = directory / 'fixtures'
    destination.mkdir(parents=True, exist_ok=True)
    for record in FIXTURES:
        path = destination / record['name']
        if path.exists():
            data = path.read_bytes()
        else:
            with urllib.request.urlopen(record['url'], timeout=30) as response:
                data = response.read(record['bytes'] + 1)
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Public fixture changed: ' + record['name'])
        if not path.exists():
            path.write_bytes(data)
    (destination / 'manifest.json').write_text(json.dumps(FIXTURES, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=HERE / 'private/stt-quartznet')
    parser.add_argument('--wav', type=Path, nargs='+')
    parser.add_argument('--fetch-fixtures', action='store_true')
    args = parser.parse_args()
    if args.fetch_fixtures:
        fetch_fixtures(args.directory)
    if args.wav is None:
        if not args.fetch_fixtures:
            parser.error('Provide --wav or --fetch-fixtures')
        args.wav = [args.directory / ('fixtures/' + name) for name in ('0.wav', '1.wav')]
    torch.set_num_threads(4)
    model = Decoder(args.directory)
    references = {}
    source = args.directory / 'fixtures/trans.txt'
    if source.exists():
        references = dict(line.split(' ', 1) for line in source.read_text().splitlines() if line)
    results = []
    for path in args.wav:
        data, rate = sf.read(path, dtype='float32', always_2d=False)
        if rate != 16000 or data.ndim != 1 or not (320 <= len(data) <= rate * 30) or not np.isfinite(data).all():
            raise ValueError('Expected finite mono 16 kHz audio up to 30 seconds')
        start = time.perf_counter(); text = model.decode(data); elapsed = time.perf_counter() - start
        reference = references.get(path.name, '').lower()
        error = distance(reference.split(), text.split()) if reference else None
        item = {'file': path.name, 'wav_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'duration_seconds': len(data)/rate, 'host_inference_seconds': elapsed,
                'host_real_time_factor': elapsed/(len(data)/rate), 'transcript': text,
                'reference': reference, 'word_errors': error, 'reference_words': len(reference.split())}
        results.append(item)
    report = {'scope': 'Host float sanity experiment; no official-runtime parity or P4 qualification',
              'torch_version': torch.__version__, 'threads': 4, 'results': results}
    (args.directory / 'float-results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
