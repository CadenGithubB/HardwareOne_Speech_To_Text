#!/bin/bash
# Unattended overnight pipeline: prepare data as downloads land, measure the
# baseline, fine-tune until the deadline, then measure and report.
# Usage: caffeinate -dims nohup run_overnight.sh HH:MM &
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
set -u
DEADLINE=${1:-06:30}
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"
P=${HW1_STT_PYTHON:-$PWD/../stt_p4/private/export-venv/bin/python}
export PYTHONPATH=$STT_ROOT/pydeps
export PYTORCH_ENABLE_MPS_FALLBACK=1
ROOT=$STT_ROOT
LOG=$ROOT/logs/overnight.log
S=$ROOT/stores
DL=$ROOT/logs/download.log
BASE=$HERE/../speech_portable/private/stt-quartznet
RUN=$ROOT/work/run2  # run1 (lr 2e-4) damaged the model; kept for reference
TESTS="ami-sdm-test ami-ihm-test librispeech-test-clean"

say() { echo "$(date +%T) $*" | tee -a "$LOG"; }
downloaded() { [ -f "$1.done" ]; }
ami_done() { grep -q "DONE ami" "$DL" 2>/dev/null; }
prep() { # store-name prepare-args...
  local name=$1; shift
  if [ -f "$S/$name/index.json" ]; then return 0; fi
  say "prepare $name"
  if $P prepare_data.py "$@" >> "$LOG" 2>&1; then say "prepared $name"; else say "prepare $name FAILED"; fi
}
before() { [ "$(date +%H%M)" -lt "$1" ] || [ "$(date +%H)" -gt 12 ]; }  # HHMM, same night

say "=== overnight pipeline start, training deadline $DEADLINE ==="

# 1. AMI meetings (single distant mic + headset mix), LibriSpeech (HF parquet)
#    and the optional noise/reverb corpora, prepared in parallel as they land.
libri_done() { grep -q "DONE libri" "$DL" 2>/dev/null; }
(
  until libri_done; do sleep 30; done
  prep librispeech-dev-clean librispeech --name dev-clean
  prep librispeech-test-clean librispeech --name test-clean
  prep librispeech-train-clean-100 librispeech --name train-clean-100
) &
LIBRI_PID=$!
( until downloaded $ROOT/rirs/rirs_noises.zip; do sleep 30; done; prep rirs rirs ) &
( until downloaded $ROOT/musan/musan.tar.gz; do sleep 30; done; prep musan-noise musan ) &

until ami_done; do sleep 30; done
AMI_PIDS=""
for spec in "sdm test" "sdm validation" "ihm validation" "ihm test" "sdm train"; do
  set -- $spec
  prep ami-$1-$2 ami --mic $1 --split $2 &
  AMI_PIDS="$AMI_PIDS $!"
done
prep ami-ihm-train ami --mic ihm --split train
wait $AMI_PIDS
wait "$LIBRI_PID"

# 2. Baseline on the held-out test sets.
if [ ! -f "$ROOT/work/baseline.json" ]; then
  say "baseline evaluation"
  $P evaluate.py --ckpt "$BASE" --sets $TESTS --examples 12 --out "$ROOT/work/baseline.json" >> "$LOG" 2>&1
fi
[ -f "$S/rirs/index.json" ] || say "RIRs not ready; using synthetic reverberation"
[ -f "$S/musan-noise/index.json" ] || say "MUSAN not ready; using synthetic noise and speech babble"

# 5. Train until the deadline; resume with smaller batches after a crash.
MAX_SECONDS=110
DL_HHMM=${DEADLINE/:/}
while before "$DL_HHMM"; do
  say "train start (max_seconds=$MAX_SECONDS)"
  $P train.py --init "$BASE" --out "$RUN" --deadline "$DEADLINE" --max-seconds $MAX_SECONDS >> "$LOG" 2>&1
  rc=$?
  [ $rc -eq 0 ] && break
  if [ $rc -eq 75 ]; then say "train restarting to release memory"; continue; fi
  say "train exited with error $rc; retrying smaller"
  MAX_SECONDS=$(( MAX_SECONDS * 3 / 4 ))
  [ $MAX_SECONDS -lt 30 ] && MAX_SECONDS=30
  sleep 20
done

# 6. Final report on the same held-out test sets.
if [ -d "$RUN/best" ]; then
  say "final evaluation of best checkpoint"
  $P evaluate.py --ckpt "$RUN/best" --sets $TESTS --examples 12 --out "$ROOT/work/final.json" >> "$LOG" 2>&1
  $P - <<'EOF' >> "$LOG" 2>&1
import os
import json
b = json.load(open(os.environ['STT_ROOT'] + '/work/baseline.json'))['results']
f = json.load(open(os.environ['STT_ROOT'] + '/work/final.json'))['results']
lines = ['# Overnight fine-tuning report', '', '| Test set | Before WER | After WER |', '|---|---:|---:|']
for k in f:
    lines.append(f"| {k} | {b[k]['wer']*100:.1f}% | {f[k]['wer']*100:.1f}% |")
lines += ['', '## Example transcripts (after)', '']
for k in f:
    lines.append(f'### {k}')
    for e in f[k]['examples']:
        lines.append(f"- ref: {e['ref']}\n  hyp: {e['hyp']}")
open(os.environ['STT_ROOT'] + '/work/REPORT.md', 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines[:8]))
EOF
fi
say "=== overnight pipeline finished ==="
