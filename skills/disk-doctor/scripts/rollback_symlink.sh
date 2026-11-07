#!/bin/bash
# macOS: roll back a symlink move created by move_with_symlink.sh
#
# Usage:
#   ./rollback_symlink.sh --src "$HOME/Library/Caches" --force
#
# It will:
#   1. check $SRC is a symlink pointing to an existing directory
#   2. remove the symlink
#   3. move the data back from the link target
#
# Default is DRY-RUN.

set -u

SRC=""
FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --src) SRC="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) echo "usage: $0 --src <symlink path> [--force]"; exit 0 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

fail() { echo "NO-GO: $*"; exit 1; }
ok()   { echo "  ok  $*"; }

[ -n "$SRC" ] || fail "--src required"

if [ ! -L "$SRC" ]; then
  fail "not a symlink: $SRC (nothing to roll back)"
fi

TARGET=$(readlink "$SRC")
echo "symlink: $SRC -> $TARGET"

[ -d "$TARGET" ] || fail "link target missing: $TARGET (data may already be gone)"

SIZE=$(du -sh "$TARGET" 2>/dev/null | awk '{print $1}')
AVail_KB=$(df -Pk "$(dirname "$SRC")" | awk 'NR==2 {print $4}')
NEED_KB=$(du -sk "$TARGET" 2>/dev/null | awk '{print $1}')
if [ -n "${NEED_KB:-}" ] && [ "$Avail_KB" -lt "$NEED_KB" ]; then
  fail "not enough space back on source disk: need $((NEED_KB/1024)) MB, have $((Avail_KB/1024)) MB"
fi

echo "PLAN:"
echo "  remove symlink $SRC"
echo "  move   $TARGET  ->  $SRC   ($SIZE)"

if [ "$FORCE" -ne 1 ]; then
  echo ""
  echo "DRY-RUN. Nothing changed. Re-run with --force to execute."
  exit 0
fi

rm "$SRC" || fail "cannot remove symlink"
mv "$TARGET" "$SRC" || fail "move back failed; data still at $TARGET"
ok "rolled back"

echo "DONE. Reopen the app and confirm your data is there."
