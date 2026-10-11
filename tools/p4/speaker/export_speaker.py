#!/usr/bin/env python3
"""Fast ResNet-34 speaker trunk -> ESP-DL (esp-ppq, 8-bit weights / 16-bit activations), checked with the device's
own rules, and packed as speaker.spk for the P4.

  export_speaker.py [--quant-type w8a16] [--out DIR] [--convs 21]

Device contract (stt/speaker_frontend.h, speaker_model.h, speaker_cluster.h):
- features: the centre (frames-1)*160 samples of a longer phrase, 40 log-mel (400-sample Hamming in a 512 FFT,
  hop 160, HTK mel 0-8 kHz, log(x+1e-6)), each band normalised over those frames; a shorter phrase's frames are
  repeated to fill the window;
- ESP-DL runs the convolution trunk on [1, 40, frames, 1] -> [1, frames/4, 128];
- the device does attention pooling + projection (128 -> 512) in float from the head weights;
- labels: join the closest speaker at cosine >= threshold; below it a phrase >= 2 s starts a speaker, a shorter
  one is a tentative label for the closest speaker that does not update it.
Calibration uses train stores only; the threshold is chosen on the dev stores (-g2 = simulated glasses).
Writes speaker.spk, speaker_trunk.espdl, fixture.bin (a test phrase's PCM + its expected embedding), report.json.
Numbers only.
"""
import argparse
import hashlib
import json
import random
import struct
import sys
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))   # experiments/stt_p4: export_quartznet.metadata
import proto  # noqa: E402

FRAMES, HOP = 300, 160
MIN_NEW_S = 2.0


class Trunk(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, x):
        return self.m.trunk(x)


def feats_for(x):
    """PCM float [N] -> [1, 1, 40, FRAMES] exactly as the device front end."""
    span = (FRAMES - 1) * HOP
    if len(x) > span:
        s = (len(x) - span) // 2
        x = x[s:s + span]
    f = proto.features(x)
    t = f.shape[-1]
    if t < FRAMES:
        f = f[..., torch.arange(FRAMES) % t]
    return f[..., :FRAMES]


def device_labels(embs, durs, threshold, max_speakers=8):
    sums, labels = [], []
    for e, d in zip(embs, durs):
        if not sums:
            sums.append(e.copy()); labels.append(0); continue
        sims = [float(np.dot(e, s / np.linalg.norm(s))) for s in sums]
        j = int(np.argmax(sims))
        if sims[j] < threshold and len(sums) < max_speakers and d >= MIN_NEW_S:
            sums.append(e.copy()); labels.append(len(sums) - 1); continue
        labels.append(j)
        if sims[j] >= threshold:
            sums[j] = sums[j] + e
    return labels


