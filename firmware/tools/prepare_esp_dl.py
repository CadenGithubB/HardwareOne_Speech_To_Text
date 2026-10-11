#!/usr/bin/env python3
"""Stage the patched ESP-DL 3.3.12 that the hw1_stt component needs (ESP32-P4); never edit the original.

The component manifest (firmware/components/hw1_stt/idf_component.yml) points espressif/esp-dl
at firmware/.sdk-overrides/esp32p4/espressif__esp-dl, which this script creates: the pristine
3.3.12 package plus firmware/tools/esp-dl-3.3.12-hw1.patch, both digest-checked. The patch:

  - pointwise-conv tiles sized for the P4's shared 64 KB L1D (16 KB filter
    tile instead of 32 KB, 64-pixel spatial tile instead of 32; bit-exact,
    only the order of tile calls changes);
  - single-column int8 depthwise layers ([K,1] filters) run per 64-channel
    block so the sliding window and the block's filter stay in L1, and split
    across the two cores by channel halves at every length instead of by
    rows (bit-identical output: channels are independent);
  - prepared conv args: while hw1_dl_prepare_mode is set (dl_module_base.cpp)
    a pass over the model builds every Conv layer's ConvOpArgs and keeps a
    copy in a per-layer metadata block, and Add, LUT and Relu return; each
    Conv then runs on its prepared args once (same args, bit-identical
    output). With the flag never set every module runs as upstream;
  - int8 LUT layers whose table is exactly ReLU (dl_base_lut.cpp checks all
    256 entries on every call) run as a 16-byte vector max
    (dl/tool/isa/esp32p4/dl_esp32p4_s8_relu_hw1.S) instead of a per-byte
    table lookup; any other table keeps the lookup (identical output);
  - dl_tool_metadata.{hpp,cpp}: every block a dl::Model keeps for its lifetime
    is requested through one allocator hook. With no hook installed each site
    behaves exactly as upstream; the STT runtime installs an explicit PSRAM
    request (components/hw1_stt/stt/stt_dl_metadata.cpp, ps_alloc);
  - 16-bit-activation KxK convs whose filter outgrows the cache (the speaker
    model's 128 -> 128 3x3 layers: 147 KB per output pixel) run per block of
    output channels whose filter slice fits hw1_dl_conv_block_bytes (24 KB);
    each output is the same kernel's full reduction (bit-identical); int8
    layers are untouched;
  - Model::module_count() and module_name(i) (execution-plan size and names),
    for the speaker model's per-layer profile;
  - Gemm and MatMul pass std::vector<int>{1, 1} strides/dilations, which the
    templated ConvOpArgs constructor needs (braced lists do not deduce);
  - hw1_dl_log_kernel_binds: when set (speaker diagnostics only), each
    distinct conv kernel key is logged once as it binds (TL kbind);
  - dl_fft pinned to ==0.7.0: a local component's dependencies join the root
    solve, which would otherwise be free to pick a newer dl_fft.

The pristine package comes from --source, a managed_components/ folder of one of the example
projects, the IDF component manager cache, or (failing those) a download of the published
package from components.espressif.com; whichever is used must match the pinned tree digest
before the patch is applied. An existing destination is verified, never overwritten.

Usage, with ESP-IDF 5.5.5 exported:  python3 firmware/tools/prepare_esp_dl.py
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent  # firmware/
NAME = "espressif__esp-dl"
VERSION = "3.3.12"
COMPONENT_HASH = "d792e72ab3858d805d8918d1215a862541344625f62134597866834de666fd04"
SOURCE_TREE_SHA256 = "e5c5155078c46e090ad7f08a7239bb52d456394fab1356d78b4c127eefcb6e86"
PATCH = ROOT / "esp-dl-3.3.12-hw1.patch"
ARCHIVE_URL = f"https://components-file.espressif.com/components/espressif/esp-dl/{VERSION}/{NAME}-v{VERSION}.zip"
# The component manager adds the registry's checksum list to its copy of a package; the tree digest includes it.
CHECKSUMS_URL = f"https://components-file.espressif.com/components/espressif/esp-dl/{VERSION}/CHECKSUMS.json"
PATCH_SHA256 = "a8e46fd492c3c474a8ad757cdf2401e1cbd76aaaa7bc915cfa83b6bda4fc6d75"
PATCHED_TREE_SHA256 = "684fd6e837b2ad74c8eaebf148567462861e875322c745e3766d0645fedc019b"
MANIFEST = "hw1-esp-dl-override.json"
# Present only in component-manager copies; not part of the package itself.
IGNORED = {".component_hash", MANIFEST}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_digest(root: Path) -> str:
    entries = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"unexpected symlink: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            if relative not in IGNORED:
                entries[relative] = digest(path.read_bytes())
    sha = hashlib.sha256()
    for relative, value in sorted(entries.items()):
        sha.update(relative.encode() + b"\0" + bytes.fromhex(value))
    return sha.hexdigest()


def cache_roots() -> list[Path]:
    roots = []
    if os.environ.get("IDF_COMPONENT_CACHE_PATH"):
        roots.append(Path(os.environ["IDF_COMPONENT_CACHE_PATH"]))
    try:  # the component manager's own answer, when its Python package is importable
        from idf_component_tools.file_cache import FileCache  # type: ignore
        roots.append(Path(FileCache().path()))
    except Exception:
        pass
    home = Path.home()
    roots += [home / "Library/Caches/Espressif/ComponentManager", home / ".cache/Espressif/ComponentManager"]
    if os.environ.get("LOCALAPPDATA"):
        roots.append(Path(os.environ["LOCALAPPDATA"]) / "Espressif/ComponentManager/Cache")
    return roots


def candidates(source: Path | None) -> list[Path]:
    if source is not None:
        return [source]
    found = sorted(REPO.glob(f"examples/*/managed_components/{NAME}"))
    for root in cache_roots():
        if root.is_dir():
            found += sorted(root.glob(f"*/{NAME}_{VERSION}_*"))
    return found


def download(into: Path) -> Path:
    """Fetch the published package archive and unpack it under `into`."""
    archive = into / "package.zip"
    print(f"Downloading {ARCHIVE_URL} ...", flush=True)
    with urllib.request.urlopen(ARCHIVE_URL, timeout=120) as response, archive.open("wb") as out:
        shutil.copyfileobj(response, out)
    unpacked = into / NAME
    unpacked.mkdir()
    with zipfile.ZipFile(archive) as archive_zip:
        for member in archive_zip.infolist():
            target = (unpacked / member.filename).resolve()
            if not str(target).startswith(str(unpacked.resolve())):
                raise ValueError(f"archive member escapes the package directory: {member.filename}")
        archive_zip.extractall(unpacked)
    with urllib.request.urlopen(CHECKSUMS_URL, timeout=120) as response, (unpacked / "CHECKSUMS.json").open("wb") as out:
        shutil.copyfileobj(response, out)
    return unpacked


def find_source(source: Path | None, scratch: Path) -> Path:
    for path in candidates(source):
        if (path / "idf_component.yml").is_file() and tree_digest(path) == SOURCE_TREE_SHA256:
            return path
    if source is None:
        unpacked = download(scratch)
        if tree_digest(unpacked) == SOURCE_TREE_SHA256:
            return unpacked
        raise ValueError(f"the downloaded esp-dl {VERSION} package does not match the pinned tree digest")
    raise ValueError(
        f"no pristine esp-dl {VERSION} (component hash {COMPONENT_HASH[:8]}) at --source {source}: pass the "
        f"espressif__esp-dl directory a P4 build left in managed_components/, or the package from "
        f"components.espressif.com (espressif/esp-dl {VERSION}).")


def expected_manifest() -> dict:
    return {"schema": 1, "component": "espressif/esp-dl", "version": VERSION,
            "component_hash": COMPONENT_HASH, "source_tree_sha256": SOURCE_TREE_SHA256,
            "patch_sha256": PATCH_SHA256, "tree_sha256": PATCHED_TREE_SHA256}


def verify(destination: Path) -> None:
    if destination.is_symlink():
        raise ValueError("override destination must not be a symlink")
    manifest = json.loads((destination / MANIFEST).read_text())
    if manifest != expected_manifest():
        raise ValueError("ESP-DL override provenance mismatch (re-stage it: remove the directory and rerun)")
    if tree_digest(destination) != PATCHED_TREE_SHA256:
        raise ValueError("ESP-DL override changed after preparation")


def prepare(destination: Path, source: Path | None, check: bool = False) -> Path:
    if digest(PATCH.read_bytes()) != PATCH_SHA256:
        raise ValueError("ESP-DL patch differs from the reviewed version")
    if destination.exists() or destination.is_symlink():
        verify(destination)
        return destination
    if check:
        raise ValueError("ESP-DL override has not been prepared")
    destination.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=".esp-dl-source-", dir=destination.parent))
    stage = Path(tempfile.mkdtemp(prefix=".esp-dl-", dir=destination.parent))
    try:
        pristine = find_source(source, scratch)
        shutil.copytree(pristine, stage, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*IGNORED))
        applied = subprocess.run(["patch", "-f", "-F", "0", "-p", "1"], input=PATCH.read_bytes(),
                                 cwd=stage, capture_output=True)
        if applied.returncode:
            raise ValueError("ESP-DL patch failed: " + applied.stdout.decode() + applied.stderr.decode())
        for leftover in list(stage.rglob("*.orig")) + list(stage.rglob("*.rej")):
            leftover.unlink()
        if tree_digest(stage) != PATCHED_TREE_SHA256:
            raise ValueError("prepared ESP-DL override does not match the reviewed result")
        (stage / MANIFEST).write_text(json.dumps(expected_manifest(), indent=2, sort_keys=True) + "\n")
        stage.rename(destination)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        if stage.exists():
            shutil.rmtree(stage)
    verify(destination)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, help="a pristine espressif__esp-dl 3.3.12 directory (default: look in examples/*/managed_components, the component manager cache, then download)")
    parser.add_argument("--destination", type=Path, default=REPO / ".sdk-overrides/esp32p4" / NAME)
    parser.add_argument("--check", action="store_true", help="verify an existing override; stage nothing")
    args = parser.parse_args()
    try:
        output = prepare(args.destination.absolute(), args.source, args.check)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"ESP-DL override: {exc}\n")
    print(f"Verified ESP-DL override: {output}")


if __name__ == "__main__":
    sys.exit(main())
