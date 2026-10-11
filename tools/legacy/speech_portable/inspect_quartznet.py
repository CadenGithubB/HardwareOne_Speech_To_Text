#!/usr/bin/env python3
"""Bounded, host-only inspection of NVIDIA's official QuartzNet-5x5 checkpoint.

No board access, arbitrary pickle loading, or checkpoint code execution. Requires
PyYAML and PyTorch >= 2.6; use the isolated environment documented in TRANSCRIPTION.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent
URL = ('https://api.ngc.nvidia.com/v2/models/nvidia/nemospeechmodels/versions/'
       '1.0.0a5/files/QuartzNet5x5LS-En.nemo')
EXPECTED_ARCHIVE = 'd12bae27c1aa66cf69111ce3f8e56ac7aa25dac27734ea4c3315a259966a02f5'
MAX_DOWNLOAD = 64 * 1024 * 1024
MAX_UNPACKED = 128 * 1024 * 1024
MAX_MEMBERS = 512


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(directory):
    archive = directory / 'QuartzNet5x5LS-En.nemo'
    if archive.exists():
        raise ValueError('Refusing to overwrite existing checkpoint')
    part = archive.with_suffix('.nemo.part')
    total = 0
    with urllib.request.urlopen(URL, timeout=45) as response, part.open('xb') as output:
        advertised = response.headers.get('Content-Length')
        if advertised and int(advertised) > MAX_DOWNLOAD:
            raise ValueError('Advertised download exceeds bound')
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_DOWNLOAD:
                raise ValueError('Download exceeds bound')
            output.write(chunk)
    part.rename(archive)
    record = {'url': URL, 'bytes': total, 'sha256': digest(archive)}
    (directory / 'download.json').write_text(json.dumps(record, indent=2) + '\n')
    return archive


def inspect_archive(archive, directory):
    if archive.is_symlink() or archive.stat().st_size > MAX_DOWNLOAD:
        raise ValueError('Unsafe or oversized archive')
    if digest(archive) != EXPECTED_ARCHIVE:
        raise ValueError('Official checkpoint bytes changed; review before loading')
    members = []
    total = 0
    names = set()
    selected = {}
    with tarfile.open(archive, mode='r:*') as bundle:
        for member in bundle:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Unsafe archive path')
            name = path.as_posix()
            if len(members) >= MAX_MEMBERS or name in names:
                raise ValueError('Too many or duplicate archive members')
            names.add(name)
            if not (member.isdir() or member.isfile()):
                raise ValueError('Archive links/special files are not permitted')
            if member.size < 0 or member.size > MAX_UNPACKED:
                raise ValueError('Invalid archive member size')
            total += member.size
            if total > MAX_UNPACKED:
                raise ValueError('Expanded archive exceeds bound')
            members.append({'name': name, 'bytes': member.size, 'directory': member.isdir()})
            if member.isfile() and path.name in ('model_config.yaml', 'model_weights.ckpt'):
                if path.name in selected:
                    raise ValueError('Ambiguous checkpoint layout')
                # No archive path is used as an output path. Select two known basenames.
                source = bundle.extractfile(member)
                payload = source.read(member.size + 1)
                if len(payload) != member.size:
                    raise ValueError('Archive member length mismatch')
                selected[path.name] = payload
    if set(selected) != {'model_config.yaml', 'model_weights.ckpt'}:
        raise ValueError('Expected NeMo config and state tensors not found')
    for name, payload in selected.items():
        output = directory / name
        if output.is_symlink():
            raise ValueError('Refusing a symlink output')
        if output.exists() and output.read_bytes() != payload:
            raise ValueError('Refusing to replace different extracted content')
        output.write_bytes(payload)
    return members


def inspect_tensors(directory):
    import torch
    # weights_only=True is deliberate. There is no unrestricted pickle fallback.
    version = tuple(int(part) for part in torch.__version__.split('+')[0].split('.')[:2])
    if version < (2, 6):
        raise ValueError('PyTorch >= 2.6 required for weights-only loading')
    state = torch.load(directory / 'model_weights.ckpt', map_location='meta', weights_only=True)
    if not isinstance(state, dict) or len(state) > 10000:
        raise ValueError('Unexpected state dictionary')
    tensors = []
    parameters = buffers = unknown = total_bytes = conv_weights = 0
    for name, tensor in state.items():
        if not isinstance(name, str) or not isinstance(tensor, torch.Tensor):
            raise ValueError('Checkpoint must contain only named tensors')
        count = tensor.numel()
        size = count * tensor.element_size()
        total_bytes += size
        if total_bytes > MAX_UNPACKED:
            raise ValueError('Tensor storage exceeds bound')
        if name.startswith('preprocessor.') or name.endswith(('.running_mean', '.running_var', '.num_batches_tracked')):
            role = 'buffer'; buffers += count
        elif name.endswith(('.weight', '.bias')):
            role = 'parameter'; parameters += count
        else:
            role = 'unclassified'; unknown += count
        if role == 'parameter' and tensor.ndim == 3:
            conv_weights += count
        tensors.append({'name': name, 'shape': list(tensor.shape), 'dtype': str(tensor.dtype),
                        'elements': count, 'bytes': size, 'role_by_state_key': role})
    return {'torch_version': torch.__version__, 'tensor_count': len(tensors),
            'parameter_elements_by_state_key': parameters,
            'buffer_elements_by_state_key': buffers, 'unclassified_elements': unknown,
            'tensor_bytes': total_bytes, 'conv_weight_elements': conv_weights,
            'tensors': tensors}


def architecture_estimates(config, tensors):
    hop = config['preprocessor']['params']['window_stride']
    receptive = jump = 1
    stages = []
    for index, block in enumerate(config['encoder']['params']['jasper']):
        for _ in range(block['repeat']):
            receptive += (block['kernel'][0] - 1) * block['dilation'][0] * jump
            jump *= block['stride'][0]
        stages.append({'block': index, 'receptive_input_frames': receptive, 'input_frame_stride': jump})
    return {
        'receptive_input_frames': receptive,
        'receptive_span_seconds': (receptive - 1) * hop,
        'symmetric_right_context_seconds': (receptive - 1) * hop / 2,
        'output_frames_per_audio_second': 1 / (jump * hop),
        'convolution_macs_per_audio_second_estimate': tensors['conv_weight_elements'] / (jump * hop),
        'int8_parameter_bytes_before_scales_estimate': tensors['parameter_elements_by_state_key'],
        'normalization': config['preprocessor']['params']['normalize'],
        'stages': stages,
        'limitations': 'Context excludes STFT centering; normalization uses the full utterance. MACs exclude frontend, normalization, activations and buffer movement. No P4 timing or quantization measured.',
    }


def main():
    import yaml
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--directory', type=Path, default=HERE / 'private/stt-quartznet')
    args = parser.parse_args()
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    archive = download(directory) if args.download else directory / 'QuartzNet5x5LS-En.nemo'
    members = inspect_archive(archive, directory)
    config = yaml.safe_load((directory / 'model_config.yaml').read_text())
    if not isinstance(config, dict):
        raise ValueError('Expected mapping configuration')
    tensors = inspect_tensors(directory)
    report = {'url': URL, 'archive_bytes': archive.stat().st_size, 'archive_sha256': digest(archive),
              'members': members, 'config_sha256': digest(directory / 'model_config.yaml'),
              'weights_sha256': digest(directory / 'model_weights.ckpt'), 'config': config,
              'estimates': architecture_estimates(config, tensors), **tensors}
    (directory / 'inspection.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key not in ('config', 'tensors')}, indent=2))


if __name__ == '__main__':
    main()
