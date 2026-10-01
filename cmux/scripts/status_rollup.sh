#!/bin/bash
# Status roll-up across all cmux workspaces: last screen lines + prompt state.
# Usage: status_rollup.sh [lines-per-workspace, default 4]
CMUX=/Applications/cmux.app/Contents/Resources/bin/cmux
LINES=${1:-4}
$CMUX tree --all 2>/dev/null | grep -o 'workspace workspace:[0-9]* "[^"]*"' | while read -r _ ws title; do
  echo "=== $ws $title"
  screen=$($CMUX read-screen --workspace "$ws" --lines "$LINES" 2>/dev/null)
  if echo "$screen" | grep -q 'esc to interrupt'; then state="WORKING"
  elif echo "$screen" | grep -qi 'permission\|approve\|y/n\|waiting'; then state="NEEDS INPUT"
  else state="idle"; fi
  echo "[$state]"
  echo "$screen" | grep -v '^─*$' | grep -v '⏵⏵\|/rc$' | tail -3
done
