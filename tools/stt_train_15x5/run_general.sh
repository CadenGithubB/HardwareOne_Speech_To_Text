#!/bin/bash
# Broad-use pipeline (2026-10-02), one job at a time:
#  1. simulated-glasses copies of the new test/dev sets
#  2. BENCHMARK.md with the Broad column (every model, cached per weights SHA)
#  3. LM candidates ranked on five kinds of speech (deployed acoustic model)
#  4. clean training run for wide everyday use: NVIDIA's original 15x5,
#     --mix general (People's Speech 30, AMI 25, LibriSpeech 20, VoxPopuli 25),
#     G2 channel aug 0.3, AdamW 2e-5, 350 h, checkpoints chosen by --dev broad;
#     then full test sets and a benchmark row
# Usage: nohup caffeinate -dims ./run_general.sh > /dev/null 2>&1 &
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
set -u
cd "$(dirname "$0")"
P=${HW1_STT_PYTHON:-$PWD/../stt_p4/private/export-venv/bin/python}
export PYTHONPATH=$STT_ROOT/pydeps
export PYTORCH_ENABLE_MPS_FALLBACK=1
ROOT=$STT_ROOT
LOG=$ROOT/logs/general.log
OUT=$ROOT/work/general/quartznet15x5
say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
busy() { pgrep -f "train.py|evaluate.py|tune.py|lm_eval.py|benchmark.py|session_cache_eval|prepare_data.py" >/dev/null; }

say "=== general pipeline (pid $$) ==="
while busy; do sleep 60; done

say "1. glasses-channel copies"
$P make_g2_stores.py librispeech-test-clean voxpopuli-validation librispeech-dev-clean peoples-dev voxpopuli-dev \
  >> "$LOG" 2>&1 || { say "g2 copies FAILED"; exit 1; }

say "2. benchmark with the Broad column"
$P benchmark.py --import-existing --run >> "$LOG" 2>&1 || say "benchmark FAILED"

say "3. LM candidates on five kinds of speech"
L=$ROOT/work/lm
(cd ../stt_train/lm && $P lm_eval.py --ckpt $ROOT/work/run15x5b/full/best \
    --sets ami-sdm-test ami-ihm-test libri-test peoples-test vox-test \
    --lms $L/meeting-15x5b.lm $L/v2/A-w60-v40k-2.5M.lm $L/v2/B-auto-v40k-2.5M.lm $L/v2/C-w60-v50k-5M.lm $L/v2/D-w60-v65k-8M.lm \
    --out $L/v2/broad-eval.json) >> "$LOG" 2>&1 || say "LM eval FAILED"
$P - >> "$LOG" 2>&1 <<'EOF'
import os
import json
from train import broad_score
d = json.load(open(os.environ['STT_ROOT'] + '/work/lm/v2/broad-eval.json'))
print('LM broad ranking (WER %, lower is better):')
rows = [('no LM (greedy)', d['greedy'])] + [(k.split('/')[-1], {s: v for s, v in r.items() if s != 'params'}) for k, r in d['lms'].items()]
for name, w in sorted(rows, key=lambda r: broad_score(r[1])):
    print(f"  {name:28s} broad {broad_score(w) * 100:6.2f}  " + '  '.join(f'{s} {v * 100:5.2f}' for s, v in w.items()))
EOF

say "4. clean general-use training run"
mkdir -p "$OUT"
END=$(cat "$OUT.deadline-epoch" 2>/dev/null || echo $(( $(date +%s) + 34 * 3600 )))
echo "$END" > "$OUT.deadline-epoch"
fails=0
until grep -q '"finished"' "$OUT/train.jsonl" 2>/dev/null; do
  left=$(( (END - $(date +%s)) / 60 ))
  [ $left -le 0 ] && { say "deadline passed"; break; }
  $P train.py --init $STT_ROOT/models/quartznet15x5 --out "$OUT" --deadline "+$(echo "scale=2; $left/60" | bc)h" \
    --mix general --dev broad --g2-prob 0.3 --accum 4 --optimizer adamw --lr 2e-5 \
    --target-hours 350 --eval-hours 35 --first-eval-hours 17.5 >> "$LOG" 2>&1
  rc=$?
  [ $rc -eq 0 ] && break
  [ $rc -eq 75 ] && continue
  fails=$((fails + 1)); [ $fails -ge 4 ] && { say "training failed $fails times (rc=$rc)"; exit 1; }
  say "training exited $rc; retrying"; sleep 20
done
say "test sets for the general model"
$P - <<'EOF'
import os
import json
from pathlib import Path
p = Path('benchmark_models.json'); m = json.loads(p.read_text())
if not any(x['name'] == 'QuartzNet15x5 general' for x in m):
    m.append({'name': 'QuartzNet15x5 general', 'ckpt': os.environ['STT_ROOT'] + '/work/general/quartznet15x5/best',
              'note': '2026-10-03: NVIDIA original; --mix general (PS 30, AMI 25, Libri 20, VoxPopuli 25), '
                      'G2 aug 0.3, AdamW 2e-5, 350 h, chosen by --dev broad'})
    p.write_text(json.dumps(m, indent=2) + '\n')
EOF
$P benchmark.py --run >> "$LOG" 2>&1 || say "benchmark FAILED"
say "=== general pipeline finished; see BENCHMARK.md ==="
