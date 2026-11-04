#!/usr/bin/env python3
"""Exhaustively audit serialized int16 ReLU tables using P4 nearest-even indexing.

Requires the export environment's NumPy/esp-ppq packages. This characterizes the
model's lookup approximation; it does not validate the P4 SIMD implementation,
whole-network numerics, speaker accuracy, or timing. Keep output private.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np


def audit(graph):
    initializers = {tensor.name.decode(): tensor for tensor in graph.initializer}
    metadata = {
        value.name.decode(): value
        for value in list(graph.input) + list(graph.output) + list(graph.valueInfo)
    }
    rows = []
    for node in graph.node:
        attributes = {attribute.name.decode(): attribute for attribute in node.attribute}
        if node.opType != b'Relu' or 'lut' not in attributes:
            continue
        name = bytes(attributes['lut'].s).decode()
        tensor = initializers[name]
        if int(tensor.dataType) != 5:  # This audit deliberately covers signed int16 only.
            continue
        elements = int(np.prod(tensor.dims))
        if elements < 2 or 65536 % (elements - 1):
            raise ValueError('Invalid int16 table size: ' + name)
        step = 65536 // (elements - 1)
        if step & (step - 1):
            raise ValueError('SDK nearest-neighbor indexing requires power-of-two step')
        raw = b''.join(bytes(chunk.bytes) for chunk in tensor.rawData)
        table = np.frombuffer(raw, dtype='<i2')[:elements].astype(np.int32)
        if len(table) != elements:
            raise ValueError('Truncated table: ' + name)
        input_metadata = metadata[node.input[0].decode()]
        output_metadata = metadata[node.output[0].decode()]
        if len(input_metadata.exponents) != 1 or len(output_metadata.exponents) != 1:
            raise ValueError('Expected scalar activation exponents')
        input_exponent = int(input_metadata.exponents[0])
        output_exponent = int(output_metadata.exponents[0])

        def exact_relu(values):
            scaled = np.ldexp(np.maximum(values, 0).astype(float),
                              input_exponent - output_exponent)
            return np.clip(np.rint(scaled), 0, 32767).astype(int)

        inputs = np.arange(-32768, 32768, dtype=np.int32)
        # This is the pinned SDK's PIE_V2 scalar-tail rule, including ties-to-even.
        indices = np.rint((inputs + 32768) / step).astype(int)
        actual = table[indices]
        error = np.abs(actual - exact_relu(inputs))
        grid = np.arange(elements) * step - 32768
        rows.append({
            'node': node.name.decode(), 'table': name, 'entries': elements,
            'step': step, 'input_exponent': input_exponent,
            'output_exponent': output_exponent,
            'table_grid_exact_relu': bool(np.array_equal(table, exact_relu(grid))),
            'all_int16_inputs': len(inputs), 'over_one_unit': int((error > 1).sum()),
            'max_abs_error': int(error.max()),
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True, help='Existing unencrypted ESPDL trunk')
    parser.add_argument('--output', type=Path, required=True, help='Fresh ignored private JSON path')
    args = parser.parse_args()
    data = args.model.read_bytes()
    if len(data) < 32 or data[:4] != b'EDL2' or struct.unpack_from('<II', data, 4) != (0, len(data) - 16):
        raise ValueError('Expected an unencrypted, bounded EDL2 trunk')
    if args.output.exists():
        raise FileExistsError('Use a fresh private output file')
    from esp_ppq.parser.espdl import helper  # Registers generated FlatBuffers imports.
    from FlatBuffers.Dl.Model import Model, ModelT
    del helper
    graph = ModelT.InitFromObj(Model.GetRootAs(data, 16)).graph
    rows = audit(graph)
    result = {
        'model_sha256': hashlib.sha256(data).hexdigest(),
        'scope': 'Serialized tables and P4 nearest-even index rule; exhaustive signed-int16 input domain',
        'relu_nodes_with_tables': len(rows),
        'unique_tables': len({row['table'] for row in rows}), 'rows': rows,
    }
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({
        'nodes': len(rows), 'unique_tables': result['unique_tables'],
        'steps': sorted({row['step'] for row in rows}),
        'max_error_range': [min(row['max_abs_error'] for row in rows),
                            max(row['max_abs_error'] for row in rows)] if rows else None,
    }, indent=2))


if __name__ == '__main__':
    main()
