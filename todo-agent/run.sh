#!/bin/bash
# Every five minutes: keep the cmux registry honest, then look for new @claude
# instructions in the To Do note and hand them to the Chief of Staff.
#
# Deliberately cheap. When nothing has changed this does two AppleScript reads
# and one cmux call, and writes a single line to the log. It must stay that way,
# because it runs 288 times a day.
#
# Nothing here dispatches email. The Chief of Staff prompt says drafts only, and
# the global send guard still applies to whatever it delegates.

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

TA="$HOME/.claude/skills/todo-agent"

# cmux 0.64.23 defaults its socket to "cmux processes only", and launchd is not a
# cmux process, so every hand-off failed with "Access denied" (15-17 Sep 2026).
# With cmux's Socket Control Mode set to Password, the job authenticates with the
# password kept in this 0600 file. Sessions inside cmux still connect without it.
# cmux keeps the live password here and regenerates it when the mode is
# changed in its UI, so read cmux's own copy FIRST and treat the skill's copy
# as a fallback. On 4 Oct 2026 cmux rotated its password; the stale copy here
# locked the job out with "Invalid password" for two days.
CMUX_PWF="$HOME/.local/state/cmux/socket-control-password"
PWF="$TA/state/cmux-socket-password"
if [ -s "$CMUX_PWF" ]; then
  export CMUX_SOCKET_PASSWORD="$(cat "$CMUX_PWF")"
elif [ -s "$PWF" ]; then
  export CMUX_SOCKET_PASSWORD="$(cat "$PWF")"
fi
LOG="$TA/logs/todo-agent.log"
mkdir -p "$TA/logs"

stamp() { date "+%Y-%m-%d %H:%M:%S"; }

# The registry has to be current BEFORE the scan, because the scan resolves
# "Chief of staff" to a workspace number through it.
/usr/bin/python3 "$HOME/.claude/skills/cmux/scripts/refresh_registry.py" --quiet --soft \
  >>"$LOG" 2>&1

# Preflight: can a delivery to the Chief of staff even be addressed? This
# resolves the name against the live tree and types nothing. It exists because
# send_task.py changed its contract on 30 Sep 2026 to refuse workspace NUMBERS,
# this job kept passing one, and every pickup from 09:18 on 1 Oct was refused
# and counted as a transient failure: two instructions reached 27 retries while
# the job reported itself healthy. A contract change must fail loudly, once.
PRE=$(/usr/bin/python3 "$TA/scripts/todo_agent.py" preflight 2>&1)
PRC=$?
if [ $PRC -ne 0 ]; then
  printf '[%s] PREFLIGHT FAILED, nothing scanned: %s\n' "$(stamp)" "$PRE" >>"$LOG"
  NAG="$TA/state/last-alert"
  now=$(date +%s); last=$(cat "$NAG" 2>/dev/null || echo 0)
  if [ $((now - last)) -ge 3600 ]; then
    echo "$now" >"$NAG"
    /usr/bin/osascript -e 'display notification "To Do pickup cannot reach the Chief of staff. See todo-agent.log" with title "To Do agent" sound name "Funk"' >>"$LOG" 2>&1
  fi
  exit 0
fi

# Snapshot the cmux workspace order, so a relaunch cannot lose it. Cheap (one
# tree read) and silent unless something is wrong. cmux does not restore the
# order reliably: on 6 Oct 2026 a relaunch left every workspace a median of 4
# places from where it had been, one of them 50 places out.
/usr/bin/python3 "$HOME/.claude/skills/cmux/scripts/workspace_order.py" snapshot --quiet \
  >>"$LOG" 2>&1

OUT=$(/usr/bin/python3 "$TA/scripts/todo_agent.py" scan 2>&1)
RC=$?

# Only log the quiet ticks once an hour; log anything interesting every time.
if [ $RC -ne 0 ] || ! printf '%s' "$OUT" | grep -q "nothing new"; then
  printf '[%s] %s\n' "$(stamp)" "$OUT" >>"$LOG"
elif [ "$(date +%M)" -lt 5 ]; then
  printf '[%s] %s\n' "$(stamp)" "$OUT" >>"$LOG"
fi

# Say something out loud when the channel is shut, because the log is the only
# place this has ever shown up. On 24 Sep 2026 cmux's socket mode changed, every
# hand-off was refused for most of a day, and two of Stephen's instructions sat
# undelivered through 25 and 29 retries while everything looked healthy.
#
# At most one notification an hour, so a long outage nags rather than floods.
NAG="$TA/state/last-alert"
BLOCKED_RE="Access denied|no socket password|auth_required|Address the workspace by NAME|PREFLIGHT FAILED"
blocked=no
printf '%s' "$OUT" | grep -q -E "$BLOCKED_RE" && blocked=yes
tail -3 "$LOG" | grep -q -E "$BLOCKED_RE" && blocked=yes
stuck=$(printf '%s' "$OUT" | grep -c -E "STUCK|BLOCKED")

if [ "$blocked" = yes ] || [ "$stuck" -gt 0 ]; then
  now=$(date +%s)
  last=$(cat "$NAG" 2>/dev/null || echo 0)
  if [ $((now - last)) -ge 3600 ]; then
    echo "$now" >"$NAG"
    if [ "$blocked" = yes ]; then
      what="cmux is refusing the To Do pickup. Run enable_cmux_socket_password.sh"
    else
      what="$stuck To Do instruction(s) undelivered and retrying"
    fi
    /usr/bin/osascript -e "display notification \"$what\" with title \"To Do agent\" sound name \"Funk\"" \
      >>"$LOG" 2>&1
    printf '[%s] ALERTED: %s\n' "$(stamp)" "$what" >>"$LOG"
  fi
fi

# Keep the log to the last 2000 lines.
if [ -f "$LOG" ] && [ "$(wc -l <"$LOG")" -gt 2000 ]; then
  tail -n 1000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

exit 0
