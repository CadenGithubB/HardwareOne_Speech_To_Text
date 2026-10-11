#!/usr/bin/env bash
# Build only. Does not open ports, flash hardware or alter qualified snapshots.
set -euo pipefail
speech_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
camera_dir="${speech_dir}/../camera_portable"
jpeg_dir="${speech_dir}/../jpeg_portable"
roles_dir="${speech_dir}/../p4_ble_roles"
: "${IDF_PATH:?Activate the pinned ESP-IDF 5.5.5 first}"
target="${1:-}"
action="${2:-build}"
case "$action" in build|reconfigure) ;; *) echo "Expected build or reconfigure" >&2; exit 2 ;; esac
case "$target" in
  p4)
    chip=esp32p4; board=p4x_eye
    defaults="${roles_dir}/sdkconfig.connectivity.defaults;${roles_dir}/sdkconfig.p4.bluetooth.defaults;${camera_dir}/sdkconfig.p4.camera.defaults"
    ;;
  s3)
    chip=esp32s3; board=xiao_s3
    defaults="${roles_dir}/sdkconfig.connectivity.defaults;${camera_dir}/sdkconfig.s3.camera.defaults"
    ;;
  *) echo "usage: $0 p4|s3" >&2; exit 2 ;;
esac
defaults="${defaults};${speech_dir}/sdkconfig.speech.defaults"
if [[ "$target" == p4 ]]; then
  defaults="${defaults};${speech_dir}/sdkconfig.p4.speech.defaults"
fi
if [[ "$target" == s3 ]]; then
  defaults="${defaults};${speech_dir}/sdkconfig.s3.speech.defaults"
fi
python3 -B "${speech_dir}/prepare.py" --target "$target" --check
python3 -B "${roles_dir}/prepare_idf_bt.py" --destination "${jpeg_dir}/private/idf-components/bt" --check
extra="${jpeg_dir}/private/idf-components/bt"
if [[ "$target" == p4 ]]; then
  python3 -B "${jpeg_dir}/prepare_idf_jpeg.py" --idf "$IDF_PATH" --check
  extra="${extra};${jpeg_dir}/private/idf-components/esp_driver_jpeg"
fi
build_dir="${speech_dir}/private/build-${target}"
if [[ "$target" == p4 && -f "${build_dir}/sdkconfig" ]]; then
  python3 - "${build_dir}/sdkconfig" <<'PYCONFIG'
from pathlib import Path
import sys
lines = Path(sys.argv[1]).read_text().splitlines()
if 'CONFIG_ESP_HOSTED_MEMPOOL_PREFER_SPIRAM=y' not in lines:
    raise SystemExit('P4 config is stale: stop builds, then run prepare.py --target p4 --apply-p4-config')
PYCONFIG
fi
export HW_BOARD="$board"
unset HW_DEPLOYMENT HW_OTA_LAYOUT
idf.py -C "${speech_dir}/private/app-${target}" -B "$build_dir" \
  -DIDF_TARGET="$chip" -DSDKCONFIG="${build_dir}/sdkconfig" \
  -DEXTRA_COMPONENT_DIRS="$extra" \
  -DHW1_MESH_EXPERIMENT_FEATURE_FILE="${speech_dir}/features-${target}.h" \
  -DHW1_MESH_EXPERIMENT_SDKCONFIG_FILE="$defaults" "$action"
