#!/bin/bash
# QuartzNet15x5 fine-tune with the run2 (5x5) recipe, queued behind run3.
#  1. wait for the 5x5 day run (experiments/stt_train/run_day.sh) to finish
#  2. baseline of the original 15x5 on the full test sets
#  3. short memory/speed benchmark to pick the gradient-accumulation split
#  4. train to run2's audio budget (~175 h), capped by the deadline
#  5. final test eval of best, CPU speed of both models, REPORT.md
# Usage: nohup caffeinate -dims ./run_15x5.sh [HH:MM training deadline] &
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
set -u
DEADLINE=${1:-06:15}
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"
P=${HW1_STT_PYTHON:-$PWD/../stt_p4/private/export-venv/bin/python}
export PYTHONPATH=$STT_ROOT/pydeps
export PYTORCH_ENABLE_MPS_FALLBACK=1
ROOT=$STT_ROOT
LOG=$ROOT/logs/run15x5.log
DAYLOG=$ROOT/logs/day.log
OTHER=$(cd "$HERE/../stt_train" && pwd)
MODEL=$STT_ROOT/models/quartznet15x5
BASE5=$HERE/../speech_portable/private/stt-quartznet
RUN=$ROOT/work/run15x5
TESTS="ami-sdm-test ami-ihm-test librispeech-test-clean"
mkdir -p "$RUN"

say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
before() { [ "$(date +%H%M)" -lt "$1" ] || [ "$(date +%H)" -gt 12 ]; }  # HHMM, next morning

# Python processes whose working directory is experiments/stt_train
# (train.py and its DataLoader workers, evaluate.py, prepare_data.py).
other_pids() {
  for pid in $(pgrep -f 'python' 2>/dev/null); do
    cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
    [ "$cwd" = "$OTHER" ] && echo "$pid"
  done
}
other_train() {
  for pid in $(other_pids); do
    ps -o command= -p "$pid" 2>/dev/null | grep -q 'train.py' && return 0
  done
  return 1
}

say "=== run15x5 queued (pid $$), training deadline $DEADLINE; waiting for run3 ==="

# 1. Wait for run3: its log line AND no train.py from experiments/stt_train.
#    Fallback if run_day.sh disappears without the line (killed by hand):
#    proceed after 30 min with neither run_day.sh nor stt_train python alive.
idle=0
until grep -q '=== day run finished ===' "$DAYLOG" 2>/dev/null && ! other_train; do
  if ! pgrep -f 'run_day.sh' >/dev/null && [ -z "$(other_pids)" ]; then
    idle=$((idle + 1))
    [ $idle -ge 30 ] && { say "run_day.sh gone without its finish line; proceeding"; break; }
  else
    idle=0
  fi
  sleep 60
done
# Let stragglers (evaluate.py / prepare_data.py in stt_train) finish; max 2 h.
for _ in $(seq 120); do
  [ -z "$(other_pids)" ] && break
  sleep 60
done
[ -n "$(other_pids)" ] && say "stt_train python still running ($(other_pids | tr '\n' ' ')); starting anyway"
other_train && { say "run3 train.py still running; refusing to start"; exit 1; }
say "run3 finished; starting 15x5"
sleep 30

# 2. Baseline of the original 15x5 on the full test sets (MPS, as the 5x5's).
if [ ! -f "$RUN/baseline.json" ]; then
  say "baseline evaluation (full test sets)"
  $P evaluate.py --ckpt "$MODEL" --sets $TESTS --examples 12 --out "$RUN/baseline.json" >> "$LOG" 2>&1 \
    || $P evaluate.py --device cpu --ckpt "$MODEL" --sets $TESTS --examples 12 --out "$RUN/baseline.json" >> "$LOG" 2>&1 \
    || say "baseline evaluation FAILED"
fi

# 3. Pick micro-batches: effective batch stays run2's 110 s / 32 items.
ACCUM=${ACCUM:-}
if [ -z "$ACCUM" ] && [ ! -f "$RUN/resume.pt" ]; then
  for a in 2 4; do
    say "benchmark accum=$a ($((110 / a)) s micro-batches)"
    $P train.py --init "$MODEL" --out "$RUN/bench-a$a" --deadline "$DEADLINE" --accum $a \
      --benchmark-steps 60 >> "$LOG" 2>&1
    rc=$?
    line=$(grep '"benchmark"' "$RUN/bench-a$a/train.jsonl" 2>/dev/null | tail -1)
    say "benchmark accum=$a rc=$rc $line"
    mem=$(echo "$line" | sed -n 's/.*"mem_gb": \([0-9.]*\).*/\1/p')
    if [ $rc -eq 0 ] && [ -n "$mem" ] && awk "BEGIN{exit !($mem <= 5.3)}"; then
      ACCUM=$a
      rate=$(echo "$line" | sed -n 's/.*"audio_seconds_per_second": \([0-9.]*\).*/\1/p')
      [ -n "$rate" ] && say "expected training time for 175 h: $(awk "BEGIN{printf \"%.1f\", 175*3600/$rate/3600}") h + ~9 CPU dev evals"
      break
    fi
    sleep 20
  done
fi
ACCUM=${ACCUM:-4}
[ -f "$RUN/accum" ] && [ -f "$RUN/resume.pt" ] && ACCUM=$(cat "$RUN/accum")
echo $ACCUM > "$RUN/accum"

# 4. Train until the audio budget or the deadline; restart on memory exits,
#    split batches further after a crash.
DL_HHMM=${DEADLINE/:/}
fails=0
while before "$DL_HHMM"; do
  say "train start (accum=$ACCUM)"
  $P train.py --init "$MODEL" --out "$RUN" --deadline "$DEADLINE" --accum $ACCUM >> "$LOG" 2>&1
  rc=$?
  [ $rc -eq 0 ] && break
  if [ $rc -eq 75 ]; then say "train restarting to release memory"; continue; fi
  fails=$((fails + 1))
  [ $fails -ge 6 ] && { say "train failed $fails times; giving up"; break; }
  [ $ACCUM -lt 8 ] && ACCUM=$((ACCUM * 2))
  echo $ACCUM > "$RUN/accum"
  say "train exited with error $rc; retrying with accum=$ACCUM"
  sleep 20
done

# 5. Final test eval of the best checkpoint, CPU speed, report.
if [ -d "$RUN/best" ]; then
  say "final evaluation of best checkpoint"
  $P evaluate.py --ckpt "$RUN/best" --sets $TESTS --examples 12 --out "$RUN/final.json" >> "$LOG" 2>&1 \
    || $P evaluate.py --device cpu --ckpt "$RUN/best" --sets $TESTS --examples 12 --out "$RUN/final.json" >> "$LOG" 2>&1 \
    || say "final evaluation FAILED"
fi
say "CPU speed measurement"
$P speed.py --ckpt 5x5="$BASE5" 15x5="$MODEL" --threads 1 0 --per-set 20 --out "$RUN/speed.json" >> "$LOG" 2>&1
$P report.py >> "$LOG" 2>&1 && say "report: $RUN/REPORT.md"
say "=== run15x5 finished ==="
