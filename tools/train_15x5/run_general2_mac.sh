#!/bin/bash
# general2 on this Mac (2026-10-05; the A4000 PC route was dropped), from the ground up.
# The kit/run_continuation.sh recipe with this Mac's settings, one job at a time:
#  1. transcript filter for the 60 new People's Speech shards (keep.json)
#  2. training from NVIDIA's original QuartzNet15x5 (none of our earlier training;
#     the user asked for a run from the ground up): --mix general2 (+People's
#     Speech, +Common Voice), MUSAN + DEMAND noise, 4% noise-only clips with empty
#     transcripts, glasses channel 30%, NO rollback, AdamW peak LR 2e-5 (as the
#     general run), 500 h, checkpoints chosen by the Broad dev score
#  3. full test sets + noise columns: a 'QuartzNet15x5 general2' row in BENCHMARK.md
# Usage: nohup caffeinate -dims ./run_general2_mac.sh > /dev/null 2>&1 &
# Re-running resumes (filter skipped once keep.json exists, training from resume.pt).
set -u
cd "$(dirname "$0")"
P=${HW1_STT_PYTHON:-$PWD/../stt_p4/private/export-venv/bin/python}
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
export PYTHONPATH=$STT_ROOT/pydeps
export PYTORCH_ENABLE_MPS_FALLBACK=1
LOG=$STT_ROOT/logs/general2.log
OUT=$STT_ROOT/work/general2/quartznet15x5
INIT=$STT_ROOT/models/quartznet15x5                     # NVIDIA's original weights
FILTER_CKPT=$STT_ROOT/work/general/quartznet15x5/best  # transcript filter only
say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
busy() { pgrep -f "train.py|evaluate.py|tune.py|lm_eval.py|benchmark.py|session_cache_eval|prepare_data.py|filter_store.py" >/dev/null; }
mkdir -p "$STT_ROOT/logs" "$OUT"
say "=== general2 on the Mac (pid $$) ==="
while busy; do sleep 60; done

if [ ! -f "$STT_ROOT/stores/peoples-clean-train2/keep.json" ]; then
  say "1. transcript filter: peoples-clean-train2"
  $P filter_store.py --store peoples-clean-train2 --ckpt "$FILTER_CKPT" --max-cer 0.5 >> "$LOG" 2>&1 \
    || { say "filter FAILED"; exit 1; }
  say "   $(grep '"kept"' "$LOG" | tail -1)"
fi

say "2. training from NVIDIA's original model (500 h of audio, at most 42 h)"
END=$(cat "$OUT.deadline-epoch" 2>/dev/null || echo $(( $(date +%s) + 42 * 3600 )))
echo "$END" > "$OUT.deadline-epoch"
fails=0
until grep -q '"finished"' "$OUT/train.jsonl" 2>/dev/null; do
  left=$(( (END - $(date +%s)) / 60 ))
  [ $left -le 0 ] && { say "deadline passed"; break; }
  $P train.py --init "$INIT" --out "$OUT" --deadline "+$(echo "scale=2; $left/60" | bc)h" \
    --mix general2 --dev broad --g2-prob 0.3 --noise-pool musan+demand --noise-only-share 0.04 \
    --rollback off --accum 4 --optimizer adamw --lr 2e-5 --warmup 300 \
    --target-hours 500 --eval-hours 35 --first-eval-hours 17.5 >> "$LOG" 2>&1
  rc=$?
  [ $rc -eq 0 ] && break
  [ $rc -eq 75 ] && continue  # memory restart: resumes from resume.pt
  fails=$((fails + 1)); [ $fails -ge 4 ] && { say "training failed $fails times (rc=$rc)"; exit 1; }
  say "training exited $rc; retrying"; sleep 20
done

say "3. test sets for general2"
$P - <<'EOF'
import json
from pathlib import Path
p = Path('benchmark_models.json'); m = json.loads(p.read_text())
if not any(x['name'] == 'QuartzNet15x5 general2' for x in m):
    m.append({'name': 'QuartzNet15x5 general2', 'ckpt': 'work/general2/quartznet15x5/best',
              'note': '2026-10-05: NVIDIA original; --mix general2 (+People\'s Speech 2, +Common Voice), '
                      'MUSAN+DEMAND noise, 4% noise-only, G2 aug 0.3, no rollback, AdamW 2e-5, 500 h, chosen by --dev broad'})
    p.write_text(json.dumps(m, indent=2) + '\n')
EOF
$P benchmark.py --run >> "$LOG" 2>&1 || say "benchmark FAILED"
say "=== general2 finished; see BENCHMARK.md ==="
