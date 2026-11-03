#!/bin/zsh
# Build PCM-bench arms from the HardwareOne bench branch (claude/stt-bench).
#
#   build_arms.sh "NAME X FIRST_FAST END_SILENCE_MS SHORT_CLOSE_MS" [...]
#
# For each arm: set the macro defaults in System_STT.cpp (draft pacing X, first-draft fast,
# phrase-closing pauses), build the p4-openclaw configuration, check 64-byte L2 lines and 250 MHz
# PSRAM, and save the app, ELF, sdkconfig, build manifest and source diff to $ARM_OUT/arm-NAME/
# plus $ARM_OUT/bench-NAME.bin for heaptw_remote.py flash. Production defaults are restored at the end.
#
# HW1_BENCH   bench checkout (default ~/esp/hw1-bench)
# ARM_OUT     output folder (default ./arms)
# IDF_EXPORT  ESP-IDF export script (default ~/esp/esp-idf/export.sh)
B=${HW1_BENCH:-$HOME/esp/hw1-bench}
OUT=${ARM_OUT:-$PWD/arms}
F=$B/components/hardwareone/System_STT.cpp
setm() { sed -i '' -E "s/^#define $1 [0-9]+$/#define $1 $2/" $F; grep -q "^#define $1 $2$" $F || { echo "macro $1 not set"; exit 1; }; }
source ${IDF_EXPORT:-$HOME/esp/esp-idf/export.sh} >/dev/null 2>&1
mkdir -p $OUT
cd $B || exit 1
for spec in "$@"; do
  set -- ${=spec}
  name=$1
  setm HW1_STT_DRAFT_PACE_X $2; setm HW1_STT_DRAFT_FIRST_FAST $3; setm HW1_STT_END_SILENCE_MS $4; setm HW1_STT_SHORT_CLOSE_MS $5
  python3 tools/build_config.py build p4-openclaw > $OUT/build-$name.log 2>&1 || { echo "$name build failed (see $OUT/build-$name.log)"; exit 1; }
  d=$OUT/arm-$name; mkdir -p $d
  cp build-config-p4-openclaw/{hardwareone-idf.bin,hardwareone-idf.elf,sdkconfig,BUILD_INFO.md} $d/
  git diff > $d/source.diff
  shasum -a 256 $d/hardwareone-idf.bin | cut -c1-64 > $d/app.sha256
  cp $d/hardwareone-idf.bin $OUT/bench-$name.bin
  grep -q "^CONFIG_CACHE_L2_CACHE_LINE_64B=y" $d/sdkconfig && grep -q "^CONFIG_SPIRAM_SPEED_250M=y" $d/sdkconfig \
    || { echo "$name: build folder is not on 64-byte L2 lines and 250 MHz PSRAM"; exit 1; }
  echo "$name built $(cut -c1-8 $d/app.sha256)"
done
setm HW1_STT_DRAFT_PACE_X 1; setm HW1_STT_DRAFT_FIRST_FAST 0; setm HW1_STT_END_SILENCE_MS 600; setm HW1_STT_SHORT_CLOSE_MS 1000
echo "all built; production defaults restored"
