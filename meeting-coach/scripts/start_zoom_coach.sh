#!/usr/bin/env bash
# Start the ZOOM-NATIVE live transcript producer (no Fireflies bot).
# Reads the transcript that Zoom's "My notes" panel writes locally.
#
# Prereq at meeting time: Stephen starts a Zoom note with Transcript on
# (the "My notes" window from the meeting toolbar) and leaves that window
# open. Nothing joins the call; invisible to other participants.
#
# Usage:
#   start_zoom_coach.sh
#
# Output (parseable by Claude):
#   COACH_TRANSCRIPT=<path to jsonl file being appended>
#   COACH_PID=<pid of producer>
#   COACH_LOG=<path to producer stdout/stderr log>

set -euo pipefail

COACH_DIR="${COACH_DIR:-$HOME/.coach}"
TRANSCRIPT="${COACH_TRANSCRIPT:-$HOME/live-transcript.jsonl}"
PRODUCER="$HOME/.claude/skills/meeting-coach/scripts/zoom_notes_live.py"

if [[ ! -f "$PRODUCER" ]]; then
    echo "ERROR: zoom_notes_live.py not found at $PRODUCER" >&2
    exit 1
fi

mkdir -p "$COACH_DIR"
ts=$(date +%Y%m%d-%H%M%S)
log="$COACH_DIR/$ts-zoom.log"

# Rotate any prior transcript file so we don't mix meetings
if [[ -s "$TRANSCRIPT" ]]; then
    old_ts=$(date -r "$TRANSCRIPT" +%Y%m%d-%H%M%S 2>/dev/null || echo old)
    mv "$TRANSCRIPT" "$COACH_DIR/transcript-$old_ts.jsonl"
fi
: > "$TRANSCRIPT"

nohup python3 "$PRODUCER" -o "$TRANSCRIPT" --interval 2 >"$log" 2>&1 &
pid=$!

sleep 2
if ! kill -0 "$pid" 2>/dev/null; then
    echo "ERROR: producer died immediately; check log: $log" >&2
    tail -n 20 "$log" >&2 || true
    exit 1
fi

# Second, independent recording of the call. Zoom's own transcript stopped
# at 10:18 during the i4i panel on 11 Nov 2026 while the meeting ran to 10:31,
# and the last 13 minutes were lost for good. This records mic and system
# audio locally with whisper.cpp, so a Zoom dropout no longer costs content.
# Launched as a .command in Terminal because system audio capture needs
# Terminal's Screen Recording permission, which a background process lacks.
# Skip with COACH_NO_BACKUP=1.
backup=""
if [[ "$(uname)" == "Darwin" && -z "${COACH_NO_BACKUP:-}" ]]; then
    tx_dir="$HOME/Library/CloudStorage/Dropbox/sm_elaitra/transcripts"
    mkdir -p "$tx_dir"
    backup="$tx_dir/$(date +%Y-%m-%d_%H%M)-backup-recording.md"
    rec="$COACH_DIR/backup-recorder.command"
    cat >"$rec" <<REC
#!/bin/bash
printf '\033[1mBackup recording\033[0m (independent of Zoom). Ctrl-C to stop.\nSaving to: $backup\n\n'
exec "\$HOME/.local/share/transcribe-md/scripts/transcribe-to-md" "$backup"
REC
    chmod +x "$rec"
    open -a Terminal "$rec" >/dev/null 2>&1 || true
fi

# The coach itself: one interactive terminal window (coach_tui.py) with the
# typed-question prompt, hotkeys and the guide pinned at the bottom. Replaces
# the Safari page, the "Ask coach" note and the transcript glance pane, per
# Stephen on 11 Nov 2026. Skip with COACH_NO_WINDOW=1.
if [[ "$(uname)" == "Darwin" && -z "${COACH_NO_WINDOW:-}" ]]; then
    tui="$COACH_DIR/coach.command"
    cat >"$tui" <<TUI
#!/bin/zsh -il
exec /opt/anaconda3/bin/python3 "\$HOME/.claude/skills/meeting-coach/scripts/coach_tui.py"
TUI
    chmod +x "$tui"
    open -a Terminal "$tui" >/dev/null 2>&1 || true
fi

cat <<EOF
COACH_TRANSCRIPT=$TRANSCRIPT
COACH_PID=$pid
COACH_LOG=$log
COACH_MODE=zoom-native
COACH_BACKUP=$backup
EOF
