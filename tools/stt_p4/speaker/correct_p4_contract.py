#!/usr/bin/env python3
"""Build an experimental speaker.spk for the pinned P4 trunk. Use a locally regenerated PPQ graph only."""
import argparse
import hashlib
import struct
from pathlib import Path

import numpy as np
import torch
from esp_ppq import TorchExecutor
from esp_ppq.api import load_native_graph
from esp_ppq.executor.base import QuantOPRuntimeHook
from esp_ppq.parser.espdl import helper  # registers the generated FlatBuffers package
from FlatBuffers.Dl.Model import Model


SOURCE_SHA = '650f48bd23f804238caec6aa561d8951c61a099ba03d11e722af696ec3628f83'
ARITHMETIC = {'Conv', 'Gemm', 'Mul', 'Add', 'GlobalAveragePool', 'ReduceMean'}


class WideArithmetic(QuantOPRuntimeHook):
    """Keep quantized operands and grids. Avoid float32 rounding before requantization."""

    def pre_forward_hook(self, inputs, quant_inputs, quant_configs):
        return [value.double() if value.is_floating_point() else value for value in quant_inputs]


def arithmetic_hooks(graph):
    return {op.name: WideArithmetic(op) for op in graph.operations.values() if op.type in ARITHMETIC}


def fixture(executor, features, hooks):
    with torch.inference_mode():
        values = executor.forward(inputs=features, hooks=hooks)[0].transpose(1, 2).numpy()
    q = np.rint(values * 2048).astype('<i2')
    if q.shape != (1, 75, 128) or not np.array_equal(values, q / 2048):
        raise ValueError('Unexpected output grid')
    return q.tobytes()


def synthetic_input():
    # Same unsigned recurrence as speaker_contract.cpp, in runtime tensor order.
    state = 1
    samples = []
    for _ in range(12000):
        state = (1664525 * state + 1013904223) & 0xffffffff
        samples.append((state >> 19) - 4096)
    return torch.tensor(samples, dtype=torch.float32).reshape(1, 1, 40, 300) / 2048


def correct(blob, native):
    if hashlib.sha256(blob).hexdigest() != SOURCE_SHA:
        raise ValueError('Unsupported speaker package')
    offset, size = struct.unpack_from('<II', blob, 60)
    if offset + size != len(blob) - 32:
        raise ValueError('Invalid trunk bounds')
    trunk = bytearray(blob[offset:offset + size])
    graph = Model.GetRootAs(trunk, 16).Graph()
    test_input = graph.TestInputsValue(0)
    test_output = graph.TestOutputsValue(0)
    start = test_input.RawData(0)._tab.Pos
    x = np.frombuffer(trunk, dtype='<i2', count=12000, offset=start).reshape(1, 1, 40, 300).copy()
    features = torch.from_numpy(x).float() / 2048
    executor = TorchExecutor(graph=native, device='cpu')

    start = test_output.RawData(0)._tab.Pos
    original = fixture(executor, features, {})
    if trunk[start:start + len(original)] != original:
        raise ValueError('Native float32 graph does not reproduce the original exported fixture')
    trunk[start:start + len(original)] = fixture(executor, features, arithmetic_hooks(native))

    # Remove only the lut attribute from ReLU nodes. Writing a shorter vector
    # of relative FlatBuffer offsets preserves every existing tensor alignment.
    changed = 0
    for i in range(graph.NodeLength()):
        node = graph.Node(i)
        if node.OpType() != b'Relu':
            continue
        attrs = [node.Attribute(j) for j in range(node.AttributeLength())]
        keep = [a for a in attrs if a.Name() != b'lut']
        if len(keep) == len(attrs):
            continue
        vector = node._tab.Vector(node._tab.Offset(14))
        struct.pack_into('<I', trunk, vector - 4, len(keep))
        for index, attr in enumerate(keep):
            pos = vector + index * 4
            struct.pack_into('<I', trunk, pos, attr._tab.Pos - pos)
        if [node.Attribute(j).Name() for j in range(node.AttributeLength())] != [a.Name() for a in keep]:
            raise ValueError('Failed to preserve ReLU attributes')
        changed += 1
    if changed != 16:
        raise ValueError(f'Unexpected ReLU count {changed}')
    body = blob[:offset] + trunk
    return body + hashlib.sha256(body).digest(), fixture(executor, synthetic_input(), arithmetic_hooks(native))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--trusted-native', required=True, type=Path, help='Local PPQ pickle generated from the original calibration')
    parser.add_argument('--output', required=True, type=Path, help='Fresh private output directory')
    args = parser.parse_args()
    torch.set_num_threads(2)
    candidate, second = correct(args.source.read_bytes(), load_native_graph(str(args.trusted_native)))
    args.output.mkdir()
    (args.output / 'speaker.spk').write_bytes(candidate)
    (args.output / 'synthetic-reference.bin').write_bytes(second)
    print(hashlib.sha256(candidate).hexdigest())


if __name__ == '__main__':
    main()
