#!/bin/bash
# Daytime continuation (run3): fine-tune from run2's best with more data as it
# lands, until the deadline; then report against the baseline and run2.
# Usage: caffeinate -dims nohup run_day.sh HH:MM &
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
set -u
DEADLINE=${1:-18:00}
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"
P=${HW1_STT_PYTHON:-$PWD/../stt_p4/private/export-venv/bin/python}
export PYTHONPATH=$STT_ROOT/pydeps
export PYTORCH_ENABLE_MPS_FALLBACK=1
ROOT=$STT_ROOT
LOG=$ROOT/logs/day.log
S=$ROOT/stores
DL=$ROOT/logs/download.log
INIT=$ROOT/work/run3-init   # frozen copy of run2/best (what went on the P4)
RUN=$ROOT/work/run3
TESTS="ami-sdm-test ami-ihm-test librispeech-test-clean"

say() { echo "$(date +%T) $*" | tee -a "$LOG"; }
prep() { # store-name prepare-args...
  local name=$1; shift
  if [ -f "$S/$name/index.json" ]; then return 0; fi
  say "prepare $name"
  if nice -n 5 $P prepare_data.py "$@" >> "$LOG" 2>&1; then say "prepared $name"; else say "prepare $name FAILED"; fi
}
before() { [ "$(date +%H%M)" -lt "$1" ]; }

say "=== day run start, deadline $DEADLINE ==="
[ -d "$INIT" ] || { say "missing $INIT"; exit 1; }

# New corpora are prepared in the background; train.py restarts itself to
# pick each one up at its next evaluation.
( until grep -q "DONE libri360" "$DL" 2>/dev/null; do sleep 60; done
  prep librispeech-train-clean-360 librispeech --name train-clean-360 ) &
( until grep -q "DONE voxpopuli" "$DL" 2>/dev/null; do sleep 60; done
  prep voxpopuli-validation voxpopuli --split validation --max-hours 3
  prep voxpopuli-train voxpopuli --split train --max-hours 120 ) &

MAX_SECONDS=110
DL_HHMM=${DEADLINE/:/}
while before "$DL_HHMM"; do
  say "train start (max_seconds=$MAX_SECONDS)"
  $P train.py --init "$INIT" --out "$RUN" --deadline "$DEADLINE" --lr 1.5e-5 --max-seconds $MAX_SECONDS >> "$LOG" 2>&1
  rc=$?
  [ $rc -eq 0 ] && break
  if [ $rc -eq 75 ]; then say "train restarting (memory or new data)"; continue; fi
  say "train exited with error $rc; retrying smaller"
  MAX_SECONDS=$(( MAX_SECONDS * 3 / 4 ))
  [ $MAX_SECONDS -lt 30 ] && MAX_SECONDS=30
  sleep 20
done

if [ -d "$RUN/best" ]; then
  say "final evaluation of run3 best"
  $P evaluate.py --ckpt "$RUN/best" --sets $TESTS voxpopuli-validation --examples 12 --out "$ROOT/work/final-run3.json" >> "$LOG" 2>&1
  $P - <<'PY' >> "$LOG" 2>&1
import os
import json
load = lambda p: json.load(open(p))['results']
b, r2, r3 = load(os.environ['STT_ROOT'] + '/work/baseline.json'), load(os.environ['STT_ROOT'] + '/work/final.json'), load(os.environ['STT_ROOT'] + '/work/final-run3.json')
f = lambda d, k: f"{d[k]['wer']*100:.1f}%" if k in d else '-'
lines = ['# Day run (run3) report', '', '| Test set | Original | Run 2 (on P4) | Run 3 |', '|---|---:|---:|---:|']
lines += [f'| {k} | {f(b, k)} | {f(r2, k)} | {f(r3, k)} |' for k in r3]
open(os.environ['STT_ROOT'] + '/work/REPORT-run3.md', 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
PY
fi
say "=== day run finished ==="
