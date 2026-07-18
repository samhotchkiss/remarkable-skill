#!/bin/bash
# sync-now.sh — trigger an immediate mirror sync (for agents).
# Use after uploading a file, or when the user says "look at my latest markup".
# Synchronous: returns when the sync pass completes.
set -e
SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
MIRROR="${REMARKABLE_MIRROR:-$HOME/reMarkable}"
LOCK="$MIRROR/.mirror/lock"

cd "$SKILL_DIR"
for i in $(seq 1 40); do
  out=$(npx tsx assets/scripts/mirror-sync.ts 2>&1)
  echo "$out"
  if ! grep -q "another sync is running" <<<"$out"; then
    exit 0
  fi
  sleep 3   # scheduled run in flight — wait for it, then run to be sure
done
echo "timed out waiting for in-flight sync" >&2
exit 1
