#!/bin/zsh
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
REPO_ROOT=${REPO_ROOT:-$(git -C "$(dirname "$0")" rev-parse --show-toplevel)}
# Evaluate 5x5 run2 (first: provides deployed frontend tensors) and 15x5 base.
cd $REPO_ROOT/experiments/stt_p4
P=${HW1_STT_PYTHON:-$REPO_ROOT/experiments/stt_p4/private/export-venv/bin/python}
D=$STT_ROOT/work/deploy15
export PYTHONDONTWRITEBYTECODE=1
# evaluate_dev_int8 loads each checkpoint with one override hash at a time; use a
# wrapper that sets the right hash per checkpoint via quartznet_graph.allowed_weights_sha256.
exec /usr/bin/time -l nice -n 10 $P - "$@" <<'PY'
import os, sys, runpy
import quartznet_graph as g
extra={'d6e7f963195194345e313d0a4ec6182967313a71acfff49a4622a42c968d9900','b2eb3ebc66e9e82829818131c4da02cf9e1109003c3d445b824d9489869143f9'}
g.allowed_weights_sha256=lambda: {g.WEIGHTS_SHA256}|extra
import evaluate_dev_int8
evaluate_dev_int8.load_checkpoint=g.load_checkpoint
sys.argv=['evaluate_dev_int8.py']+sys.argv[1:]
evaluate_dev_int8.main()
PY
