#!/bin/bash
# Put the general2 LR 1e-5 model (best Broad so far: 22.80, phantom words 9.5/min)
# on the P4 (2026-10-08, at the user's request). The general + noise-only
# training run is paused for the CPU-heavy part and relaunched after it.
#  1. export (int8 calibrated on AMI, LibriSpeech, People's Speech, VoxPopuli
#     dev clips), pack, build the firmware pinned to this model
#  2. retune LM candidate A (2.5 MB) for this checkpoint
#  3. resume the paused training run (one heavy job at a time)
#  4. wait for the SD card in the Mac ($CARD): copy model + LM, verify after a
#     remount, eject
#  5. check the P4 on $PORT (or HW1_P4_PORT) is the test unit (UNIT_MAC from
#     private/unit.env), flash the app partition
# Rollback: re-flash private/build-p4-gen-17868 and put work/lm/meeting-gen-17868.lm
# back as meeting.lm; the old model file stays on the card.
CARD=${CARD:?set CARD to the mounted microSD card volume}
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"
P=${HW1_STT_PYTHON:-$HERE/private/export-venv/bin/python}
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
RUN=$STT_ROOT/work/general2-lr1e5/quartznet15x5
LOG=$STT_ROOT/logs/deploy-gen2.log
PORT=${PORT:-${HW1_P4_PORT:-}}
IDF_ENV=${IDF_ENV:-$HOME/esp/esp-idf/export.sh}
[ -f "$HERE/private/unit.env" ] && . "$HERE/private/unit.env"
say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

CK=$RUN/best
STEP=$("$P" -c "import json;print(json.load(open('$CK/metrics.json'))['step'])")
NAME=gen2-$STEP
say "=== deploy $NAME ($CK) ==="

export CALIB="ami-sdm-validation:20 ami-ihm-validation:20 librispeech-dev-clean:20 peoples-dev:20 voxpopuli-dev:20"
./deploy_15x5.sh "$CK" "$NAME" stage export pack build >> "$LOG" 2>&1 || { say "export/build FAILED"; exit 1; }
say "built firmware for $NAME"

L=$STT_ROOT/work/lm
say "retuning LM candidate A for $NAME"
(cd ../stt_train && PYTHONPATH=$STT_ROOT/pydeps $P lm/tune.py --ckpt "$CK" --lm $L/v2/A-w60-v40k-2.5M.lm \
    --out-lm $L/meeting-$NAME.lm --workers 2) >> "$LOG" 2>&1 || { say "LM retune FAILED"; exit 1; }
grep -E "chosen|^\| ami|^\| libri|^\| peoples|^\| vox" "$LOG" | tail -8 | tee -a "$LOG" >/dev/null

say "resuming the general + noise-only training"
(cd ../stt_train_15x5 && nohup caffeinate -dims ./run_general_noiseonly_mac.sh > /dev/null 2>&1 &)

say "READY_FOR_CARD: put the SD card in the Mac ($CARD)"
until [ -d "$CARD" ]; do sleep 10; done
sleep 5
./deploy_15x5.sh "$CK" "$NAME" card >> "$LOG" 2>&1 || { say "card copy FAILED"; exit 1; }
LM=$L/meeting-$NAME.lm ./deploy_15x5.sh "$CK" "$NAME" lm >> "$LOG" 2>&1 || { say "card LM copy FAILED"; exit 1; }
diskutil eject "$CARD" >> "$LOG" 2>&1
say "CARD_DONE: model + LM on the card, verified, ejected"

# shellcheck disable=SC1090
source "$IDF_ENV" >/dev/null 2>&1
if [ -c "$PORT" ] && python -m esptool --chip esp32p4 -p "$PORT" -b 921600 --before default_reset --after no_reset \
     chip_id 2>&1 | grep -qi "MAC: *${UNIT_MAC:-none}"; then
  PORT=$PORT ./deploy_15x5.sh "$CK" "$NAME" flash >> "$LOG" 2>&1 && say "FLASHED: $NAME firmware on the P4" \
    || say "flash FAILED"
else
  say "FLASH SKIPPED: the test P4 is not on ${PORT:-<unset>} (set PORT or HW1_P4_PORT=... and run: ./deploy_15x5.sh $CK $NAME flash)"
fi
say "=== done: put the card in the P4 and reboot it ==="
