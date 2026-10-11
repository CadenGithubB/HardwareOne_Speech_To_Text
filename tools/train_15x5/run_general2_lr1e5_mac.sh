#!/bin/bash
# Second general2 run, for the learning-rate comparison the user asked for
# (2026-10-06). Same recipe as run_general2_mac.sh (from NVIDIA's original
# QuartzNet15x5, --mix general2, MUSAN + DEMAND noise, 4% noise-only clips,
# glasses channel 30%, NO rollback, warmup + cosine fade, 500 h, chosen by the
# Broad dev score) at peak LR 1e-5 instead of 2e-5: the rate the "general" model
# was effectively trained at (its old guard halved 2e-5 at the first eval).
# Waits for the 2e-5 pipeline to exit, then names both BENCHMARK.md rows by LR.
# Usage: nohup caffeinate -dims ./run_general2_lr1e5_mac.sh > /dev/null 2>&1 &
# Re-running resumes (training from resume.pt).
set -u
cd "$(dirname "$0")"
P=${HW1_STT_PYTHON:-$PWD/../stt_p4/private/export-venv/bin/python}
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
export PYTHONPATH=$STT_ROOT/pydeps
export PYTORCH_ENABLE_MPS_FALLBACK=1
LOG=$STT_ROOT/logs/general2-lr1e5.log
OUT=$STT_ROOT/work/general2-lr1e5/quartznet15x5
INIT=$STT_ROOT/models/quartznet15x5  # NVIDIA's original weights
say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
busy() { pgrep -f "train.py|evaluate.py|tune.py|lm_eval.py|benchmark.py|session_cache_eval|prepare_data.py|filter_store.py" >/dev/null; }
mkdir -p "$STT_ROOT/logs" "$OUT"
say "=== general2 at peak LR 1e-5 (pid $$): waiting for the 2e-5 run to finish ==="
while pgrep -f "run_general2_mac.sh" >/dev/null; do sleep 120; done
while busy; do sleep 60; done

$P - <<'EOF'
import json
from pathlib import Path
p = Path('benchmark_models.json'); m = json.loads(p.read_text())
for x in m:
    if x['name'] == 'QuartzNet15x5 general2':
        x['name'] = 'QuartzNet15x5 general2 (LR 2e-5)'
p.write_text(json.dumps(m, indent=2) + '\n')
EOF

say "training from NVIDIA's original model at peak LR 1e-5 (500 h of audio, at most 42 h)"
END=$(cat "$OUT.deadline-epoch" 2>/dev/null || echo $(( $(date +%s) + 42 * 3600 )))
echo "$END" > "$OUT.deadline-epoch"
fails=0
until grep -q '"finished"' "$OUT/train.jsonl" 2>/dev/null; do
  left=$(( (END - $(date +%s)) / 60 ))
  [ $left -le 0 ] && { say "deadline passed"; break; }
  $P train.py --init "$INIT" --out "$OUT" --deadline "+$(echo "scale=2; $left/60" | bc)h" \
    --mix general2 --dev broad --g2-prob 0.3 --noise-pool musan+demand --noise-only-share 0.04 \
    --rollback off --accum 4 --optimizer adamw --lr 1e-5 --warmup 300 \
    --target-hours 500 --eval-hours 35 --first-eval-hours 17.5 >> "$LOG" 2>&1
  rc=$?
  [ $rc -eq 0 ] && break
  [ $rc -eq 75 ] && continue  # memory restart: resumes from resume.pt
  fails=$((fails + 1)); [ $fails -ge 4 ] && { say "training failed $fails times (rc=$rc)"; exit 1; }
  say "training exited $rc; retrying"; sleep 20
done

say "test sets for general2 at LR 1e-5"
$P - <<'EOF'
import json
from pathlib import Path
p = Path('benchmark_models.json'); m = json.loads(p.read_text())
if not any(x['name'] == 'QuartzNet15x5 general2 (LR 1e-5)' for x in m):
    m.append({'name': 'QuartzNet15x5 general2 (LR 1e-5)', 'ckpt': 'work/general2-lr1e5/quartznet15x5/best',
              'note': '2026-10-07: as general2 (LR 2e-5) but peak LR 1e-5; NVIDIA original, --mix general2, '
                      'MUSAN+DEMAND noise, 4% noise-only, G2 aug 0.3, no rollback, 500 h, chosen by --dev broad'})
    p.write_text(json.dumps(m, indent=2) + '\n')
EOF
$P benchmark.py --run >> "$LOG" 2>&1 || say "benchmark FAILED"
say "=== general2 LR 1e-5 finished; see BENCHMARK.md ==="
