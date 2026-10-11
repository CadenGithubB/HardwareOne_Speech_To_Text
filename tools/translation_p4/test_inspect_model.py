"""Boundary checks for the offline model inspector; no vendor runtime required."""
import hashlib
import struct
import unittest

from inspect_model import inspect_bytes


def fixture(name=b'Wemb\0', dtype=0x4101, shape=(2, 2), payload=None):
    if payload is None:
        payload = bytes([1, 2, 3, 4]) + struct.pack('<f', 127.0)
    data = struct.pack('<QQQQQQ', 1, 1, len(name), dtype, len(shape), len(payload))
    data += name + struct.pack('<' + 'i' * len(shape), *shape)
    return data + struct.pack('<Q', 0) + payload


def inspect(data):
    return inspect_bytes(data, hashlib.sha256(data).hexdigest())


class ModelInspectionTests(unittest.TestCase):
    def test_valid_map_accounts_for_every_byte(self):
        data = fixture()
        report = inspect(data)
        tensor = report['tensors'][0]
        self.assertEqual(report['embedding_float32_bytes'], 16)
        self.assertEqual(tensor['quantization_multiplier'], 127)
        self.assertEqual(tensor['stored_bytes'], 8)
        self.assertEqual(report['metadata_range'][1], tensor['offset'])
        self.assertEqual(tensor['end'], len(data))

    def test_wrong_pin(self):
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            inspect_bytes(fixture(), '0' * 64)

    def test_truncation_and_trailing_data(self):
        data = fixture()
        for mutated in (data[:-1], data[:20], data + b'junk'):
            with self.subTest(size=len(mutated)), self.assertRaises(ValueError):
                inspect(mutated)

    def test_invalid_version_and_oversized_header_count(self):
        for version, count in ((2, 1), (1, 2049), (1, 0)):
            data = struct.pack('<QQ', version, count) + fixture()[16:]
            with self.subTest(version=version, count=count), self.assertRaises(ValueError):
                inspect(data)

    def test_invalid_name_type_and_dimensions(self):
        for data in (fixture(name=b'Wemb!'), fixture(name=b'We\0b\0'),
                     fixture(dtype=0x1801), fixture(shape=(-2, 2)),
                     fixture(shape=(2**30, 2)), fixture(shape=(2, 3)),
                     fixture(name=b'line\n\0')):
            with self.subTest(data=data), self.assertRaises(ValueError):
                inspect(data)

    def test_invalid_quantization_scale(self):
        for scale in (float('nan'), float('inf'), 0.0, -1.0):
            with self.subTest(scale=scale), self.assertRaises(ValueError):
                inspect(fixture(payload=bytes(4) + struct.pack('<f', scale)))

    def test_uint8_metadata_is_data(self):
        report = inspect(fixture(name=b'special:model.yml\0', dtype=0x0201,
                                 shape=(4,), payload=b'x: 1'))
        self.assertEqual(report['embedding_float32_bytes'], 0)
        self.assertEqual(report['tensors'][0]['type'], 'uint8')


if __name__ == '__main__':
    unittest.main()
