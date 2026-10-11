#!/bin/bash
# Put the general-use 15x5 (run_general.sh) on the P4 for a live test while
# its test sets run (2026-10-03, at the user's request):
#  1. wait for the training run to finish; take its best checkpoint
#  2. export (int8 calibrated on AMI, LibriSpeech, People's Speech and
#     VoxPopuli dev clips), pack, build the firmware for it, flash the P4
#  3. retune LM candidate A (2.5 MB, broader text) for this checkpoint
#  4. wait for the SD card in the Mac ($CARD): copy model + LM, verify, eject
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
CARD=${CARD:?set CARD to the mounted microSD card volume}
set -u
: "${PORT:=${HW1_P4_PORT:?set PORT or HW1_P4_PORT for the target board}}"
export PORT
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"
P=${HW1_STT_PYTHON:-$HERE/private/export-venv/bin/python}
RUN=$STT_ROOT/work/general/quartznet15x5
LOG=$STT_ROOT/logs/deploy-general.log
say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

say "=== waiting for the general training run to finish ==="
until grep -q '"finished"' "$RUN/train.jsonl" 2>/dev/null; do sleep 60; done
CK=$RUN/best
STEP=$("$P" -c "import json;print(json.load(open('$CK/metrics.json'))['step'])")
NAME=gen-$STEP
say "best checkpoint: step $STEP ($CK) -> $NAME"

export CALIB="ami-sdm-validation:20 ami-ihm-validation:20 librispeech-dev-clean:20 peoples-dev:20 voxpopuli-dev:20"
./deploy_15x5.sh "$CK" "$NAME" stage export pack build >> "$LOG" 2>&1 || { say "export/build FAILED"; exit 1; }
say "built firmware for $NAME; flashing (app partition only)"
./deploy_15x5.sh "$CK" "$NAME" flash >> "$LOG" 2>&1 || say "flash FAILED (is the P4 on USB?)"

L=$STT_ROOT/work/lm
say "retuning LM candidate A for $NAME"
(cd ../stt_train && PYTHONPATH=$STT_ROOT/pydeps $P lm/tune.py --ckpt "$CK" --lm $L/v2/A-w60-v40k-2.5M.lm \
    --out-lm $L/meeting-$NAME.lm --workers 2) >> "$LOG" 2>&1 || { say "LM retune FAILED"; exit 1; }
grep -E "chosen|^\| ami|^\| libri" "$LOG" | tail -7 | tee -a "$LOG" >/dev/null

say "READY_FOR_CARD: put the SD card in the Mac ($CARD)"
until [ -d "$CARD" ]; do sleep 10; done
sleep 5
./deploy_15x5.sh "$CK" "$NAME" card >> "$LOG" 2>&1 || { say "card copy FAILED"; exit 1; }
LM=$L/meeting-$NAME.lm ./deploy_15x5.sh "$CK" "$NAME" lm >> "$LOG" 2>&1 || { say "card LM copy FAILED"; exit 1; }
diskutil eject "$CARD" >> "$LOG" 2>&1
say "CARD_DONE: model + LM on the card, verified, ejected. Put it in the P4 and reboot."
