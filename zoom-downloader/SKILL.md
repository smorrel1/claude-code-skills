---
name: zoom-downloader
description: Move Zoom Docs transcript exports from ~/Downloads into the transcripts folder with a date-stamped filename
---

# Zoom Notes Downloader

A launchd folder-watcher that picks up Zoom Docs transcript exports from `~/Downloads/` and renames + moves them into the transcripts folder the `after-meeting` skill watches.

## Workflow

1. After a meeting, open the Zoom Doc at <https://docs.zoom.us/recent>.
2. Click the **Transcript** button, then the **download arrow** at the top-right of the transcript panel.
3. Zoom saves the file as `~/Downloads/transcript.txt` (or, if you used Save As to add a name, `~/Downloads/transcript-<name>.txt`).
4. The watcher fires within ~1 second, validates the file as a Zoom transcript, and moves it to:
   ```
   ~/Library/CloudStorage/Dropbox/sm_elaitra/transcripts/YYYY-MM-DD_HHMM-Zoom-<suffix>.txt
   ```
   where `HHMM` is the first speaker timestamp in the file and `<suffix>` is whatever you typed after "transcript-" in Save As (or "Doc" if you left the default).

## Why this design

Zoom does **not** expose a REST API for the "My Notes" / Hub documents at docs.zoom.us (confirmed by Zoom staff on the developer forum, 2026-04). The previous Selenium-based scraper broke when Chrome 148+ disabled CDP on the default profile. The AI Companion summary REST API works but returns *summaries*, not *transcripts*, and only when "Auto-generate summary" is enabled.

So the long-term answer is: stop trying to automate the fetch, automate the file-moving instead. Your manual "click Download arrow" workflow is already minimal; the watcher just removes the rename+move step.

## Components

| Path | Purpose |
|---|---|
| `~/git/zoom_downloader/move_transcript.py` | The mover. Scans `~/Downloads` for `transcript*.txt` whose first non-blank line matches `HH:MM:SS --> HH:MM:SS`. |
| `~/git/zoom_downloader/move_transcript.sh` | launchd wrapper. Sleeps 1s, rotates the log at 1 MB, runs the mover. |
| `~/Library/LaunchAgents/com.elaitra.zoom-transcript-watcher.plist` | launchd agent. Fires on changes to `~/Downloads`. |
| `~/Library/Logs/elaitra-transcript-watcher.log` | What the mover did each fire. Rotated to `.1` at 1 MB. |

## Installing / reinstalling

```bash
launchctl bootout gui/$UID/com.elaitra.zoom-transcript-watcher 2>/dev/null
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.elaitra.zoom-transcript-watcher.plist
launchctl list | grep elaitra   # verify
```

## Testing

```bash
cat > ~/Downloads/transcript-test.txt <<'EOF'
09:30:00 --> 09:30:02
Speaker 1: Testing.
EOF
sleep 3
ls ~/Library/CloudStorage/Dropbox/sm_elaitra/transcripts/ | grep Zoom-test
tail ~/Library/Logs/elaitra-transcript-watcher.log
```

## What's NOT used anymore

`~/git/zoom_downloader/zoom_notes_downloader.py` still exists as a working REST client for AI Companion meeting *summaries* (not transcripts). It is no longer on cron. Keep it around in case Zoom ever publishes a transcript API, or in case you turn on "Auto-generate summary" and want a summary archive separately from transcripts. The `.env` with the GetNotes OAuth credentials likewise stays in place; rotate them in Zoom Marketplace if you want to be tidy.

`~/git/zoom_downloader/HANDOVER-fix-chrome149-cdp.md` is historical context for the failed Selenium approach.
