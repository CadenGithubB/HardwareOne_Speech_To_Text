#!/bin/bash
# Overnight host queue (phase 5): G2c reference, then train -> int8 export -> device-rule validation
# score for each declared recall variant, serially, one math thread. AMI test is never read here.
# Run from the repository root:  nohup caffeinate -ims tools/overlap_gate/night_host_queue.sh > LOG 2>&1 &
set -u
PY=private/layer-sensitivity-20261103/export-venv/bin/python
P5=private/training-track/overlap-gate/phase5
mkdir -p "$P5"
export OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
echo "=== queue start $(date)"
echo "=== g2c reference eval $(date)"
$PY -B tools/overlap_gate/variant_eval.py private/training-track/overlap-gate/phase3c
for v in g2d g2e g2f g2g; do
  echo "=== $v train $(date)"
  $PY -B tools/overlap_gate/g2_train.py --variant "$v" --threads 1 || { echo "=== $v train FAILED"; continue; }
  echo "=== $v export $(date)"
  $PY -B tools/overlap_gate/g2_export.py --phase3 "$P5/$v" > "$P5/$v/export.log" 2>&1 || { echo "=== $v export FAILED"; tail -5 "$P5/$v/export.log"; continue; }
  echo "=== $v eval $(date)"
  $PY -B tools/overlap_gate/variant_eval.py "$P5/$v" || echo "=== $v eval FAILED"
done
$PY -B tools/overlap_gate/variant_eval.py --summary
echo "=== queue end $(date)"
