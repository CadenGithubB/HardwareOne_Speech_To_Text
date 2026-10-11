#!/bin/bash
# One change at a time (2026-10-07): the recipe that produced the P4's "general"
# model plus ONLY the noise-only clips. Same as general: NVIDIA's original
# QuartzNet15x5, --mix general, MUSAN background noise, glasses channel 30%,
# 350 h, chosen by the Broad dev score, at peak LR 1e-5 (the rate general
# effectively trained at after its old guard halved 2e-5), no rollback, warmup
# + cosine fade. Added: 4% noise-only clips with empty transcripts, cut from
# MUSAN + DEMAND exactly as in the general2 runs (--noise-only-pool), which took
# phantom words on held-out noise from 30 to 8 per minute there.
# Waits for the general2 LR 1e-5 pipeline to exit.
# Usage: nohup caffeinate -dims ./run_general_noiseonly_mac.sh > /dev/null 2>&1 &
# Re-running resumes (training from resume.pt).
set -u
cd "$(dirname "$0")"
P=${HW1_STT_PYTHON:-$PWD/../stt_p4/private/export-venv/bin/python}
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
export PYTHONPATH=$STT_ROOT/pydeps
export PYTORCH_ENABLE_MPS_FALLBACK=1
LOG=$STT_ROOT/logs/general-noiseonly.log
OUT=$STT_ROOT/work/general-noiseonly/quartznet15x5
INIT=$STT_ROOT/models/quartznet15x5  # NVIDIA's original weights
say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
busy() { pgrep -f "train.py|evaluate.py|tune.py|lm_eval.py|benchmark.py|session_cache_eval|prepare_data.py|filter_store.py" >/dev/null; }
mkdir -p "$STT_ROOT/logs" "$OUT"
say "=== general + noise-only (pid $$): waiting for the general2 LR 1e-5 run to finish ==="
while pgrep -f "run_general2_lr1e5_mac.sh" >/dev/null; do sleep 120; done
while busy; do sleep 60; done

say "training from NVIDIA's original model: general recipe + 4% noise-only clips (350 h of audio, at most 32 h)"
END=$(cat "$OUT.deadline-epoch" 2>/dev/null || echo $(( $(date +%s) + 32 * 3600 )))
echo "$END" > "$OUT.deadline-epoch"
fails=0
until grep -q '"finished"' "$OUT/train.jsonl" 2>/dev/null; do
  left=$(( (END - $(date +%s)) / 60 ))
  [ $left -le 0 ] && { say "deadline passed"; break; }
  $P train.py --init "$INIT" --out "$OUT" --deadline "+$(echo "scale=2; $left/60" | bc)h" \
    --mix general --dev broad --g2-prob 0.3 --noise-pool musan \
    --noise-only-share 0.04 --noise-only-pool musan+demand \
    --rollback off --accum 4 --optimizer adamw --lr 1e-5 --warmup 300 \
    --target-hours 350 --eval-hours 35 --first-eval-hours 17.5 >> "$LOG" 2>&1
  rc=$?
  [ $rc -eq 0 ] && break
  [ $rc -eq 75 ] && continue  # memory restart: resumes from resume.pt
  fails=$((fails + 1)); [ $fails -ge 4 ] && { say "training failed $fails times (rc=$rc)"; exit 1; }
  say "training exited $rc; retrying"; sleep 20
done

say "test sets for general + noise-only"
$P - <<'EOF'
import json
from pathlib import Path
p = Path('benchmark_models.json'); m = json.loads(p.read_text())
if not any(x['name'] == 'QuartzNet15x5 general + noise-only' for x in m):
    m.append({'name': 'QuartzNet15x5 general + noise-only', 'ckpt': 'work/general-noiseonly/quartznet15x5/best',
              'note': '2026-10-08: the general recipe (NVIDIA original, --mix general, MUSAN noise, G2 aug 0.3, 350 h, '
                      'peak LR 1e-5, no rollback) + 4% noise-only clips from MUSAN+DEMAND; one change at a time'})
    p.write_text(json.dumps(m, indent=2) + '\n')
EOF
$P benchmark.py --run >> "$LOG" 2>&1 || say "benchmark FAILED"
say "=== general + noise-only finished; see BENCHMARK.md ==="
