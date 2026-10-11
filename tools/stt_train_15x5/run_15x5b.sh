#!/bin/bash
# Continued 15x5 fine-tune (run15x5b) from run15x5's best (step 8877), with the
# options added 2026-09-30: broader data (+VoxPopuli), simulated glasses-mic
# channel augmentation (--g2-prob) and glasses-channel dev sets (--dev g2).
#  1. trial: NeMo-style NovoGrad at 1e-3 for 12 h of audio (~1.5 h with evals)
#  2. choose the optimizer: NovoGrad if the trial's best beats its own step-0
#     score by >= 1% relative, otherwise the proven AdamW 2e-5
#  3. full run: 175 h of audio (~13-15 h), from run15x5/best again
#  4. test sets (incl. the -g2 copies) for best; compare with run15x5's
#     final.json / final-g2.json before deploying anything
# Usage: nohup caffeinate -dims ./run_15x5b.sh > /dev/null 2>&1 &
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"
P=${HW1_STT_PYTHON:-$PWD/../stt_p4/private/export-venv/bin/python}
export PYTHONPATH=$STT_ROOT/pydeps
export PYTORCH_ENABLE_MPS_FALLBACK=1
ROOT=$STT_ROOT
LOG=$ROOT/logs/run15x5b.log
INIT=$ROOT/work/run15x5/best
RUN=$ROOT/work/run15x5b
TRIAL=$RUN/trial-novograd
FULL=$RUN/full
COMMON=(--init "$INIT" --mix broad --dev g2 --g2-prob 0.3 --accum 4)
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

score_of() {  # <run dir> <jq-like selector: first|best> -> score
  "$P" - "$1" "$2" <<'EOF'
import json, sys
from pathlib import Path
run, which = Path(sys.argv[1]), sys.argv[2]
evals = [json.loads(l) for l in open(run / 'train.jsonl') if '"event": "eval"' in l]
if which == 'first':
    print(evals[0]['score'])
else:
    print(json.loads((run / 'best' / 'metrics.json').read_text())['score'])
EOF
}

say "=== run15x5b start (pid $$) ==="

# 1. NovoGrad trial
if [ ! -f "$RUN/optimizer" ]; then
  if ! grep -q '"finished"' "$TRIAL/train.jsonl" 2>/dev/null; then
    say "trial: NovoGrad lr 1e-3, 12 h of audio"
    train "$TRIAL" --optimizer novograd --lr 1e-3 --warmup 100 --target-hours 12 \
      --first-eval-hours 6 --eval-hours 6 --deadline "$(date -v+5H +%H:%M)" || say "trial FAILED"
  fi
  # 2. choose
  OPT=adamw
  if grep -q '"finished"' "$TRIAL/train.jsonl" 2>/dev/null; then
    s0=$(score_of "$TRIAL" first); sb=$(score_of "$TRIAL" best)
    awk "BEGIN{exit !($sb <= $s0 * 0.99)}" && OPT=novograd
    say "trial: step-0 score $s0, best $sb -> $OPT"
  fi
  echo $OPT > "$RUN/optimizer"
fi
OPT=$(cat "$RUN/optimizer")

# 3. full run
if [ "$OPT" = novograd ]; then
  OPT_ARGS=(--optimizer novograd --lr 1e-3)
else
  OPT_ARGS=(--optimizer adamw --lr 2e-5)
fi
if ! grep -q '"finished"' "$FULL/train.jsonl" 2>/dev/null; then
  DEADLINE=$(cat "$RUN/deadline" 2>/dev/null || date -v+20H +%H:%M)
  echo "$DEADLINE" > "$RUN/deadline"
  say "full run: $OPT ${OPT_ARGS[*]}, 175 h of audio, deadline $DEADLINE"
  train "$FULL" "${OPT_ARGS[@]}" --deadline "$DEADLINE" || say "full run FAILED"
fi

# 4. test sets
if [ -d "$FULL/best" ]; then
  say "final evaluation of best checkpoint"
  $P evaluate.py --ckpt "$FULL/best" --sets $TESTS --examples 12 --out "$FULL/final.json" >> "$LOG" 2>&1 \
    || say "final evaluation FAILED"
fi
say "=== run15x5b finished ==="
