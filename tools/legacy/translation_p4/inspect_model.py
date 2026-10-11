#!/usr/bin/env python3
"""Inspect a pinned Marian v1 binary without loading/executing a model runtime.

Format sources (read 2026-09-29):
https://raw.githubusercontent.com/browsermt/marian-dev/master/src/common/binary.cpp
https://raw.githubusercontent.com/browsermt/marian-dev/master/src/common/binary.h
https://raw.githubusercontent.com/browsermt/marian-dev/master/src/common/types.h
https://raw.githubusercontent.com/browsermt/marian-dev/master/src/tensors/cpu/integer_common.h

The report is an on-disk tensor map, not an inference-RAM measurement. Only the
plain numeric/intgemm types used by these model candidates are supported.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct

MAX_BYTES = 64 * 1024 * 1024
MAX_TENSORS = 2048
TYPES = {
    0x0101: ('int8', 1), 0x0102: ('int16', 2),
    0x0104: ('int32', 4), 0x0108: ('int64', 8),
    0x0201: ('uint8', 1), 0x0202: ('uint16', 2),
    0x0204: ('uint32', 4), 0x0208: ('uint64', 8),
    0x0402: ('float16', 2), 0x0404: ('float32', 4),
    0x0408: ('float64', 8),
    0x4101: ('intgemm8', 1), 0x4102: ('intgemm16', 2),
}


def inspect_bytes(data, expected_sha256):
    if not re.fullmatch('[0-9a-fA-F]{64}', expected_sha256):
        raise ValueError('Expected SHA-256 must contain exactly 64 hex digits')
    if not 16 <= len(data) <= MAX_BYTES:
        raise ValueError('Model size outside 16-byte to 64-MiB bound')
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_sha != expected_sha256.lower():
        raise ValueError('Model SHA-256 does not match the supplied pin')
    cursor = 0

    def take(size):
        nonlocal cursor
        if size < 0 or size > len(data) - cursor:
            raise ValueError('Truncated or out-of-bounds model field')
        start = cursor
        cursor += size
        return memoryview(data)[start:cursor]

    version, count = struct.unpack('<QQ', take(16))
    if version != 1:
        raise ValueError('Only Marian binary version 1 is supported')
    if not 1 <= count <= MAX_TENSORS:
        raise ValueError('Tensor count outside supported bound')
    headers = [struct.unpack('<QQQQ', take(32)) for _ in range(count)]
    names, seen = [], set()
    for name_size, dtype, rank, length in headers:
        if not 2 <= name_size <= 256 or not 1 <= rank <= 4:
            raise ValueError('Unsupported tensor name length or rank')
        if dtype not in TYPES or not 1 <= length <= MAX_BYTES:
            raise ValueError('Unsupported tensor type or byte count')
        raw = bytes(take(name_size))
        if raw[-1] != 0 or b'\0' in raw[:-1]:
            raise ValueError('Tensor name must have one terminal NUL')
        name = raw[:-1].decode('utf-8')
        if not name.isprintable() or name in seen:
            raise ValueError('Invalid or duplicate tensor name')
        seen.add(name)
        names.append(name)
    shapes = []
    for _, _, rank, _ in headers:
        shape = list(struct.unpack('<' + 'i' * rank, take(4 * rank)))
        if any(dim <= 0 or dim > MAX_BYTES for dim in shape):
            raise ValueError('Tensor dimensions must be positive and bounded')
        shapes.append(shape)
    padding = struct.unpack('<Q', take(8))[0]
    metadata_end = cursor
    if padding > 256:
        raise ValueError('Unexpected leading alignment padding')
    take(padding)
    data_start = cursor
    tensors = []
    type_summary = {}
    for header, name, shape in zip(headers, names, shapes):
        _, dtype, _, length = header
        type_name, width = TYPES[dtype]
        elements = math.prod(shape)
        value_bytes = elements * width
        is_intgemm = dtype in (0x4101, 0x4102)
        required_bytes = value_bytes + (4 if is_intgemm else 0)
        if required_bytes > MAX_BYTES or not required_bytes <= length <= required_bytes + 255:
            raise ValueError('Tensor shape/type does not match its byte count')
        offset = cursor
        values = take(length)
        row = dict(name=name, type=type_name, type_code=dtype, shape=shape,
                   elements=elements, offset=offset, end=cursor,
                   stored_bytes=length, value_bytes=value_bytes,
                   padding_bytes=length-required_bytes,
                   sha256=hashlib.sha256(values).hexdigest())
        if is_intgemm:
            multiplier = struct.unpack_from('<f', values, value_bytes)[0]
            if not math.isfinite(multiplier) or multiplier <= 0:
                raise ValueError('Invalid intgemm quantization multiplier')
            row['quantization_multiplier'] = multiplier
        if 'Wemb' in name and is_intgemm:
            row['stock_loader_float32_embedding_bytes'] = elements * 4
        summary = type_summary.setdefault(type_name, dict(tensors=0, stored_bytes=0, elements=0))
        summary['tensors'] += 1
        summary['stored_bytes'] += length
        summary['elements'] += elements
        tensors.append(row)
    if cursor != len(data):
        raise ValueError('Unexpected trailing bytes after the last tensor')
    embeddings = [row for row in tensors if 'stock_loader_float32_embedding_bytes' in row]
    return dict(schema=1, model_sha256=actual_sha, file_bytes=len(data),
                binary_version=version, tensor_count=count,
                metadata_range=[0, metadata_end],
                alignment_padding_range=[metadata_end, data_start],
                tensor_data_range=[data_start, cursor],
                ranges_are_half_open=True, all_bytes_accounted_for=True,
                type_summary=type_summary,
                model_elements_excluding_metadata=sum(row['elements'] for row in tensors
                                                      if not row['name'].startswith('special:')),
                embedding_float32_bytes=sum(row['stock_loader_float32_embedding_bytes'] for row in embeddings),
                stock_loader_item_logical_bytes_inferred=sum(
                    row.get('stock_loader_float32_embedding_bytes', row['stored_bytes'])
                    for row in tensors),
                note='Disk layout only; stock loader copies/reformats tensors and expands intgemm embeddings.',
                tensors=tensors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', type=Path)
    parser.add_argument('--sha256', required=True, help='Pinned SHA-256 of the decompressed model binary')
    parser.add_argument('--output', type=Path, help='Write report to a new file; default stdout')
    args = parser.parse_args()
    try:
        with args.model.open('rb') as handle:
            data = handle.read(MAX_BYTES + 1)
        report = inspect_bytes(data, args.sha256)
        text = json.dumps(report, indent=2) + '\n'
        if args.output:
            with args.output.open('x') as handle:
                handle.write(text)
        else:
            print(text, end='')
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f'Model inspection failed: {error}\n')


if __name__ == '__main__':
    main()
