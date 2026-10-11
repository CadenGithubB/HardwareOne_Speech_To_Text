#!/bin/bash
# Fine-tune NVIDIA's Citrinet-384 (LibriSpeech-only, CC-BY-4.0) for meetings
# with the run15x5b data recipe: broad mix (+VoxPopuli), simulated G2 glasses
# channel (--g2-prob 0.3), glasses-channel dev sets.
#  1. two 12 h-audio learning-rate trials (AdamW 2e-5 and 1e-4) from the
#     pretrained weights; the model has to move from audiobooks to meetings,
#     so the 15x5's 2e-5 may be too timid
#  2. pick the trial with the better best-score
#  3. full run: 175 h of audio from the pretrained weights at that rate
#  4. full test sets (incl. -g2) for best; compare with run15x5b/full/final.json
# Usage: nohup caffeinate -dims ./run_citrinet384.sh > /dev/null 2>&1 &
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"
P=${HW1_STT_PYTHON:-$PWD/../stt_p4/private/export-venv/bin/python}
export PYTHONPATH=$STT_ROOT/pydeps
export PYTORCH_ENABLE_MPS_FALLBACK=1
ROOT=$STT_ROOT
LOG=$ROOT/logs/citrinet384.log
INIT=$ROOT/models/citrinet384_ls
RUN=$ROOT/work/citrinet384
FULL=$RUN/full
COMMON=(--init "$INIT" --mix broad --dev g2 --g2-prob 0.3 --accum 4 --optimizer adamw)
TESTS="ami-sdm-test ami-ihm-test librispeech-test-clean ami-sdm-test-g2 ami-ihm-test-g2"
mkdir -p "$RUN"

say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

# train <out> <args...>: restart on memory exits (75), give up after 4 errors.
train() {
  local out=$1; shift
  local fails=0 rc
  while :; do
    $P train.py --out "$out" "${COMMON[@]}" "$@" >> "$LOG" 2>&1
    rc=$?
    [ $rc -eq 0 ] && return 0
    if [ $rc -eq 75 ]; then say "train restarting to release memory"; continue; fi
    fails=$((fails + 1))
    [ $fails -ge 4 ] && { say "train failed $fails times (rc=$rc); giving up"; return 1; }
    say "train exited with error $rc; retrying"
    sleep 20
  done
}

best_score() {  # <run dir> -> best score (lower is better), or 9 if none
  "$P" -c "import json,sys; print(json.load(open(sys.argv[1]+'/best/metrics.json'))['score'])" "$1" 2>/dev/null || echo 9
}

say "=== citrinet384 start (pid $$) ==="

# 1. learning-rate trials
if [ ! -f "$RUN/lr" ]; then
  for lr in 2e-5 1e-4; do
    t=$RUN/trial-lr$lr
    if ! grep -q '"finished"' "$t/train.jsonl" 2>/dev/null; then
      say "trial: AdamW lr $lr, 12 h of audio"
      train "$t" --lr $lr --warmup 100 --target-hours 12 --first-eval-hours 6 --eval-hours 6 \
        --deadline "$(date -v+4H +%H:%M)" || say "trial lr $lr FAILED"
    fi
  done
  # 2. choose
  a=$(best_score "$RUN/trial-lr2e-5"); b=$(best_score "$RUN/trial-lr1e-4")
  LR=2e-5
  awk "BEGIN{exit !($b < $a)}" && LR=1e-4
  say "trials: lr 2e-5 best $a, lr 1e-4 best $b -> $LR"
  echo $LR > "$RUN/lr"
fi
LR=$(cat "$RUN/lr")

# 3. full run
if ! grep -q '"finished"' "$FULL/train.jsonl" 2>/dev/null; then
  DEADLINE=$(cat "$RUN/deadline" 2>/dev/null || date -v+20H +%H:%M)
  echo "$DEADLINE" > "$RUN/deadline"
  say "full run: AdamW lr $LR, 175 h of audio, deadline $DEADLINE"
  train "$FULL" --lr "$LR" --deadline "$DEADLINE" || say "full run FAILED"
fi

# 4. test sets
if [ -d "$FULL/best" ]; then
  say "final evaluation of best checkpoint"
  $P evaluate.py --ckpt "$FULL/best" --sets $TESTS --examples 12 --out "$FULL/final.json" >> "$LOG" 2>&1 \
    || say "final evaluation FAILED"
fi
say "=== citrinet384 finished ==="
