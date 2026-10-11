#!/usr/bin/env bash
# Copy this repo's shared folders into a HardwareOne checkout: tools/<name> -> experiments/<name>.
#
#   tools/sync_to_hardwareone.sh <HardwareOne checkout> [--dry-run]
#
# This repo is the master copy of these folders. Only files it tracks are copied (new or changed ones);
# nothing in HardwareOne is deleted or committed. Scripts that exist only in HardwareOne's copy are listed,
# so a script removed here can be removed there by hand (its docs and results stay there; they are not
# kept here). Review with `git -C <checkout> diff`, then commit in HardwareOne.
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
DST=${1:?usage: sync_to_hardwareone.sh <HardwareOne checkout> [--dry-run]}
DRY=${2:-}
git -C "$DST" rev-parse --show-toplevel >/dev/null 2>&1 || { echo "not a git checkout: $DST" >&2; exit 1; }
[ -d "$DST/experiments" ] || { echo "no experiments/ folder in $DST" >&2; exit 1; }
FOLDERS="stt_p4 stt_train stt_train_15x5 speech_portable translation_p4"
cd "$HERE"
added=0; updated=0
for f in $FOLDERS; do
  while IFS= read -r p; do
    rel=${p#tools/}; t="$DST/experiments/$rel"
    if [ -f "$t" ] && cmp -s "$p" "$t"; then continue; fi
    if [ -f "$t" ]; then echo "update experiments/$rel"; updated=$((updated + 1))
    else echo "add    experiments/$rel"; added=$((added + 1)); fi
    if [ "$DRY" != "--dry-run" ]; then mkdir -p "$(dirname "$t")"; cp -p "$p" "$t"; fi
  done < <(git ls-files "tools/$f")
  while IFS= read -r q; do
    rel=${q#experiments/}
    [ -e "tools/$rel" ] && continue
    case "$rel" in                      # HardwareOne's own docs and results: expected to differ
      *.md|*.html|*.png|*.txt|*/results/*|*/timeline-*|*validation*.json|*provenance*.json|*host-screen*|*model-tensors*) continue ;;
    esac
    echo "only in HardwareOne: $q"
  done < <(git -C "$DST" ls-files "experiments/$f")
done
echo "$added added, $updated updated$([ "$DRY" = "--dry-run" ] && echo ' (dry run: nothing copied)')"
