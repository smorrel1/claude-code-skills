#!/bin/bash
# Dead-session sweep. Every 15 minutes via launchd, and once after a cmux
# relaunch. Revives panels that fell back to a bare shell, which otherwise
# swallow any brief typed into them.
#
# Quiet by design: it prints only when something was revived or failed, so the
# log stays readable and the Chief of staff is told only when it matters.

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

SKILL="$HOME/.claude/skills/cmux"
LOG="$SKILL/state/dead-sessions.log"
mkdir -p "$SKILL/state"

# Nothing to do if cmux is not running: every panel would read as asleep.
if ! pgrep -xq cmux; then
  echo "$(date '+%Y-%m-%d %H:%M:%S')  cmux not running, skipped" >> "$LOG"
  exit 0
fi

# One sweep at a time. A revival waits up to 75 seconds per panel, so a slow
# run must not have the next one climbing over it. macOS ships no flock, so
# this uses mkdir, which is atomic, plus a staleness check in case a sweep was
# killed before it could clean up.
LOCK="$SKILL/state/.dead-check.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then
    rmdir "$LOCK" 2>/dev/null && mkdir "$LOCK" 2>/dev/null
  else
    echo "$(date '+%Y-%m-%d %H:%M:%S')  previous sweep still running, skipped" >> "$LOG"
    exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

timeout 900 python3 "$SKILL/scripts/check_dead_sessions.py" --apply --quiet
