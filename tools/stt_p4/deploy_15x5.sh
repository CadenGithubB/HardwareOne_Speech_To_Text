#!/usr/bin/env bash
# Put a fine-tuned QuartzNet15x5 checkpoint on the P4X-EYE for a live test.
#
# Reproduces the 2026-09-29 base-15x5 deployment (export-base15 / install-*)
# for any checkpoint, without touching that deployment:
#   stage   copy weights + config, and the base fixtures, into deploy15/ckpt-<name>
#   export  int8 ESP-DL export with the same calibration as export-base15 (~8 min)
#   pack    HW1STT1 envelope + firmware identity header (new artifact file name)
#   build   clone of the 15x5 test firmware (private/app-p4-15x5) plus
#           deploy_15x5.patch (stored-model loader, load timings, 40 MHz SD,
#           preemptible/paced drafts, inference watchdog scope, recording clock), with
#           this model's identity and path; headless, model on microSD
#   card    copy the model to "<card>/STT Models/" (card mounted on this Mac),
#           keeping any other models there
#   flash   write only the app partition (0x10000); bootloader, partition table,
#           LittleFS (settings) and NVS are preserved
#   lm      copy the word LM ($LM) to "<card>/STT Models/meeting.lm". The
#           firmware reads the card's copy first, then the onboard one.
#   lm-remove-onboard
#           delete /STT Models/meeting.lm from the P4's LittleFS over USB
#           (read partition, remove that one file, verify the rest, write back);
#           the image before is kept in deploy15/lmrm-<time>/ for rollback
#
# Usage:
#   experiments/stt_p4/deploy_15x5.sh <checkpoint-dir> <name> [steps...]
#     steps default to: stage export pack build card
#     flash is never implied; add it explicitly (PORT=/dev/cu.usbmodemXXXX).
#   e.g. deploy_15x5.sh "$STT_ROOT/work/run15x5/best" ft15-8877 all flash
#
# Environment (local defaults can be overridden):
#   STT_ROOT  STT data root                   (required)
#   CARD      mounted SD card volume          (required for card and lm)
#   LM        word LM for the lm step         (work/lm/meeting-15x5ft.lm)
#   PORT      P4 USB-Serial/JTAG port         (or HW1_P4_PORT; required for USB steps)
#   ARTIFACT  file name on the card           (quartznet15x5-<name>.p4.stt)
#   CODEC     none (stored, ~20 MB, fast load) or zlib (~15 MB)   (none)
#   CALIB     int8 calibration clips, "store:count ..."  (AMI sdm/ihm + Libri dev, 20 each)
#   CAPTION_TEST=1  also build the Conversate caption test (see G2_Glasses.cpp)
#   IDF_ENV   script that exports ESP-IDF 5.5.5 (~/esp/esp-idf/export.sh)
#
# The firmware pins the model by SHA-256, so each checkpoint gets its own image;
# re-flash the matching build (or the original install) to switch back.
set -euo pipefail

