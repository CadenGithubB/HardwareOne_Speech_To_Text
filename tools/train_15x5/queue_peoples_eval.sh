#!/bin/bash
# Non-AMI evaluation (2026-10-02), one job at a time, after the session-cache
# evaluation and the People's Speech test download:
#  1. store peoples-clean-test: ~10 h sampled from every test shard (held out)
#  2. its simulated-glasses copy (make_g2_stores.py)
#  3. BENCHMARK.md: every model on the two new sets (greedy, cached per SHA)
#  4. LM candidates (current meeting-15x5b vs v2 A-D) on the People's Speech
#     test subset with the deployed acoustic checkpoint
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
set -u
cd "$(dirname "$0")"
P=${HW1_STT_PYTHON:-$PWD/../stt_p4/private/export-venv/bin/python}
export PYTHONPATH=$STT_ROOT/pydeps
export PYTORCH_ENABLE_MPS_FALLBACK=1
LOG=$STT_ROOT/logs/peoples-eval.log
say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

say "=== queued (pid $$): waiting for session-cache eval and the test download ==="
until grep -q '^exit=' $STT_ROOT/logs/session-cache-m10.log 2>/dev/null \
      && [ "$(ls $STT_ROOT/peoples_speech/clean_test_*.parquet.done 2>/dev/null | wc -l)" -ge 9 ]; do
  sleep 60
done

if [ ! -f $STT_ROOT/stores/peoples-clean-test/index.json ]; then
  say "1. store peoples-clean-test (~10 h sample)"
  (cd ../stt_train && $P prepare_data.py peoples --split test --fraction 0.17 --max-hours 11) >> "$LOG" 2>&1 \
    || { say "store FAILED"; exit 1; }
fi
if [ ! -f $STT_ROOT/stores/peoples-clean-test-g2/index.json ]; then
  say "2. glasses-channel copy"
  $P make_g2_stores.py peoples-clean-test >> "$LOG" 2>&1 || { say "g2 copy FAILED"; exit 1; }
fi
say "3. benchmark on the new sets"
$P benchmark.py --import-existing --run >> "$LOG" 2>&1 || say "benchmark FAILED"
say "4. LM candidates on People's Speech"
L=$STT_ROOT/work/lm
(cd ../stt_train/lm && $P lm_eval.py --ckpt $STT_ROOT/work/run15x5b/full/best \
    --lms $L/meeting-15x5b.lm $L/v2/A-w60-v40k-2.5M.lm $L/v2/B-auto-v40k-2.5M.lm $L/v2/C-w60-v50k-5M.lm $L/v2/D-w60-v65k-8M.lm \
    --out $L/v2/peoples-eval.json) >> "$LOG" 2>&1 || say "LM eval FAILED"
say "=== done ==="
