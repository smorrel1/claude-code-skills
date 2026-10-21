#!/bin/bash
# Dead-session sweep. Every 15 minutes via launchd, and once after a cmux
# relaunch. Revives panels that fell back to a bare shell, which otherwise
# swallow any brief typed into them.
#
# Quiet by design: it prints only when something was revived or failed, so the
# log stays readable and the Chief of staff is told only when it matters.

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

SKILL="$HOME/.claude/skills/cmux"
CMUX="/Applications/cmux.app/Contents/Resources/bin/cmux"
LOG="$SKILL/state/dead-sessions.log"
mkdir -p "$SKILL/state"

# Nothing to do if cmux cannot be reached: every panel would read as asleep.
# Ask the CLI rather than looking for a process. `pgrep -xq cmux` was the
# first attempt and it can never match, because the process name is the full
# path "/Applications/cmux.app/Contents/MacOS/cmux", not the bare word. That
# silently turned the whole sweep into a no-op on 21 Oct 2026. Probing the
# CLI also tests the one thing the sweep actually depends on, which a process
# check does not: that the app answers.
if ! "$CMUX" tree --all >/dev/null 2>&1; then
  echo "$(date '+%Y-%m-%d %H:%M:%S')  cmux not reachable, skipped" >> "$LOG"
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
