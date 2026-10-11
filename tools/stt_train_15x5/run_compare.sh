#!/bin/bash
# Architecture comparison on the expanded data (2026-10-01): NVIDIA's
# QuartzNet15x5 and Citrinet-384, both from their ORIGINAL checkpoints, with an
# identical recipe: --mix expanded (People's Speech filtered by keep.json,
# LibriSpeech-360 subset, VoxPopuli shards 8-11), G2 channel augmentation 0.3,
# G2 dev sets, AdamW 2e-5, 175 h of audio. Then full test sets and BENCHMARK.md.
#  0. wait until peoples-clean-train/keep.json exists (filter reviewed by hand)
#  1. Citrinet-384 (~6 h)   2. QuartzNet15x5 (~13 h)   3. test sets + benchmark
# Usage: nohup caffeinate -dims ./run_compare.sh > /dev/null 2>&1 &
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"
P=${HW1_STT_PYTHON:-$PWD/../stt_p4/private/export-venv/bin/python}
export PYTHONPATH=$STT_ROOT/pydeps
export PYTORCH_ENABLE_MPS_FALLBACK=1
ROOT=$STT_ROOT
LOG=$ROOT/logs/compare.log
RUN=$ROOT/work/expanded
KEEP=$ROOT/stores/peoples-clean-train/keep.json
COMMON=(--mix expanded --dev g2 --g2-prob 0.3 --accum 4 --optimizer adamw --lr 2e-5 --target-hours 175)
TESTS="ami-sdm-test ami-ihm-test librispeech-test-clean ami-sdm-test-g2 ami-ihm-test-g2"
mkdir -p "$RUN"

say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

# train <name> <init>: restart on memory exits (75), give up after 4 errors.
train() {
  local out=$RUN/$1 init=$2 fails=0 rc deadline
  grep -q '"finished"' "$out/train.jsonl" 2>/dev/null && { say "$1 already finished"; return 0; }
  deadline=$(cat "$out.deadline" 2>/dev/null || date -v+22H +%H:%M)
  echo "$deadline" > "$out.deadline"
  say "$1: from $init, deadline $deadline"
  while :; do
    $P train.py --init "$init" --out "$out" --deadline "$deadline" "${COMMON[@]}" >> "$LOG" 2>&1
    rc=$?
    [ $rc -eq 0 ] && break
    if [ $rc -eq 75 ]; then continue; fi
    fails=$((fails + 1))
    [ $fails -ge 4 ] && { say "$1 failed $fails times (rc=$rc); giving up"; return 1; }
    say "$1 exited with error $rc; retrying"
    sleep 20
  done
  say "$1: test sets"
  $P evaluate.py --ckpt "$out/best" --sets $TESTS --examples 12 --out "$out/final.json" >> "$LOG" 2>&1 \
    || say "$1 test evaluation FAILED"
}

say "=== compare start (pid $$); waiting for $KEEP ==="
until [ -f "$KEEP" ]; do sleep 60; done
say "keep.json: $(head -c 300 "$KEEP" | sed 's/"keep": \[[^]]*\], //')"

train citrinet384 $ROOT/models/citrinet384_ls
train quartznet15x5 $STT_ROOT/models/quartznet15x5

# Add both to the benchmark (names fixed so re-runs do not duplicate rows).
"$P" - <<'EOF'
import os
import json
from pathlib import Path
path = Path('benchmark_models.json')
models = json.loads(path.read_text())
names = {m['name'] for m in models}
for name, ckpt in [('Citrinet-384 expanded data', os.environ['STT_ROOT'] + '/work/expanded/citrinet384/best'),
                   ('QuartzNet15x5 expanded data', os.environ['STT_ROOT'] + '/work/expanded/quartznet15x5/best')]:
    if name not in names and Path(ckpt, 'model_weights.ckpt').exists():
        models.append({'name': name, 'ckpt': ckpt,
                       'note': '2026-10-02: from NVIDIA original; --mix expanded (+People\'s Speech filtered, '
                               'Libri-360 subset, VoxPopuli 8-11), G2 aug 0.3, AdamW 2e-5, 175 h'})
path.write_text(json.dumps(models, indent=2) + '\n')
EOF
$P benchmark.py --import-existing --run >> "$LOG" 2>&1
say "=== compare finished; see BENCHMARK.md ==="
