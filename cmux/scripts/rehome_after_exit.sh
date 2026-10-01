#!/bin/bash
# Deadman re-homer: waits for a wrongly-placed claude PID to exit, then resumes
# sessions into their rightful panels by id. Written 17 Sep 2026 for the case where
# the repairing session is ITSELF squatting in the wrong panel and cannot move itself.
# Uses `claude --resume <id>` (never bare --continue) because a panel whose record
# was rebound to another session rejects `cmux restore claude <id>` with
# "no longer matches the session". Panels must be materialized (viewed) beforehand.
# Usage: nohup rehome_after_exit.sh <pid-to-wait-for> <panel-uuid>=<session-id> [...] &
CMUX=/Applications/cmux.app/Contents/Resources/bin/cmux
PID="$1"; shift
while kill -0 "$PID" 2>/dev/null; do sleep 3; done
sleep 5
for pair in "$@"; do
  panel="${pair%%=*}"; sid="${pair#*=}"
  "$CMUX" send --surface "$panel" "claude --resume $sid"
  sleep 1
  "$CMUX" send-key --surface "$panel" Enter
  sleep 6
done
