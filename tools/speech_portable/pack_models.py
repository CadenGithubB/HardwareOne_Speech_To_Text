#!/usr/bin/env python3
"""Pack the pinned ESP-SR models deterministically; no device or flash access."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import yaml

HERE = Path(__file__).resolve().parent
EXPECTED_STOCK_BUNDLE_SHA256 = '16f3ef0bd4d961da5811acded6a1f7c9b64dfa1ebd120705d7b6a3f7906e8a17'
SELECTED = {
    'fst': 'model/multinet_model/fst',
    'mn7_en': 'model/multinet_model/mn7_en',
    'wn9_hiesp': 'model/wakenet_model/wn9_hiesp',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pack(package):
    """Same little-endian layout as ESP-SR pack_model.py, in sorted file order."""
    manifest = yaml.safe_load((package / 'idf_component.yml').read_text())
    if manifest.get('version') != '2.5.5':
        raise ValueError('Expected official ESP-SR 2.5.5 package')
    models = {}
    sources = {}
    for name, relative in sorted(SELECTED.items()):
        directory = package / relative
        files = {}
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.is_symlink():
                raise ValueError('Unexpected model directory entry: ' + str(path))
            data = path.read_bytes()
            relative_file = str(path.relative_to(package))
            sources[relative_file] = sha(data)
            files[path.name] = data
        if not files or (name != 'fst' and '_MODEL_INFO_' not in files):
            raise ValueError('Incomplete model: ' + name)
        models[name] = files
    header_size = 4 + 36 * len(models) + 40 * sum(len(files) for files in models.values())
    header = bytearray(struct.pack('<I', len(models)))
    payload = bytearray()
    def name_field(value):
        encoded = value.encode('ascii')
        if not encoded or len(encoded) >= 32:
            raise ValueError('Invalid packed model/file name: ' + value)
        return encoded.ljust(32, b'\0')
    for name, files in models.items():
        header.extend(name_field(name))
        header.extend(struct.pack('<I', len(files)))
        for filename, data in files.items():
            header.extend(name_field(filename))
            header.extend(struct.pack('<II', header_size + len(payload), len(data)))
            payload.extend(data)
    if len(header) != header_size:
        raise ValueError('Packed header size mismatch')
    binary = bytes(header + payload)
    if sha(binary) != EXPECTED_STOCK_BUNDLE_SHA256:
        raise ValueError('Packed bytes differ from the pinned unmodified model fixture')
    return binary, sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=('p4', 's3'), required=True)
    args = parser.parse_args()
    package = HERE / ('private/app-' + args.target) / 'managed_components/espressif__esp-sr'
    lock = yaml.safe_load((HERE / ('dependencies-' + args.target + '.lock')).read_text())
    expected_hash = lock['dependencies']['espressif/esp-sr']['component_hash']
    if (package / '.component_hash').read_text().strip() != expected_hash:
        raise ValueError('Managed ESP-SR package hash differs from the qualified lock')
    config = HERE / ('private/build-' + args.target) / 'sdkconfig'
    if config.exists():
        values = dict(line.split('=', 1) for line in config.read_text().splitlines()
                      if line.startswith('CONFIG_') and '=' in line)
        wanted = {'CONFIG_SR_WN_WN9_HIESP': 'y', 'CONFIG_SR_MN_EN_MULTINET7_QUANT': 'y',
                  'CONFIG_SR_MN_CN_NONE': 'y', 'CONFIG_SR_NSN_WEBRTC': 'y',
                  'CONFIG_SR_VADN_WEBRTC': 'y'}
        for key, value in wanted.items():
            if values.get(key) != value:
                raise ValueError('Unexpected configured model choice: ' + key)
        selected = {key for key, value in values.items() if key.startswith('CONFIG_SR_WN_') and value == 'y'}
        if selected != {'CONFIG_SR_WN_WN9_HIESP'}:
            raise ValueError('Unexpected additional configured wake models')
    else:
        raise ValueError('Configure the speech application before packing its models')
    binary, sources = pack(package)
    out = HERE / ('private/models-' + args.target)
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    (out / 'srmodels.bin').write_bytes(binary)
    record = {'schema': 2, 'esp_sr_version': '2.5.5', 'component_hash': expected_hash,
              'models': sorted(SELECTED), 'source_sha256': sources,
              'packed_transforms': {}, 'packer_sha256': sha(Path(__file__).read_bytes()),
              'bytes': len(binary), 'sha256': sha(binary),
              'sdkconfig_sha256': sha(config.read_bytes())}
    (out / 'models-manifest.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'path': str(out / 'srmodels.bin'), 'bytes': len(binary), 'sha256': sha(binary)}))


if __name__ == '__main__':
    main()
