---
name: zoom-downloader
description: Download Zoom meeting transcripts from docs.zoom.us and save as markdown files
---

# Zoom Notes Downloader

Downloads meeting transcripts/notes from Zoom Docs (docs.zoom.us) and saves them as markdown files in the Google Drive agendas-minutes-notes folder.

## What It Does

The script reads Chrome's Zoom session cookies directly from the local Chrome cookie database (decrypting with the macOS Keychain key), launches a headless Selenium browser with those injected cookies, navigates to `docs.zoom.us/recent`, discovers all meeting note documents, and saves each transcript as a markdown file. A `state.json` file alongside the script tracks which documents have already been downloaded so subsequent runs only fetch new notes.

## Prerequisites

- **Python packages:** `selenium`, `cryptography`
  ```bash
  pip install selenium cryptography
  ```
- **chromedriver:**
  - Mac: `/opt/homebrew/bin/chromedriver` (install via `brew install chromedriver`)
  - Ubuntu (mhutel): `/usr/local/bin/chromedriver`
- **Zoom login:** Must be logged into Zoom in Chrome before running (script extracts auth cookies from Chrome's cookie DB)
- **Chrome must be closed** before running -- the script copies Chrome's cookie database file, which requires Chrome not to have an exclusive lock on it. If Chrome is open, cookie extraction may fail or return stale/incomplete cookies.

## Default Output Directory

**Mac:**
```
~/Library/CloudStorage/GoogleDrive-stephen.morrell@elaitra.com/Shared drives/Elaitra_gc/agendas-minutes-notes/
```

**Ubuntu (mhutel):**
```
~/gdrive/Elaitra_gc/agendas-minutes-notes/
```

Override with `--output-dir /path/to/dir`.

## Usage

Run from the skill directory:

```bash
cd ~/.claude/skills/zoom-downloader

# Download all new notes (most common)
python3 scripts/zoom_notes_downloader.py

# List all available notes without downloading anything
python3 scripts/zoom_notes_downloader.py --dry-run

# Re-download everything (ignores state.json)
python3 scripts/zoom_notes_downloader.py --all

# Show browser window for debugging (non-headless)
python3 scripts/zoom_notes_downloader.py --visible

# Specify a Chrome profile explicitly
python3 scripts/zoom_notes_downloader.py --profile "Default"

# Write to a different output directory
python3 scripts/zoom_notes_downloader.py --output-dir /path/to/output
```

## Filename Format

Downloaded files follow this naming convention:

```
YYYYMMDD-HHMM-Zoom-Description.md
```

Examples:
- `20251103-0930-Zoom-Weekly-standup.md`
- `20251210-1400-Zoom-Investor-call.md`
- `undated-a3f2bc-Zoom-Notes.md` (for docs without a parseable date in the title)

## State Tracking

`state.json` is stored alongside the script at:
```
~/.claude/skills/zoom-downloader/scripts/state.json
```

It records each downloaded document by Zoom doc ID, including title, filename, download timestamp, and transcript size. Delete or reset this file to force a full re-download (or use `--all`).

## Cron / Scheduled Automation

The `run_script.sh` helper wraps the Python script with logging for cron jobs. It logs to `~/git/zoom_downloader/cron_log.txt`. To schedule daily downloads:

```bash
# Edit crontab
crontab -e

# Add a daily run at 8am
0 8 * * * ~/.claude/skills/zoom-downloader/scripts/run_script.sh zoom_notes_downloader.py
```

## Troubleshooting

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| `Cookie DB not found` | Chrome profile path wrong | Check `~/Library/Application Support/Google/Chrome/` for profile dirs |
| `Could not retrieve Chrome Safe Storage key` | Keychain access denied | Run from Terminal (not a background process) so macOS can prompt for Keychain access |
| Redirected to Zoom sign-in page | Cookies expired or Chrome was open | Close Chrome fully, re-login to Zoom in Chrome, re-run |
| `Could not start Chrome` | chromedriver not found or version mismatch | Check chromedriver path, run `chromedriver --version` and `google-chrome --version` to verify versions match |
| Empty transcripts | Zoom Docs page structure changed | Run with `--visible` to debug the browser rendering |
