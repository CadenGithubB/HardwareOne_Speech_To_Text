#!/bin/bash
# flash_variant.sh <build-dir-name>: MAC check, partition-table check, app-only flash.
# HW1_STT_P4: the HardwareOne experiments/stt_p4 folder with private/<build-dir>/ and private/unit.env.
set -u
D=$(cd "$(dirname "$0")" && pwd)
L=$D/private; mkdir -p "$L"                # chip ID and partition-table reads (git-ignored)
cd "${HW1_STT_P4:?set HW1_STT_P4 to the HardwareOne experiments/stt_p4 folder}"
B=private/$1/hardwareone-idf.bin
[ -f "$B" ] || { echo "no $B"; exit 1; }
PORT=$(HW1_STT_P4=$PWD "${HW1_STT_PYTHON:-python3}" "$D/find_p4_port.py" 2>/dev/null | tail -1)
. private/unit.env; source ~/esp/esp-idf/export.sh >/dev/null 2>&1
python -m esptool --chip esp32p4 -p "$PORT" -b 921600 --before default_reset --after no_reset chip_id > $L/chipid.log 2>&1
grep -qi "MAC: *$UNIT_MAC" $L/chipid.log || { echo "not the test P4 on $PORT"; exit 1; }
python -m esptool --chip esp32p4 -p "$PORT" -b 921600 --before no_reset --after no_reset read_flash 0x8000 0xc00 $L/pt.bin > /dev/null 2>&1
cmp -s $L/pt.bin private/build-p4-gen2-25397/partition_table/partition-table.bin || { echo "partition table differs: not flashing"; exit 1; }
python -m esptool --chip esp32p4 -p "$PORT" -b 921600 --before no_reset --after hard_reset write_flash 0x10000 "$B" 2>&1 | grep -E "Hash of data verified" >/dev/null \
  && echo "flashed $1 on $PORT ($(shasum -a 256 $B | cut -c1-12))" || { echo "flash FAILED"; exit 1; }
