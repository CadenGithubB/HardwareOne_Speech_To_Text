#!/bin/bash
# Continuation run on the Ubuntu A4000 PC (2026-10-03). Run from the kit
# folder on the SSD after bash setup_ubuntu.sh:
#   nohup bash run_continuation.sh > /dev/null 2>&1 &   (log: <SSD>/stt/logs/continuation.log)
# Steps, one at a time; each is skipped if already done, so re-running resumes:
#  1. transcript filter for the 60 new People's Speech shards (GPU, minutes)
#  2. 60-step speed check: bf16 + full batch, falling back to fp32 / 2 micro-batches
#  3. continuation from the general model's best checkpoint: --mix general2
#     (+People's Speech, +Common Voice), DEMAND background noise, 4% noise-only
#     clips with empty transcripts, glasses channel 30%, NO rollback, peak LR
#     1e-5, 500 h of audio, checkpoints chosen by the Broad dev score
#  4. full test sets + noise columns (benchmark.py); BENCHMARK.md in the kit
set -u
KIT=$(cd "$(dirname "$0")" && pwd)
# Keep the PC awake while this runs: a suspended PC stops the training.
if [ -z "${HW1_AWAKE:-}" ]; then
  if command -v systemd-inhibit >/dev/null && systemd-inhibit --what=sleep:idle true 2>/dev/null; then
    export HW1_AWAKE=1
    exec systemd-inhibit --what=sleep:idle --who="HardwareOne STT" --why="training run" bash "$KIT/run_continuation.sh" "$@"
  fi
  echo "note: could not block sleep; turn off Settings > Power > Automatic Suspend so the PC stays awake"
fi
export STT_ROOT=${STT_ROOT:-$(dirname "$KIT")/stt}
PY=${PY:-$HOME/hw1-stt-venv/bin/python}
[ -x "$PY" ] || { echo "$PY not found: run setup_ubuntu.sh first"; exit 1; }
export HW1_LC3_BUILD=${HW1_LC3_BUILD:-$(dirname "$(dirname "$PY")")/lc3}  # built by setup_ubuntu.sh
WORKERS=${WORKERS:-$(( $(nproc) > 4 ? $(nproc) - 2 : 2 ))}
OUT=$STT_ROOT/work/general2/quartznet15x5
INIT=$STT_ROOT/work/general/quartznet15x5/best
LOG=$STT_ROOT/logs/continuation.log
mkdir -p "$STT_ROOT/logs" "$OUT"
say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
cd "$KIT/experiments/stt_train_15x5"
[ -d "$STT_ROOT/stores" ] || { echo "no stores under $STT_ROOT (set STT_ROOT=<mount>/stt)"; exit 1; }

say "=== continuation on $(hostname) | STT_ROOT=$STT_ROOT | workers $WORKERS ==="

if [ ! -f "$STT_ROOT/stores/peoples-clean-train2/keep.json" ]; then
  say "1. transcript filter: peoples-clean-train2"
  "$PY" filter_store.py --store peoples-clean-train2 --ckpt "$INIT" --max-cer 0.5 >> "$LOG" 2>&1 \
    || { say "filter FAILED"; exit 1; }
  tail -1 "$LOG"
fi

COMMON=(--init "$INIT" --mix general2 --dev broad --g2-prob 0.3 --noise-pool musan+demand
        --noise-only-share 0.04 --rollback off --optimizer adamw --lr 1e-5 --warmup 300 --workers "$WORKERS")
MODE=$(cat "$OUT.mode" 2>/dev/null || true)
if [ -z "$MODE" ]; then
  say "2. speed check (60 steps)"
  for m in "--amp --accum 1" "--accum 1" "--amp --accum 2" "--accum 2"; do
    rm -rf "$STT_ROOT/work/bench-a4000"
    if "$PY" train.py --out "$STT_ROOT/work/bench-a4000" --deadline +1h "${COMMON[@]}" $m \
         --benchmark-steps 60 >> "$LOG" 2>&1; then
      MODE="$m"; break
    fi
    say "   mode '$m' failed; trying the next"
  done
  [ -n "$MODE" ] || { say "no training mode works"; exit 1; }
  echo "$MODE" > "$OUT.mode"
  say "   using: $MODE  ($(grep '"benchmark"' "$STT_ROOT/work/bench-a4000/train.jsonl" | tail -1))"
fi

END=$(cat "$OUT.deadline-epoch" 2>/dev/null || echo $(( $(date +%s) + 30 * 3600 )))
echo "$END" > "$OUT.deadline-epoch"
until grep -q '"finished"' "$OUT/train.jsonl" 2>/dev/null; do
  left=$(( (END - $(date +%s)) / 60 ))
  [ $left -le 0 ] && { say "deadline passed"; break; }
  say "3. continuation run ($MODE)"
  "$PY" train.py --out "$OUT" --deadline "+$(( left / 60 ))h" "${COMMON[@]}" $MODE \
    --target-hours 500 --eval-hours 35 --first-eval-hours 17.5 >> "$LOG" 2>&1 && break
  say "   training exited with an error; retrying in 30 s"; sleep 30
done

say "4. test sets"
"$PY" - <<'EOF'
import json
from pathlib import Path
p = Path('benchmark_models.json'); m = json.loads(p.read_text())
if not any(x['name'] == 'QuartzNet15x5 general2' for x in m):
    m.append({'name': 'QuartzNet15x5 general2', 'ckpt': 'work/general2/quartznet15x5/best',
              'note': 'A4000: continuation of "general"; --mix general2 (+People\'s Speech, +Common Voice), '
                      'DEMAND noise, 4% noise-only, G2 aug 0.3, no rollback, LR 1e-5, 500 h'})
    p.write_text(json.dumps(m, indent=2) + '\n')
EOF
"$PY" benchmark.py --run >> "$LOG" 2>&1 || say "benchmark FAILED"
say "=== done: bring the SSD back to the Mac (results in work/general2, BENCHMARK.md in the kit) ==="
