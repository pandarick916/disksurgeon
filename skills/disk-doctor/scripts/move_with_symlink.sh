#!/bin/bash
# macOS: move a large folder to another disk and leave a symlink behind.
# Default is DRY-RUN. Pass --force to actually move.
#
# Usage:
#   ./move_with_symlink.sh --src "$HOME/Library/Caches" --dst "/Volumes/Data/Caches"
#   ./move_with_symlink.sh --src "$HOME/Library/Caches" --dst "/Volumes/Data/Caches" --force
#
# Safety rules:
#   - never touches /System /Library /Applications /usr /bin /sbin
#   - never follows an existing symlink (refuses)
#   - requires dst disk free >= src size * 1.10
#   - keeps source until copy verified

set -u

SRC=""
DST=""
FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --src) SRC="$2"; shift 2 ;;
    --dst) DST="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help)
      echo "usage: $0 --src <dir> --dst <dir> [--force]"
      exit 0 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

fail() { echo "NO-GO: $*"; exit 1; }
ok()   { echo "  ok  $*"; }

# ---------- 1. preflight ----------
[ -n "$SRC" ] || fail "--src required"
[ -n "$DST" ] || fail "--dst required"

[ -d "$SRC" ] || fail "source not found: $SRC"

# refuse symlink as source (we would loop)
if [ -L "$SRC" ]; then
  fail "source is already a symlink: $SRC -> $(readlink "$SRC")"
fi

# refuse system paths
case "$SRC" in
  /System|/System/*|/Library|/Library/*|/Applications|/Applications/*|\
  /usr|/usr/*|/bin|/bin/*|/sbin|/sbin/*|/etc|/etc/*|/private|/private/*)
    fail "refusing to move a system path: $SRC" ;;
esac

# dst must not exist yet
if [ -e "$DST" ]; then
  fail "destination already exists: $DST (remove it or pick another name)"
fi

# dst parent disk must exist
DST_PARENT=$(dirname "$DST")
[ -d "$DST_PARENT" ] || fail "destination parent missing: $DST_PARENT"

# free space check on dst volume
SRC_KB=$(du -sk "$SRC" 2>/dev/null | awk '{print $1}')
[ -n "${SRC_KB:-}" ] || fail "cannot measure source size"
NEED_KB=$(( SRC_KB * 11 / 10 ))
AVAIL_KB=$(df -Pk "$DST_PARENT" | awk 'NR==2 {print $4}')
if [ "$AVAIL_KB" -lt "$NEED_KB" ]; then
  fail "not enough space on target: need $((NEED_KB/1024)) MB, have $((AVAIL_KB/1024)) MB"
fi
ok "source $(du -sh "$SRC" | awk '{print $1}'), target free $((AVAIL_KB/1024/1024)) GB"

echo "PLAN:"
echo "  move   $SRC  ->  $DST"
echo "  link   $SRC  ->  $DST   (symlink)"
echo "  reclaim $(du -sh "$SRC" | awk '{print $1}') on source disk"

if [ "$FORCE" -ne 1 ]; then
  echo ""
  echo "DRY-RUN. Nothing changed. Re-run with --force to execute."
  exit 0
fi

# ---------- 2. copy ----------
echo ""
echo "copying (source kept until verified)..."
mkdir -p "$DST" || fail "cannot create $DST"
rsync -aH --partial "$SRC"/ "$DST"/ || fail "rsync failed, source untouched"

# ---------- 3. verify ----------
SRC_FILES=$(find "$SRC" -type f 2>/dev/null | wc -l | tr -d ' ')
DST_FILES=$(find "$DST" -type f 2>/dev/null | wc -l | tr -d ' ')
if [ "$SRC_FILES" != "$DST_FILES" ]; then
  fail "file count mismatch (src=$SRC_FILES dst=$DST_FILES), source kept at $SRC"
fi
ok "verified $DST_FILES files"

# ---------- 4. replace with symlink ----------
mv "$SRC" "${SRC}.oldmove" || fail "cannot rename source"
if ! ln -s "$DST" "$SRC"; then
  mv "${SRC}.oldmove" "$SRC"
  fail "symlink failed, rolled back"
fi
ok "symlink created"

# ---------- 5. done ----------
if [ -d "${SRC}.oldmove" ]; then
  echo ""
  echo "old copy kept at: ${SRC}.oldmove"
  echo "After you confirm the app works, delete it with:"
  echo "    rm -rf \"${SRC}.oldmove\""
  echo ""
  echo "To roll back instead:"
  echo "    rm \"$SRC\" && mv \"${SRC}.oldmove\" \"$SRC\""
fi

echo "DONE."