CKPT_SRC=${1:?checkpoint directory (model_weights.ckpt + model_config.yaml)}
NAME=${2:?short name, e.g. ft15-8877}
shift 2
STEPS=("$@")
[ ${#STEPS[@]} -eq 0 ] && STEPS=(stage export pack build card)
[ "${STEPS[0]}" = all ] && STEPS=(stage export pack build card "${STEPS[@]:1}")

HERE=$(cd "$(dirname "$0")" && pwd)
STT=${STT_ROOT:?set STT_ROOT to the STT data root}   # speech stores, work and logs
DEPLOY=$STT/work/deploy15
BASE_CKPT=$DEPLOY/ckpt-base15            # fixtures 0.wav/1.wav + trans.txt
CKPT=$DEPLOY/ckpt-$NAME
EXPORT=$DEPLOY/export-$NAME
ARTIFACT=${ARTIFACT:-quartznet15x5-$NAME.p4.stt}
IDENTITY=stt_model_identity_$NAME.h
CODEC=${CODEC:-none}
# int8 calibration clips (dev stores only). Broad-use models: add peoples-dev:20 voxpopuli-dev:20.
CALIB=${CALIB:-ami-sdm-validation:20 ami-ihm-validation:20 librispeech-dev-clean:20}
FW_PATCH=$HERE/deploy_15x5.patch   # stored-codec loader, load timings, 40 MHz SD, draft pacing, LM on card
PY=${HW1_STT_PYTHON:-$HERE/private/export-venv/bin/python}
SRC_APP=$HERE/private/app-p4-15x5
SRC_FEATURES=$HERE/features-p4-noweb-15x5.h
APP=$HERE/private/app-p4-$NAME
FEATURES=$HERE/private/features-p4-noweb-$NAME.h
BUILD=$HERE/private/build-p4-$NAME
CARD=${CARD:-}                            # mounted microSD card (card and lm steps)
LM=${LM:-$STT/work/lm/meeting-15x5ft.lm}
# The P4X-EYE these test builds may be flashed to. Kept out of git: set UNIT_MAC
# in the environment or in the ignored private/unit.env (UNIT_MAC=xx:xx:...).
[ -f "$HERE/private/unit.env" ] && . "$HERE/private/unit.env"
UNIT_MAC=${UNIT_MAC:?set UNIT_MAC (env or private/unit.env) to the target P4X-EYE MAC}
LFS_OFFSET=0x625000 LFS_SIZE=0x9DB000
LFS_PY=${HW1_LITTLEFS_PYTHON:-$HERE/private/build-p4/littlefs_py_venv/bin/python}
PORT=${PORT:-${HW1_P4_PORT:-}}
IDF_ENV=${IDF_ENV:-$HOME/esp/esp-idf/export.sh}   # ESP-IDF 5.5.5; the /tmp install was wiped 2026-10-02
EXP=$(cd "$HERE/.." && pwd)
SDK_DEFAULTS="$EXP/p4_ble_roles/sdkconfig.connectivity.defaults;$EXP/p4_ble_roles/sdkconfig.p4.bluetooth.defaults;$EXP/camera_portable/sdkconfig.p4.camera.defaults;$EXP/speech_portable/sdkconfig.speech.defaults;$EXP/speech_portable/sdkconfig.p4.speech.defaults;$HERE/sdkconfig.stt.defaults"
EXTRA_DIRS="$HERE/private/idf-components-l2cap/bt;$HERE/private/idf-components-l2cap/esp_driver_jpeg"

say() { echo "[$(date +%T)] $*"; }
sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
json() { "$PY" -c "import json,sys;d=json.load(open(sys.argv[1]));print(eval(sys.argv[2]))" "$@"; }

step_stage() {
  mkdir -p "$CKPT"
  for f in model_weights.ckpt model_config.yaml; do
    if [ ! -f "$CKPT/$f" ] || [ "$(sha "$CKPT/$f")" != "$(sha "$CKPT_SRC/$f")" ]; then
      cp "$CKPT_SRC/$f" "$CKPT/$f"
    fi
  done
  [ -d "$CKPT/fixtures" ] || cp -R "$BASE_CKPT/fixtures" "$CKPT/"
  say "staged $CKPT (weights $(sha "$CKPT/model_weights.ckpt" | cut -c1-12))"
}

step_export() {
  local want; want=$(sha "$CKPT/model_weights.ckpt")
  if [ -f "$EXPORT/manifest.json" ] && [ "$(json "$EXPORT/manifest.json" "d['checkpoint']['weights_sha256']")" = "$want" ]; then
    say "export exists for these weights: $EXPORT"; return
  fi
  say "exporting (int8 w8a8, 60 calibration clips; ~8 min) → $EXPORT.log"
  (cd "$HERE" && PYTHONPATH=$STT/pydeps HW1_STT_ALLOW_WEIGHTS_SHA256=$want caffeinate -i "$PY" export_quartznet.py \
      --checkpoint "$CKPT" --output "$EXPORT" --frontend portable --stage full --quant-type w8a8 \
      --calib-stores $CALIB --calib-seed 2026 \
      --frontend-checkpoint ../speech_portable/private/stt-quartznet) > "$EXPORT.log" 2>&1 \
    || { say "export FAILED; see $EXPORT.log"; exit 1; }
  say "export done"
}

step_pack() {
  local fe; fe=$(json "$EXPORT/manifest.json" "d['frontend_contract_sha256']")
  (cd "$HERE" && "$PY" pack_model.py --manifest "$EXPORT/manifest.json" --frontend-sha256 "$fe" \
      --artifact-name "$ARTIFACT" --identity-name "$IDENTITY" --codec "$CODEC") > "$EXPORT/pack.log"
  say "packed $EXPORT/$ARTIFACT ($(stat -f %z "$EXPORT/$ARTIFACT") bytes, sha $(sha "$EXPORT/$ARTIFACT" | cut -c1-12))"
}

step_build() {
  if [ ! -d "$APP" ]; then
    say "cloning firmware tree → $APP"
    cp -c -R "$SRC_APP" "$APP"            # APFS clone: near-instant, no extra space
  fi
  if ! grep -q readStoredModel "$APP/components/hardwareone/stt/quartznet_runtime.cpp"; then
    (cd "$APP" && patch -p1 -N --no-backup-if-mismatch < "$FW_PATCH") || { say "firmware patch failed"; exit 1; }
  fi
  cp "$EXPORT/$IDENTITY" "$APP/components/hardwareone/stt/stt_model_identity.h"
  sed "s|^#define HW1_STT_MODEL_PATH .*|#define HW1_STT_MODEL_PATH \"/sd/STT Models/$ARTIFACT\"|" \
      "$SRC_FEATURES" > "$FEATURES"
  grep -q "\"/sd/STT Models/$ARTIFACT\"" "$FEATURES" || { say "model path not set in $FEATURES"; exit 1; }
  if [ "${CAPTION_TEST:-0}" = 1 ]; then
    # Test only: auto-arm native Conversate and play scripted TRANSCRIBE_DATA captions.
    printf '\n#undef HW1_CONVERSATE_CAPTION_TEST\n#define HW1_CONVERSATE_CAPTION_TEST 1\n' >> "$FEATURES"
  fi
  # shellcheck disable=SC1090
  source "$IDF_ENV" >/dev/null 2>&1
  say "building → $BUILD (log: $BUILD.log)"
  HW_BOARD=p4x_eye idf.py -C "$APP" -B "$BUILD" -DIDF_TARGET=esp32p4 -DSDKCONFIG="$BUILD/sdkconfig" \
      -DEXTRA_COMPONENT_DIRS="$EXTRA_DIRS" -DHW1_MESH_EXPERIMENT_FEATURE_FILE="$FEATURES" \
      -DHW1_MESH_EXPERIMENT_SDKCONFIG_FILE="$SDK_DEFAULTS" build > "$BUILD.log" 2>&1 \
    || { tail -30 "$BUILD.log"; say "build FAILED"; exit 1; }
  grep "binary size" "$BUILD.log" | tail -1
}

# Remount so verification reads the card, not macOS's cache: on 2026-10-01 a
# 64 KB block of meeting.lm landed wrong and only a fresh read showed it.
remount_card() {
  local dev; dev=$(diskutil info "$CARD" | awk '/Device Node/{print $3}')
  diskutil unmount "$CARD" >/dev/null && diskutil mount "$dev" >/dev/null || { say "remount of $CARD failed"; exit 1; }
}

step_card() {
  [ -d "$CARD" ] || { say "card not mounted at ${CARD:-<unset>} (set CARD)"; exit 1; }
  mkdir -p "$CARD/STT Models"
  cp -X "$EXPORT/$ARTIFACT" "$CARD/STT Models/$ARTIFACT.tmp"   # -X: no macOS ._ files
  mv "$CARD/STT Models/$ARTIFACT.tmp" "$CARD/STT Models/$ARTIFACT"
  dot_clean -m "$CARD/STT Models" 2>/dev/null || true   # macOS writes ._ files on FAT
  sync
  remount_card
  [ "$(sha "$CARD/STT Models/$ARTIFACT")" = "$(sha "$EXPORT/$ARTIFACT")" ] || { say "card copy mismatch"; exit 1; }
  say "card: $CARD/STT Models/$ARTIFACT verified. Eject, then put the card in the P4."
  ls -la "$CARD/STT Models/"
}

step_flash() {
  : "${PORT:?set PORT or HW1_P4_PORT for the target board}"
  [ -c "$PORT" ] || { say "no serial port $PORT"; exit 1; }
  # shellcheck disable=SC1090
  source "$IDF_ENV" >/dev/null 2>&1
  local log=$DEPLOY/install-$NAME-$(date +%H%M)
  mkdir -p "$log"
  cp "$BUILD/hardwareone-idf.bin" "$log/"
  say "flashing app partition only → $PORT"
  python -m esptool --chip esp32p4 -p "$PORT" -b 921600 --before default_reset --after hard_reset \
      write_flash 0x10000 "$BUILD/hardwareone-idf.bin" > "$log/write.log" 2>&1 \
    || { tail -20 "$log/write.log"; say "flash FAILED"; exit 1; }
  grep -E "Hash of data verified|Wrote" "$log/write.log" | tail -2
}

step_lm() {
  [ -d "$CARD" ] || { say "card not mounted at ${CARD:-<unset>} (set CARD)"; exit 1; }
  mkdir -p "$CARD/STT Models"
  cp -X "$LM" "$CARD/STT Models/meeting.lm.tmp"
  mv "$CARD/STT Models/meeting.lm.tmp" "$CARD/STT Models/meeting.lm"
  dot_clean -m "$CARD/STT Models" 2>/dev/null || true
  sync
  remount_card
  [ "$(sha "$CARD/STT Models/meeting.lm")" = "$(sha "$LM")" ] || { say "card LM copy mismatch"; exit 1; }
  say "card: $CARD/STT Models/meeting.lm ($(sha "$LM" | cut -c1-12)) verified"
}

step_lm_remove_onboard() {
  : "${PORT:?set PORT or HW1_P4_PORT for the target board}"
  [ -c "$PORT" ] || { say "no serial port $PORT"; exit 1; }
  # shellcheck disable=SC1090
  source "$IDF_ENV" >/dev/null 2>&1
  local d=$DEPLOY/lmrm-$(date +%H%M%S)
  mkdir -p "$d"
  esp() { python -m esptool --chip esp32p4 -p "$PORT" -b 921600 --before default_reset --after "$1" "${@:2}"; }
  esp no_reset chip_id > "$d/chipid.log" 2>&1
  grep -qi "MAC: *$UNIT_MAC" "$d/chipid.log" || { say "not the expected P4 ($UNIT_MAC)"; exit 1; }
  esp no_reset read_flash $LFS_OFFSET $LFS_SIZE "$d/lfs-before.bin" > "$d/read.log" 2>&1 \
    || { tail -3 "$d/read.log"; say "read FAILED"; exit 1; }
  "$LFS_PY" "$HERE/stage_stt_files.py" "$d/lfs-before.bin" "$d/lfs-after.bin" "$d/stage.json" \
      "/STT Models/meeting.lm=" > "$d/stage.log" 2>&1 \
    || { tail -3 "$d/stage.log"; say "nothing written (no onboard meeting.lm?)"; exit 1; }
  esp hard_reset write_flash $LFS_OFFSET "$d/lfs-after.bin" > "$d/write.log" 2>&1 \
    || { tail -5 "$d/write.log"; say "write FAILED; restore with: write_flash $LFS_OFFSET $d/lfs-before.bin"; exit 1; }
  say "removed onboard meeting.lm; rollback image $d/lfs-before.bin"
}

for s in "${STEPS[@]}"; do
  case $s in
    stage|export|pack|build|card|flash|lm) "step_$s" ;;
    lm-remove-onboard) step_lm_remove_onboard ;;
    *) echo "unknown step: $s" >&2; exit 2 ;;
  esac
done