def calibration(n, seed=2026):
    rng = random.Random(seed)
    out = []
    for store in ['ami-ihm-train', 'librispeech-train-clean-100', 'voxpopuli-train']:
        d, audio = proto.load_store(store)
        idx = [i for i, L in enumerate(d['lengths']) if 1.0 <= L / proto.SR <= 10.0]
        for i in rng.sample(idx, n // 3):
            off, L = d['offsets'][i], d['lengths'][i]
            out.append(feats_for(np.asarray(audio[off:off + L], dtype=np.float32) / 32768.0))
    return out


HDR = '<8sIIHHHHHHffffHHHHIIIIfI'


def pack(out, trunk_path, head, threshold):
    """speaker.spk: 128-byte header, head floats, 16-byte aligned ESP-DL model, SHA-256 of all before it."""
    trunk = trunk_path.read_bytes()
    head_bytes = b''.join(t.detach().numpy().astype('<f4').tobytes() for t in head)
    head_off = 128
    trunk_off = (head_off + len(head_bytes) + 15) // 16 * 16
    hdr = struct.pack(HDR, b'HW1SPK1\0', 1, 128,
                      40, 512, 400, 160, FRAMES, 0, 0.0, 8000.0, 1e-6, 1e-5,
                      128, 512, 1, 0,                      # trunk channels, embedding dim, pooling 1 = SAP, reserved
                      head_off, len(head_bytes), trunk_off, len(trunk),
                      float(threshold), int(MIN_NEW_S * 1000)).ljust(128, b'\0')
    body = hdr + head_bytes + b'\0' * (trunk_off - head_off - len(head_bytes)) + trunk
    blob = body + hashlib.sha256(body).digest()
    (out / 'speaker.spk').write_bytes(blob)
    return blob


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quant-type', default='w8a16', choices=['w8a8', 'w8a16'])
    ap.add_argument('--calib', type=int, default=128)
    ap.add_argument('--out', default=str(proto.STT / 'hw1-work/speaker/export_final'))
    ap.add_argument('--convs', type=int, default=21)
    a = ap.parse_args()
    torch.set_num_threads(2)
    out = Path(a.out); out.mkdir(exist_ok=True)
    model = proto.load_model()
    trunk = Trunk(model).eval()
    calib = calibration(a.calib)
    from esp_ppq.api import espdl_quantize_torch
    from esp_ppq import TorchExecutor
    from export_quartznet import metadata
    export = out / 'speaker_trunk.espdl'
    graph = espdl_quantize_torch(model=trunk, espdl_export_file=str(export), calib_dataloader=calib,
                                 calib_steps=len(calib), input_shape=[1, 1, 40, FRAMES], inputs=[calib[0]],
                                 target='esp32p4', quant_type=a.quant_type, device='cpu', error_report=False,
                                 export_test_values=True, verbose=0)
    info = metadata(export)
    ex = TorchExecutor(graph=graph, device='cpu')

    def emb(x, quant):
        with torch.inference_mode():
            f = feats_for(x)
            e = (model.pool(ex.forward(inputs=f)[0].detach()) if quant else model(f))[0].numpy()
        return e / np.linalg.norm(e)

    report = {'operators': sorted(info['operators']), 'quant_type': a.quant_type, 'frames': FRAMES,
              'trunk_bytes': export.stat().st_size, 'min_new_s': MIN_NEW_S, 'stores': {}}
    thresholds = [round(x, 2) for x in np.arange(0.30, 0.81, 0.05)]
    pooled = {th: [] for th in thresholds}
    for store in ['librispeech-dev-clean-g2', 'ami-ihm-validation-g2', 'voxpopuli-dev-g2']:
        d, audio, convs = proto.conversations(store, a.convs, 24, seed=20261011)
        cache, rows = {}, []
        for conv in convs:
            embs, true, durs = [], [], []
            for s, i in conv:
                if i not in cache:
                    off, L = d['offsets'][i], d['lengths'][i]
                    x = np.asarray(audio[off:off + L], dtype=np.float32) / 32768.0
                    cache[i] = (emb(x, True), emb(x, False))
                embs.append(cache[i][0]); true.append(s); durs.append(d['lengths'][i] / proto.SR)
            rows.append((embs, true, durs))
        cos = [float(np.dot(q, f)) for q, f in cache.values()]
        res = {'int8_vs_float_cosine_median': round(float(np.median(cos)), 4), 'min': round(float(np.min(cos)), 4)}
        for rule in ('plain', 'device'):
            best = None
            for th in thresholds:
                preds = [proto.online_labels(e, th) if rule == 'plain' else device_labels(e, du, th) for e, t, du in rows]
                acc = float(np.mean([proto.best_accuracy(t, p) for (e, t, du), p in zip(rows, preds)]))
                cnt = float(np.mean([abs(len(set(p)) - len(set(t))) for (e, t, du), p in zip(rows, preds)]))
                if rule == 'device':
                    pooled[th].append(acc)
                if best is None or acc > best[1]:
                    best = (th, acc, cnt)
            res[rule] = {'threshold': best[0], 'accuracy': round(100 * best[1], 1), 'count_error': round(best[2], 2)}
        report['stores'][store] = res
        print(store, json.dumps(res), flush=True)
    th = max(thresholds, key=lambda t: np.mean(pooled[t]))
    report['threshold'] = th
    report['pooled_device_accuracy'] = round(100 * float(np.mean(pooled[th])), 1)
    head = [model.sap_linear.weight, model.sap_linear.bias, model.attention.view(-1), model.fc.weight, model.fc.bias]
    blob = pack(out, export, head, th)
    report['spk_bytes'] = len(blob)
    report['spk_sha256'] = hashlib.sha256(blob).hexdigest()
    # Device parity fixture: one 2.6 s dev phrase as int16 + the expected unit embedding (16-bit path).
    d, audio = proto.load_store('librispeech-dev-clean')
    i = next(k for k, L in enumerate(d['lengths']) if 2.5 * proto.SR <= L <= 2.8 * proto.SR)
    pcm = np.asarray(audio[d['offsets'][i]:d['offsets'][i] + d['lengths'][i]], dtype='<i2')
    e = emb(pcm.astype(np.float32) / 32768.0, True).astype('<f4')
    (out / 'fixture.bin').write_bytes(struct.pack('<II', len(pcm), len(e)) + pcm.tobytes() + e.tobytes())
    report['fixture'] = {'store': 'librispeech-dev-clean', 'samples': len(pcm)}
    print('threshold', th, 'pooled device-rule accuracy', report['pooled_device_accuracy'], 'spk bytes',
          report['spk_bytes'], flush=True)
    (out / 'report.json').write_text(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
