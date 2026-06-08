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
  - Ubuntu: `/usr/local/bin/chromedriver`
- **Zoom login:** Must be logged into Zoom in Chrome before running (script extracts auth cookies from Chrome's cookie DB)
- **Chrome must be closed** before running -- the script copies Chrome's cookie database file, which requires Chrome not to have an exclusive lock on it. If Chrome is open, cookie extraction may fail or return stale/incomplete cookies.

## Default Output Directory

**Mac:**
```
~/Library/CloudStorage/GoogleDrive-<your-work-email>/Shared drives/<your-shared-drive>/agendas-minutes-notes/
```

**Ubuntu:**
```
~/gdrive/<your-shared-drive>/agendas-minutes-notes/
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

# Per-account state file (avoids two accounts overwriting each other's history)
python3 scripts/zoom_notes_downloader.py --account-label work --profile "Default"
python3 scripts/zoom_notes_downloader.py --account-label personal --profile "Profile 1"
```

## Multiple Zoom accounts

If you have more than one Zoom login (e.g. a work account and a personal account on different Chrome profiles), use `--account-label` to keep per-account download history separate. The script writes a separate `state-<label>.json` so the two accounts do not overwrite each other:

```bash
cd ~/.claude/skills/zoom-downloader

# Pull primary (work) account
python3 scripts/zoom_notes_downloader.py \
    --account-label work \
    --profile "Default" \
    --output-dir "$ZOOM_OUTPUT_DIR"

# Pull secondary (personal) account
python3 scripts/zoom_notes_downloader.py \
    --account-label personal \
    --profile "Profile 1" \
    --output-dir "$ZOOM_OUTPUT_DIR"
```

If you don't know which Chrome profile corresponds to which Zoom login:

```bash
# Print which profile is logged into Zoom (run before script picks one)
for p in ~/Library/Application\ Support/Google/Chrome/Default \
         ~/Library/Application\ Support/Google/Chrome/Profile\ */; do
  echo "=== $p ==="
  sqlite3 "$p/Preferences" 'select 1' 2>/dev/null && \
    python3 -c "import json; p='$p/Preferences'; d=json.load(open(p)); \
      print(d.get('account_info',[{}])[0].get('email','(no signed-in email)'))" 2>/dev/null
done
```

You can also open `chrome://version` in each profile to see which Google account is signed in.

## Filename Format

Downloaded files follow this naming convention:

```
YYYYMMDD-HHMM-Zoom-Description.md
```

Examples:
- `20251103-0930-Zoom-Weekly-standup.md`
- `20251210-1400-Zoom-Board-meeting.md`
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

## Known Limitation: Chrome 148+ Blocks CDP on Default Profile (2026-05-22)

Zoom stores authentication cookies (`_zm_ssid`, `_zm_ctaid`, `_zm_chtaid`, `cred`, `_zm_page_auth`) as **session-only, in-memory cookies** that are NOT written to Chrome's Cookies SQLite database. The 32 persistent cookies in the DB are all tracking/analytics.

Three approaches were tried and all failed:

1. **Cookie extraction (pycookiecheat / direct SQLite)**: Only gets tracking cookies. Auth cookies are session-only.
2. **Chrome CDP (`--remote-debugging-port`)**: Chrome 148+ error: "DevTools remote debugging requires a non-default data directory." Even passing the default path explicitly is rejected.
3. **Profile copy after graceful quit**: Session cookies appear in the copy but are **invalidated** when loaded in a new Chrome instance.

**Working alternatives:**
- Use the `claude-in-chrome` Chrome extension MCP tools to navigate docs.zoom.us from within the live authenticated session
- Manually open docs.zoom.us in Chrome and copy the transcript
- Investigate Zoom REST API for docs content (not yet attempted)

The script at `~/git/zoom_downloader/zoom_notes_downloader.py` still has improved code (direct Keychain decryption, CDP `Network.setCookie` injection, socket pre-check) but cannot authenticate automatically until a workaround for the session cookie issue is found.

## Troubleshooting

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| `Cookie DB not found` | Chrome profile path wrong | Check `~/Library/Application Support/Google/Chrome/` for profile dirs |
| `Could not retrieve Chrome Safe Storage key` | Keychain access denied | Run from Terminal (not a background process) so macOS can prompt for Keychain access |
| Redirected to Zoom sign-in page | Zoom auth is session-only cookies | Use chrome-in-chrome extension or manual browser instead |
| `DevTools remote debugging requires...` | Chrome 148+ blocks CDP on default profile | Cannot be fixed; use Chrome extension approach |
| `Could not start Chrome` | chromedriver not found or version mismatch | Check chromedriver path, run `chromedriver --version` and `google-chrome --version` to verify versions match |
| Empty transcripts | Zoom Docs page structure changed | Run with `--visible` to debug the browser rendering |
