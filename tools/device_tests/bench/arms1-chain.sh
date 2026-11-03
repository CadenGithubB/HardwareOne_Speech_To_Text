#!/bin/sh
# Pause-length and pacing arms on 64-byte L2 lines: flash each, 3 bench runs, then score all.
cd /Users/cadbecaimacmini/claude-heaptw || exit 1
PY=/Users/cadbecaimacmini/.espressif/python_env/idf5.5_py3.9_env/bin/python
while [ -e busy.lock ]; do sleep 20; done
touch busy.lock
for arm in prodl64 x2fes400 x2fsc700 x2fes4sc7; do
  $PY -u heaptw_remote.py flash bench-$arm.bin > flash-$arm.out 2>&1 && \
    $PY -u heaptw_remote.py bench $arm /sd/recordings/bench_conv1.pcm 3 > bench-$arm.out 2>&1
done
for arm in x2f250l64 prodl64 x2fes400 x2fsc700 x2fes4sc7; do
  d=$(ls -dt bench-$arm-2* 2>/dev/null | head -1)
  [ -n "$d" ] || { echo "$arm: no run"; continue; }
  echo "== $arm $d"
  /usr/bin/python3 benchscore.py conv1/manifest.json "$d" | grep SUMMARY
  /usr/bin/python3 truelag.py conv1/manifest.json "$d"
  /usr/bin/python3 latsplit.py "$d" | head -3
  /usr/bin/python3 draftlag.py "$d" | tail -3
done > arms1-summary.txt 2>&1
echo "$(date +%H:%M:%S) arms1 done" >> progress.log
rm -f busy.lock
