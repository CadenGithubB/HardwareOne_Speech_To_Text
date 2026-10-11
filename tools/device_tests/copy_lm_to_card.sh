#!/bin/bash
# Put the 1.6 MB LM (W10-1.6M: today's recipe + the 9.2k-term list at 10%, 43k words) on the P4's card as
# "STT Models/meeting.lm". The card's current meeting.lm is kept beside it as meeting-2.5M-gen2-25397.lm when it is
# the deployed file (same SHA-256), so going back is one rename. Waits for the card ($CARD); normal eject only.
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
set -u
CARD=${CARD:?set CARD to the mounted microSD card volume}; D="$CARD/STT Models"
NEW=$STT_ROOT/hw1-work/analysis/techvocab/lm/W10-1.6M.lm
OLD=$STT_ROOT/work/lm/meeting-gen2-25397.lm
say() { echo "$(date '+%F %T') $*"; }
say "waiting for $CARD"
until [ -d "$D" ]; do sleep 3; done
sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
if [ -f "$D/meeting.lm" ]; then
  if [ "$(sha "$D/meeting.lm")" = "$(sha "$OLD")" ]; then
    [ -f "$D/meeting-2.5M-gen2-25397.lm" ] || mv "$D/meeting.lm" "$D/meeting-2.5M-gen2-25397.lm"
    say "kept the 2.5 MB LM as meeting-2.5M-gen2-25397.lm"
  elif [ "$(sha "$D/meeting.lm")" = "$(sha "$NEW")" ]; then
    say "meeting.lm is already the 1.6 MB LM"
  else
    say "meeting.lm on the card is neither file: not touching it"; exit 1
  fi
fi
cp -X "$NEW" "$D/meeting.lm.tmp" && mv "$D/meeting.lm.tmp" "$D/meeting.lm" || { say "copy FAILED"; exit 1; }
[ "$(sha "$D/meeting.lm")" = "$(sha "$NEW")" ] && say "meeting.lm = W10-1.6M verified $(sha "$NEW" | cut -c1-12)" || { say "VERIFY FAILED"; exit 1; }
sync
diskutil eject "$CARD" && say "ejected: the card can go back in the P4" || say "eject failed (close any Finder window on the card, then eject from Finder)"
