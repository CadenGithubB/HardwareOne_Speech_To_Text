#!/usr/bin/env python3
"""Build-only speech overlay on verified, preserved portable-audio app copies.

Capture the production diff against 611dd06 only after edits are frozen. Prepare
separate private app copies; no serial access, flashing or SDK mutation occurs.
"""
import argparse
import hashlib
from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
AUDIO = HERE.parent / 'audio_portable'
BASE = '611dd06f36e105171dca286a01bf5395b805cb56'
COMPONENT = 'components/hardwareone/'
DEP_FILE = COMPONENT + 'idf_component.yml'
MANIFEST = 'speech-build-manifest.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audio_module():
    spec = importlib.util.spec_from_file_location('speech_audio_baseline', AUDIO / 'prepare.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def production_changes():
    names = subprocess.check_output(
        ['git', 'diff', '--name-only', BASE, '--', COMPONENT, 'CMakeLists.txt', 'config/sdkconfig.defaults'], cwd=REPO).decode().splitlines()
    names += subprocess.check_output(
        ['git', 'ls-files', '--others', '--exclude-standard', '--', COMPONENT],
        cwd=REPO).decode().splitlines()
    return sorted(set(p for p in names if '/test/' not in p and
                      (Path(p).suffix in ('.h', '.cpp', '.txt') or p == 'config/sdkconfig.defaults')))


def capture():
    names = production_changes()
    if not names:
        raise ValueError('No production speech changes to capture')
    # The qualified deployment manifest is narrower than the production one.
    # Permit exactly the reviewed ESP-SR pin; add it to the deployment below.
    dependency = subprocess.check_output(['git', 'show', BASE + ':' + DEP_FILE], cwd=REPO)
    wanted = dependency.replace(b'version: "^1.4.0"', b'version: "==2.5.5"')
    wanted = wanted.replace(
        b'  # ESP-SR for speech recognition (wake word + commands)\n',
        b'  # The onboard LLM kernels use DSP directly; ESP-SR 2.x no longer brings\n'
        b'  # it transitively on P4/S3. Keep the existing consumer dependency explicit.\n'
        b'  espressif/esp-dsp:\n    version: "==1.8.0"\n'
        b'  # ESP-SR for speech recognition (wake word + commands)\n')
    if wanted != (REPO / DEP_FILE).read_bytes():
        raise ValueError('Unexpected production component dependency change')
    tracked = set(subprocess.check_output(
        ['git', 'ls-files', '--', COMPONENT, 'CMakeLists.txt', 'config/sdkconfig.defaults'], cwd=REPO).decode().splitlines())
    chunks = []
    for path in names:
        if not (REPO / path).is_file():
            raise ValueError('Deleted production files require a new baseline: ' + path)
        if path in tracked:
            chunks.append(subprocess.check_output(
                ['git', 'diff', '--unified=2', '--binary', BASE, '--', path], cwd=REPO))
        else:
            result = subprocess.run(['git', 'diff', '--no-index', '--binary', '--',
                                     '/dev/null', path], cwd=REPO, capture_output=True)
            if result.returncode != 1:
                raise ValueError('New-file patch failed: ' + path)
            chunks.append(result.stdout)
    (HERE / 'integration.patch').write_bytes(b''.join(chunks))
    record = {
        'schema': 1, 'base_commit': BASE,
        'production_sources': {p: sha(REPO / p) for p in names},
        'dependency_source_sha256': sha(REPO / DEP_FILE),
        'patch_sha256': sha(HERE / 'integration.patch'),
    }
    (HERE / 'integration-inputs.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Captured', len(names), 'production sources')


def sdkconfig_paths(target):
    roles = HERE.parent / 'p4_ble_roles'
    paths = [roles / 'sdkconfig.connectivity.defaults']
    if target == 'p4':
        paths.append(roles / 'sdkconfig.p4.bluetooth.defaults')
    paths.append(HERE.parent / 'camera_portable' / ('sdkconfig.' + target + '.camera.defaults'))
    paths.append(HERE / 'sdkconfig.speech.defaults')
    if target == 'p4':
        paths.append(HERE / 'sdkconfig.p4.speech.defaults')
    if target == 's3':
        paths.append(HERE / 'sdkconfig.s3.speech.defaults')
    return paths


def inputs(target):
    data = json.loads((HERE / 'integration-inputs.json').read_text())
    if data['schema'] != 1 or data['base_commit'] != BASE:
        raise ValueError('Captured source schema/base mismatch')
    if data['patch_sha256'] != sha(HERE / 'integration.patch'):
        raise ValueError('Integration patch changed')
    if data['dependency_source_sha256'] != sha(REPO / DEP_FILE):
        raise ValueError('Component dependency source changed')
    if sorted(data['production_sources']) != production_changes():
        raise ValueError('Production file set changed; capture and refresh')
    for path, digest in data['production_sources'].items():
        if sha(REPO / path) != digest:
            raise ValueError('Source changed; capture and refresh: ' + path)
    external = [HERE / 'radio_backend.cpp', HERE / 'radio_backend.h',
                AUDIO / 'radio_backend.cpp', AUDIO / 'radio_backend.h',
                HERE.parent / 'camera_portable/radio_backend.cpp',
                HERE.parent / 'camera_portable/radio_backend.h',
                HERE.parent / 'jpeg_portable/radio_backend.cpp',
                HERE.parent / 'jpeg_portable/radio_backend.h',
                HERE.parent / 'p4_ble_roles/radio_backend.cpp',
                HERE.parent / 'p4_ble_roles/radio_backend.h',
                HERE.parent / 'p4_espnow/bridge/esp_now_hosted_host.c',
                HERE.parent / 'p4_espnow/bridge/esp_now_hosted_host.h',
                HERE.parent / 'p4_espnow/bridge/esp_now_hosted_rpc.h']
    return {
        'integration_inputs_sha256': sha(HERE / 'integration-inputs.json'),
        'prepare_sha256': sha(HERE / 'prepare.py'),
        'qualified_lock_sha256': sha(HERE / ('dependencies-' + target + '.lock')),
        'build_sha256': sha(HERE / 'build.sh'),
        'profile_sha256': sha(HERE / ('features-' + target + '.h')),
        'inherited_profile_sha256': sha(AUDIO / ('features-' + target + '.h')),
        'sdkconfig_sha256': {str(p.relative_to(REPO)): sha(p) for p in sdkconfig_paths(target)},
        'radio_shims': {str(p.relative_to(REPO)): sha(p) for p in external},
    }


# The qualified audio copies are immutable during one invocation. Avoid
# re-reading their full inherited snapshot chain at every staging/check step.
@lru_cache(maxsize=2)
def baseline(target):
    audio = audio_module()
    source = AUDIO / ('private/app-' + target)
    audio.check(target, source, current=False)
    _, expected, common = audio.baseline(target)
    expected.update(json.loads((source / 'audio-build-manifest.json').read_text())['overlay'])
    return source, expected, common


def lock_name(target):
    return 'dependencies.lock.esp32p4' if target == 'p4' else 'dependencies.lock'


def verify_lock(target, path):
    wanted = yaml.safe_load((HERE / ('dependencies-' + target + '.lock')).read_text())
    actual = yaml.safe_load(path.read_text())
    def canonical(value):
        if isinstance(value, dict):
            return {key: item.rstrip('/') if key == 'registry_url' else canonical(item)
                    for key, item in value.items()}
        if isinstance(value, list):
            return [canonical(item) for item in value]
        return value
    for key in ('target', 'version', 'dependencies'):
        if canonical(actual[key]) != canonical(wanted[key]):
            raise ValueError('Resolved dependency drift: ' + key)
    if set(actual['direct_dependencies']) != set(wanted['direct_dependencies']):
        raise ValueError('Resolved direct dependency drift')


def check(target, destination, current=True):
    source, expected, common = baseline(target)
    data = json.loads((destination / MANIFEST).read_text())
    if data['schema'] != 1 or data['target'] != target or data['base_commit'] != BASE:
        raise ValueError('Speech manifest target/schema/base mismatch')
    if data['baseline_manifest_sha256'] != sha(source / 'audio-build-manifest.json'):
        raise ValueError('Audio baseline manifest changed')
    if current and data['inputs'] != inputs(target):
        raise ValueError('Speech build inputs changed')
    expected = dict(expected)
    expected.update(data['overlay'])
    # Component Manager may refresh only its aggregate manifest hash.
    # Versions, hashes, transitive constraints and direct dependencies stay exact.
    verify_lock(target, destination / lock_name(target))
    expected.pop(lock_name(target), None)
    common.verify_files(destination, expected, 'speech application')
    return len(expected)


def prepare(target, destination, refresh=False):
    if destination.is_symlink():
        raise ValueError('Refusing a symlink destination')
    if destination.exists() and not refresh:
        raise ValueError('Destination exists; use --check or explicit --refresh')
    if refresh:
        check(target, destination, current=False)
    source, expected, common = baseline(target)
    input_record = inputs(target)
    changes = json.loads((HERE / 'integration-inputs.json').read_text())['production_sources']
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix='.speech-stage-', dir=destination.parent) as directory:
        stage = Path(directory)
        for relative in expected:
            output = common.safe_path(stage, relative)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(common.safe_path(source, relative), output)
        result = subprocess.run(['patch', '-f', '-F', '0', '-p', '1'],
                                input=(HERE / 'integration.patch').read_bytes(),
                                cwd=stage, capture_output=True)
        report = (result.stdout + result.stderr).decode()
        if result.returncode or 'fuzz' in report:
            raise ValueError('Exact-context speech patch failed: ' + report)
        deployment_manifest = stage / DEP_FILE
        if 'espressif/esp-sr:' in deployment_manifest.read_text():
            raise ValueError('Audio baseline unexpectedly includes ESP-SR')
        deployment_manifest.write_text(deployment_manifest.read_text() +
                                       '\n  espressif/esp-sr:\n    version: "==2.5.5"\n')
        shutil.copy2(HERE / ('dependencies-' + target + '.lock'), stage / lock_name(target))
        overlay = set(changes) | {DEP_FILE, lock_name(target)}
        data = {
            'schema': 1, 'target': target, 'base_commit': BASE,
            'baseline_manifest_sha256': sha(source / 'audio-build-manifest.json'),
            'inputs': input_record,
            'overlay': {p: sha(common.safe_path(stage, p)) for p in sorted(overlay)},
        }
        (stage / MANIFEST).write_text(json.dumps(data, indent=2) + '\n')
        count = check(target, stage)
        if refresh:
            old = json.loads((destination / MANIFEST).read_text())
            for relative in set(old['overlay']) | set(data['overlay']):
                src = common.safe_path(stage, relative)
                dst = common.safe_path(destination, relative)
                if not src.is_file():
                    raise ValueError('Removing an overlay needs a new copy')
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists() or sha(src) != sha(dst):
                    shutil.copy2(src, dst)
            shutil.copy2(stage / MANIFEST, destination / MANIFEST)
        else:
            # No symlinks/hardlinks: future Component Manager actions must never
            # alter the camera qualification copy or downloaded SDK directories.
            shutil.copytree(stage, destination)
            shutil.copytree(source / 'managed_components', destination / 'managed_components')
            resolved = yaml.safe_load((HERE / ('dependencies-' + target + '.lock')).read_text())
            cache = HERE / ('private/dependency-probe-' + target) / 'managed_components'
            for package in resolved['dependencies']:
                if package == 'idf':
                    continue
                name = package.replace('/', '__')
                output = destination / 'managed_components' / name
                if not output.exists() and (cache / name).is_dir():
                    shutil.copytree(cache / name, output)
                # With no local probe cache, Component Manager downloads this
                # exact version/hash from the checked-in lock at configure.


    return count


