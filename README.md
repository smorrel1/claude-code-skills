# Claude Code Skills

A collection of custom skills for [Claude Code](https://docs.anthropic.com/en/docs/claude-code), Anthropic's CLI tool for AI-assisted software development.

## What are Skills?

Skills are reusable modules that extend Claude Code's capabilities. Each skill provides:
- A `SKILL.md` file with instructions Claude reads to understand how to use the skill
- Scripts and utilities the skill uses to perform tasks
- Documentation for setup and usage

## Available Skills

| Skill | Description | Setup Required |
|-------|-------------|----------------|
| [apple-notes](#apple-notes) | Export Apple Notes to markdown | None (macOS only) |
| [gmail](#gmail) | Read, search, draft Gmail emails | OAuth setup |
| [gsheet](#google-sheets) | Read/write Google Sheets | OAuth setup (uses Gmail creds) |
| [gcal](#google-calendar) | Google Calendar CRUD operations | OAuth setup (uses Gmail creds) |
| [docx-editor](#docx-editor) | Word document character normalization | None |
| [monthly-report](#monthly-report) | Monthly board report generation | Custom paths + OAuth |

---

## Installation

### 1. Clone or Copy Skills

```bash
# Option A: Clone the repo
git clone https://github.com/YOUR_USERNAME/claude-code-skills.git ~/.claude/skills

# Option B: Copy individual skills
cp -r path/to/skill ~/.claude/skills/
```

### 2. Install Python Dependencies

Most skills auto-install dependencies on first run, but you can pre-install:

```bash
pip install google-auth google-auth-oauthlib google-api-python-client
```

### 3. Configure OAuth (for Google skills)

For Gmail, Google Sheets, and Google Calendar skills:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable the required APIs:
   - Gmail API
   - Google Sheets API
   - Google Calendar API
4. Create OAuth 2.0 credentials (Desktop app type)
5. Download `credentials.json` and place in `~/.claude/skills/gmail/`
6. First run will open browser for authorization

---

## Skill Details

### Apple Notes

Export all Apple Notes to markdown files. Fast Python-based exporter that reads directly from the Notes SQLite database.

**Requirements:** macOS with Apple Notes

**Usage:**
```bash
python3 ~/.claude/skills/apple-notes/scripts/export_notes.py
python3 ~/.claude/skills/apple-notes/scripts/export_notes.py --output ~/Documents/notes
```

**Output:** Organized markdown files by folder with date-prefixed filenames.

---

### Gmail

Read, search, and draft emails using the Gmail API.

**Setup:**
1. Place `credentials.json` in `~/.claude/skills/gmail/`
2. Run any command to trigger OAuth flow

**Usage:**
```bash
# Search emails
python3 ~/.claude/skills/gmail/scripts/gmail_utils.py search --query "from:john@example.com" --max 5

# Read specific email
python3 ~/.claude/skills/gmail/scripts/gmail_utils.py read --id "message_id"

# Create draft
python3 ~/.claude/skills/gmail/scripts/gmail_utils.py draft --to "user@example.com" --subject "Hello" --body "Message body"

# Reply to thread
python3 ~/.claude/skills/gmail/scripts/gmail_utils.py draft --reply-to "message_id" --body "Reply text"
```

---

### Google Sheets

Read and write Google Sheets data.

**Setup:** Uses credentials from Gmail skill. Requires separate OAuth authorization for Sheets scope.

**Usage:**
```bash
# List sheets
python3 ~/.claude/skills/gsheet/scripts/read_gsheet.py "SPREADSHEET_URL" --list-sheets

# Read data
python3 ~/.claude/skills/gsheet/scripts/read_gsheet.py "SPREADSHEET_URL" --sheet "Sheet1" --rows 10

# Update cell
python3 ~/.claude/skills/gsheet/scripts/read_gsheet.py "SPREADSHEET_URL" --sheet "Sheet1" --edit "A1" --value "New Value"
```

---

### Google Calendar

CRUD operations for Google Calendar.

**Setup:** Uses credentials from Gmail skill. Requires separate OAuth authorization for Calendar scope.

**Usage:**
```bash
# List calendars
python3 ~/.claude/skills/gcal/scripts/cal_utils.py calendars

# List upcoming events
python3 ~/.claude/skills/gcal/scripts/cal_utils.py list --days 7

# Create event
python3 ~/.claude/skills/gcal/scripts/cal_utils.py create --summary "Meeting" --start "2025-01-15 10:00"

# Check availability
python3 ~/.claude/skills/gcal/scripts/cal_utils.py availability 2025-01-15
```

---

### DOCX Editor

Utilities for working with Word documents, particularly fixing character encoding issues that break find-and-replace.

**Usage:**
```bash
# Normalize special characters
python3 ~/.claude/skills/docx-editor/scripts/fix_docx_chars.py "Text with "smart quotes""
```

---

### Monthly Report

**Note:** This is a personal workflow skill. Fork and customize paths in `config.py` for your own use.

Generates monthly board reports by:
1. Exporting Apple Notes
2. Consolidating meeting minutes and transcripts
3. Processing emails
4. Synthesizing into report format

**External Dependency:** This skill expects Fireflies.ai meeting transcripts to be downloaded to a local directory. Set up a cron job to periodically sync transcripts from Fireflies to your configured `FIREFLIES_DIR` path.

Example cron setup:
```bash
# Edit crontab
crontab -e

# Add jobs to download and format transcripts every 5 minutes
*/5 * * * * /path/to/fireflies_downloader/run_script.sh fireflies_downloader.py
7,12,17,22,27,32,37,42,47,52,57 * * * * /path/to/fireflies_downloader/run_script.sh format_transcripts.py
```

Example `run_script.sh` wrapper (handles conda/venv activation):
```bash
#!/bin/bash
echo "=== Job started at $(date) ===" >> "$HOME/fireflies_downloader/cron_log.txt"
source "$HOME/.bash_profile"
conda activate your-env  # or: source venv/bin/activate
cd "$HOME/fireflies_downloader"
python "$1" >> "$HOME/fireflies_downloader/cron_log.txt" 2>&1
echo "=== Job ended at $(date) with status $? ===" >> "$HOME/fireflies_downloader/cron_log.txt"
```

See `monthly-report/SKILL.md` for detailed workflow documentation.

---

## Creating Your Own Skills

1. Create a folder under `~/.claude/skills/your-skill-name/`
2. Add a `SKILL.md` file with:
   - YAML frontmatter with `name` and `description`
   - Usage instructions for Claude
3. Add scripts in a `scripts/` subdirectory
4. Claude will automatically discover and use skills based on context

### SKILL.md Template

```markdown
---
name: my-skill
description: Brief description that helps Claude know when to use this skill.
---

# My Skill

## Usage

\`\`\`bash
python3 scripts/my_script.py [options]
\`\`\`

## Examples

...
```

---

## Security Notes

- **Never commit credentials:** The `.gitignore` excludes `credentials.json`, `token.json`, and similar files
- **OAuth tokens expire:** Tokens auto-refresh, but if you see auth errors, delete `token.json` and re-authenticate
- **Scope permissions:** Each Google skill requests only the scopes it needs

---

## License

MIT License - feel free to use, modify, and share.
