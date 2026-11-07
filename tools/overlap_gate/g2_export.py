"""Export the selected G2 checkpoint to ESP-DL int8 (esp32p4, W8A8) and verify it.

Steps: fold the fixed input normalization and every BatchNorm into convolution weights/biases;
build an equivalent 2-D graph (kernels k x 1 on input [1, 64, T, 1], the layout the recognizer
export already uses); check the folded float graph against the training model; quantize with
calibration windows drawn from the training sampler only; verify the embedded test fixture through
a clean native reload; check variable input lengths; run the static named-activation screen; and
measure int8 versus float frame ROC area on the fixed validation subsample. Holds the export lock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overlap_gate import labels, scorer  # noqa: E402
from overlap_gate import g2_common as g2  # noqa: E402

ROOT = g2.ROOT
R2 = ROOT / 'private/training-track/compact16k-round2'
BUDGET = dict(max_parameters=50000, max_weight_bytes=100000, max_arena_bytes=524288)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def fold_bn(conv_w: torch.Tensor, conv_b, bn: nn.BatchNorm1d):
    scale = bn.weight / torch.sqrt(bn.running_var + bn.eps)
    w = conv_w * scale.view(-1, 1, 1)
    b = (conv_b if conv_b is not None else torch.zeros_like(bn.running_mean)) - bn.running_mean
    return w, b * scale + bn.bias


class Folded(nn.Module):
    """Plain Conv2d/ReLU/Add graph equal to G2Net with BN folded in.

    The fixed input normalization stays a separate depthwise 1x1 layer (64 weights, 64 biases)
    rather than being folded into the stem: the stem zero-pads its input, and the trained model
    pads *normalized* values, so folding would change the first and last two output frames.
    """

    def __init__(self, m: g2.G2Net):
        super().__init__()
        with torch.no_grad():
            self.norm = nn.Conv2d(g2.MELS, g2.MELS, (1, 1), groups=g2.MELS)
            self.norm.weight.copy_((1.0 / m.std.view(-1)).view(g2.MELS, 1, 1, 1))
            self.norm.bias.copy_(-(m.mean.view(-1) / m.std.view(-1)))
            w, b = fold_bn(m.stem.weight, None, m.stem_bn)
            self.stem = nn.Conv2d(g2.MELS, w.shape[0], (5, 1), stride=(2, 1), padding=(2, 0))
            self.stem.weight.copy_(w.unsqueeze(-1))
            self.stem.bias.copy_(b)
            self.blocks = nn.ModuleList()
            for blk in m.blocks:
                d = blk.dw.dilation[0]
                dw = nn.Conv2d(w.shape[0], w.shape[0], (7, 1), padding=(3 * d, 0), dilation=(d, 1), groups=w.shape[0], bias=False)
                dw.weight.copy_(blk.dw.weight.unsqueeze(-1))
                pw_w, pw_b = fold_bn(blk.pw.weight, None, blk.bn)
                pw = nn.Conv2d(w.shape[0], w.shape[0], (1, 1))
                pw.weight.copy_(pw_w.unsqueeze(-1))
                pw.bias.copy_(pw_b)
                self.blocks.append(nn.ModuleList([dw, pw]))
            self.head = nn.Conv2d(w.shape[0], g2.CLASSES, (1, 1))
            self.head.weight.copy_(m.head.weight.unsqueeze(-1))
            self.head.bias.copy_(m.head.bias)

    def forward(self, x):                                                          # x: [B, 64, T, 1] raw log-mel
        x = torch.relu(self.stem(self.norm(x)))
        for dw, pw in self.blocks:
            x = torch.relu(pw(dw(x)) + x)
        return self.head(x)                                                        # [B, 3, ceil(T/2), 1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--phase3', type=Path, default=g2.PHASE3)
    args = ap.parse_args()
    out = args.phase3 / 'export-int8'
    out.mkdir(parents=True, exist_ok=True)
    sys.path[:0] = [str(R2), str(ROOT / 'private/training-track/overlap-ab'), str(ROOT / 'private/training-track/overlap-ab/deps')]
    from resources import acquire
    lock = acquire('export')  # noqa: F841
    torch.set_num_threads(1)

    sel = json.loads((args.phase3 / 'selection.json').read_text())['selected']
    ck_path = args.phase3 / sel['checkpoint']
    assert sha(ck_path.read_bytes()) == sel['sha256']
    ck = torch.load(ck_path, weights_only=True, map_location='cpu')
    model = g2.G2Net(ck['mean'], ck['std'], **ck.get('arch', {}))
    model.load_state_dict(ck['state_dict'])
    model.eval()
    folded = Folded(model).eval()
    frontend = g2.RawFrontend()

    # Folded float graph must reproduce the training model.
    sampler = g2.Sampler(seed=2)
    feats, _t, _m = sampler.batch(8)
    with torch.inference_mode():
        ref = model(feats)
        got = folded(feats.unsqueeze(-1))[..., 0]
    fold_err = float((ref - got).abs().max())
    assert fold_err < 1e-3, fold_err

    # Calibration from training windows only.
    cal = []
    for _ in range(4):
        f, _t, _m = sampler.batch(8)
        cal.extend(x[None, :, :, None] for x in f)
    onnx_file = out / 'g2.onnx'
    torch.onnx.export(folded, (cal[0],), str(onnx_file), opset_version=18, do_constant_folding=True, dynamo=False,
                      input_names=['features'], output_names=['logits'], dynamic_axes={'features': {2: 'frames'}, 'logits': {2: 'frames2'}})
    from esp_ppq.api import espdl_quantize_onnx, export_ppq_graph, load_native_graph
    from esp_ppq import TorchExecutor, TargetPlatform, lib as PFL
    from esp_ppq.api.espdl_interface import generate_test_value
    from export_quartznet import metadata
    from FlatBuffers.Dl.Model import Model, ModelT
    shape = list(cal[0].shape)
    graph = espdl_quantize_onnx(onnx_import_file=str(onnx_file), espdl_export_file=str(out / 'g2-fixed.espdl'), calib_dataloader=cal, calib_steps=32,
                                input_shape=shape, inputs=[cal[0]], target='esp32p4', quant_type='w8a8', device='cpu', error_report=False,
                                export_test_values=True, verbose=0)
    export_ppq_graph(graph, TargetPlatform.NATIVE, str(out / 'g2.native'))
    native = load_native_graph(str(out / 'g2.native'))
    meta = metadata(out / 'g2-fixed.espdl')
    fixed = ModelT.InitFromObj(Model.GetRootAs((out / 'g2-fixed.espdl').read_bytes(), 16)).graph
    blob = lambda t: b''.join(bytes(c.bytes) for c in t.rawData)  # noqa: E731
    in_exp, out_exp = meta['inputs'][0]['exponents'][0], meta['outputs'][0]['exponents'][0]
    # ESP-DL stores test tensors channel-last: input [1, T, 1, 64], output [1, T/2, 1, 3].
    assert meta['inputs'][0]['shape'] == [1, shape[2], 1, g2.MELS], meta['inputs'][0]['shape']
    nhwc = np.frombuffer(blob(fixed.testInputsValue[0]), 'i1')[:int(np.prod(shape))].astype(np.float32).reshape(1, shape[2], 1, g2.MELS)
    ix = np.ascontiguousarray(nhwc.transpose(0, 3, 1, 2)) * 2.0 ** in_exp          # -> NCHW for the executor
    n_out = g2.CLASSES * ((shape[2] + 1) // 2)
    expected = np.frombuffer(blob(fixed.testOutputsValue[0]), 'i1')[:n_out]

    def quantized(executor, x):
        with torch.inference_mode():
            y = executor.forward(inputs=torch.from_numpy(x))[0].numpy()
        assert np.isfinite(y).all()
        return np.rint(y / 2.0 ** out_exp).clip(-128, 127).astype('i1').transpose(0, 2, 3, 1).reshape(-1)   # NHWC byte order

    executor = TorchExecutor(graph=native, device='cpu')
    assert np.array_equal(quantized(executor, ix), expected), 'embedded fixture mismatch'
    shapes = []
    with torch.inference_mode():
        for frames in (200, 301, 1000, 2000):
            x = np.resize(ix, (1, g2.MELS, frames, 1)).copy()
            y = executor.forward(inputs=torch.from_numpy(x))[0]
            assert torch.isfinite(y).all() and list(y.shape) == [1, g2.CLASSES, (frames + 1) // 2, 1], list(y.shape)
            shapes.append(dict(frames=frames, output=list(y.shape)))
    executor.tracing_operation_meta(inputs=torch.from_numpy(ix))
    values = generate_test_value(graph, 'cpu', torch.from_numpy(ix), None)
    PFL.Exporter(platform=TargetPlatform.ESPDL_INT8).export(file_path=str(out / 'g2.espdl'), graph=graph, values_for_test=values, export_config=True)
    export_ppq_graph(graph, TargetPlatform.NATIVE, str(out / 'g2.native'))
    executor = TorchExecutor(graph=load_native_graph(str(out / 'g2.native')), device='cpu')
    assert np.array_equal(quantized(executor, ix), expected), 'final native reload mismatch'

    # Static named-activation screen (same accounting as round two).
    from audit_static_memory import measure
    static = measure(out / 'g2.espdl')

    # Int8 versus float on the fixed validation subsample.
    store = g2.Store('ami-sdm-validation')
    s_f, s_q, cnt, col = [], [], [], []
    with torch.inference_mode():
        for r in g2.validation_subsample():
            pcm = store.pcm(r['store_sdm']).astype(np.float32) / 32768
            f = frontend(pcm)
            c = labels.expand(r['counts'])
            k = labels.expand(r['collar']).astype(bool)
            s_f.append(g2.overlap_posterior_10ms(model(f[None])[0], c.size))
            q = executor.forward(inputs=f[None, :, :, None])[0][0, :, :, 0]
            s_q.append(g2.overlap_posterior_10ms(q, c.size))
            cnt.append(c)
            col.append(k)
    s_f, s_q, cnt, col = map(np.concatenate, (s_f, s_q, cnt, col))
    auc_f = scorer.frame_roc(s_f, cnt, col)['auc']
    auc_q = scorer.frame_roc(s_q, cnt, col)['auc']
    rates_q = scorer.frame_rates(s_q, cnt, col)
    espdl = out / 'g2.espdl'
    status = dict(
        checkpoint=sel, folded_max_abs_diff=fold_err, quant_type='w8a8', target='esp32p4', input_exponent=in_exp, output_exponent=out_exp,
        parameters=g2.parameter_count(model), espdl_bytes=espdl.stat().st_size, espdl_sha256=sha(espdl.read_bytes()), native_sha256=sha((out / 'g2.native').read_bytes()),
        metadata=meta, fixture_byte_exact=True, checked_shapes=shapes,
        static_activation_peak_bytes=static['distinct_static_activation_peak_bytes'], static_peak_operation=static['peak_operation'], static_peak_tensors=static['peak_tensors'][:5],
        budget=BUDGET, within_budget=dict(parameters=g2.parameter_count(model) <= BUDGET['max_parameters'], weight_bytes=espdl.stat().st_size <= BUDGET['max_weight_bytes'],
                                          static_arena=static['distinct_static_activation_peak_bytes'] <= BUDGET['max_arena_bytes']),
        validation_frame_roc_auc=dict(float=auc_f, int8=auc_q, delta=auc_q - auc_f), int8_validation_rates={k: v for k, v in rates_q.items() if k.endswith('rate')},
        scope='Host ESPDL/native fixture, variable-shape and static named-activation accounting only. Not a P4 execution, timing, integrated-peak or product measurement.',
    )
    (out / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
    print(json.dumps({k: status[k] for k in ('parameters', 'espdl_bytes', 'static_activation_peak_bytes', 'within_budget', 'validation_frame_roc_auc', 'checked_shapes', 'folded_max_abs_diff')}, indent=1))


if __name__ == '__main__':
    main()