def accept_lock(target, destination):
    # First validate every source and the material lock content. Only the
    # manager's aggregate manifest metadata is allowed to change here.
    check(target, destination, current=False)
    inputs(target)
    shutil.copy2(destination / lock_name(target), HERE / ('dependencies-' + target + '.lock'))
    data = json.loads((destination / MANIFEST).read_text())
    data['overlay'][lock_name(target)] = sha(destination / lock_name(target))
    data['inputs'] = inputs(target)
    (destination / MANIFEST).write_text(json.dumps(data, indent=2) + '\n')
    return check(target, destination)



def apply_p4_config(destination):
    """Explicit, hash-backed change to the generated P4 config, never S3."""
    # Validate the sealed copy even if a deliberate source refresh is pending.
    # This action modifies only one generated configuration setting.
    check('p4', destination, current=False)
    config = HERE / 'private/build-p4/sdkconfig'
    if not config.is_file() or config.is_symlink():
        raise ValueError('Expected existing regular generated P4 sdkconfig')
    data = config.read_bytes()
    old = b'# CONFIG_ESP_HOSTED_MEMPOOL_PREFER_SPIRAM is not set\n'
    new = b'CONFIG_ESP_HOSTED_MEMPOOL_PREFER_SPIRAM=y\n'
    if data.count(new) == 1 and old not in data:
        print('P4 Hosted SPIRAM preference is already enabled')
        return
    if data.count(old) != 1 or new in data:
        raise ValueError('Unexpected existing Hosted preference; inspect sdkconfig')
    if b'CONFIG_IDF_TARGET="esp32p4"\n' not in data:
        raise ValueError('Generated config is not for P4')
    digest = hashlib.sha256(data).hexdigest()
    backup = HERE / 'private/config-backups' / (digest + '.sdkconfig')
    backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if backup.exists() and (backup.is_symlink() or backup.read_bytes() != data):
        raise ValueError('Existing config backup differs')
    if not backup.exists():
        backup.write_bytes(data)
    if config.read_bytes() != data:
        raise ValueError('Generated config changed while backing up')
    config.write_bytes(data.replace(old, new))
    print('Updated only P4 Hosted preference; previous SHA-256:', digest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--capture', action='store_true')
    actions.add_argument('--check', action='store_true')
    actions.add_argument('--refresh', action='store_true')
    actions.add_argument('--accept-lock', action='store_true')
    actions.add_argument('--apply-p4-config', action='store_true')
    parser.add_argument('--target', choices=('p4', 's3'))
    args = parser.parse_args()
    if args.capture:
        return capture()
    if not args.target:
        parser.error('--target required')
    destination = HERE / ('private/app-' + args.target)
    if args.apply_p4_config:
        if args.target != 'p4':
            parser.error('--apply-p4-config is P4-only')
        return apply_p4_config(destination)
    count = (accept_lock(args.target, destination) if args.accept_lock else
             check(args.target, destination) if args.check else
             prepare(args.target, destination, args.refresh))
    print('Verified', count, 'sources:', destination)


if __name__ == '__main__':
    main()
