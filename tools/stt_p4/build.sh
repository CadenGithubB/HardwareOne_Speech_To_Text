#!/usr/bin/env bash
set -euo pipefail
stt_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
speech_dir="${stt_dir}/../speech_portable"
camera_dir="${stt_dir}/../camera_portable"
jpeg_dir="${stt_dir}/../jpeg_portable"
roles_dir="${stt_dir}/../p4_ble_roles"
: "${IDF_PATH:?Activate pinned ESP-IDF 5.5.5 first}"
if [[ "${STT_BUILD_FROZEN:-0}" == 1 ]]; then
  python3 -B "${stt_dir}/prepare.py" --check-frozen
else
  python3 -B "${stt_dir}/prepare.py" --check
fi
python3 -B "${roles_dir}/prepare_idf_bt.py" --destination "${jpeg_dir}/private/idf-components/bt" --check
python3 -B "${jpeg_dir}/prepare_idf_jpeg.py" --idf "$IDF_PATH" --check
defaults="${roles_dir}/sdkconfig.connectivity.defaults;${roles_dir}/sdkconfig.p4.bluetooth.defaults;${camera_dir}/sdkconfig.p4.camera.defaults;${speech_dir}/sdkconfig.speech.defaults;${speech_dir}/sdkconfig.p4.speech.defaults;${stt_dir}/sdkconfig.stt.defaults"
export HW_BOARD=p4x_eye
unset HW_DEPLOYMENT HW_OTA_LAYOUT
build_dir="${stt_dir}/private/build-p4"
idf.py -C "${stt_dir}/private/app-p4" -B "$build_dir" -DIDF_TARGET=esp32p4 -DSDKCONFIG="${build_dir}/sdkconfig" \
 -DEXTRA_COMPONENT_DIRS="${jpeg_dir}/private/idf-components/bt;${jpeg_dir}/private/idf-components/esp_driver_jpeg" \
 -DHW1_MESH_EXPERIMENT_FEATURE_FILE="${stt_dir}/features-p4.h" \
 -DHW1_MESH_EXPERIMENT_SDKCONFIG_FILE="$defaults" "${1:-build}"
