---
name: monthly-report
description: Generate monthly board reports. Collects data from Apple Notes, Fireflies, Gmail, and documents, then synthesizes into formatted report. Use when asked to prepare monthly board update or monthly report.
---

# Monthly Board Report Generation

Multi-phase workflow to generate comprehensive monthly board reports.

**Note:** This is a personal workflow skill with configurable paths. Copy `config.example.py` to `config.py` and customize for your environment.

## Overview

| Phase | Description |
|-------|-------------|
| 1 | Data Collection (Notes, Fireflies, Gmail) |
| 2 | Context Setup (auto-managed per run) |
| 3 | User Confirmation (dates, sections) |
| 4 | Parallel Agent Processing (source agents) |
| 5 | Report Generation (synthesis + formatting) |

---

## Quick Start

```bash
# Full automated run (uses last report date or default 60 days)
python3 ~/.claude/skills/monthly-report/scripts/generate_monthly_report.py

# Specify start date
python3 ~/.claude/skills/monthly-report/scripts/generate_monthly_report.py --date 2025-11-11
```

---

## Configuration

Copy `config.example.py` to `config.py` and set your paths:

```python
WORKINGS_BASE = Path.home() / "Dropbox/MonthlyReport/workings"
APPLE_NOTES_EXPORT = Path.home() / "Dropbox/AppleNotesExport"
MINUTES_DIRS = [
    Path.home() / "Dropbox/agendas-minutes",
    Path.home() / "Dropbox/meeting-notes",
]
FIREFLIES_DIR = Path.home() / "Dropbox/fireflies"
MONTHLY_UPDATES_DIR = Path.home() / "Dropbox/monthly-updates"
```

---

## Phase 1: Data Collection

### 1. Apple Notes Export

Uses the `apple-notes` skill for fast export:
```bash
python3 ~/.claude/skills/apple-notes/scripts/export_notes.py --output ~/path/to/export
```

Fast Python script (~30 seconds) vs GUI Exporter app (~1 hour).

### 2. Fireflies Download

Configure `FIREFLIES_DIR` in config.py to point to your Fireflies transcript archive.

### 3. Email Download
```bash
python3 ~/.claude/skills/monthly-report/scripts/EmailsDownload.py
```

---

## Phase 2: Context Setup (Automated)

Context folders are auto-managed:
- Location: Configured via `WORKINGS_BASE` in config.py
- Naming: `context_YYYYMMDD/` (based on start date)
- Subdirectories created automatically: `summaries/`, `additional_notes/`

**Re-run handling:**
- If context folder exists, old files are stashed (timestamped)
- Safe to re-run without losing data

**Run consolidation standalone:**
```bash
python3 ~/.claude/skills/monthly-report/scripts/consolidate_files.py --date 2025-11-11
python3 ~/.claude/skills/monthly-report/scripts/consolidate_files.py  # Uses default (60 days ago)
```

---

## Phase 3: User Confirmation

### Determine Reporting Period
- Read the prior monthly report
- Determine the new reporting period dates
- Extract section headings from prior report

### STOP: Confirm with User
Before proceeding to content generation:
- State proposed coverage dates
- List provisional section headings/topics
- **Wait for user approval before continuing**

---

## Phase 4: Content Generation (Parallel Agents)

### Parallel Source Processing
Launch parallel agents to process each source file simultaneously. Each agent:
1. Reads one source file
2. Extracts relevant facts with dates
3. Organizes by topic/section
4. Writes intermediate summary to `context_YYYYMMDD/summaries/<source>_summary.md`

**Agents to launch in parallel:**

| Agent | Input Source | Output |
|-------|-------------|--------|
| Agent 1 | consolidated_fireflies_*.txt | summaries/fireflies_summary.md |
| Agent 2 | consolidated_notes_*.txt | summaries/apple_notes_summary.md |
| Agent 3-N | consolidated_dir_*.txt | summaries/dir_N_summary.md |
| Agent N+1 | emails_*.txt | summaries/emails_summary.md |

**Intermediate summary format:**
```markdown
# Source: [filename]
## Period: [date range]

### Topic 1
- [Date] Fact or event...

### Topic 2
- [Date] Fact or event...
```

### Synthesis
Once all agents complete:
1. Read the prior monthly report (structure template)
2. Read all intermediate summaries
3. Synthesize into final report sections

---

## Phase 5: Report Generation

### Generate Draft Report

**Content Requirements:**
- Synthesize all relevant events into topic headings
- Omit minor/routine issues (use prior report as threshold guideline)
- Provide substantial detail on critical strategic issues
- Be entirely factual; cite sources; label interpretations explicitly

**Style and Tone:**
- **Factual and Objective**: Stick to substantiated facts
- **Insightful and Clear**: Differentiate facts from interpretation
- **Decision-Oriented**: Provide actionable insights

**Formatting:**
- Match prior report structure, section headings, and style
- Use tables/lists sparingly to support data-rich prose
- Include executive summary

### Final Checks
- Confirm factual accuracy
- Cross-check key data points
- Ensure clarity and readability

---

## Directory Structure

Configured via config.py:

```
WORKINGS_BASE/
└── workings/
    ├── context_20251111/          # One folder per report period
    │   ├── summaries/
    │   │   ├── fireflies_summary.md
    │   │   ├── apple_notes_summary.md
    │   │   └── ...
    │   ├── additional_notes/
    │   ├── consolidated_notes_20251111.txt
    │   ├── consolidated_fireflies_20251111.txt
    │   └── ...
    └── context_20251215/

APPLE_NOTES_EXPORT/
├── Notes/
├── iCloud/
└── ...

MONTHLY_UPDATES_DIR/
└── YYYYMMDD-monthly.docx          # Final reports
```

---

## Scripts Reference

Scripts in `~/.claude/skills/monthly-report/scripts/`:

| Script | Purpose | Standalone |
|--------|---------|------------|
| `consolidate_files.py` | Consolidate by date | Yes - `--date` flag |
| `generate_monthly_report.py` | Full automation | Yes - `--date` flag |
| `EmailsDownload.py` | Gmail API download | Yes |
| `fireflies_transcript.py` | Process Fireflies | Called by consolidate |
| `rtf_consolidator.py` | RTF processing | Dependency |
| `text_cleaner.py` | Text cleaning | Dependency |

**Note:** Apple Notes export uses the separate `apple-notes` skill:
```bash
python3 ~/.claude/skills/apple-notes/scripts/export_notes.py --output ~/path
```

---

## Recovery & Re-running

**If a run fails partway:**
- Re-run the same command - existing files are stashed, not overwritten
- Check `context_YYYYMMDD/` for partial output

**If notes are stale:**
- Run apple-notes skill standalone to refresh
- generate_monthly_report.py auto-refreshes if notes >24 hours old

**To force fresh start:**
```bash
# Remove context folder and re-run
rm -rf $WORKINGS_BASE/context_YYYYMMDD/
python3 ~/.claude/skills/monthly-report/scripts/consolidate_files.py --date YYYY-MM-DD
```
