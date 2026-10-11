#!/bin/bash
# Wait for the P4's microSD on this Mac ($CARD), copy the c13 speaker model and its parity fixture
# into "STT Models/", verify, and eject normally (never forced). Other files on the card are untouched.
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
set -u
CARD=${CARD:?set CARD to the mounted microSD card volume}
SRC=$STT_ROOT/hw1-work/speaker/export_final
say() { echo "$(date '+%F %T') $*"; }
say "waiting for $CARD"
until [ -d "$CARD/STT Models" ]; do sleep 3; done
say "card mounted; copying"
for pair in "speaker.spk:speaker.spk" "fixture.bin:speaker_fixture.bin"; do
  s=${pair%%:*}; d=${pair#*:}
  cp -X "$SRC/$s" "$CARD/STT Models/$d.tmp" && mv "$CARD/STT Models/$d.tmp" "$CARD/STT Models/$d" || { say "copy $d FAILED"; exit 1; }
  a=$(shasum -a 256 "$SRC/$s" | cut -d' ' -f1); b=$(shasum -a 256 "$CARD/STT Models/$d" | cut -d' ' -f1)
  [ "$a" = "$b" ] && say "$d verified ${a:0:12}" || { say "$d VERIFY FAILED"; exit 1; }
done
sync
diskutil eject "$CARD" && say "ejected: the card can go back in the P4" || say "eject failed (close any Finder window on the card, then eject it from Finder)"
