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
| 0 | **READ `FEEDBACK_LOG.md`** before doing anything else |
| 1 | Data Collection (Notes, Fireflies, Zoom Docs, Gmail) |
| 1c | Engineering retro via gstack `/retro global <N>d` |
| 1d | Strategic diagnostic via gstack `/office-hours` (diagnose mode) |
| 2 | Context Setup (auto-managed per run) |
| 3 | User Confirmation (dates, sections) |
| 4 | Parallel Agent Processing (source agents — use Haiku for cheap extraction) |
| 5 | Report Generation: three-page main + ~10-page appendix, branded DOCX, never overwrite prior version |

## Phase 0: Read the feedback log

`FEEDBACK_LOG.md` in this skill folder is a running record of the user's corrections on prior reports. Read it first. Apply every standing item (structure, branding, deletions, framing). Append a fresh dated section after each new round of feedback; never rewrite old entries.

## Standing process notes (apply every run)

These are non-negotiable. If you find yourself about to do otherwise, stop and re-read.

- **Read `FEEDBACK_LOG.md` in the monthly-report skill before drafting.** Standing items are captured there.
- **Source-extraction sub-agents default to Haiku.** Opus is reserved for Phase 5 synthesis only.
- **Apple Notes consolidation filters by `YYYYMMDD-` filename prefix plus body `Updated:` line,** not by file mtime. (The apple-notes export re-touches every note's mtime each run, so mtime-based filtering passes through ~2,000 historical notes.)
- **Zoom-downloader runs once per Zoom account per period** (using `--account-label <name>`) with per-account state files (`state-<name>.json`). Output lands in the transcripts folder so `consolidate_files.py` picks it up.
- **Email re-query covers every configured account** across **both** inbox and sent. Any Microsoft/Outlook-backed account is read via local Mac Mail SQLite when Microsoft OAuth is unavailable.
- **Reports are versioned (v1, v2, v3, ...).** Never overwrite a prior version. v1 is retained as input to the CEO-Office Hours skill and to the strategic diagnostic (Phase 1d).
- **Report body is three pages**, followed by ~10 pages of appendices. Page 1: cash runway + fundraise pivot. Page 2: period highlights and risks. Page 3: strategic context for the next board meeting (the Phase 1d office-hours diagnostic compressed onto one page).
- **Company branding** (configure in `config.py`): wordmark top-right of page 1; icon top-right of subsequent pages; centred gray footer "<Company> -- Confidential | Page X of Y"; configurable font and heading/row colours.

## Phase 1c: gstack `/retro` (engineering retro)

Run the gstack `/retro` skill for the reporting period, e.g. `/retro global 60d` for a ~2-month period. The retro inspects all active git repos plus AI coding sessions on the machine and produces commits, LOC, contributor breakdown, AI-assisted percentage and a shipping-streak narrative.

Save the output to `context_YYYYMMDD/summaries/gstack_retro.md` (the narrative) and `context_YYYYMMDD/summaries/gstack_retro.json` (the structured snapshot). The narrative becomes the source for the report's Engineering Velocity appendix; the JSON is kept for trend comparison run-over-run.

## Phase 1d: gstack `/office-hours` (diagnose mode)

Run the gstack `/office-hours` skill in **diagnose mode** against the prior CEO/Directors' Report (v(N-1) of this document), the engineering retro from Phase 1c, the previous BoD summary, and the prior two or three monthly reports for a two-year arc.

Diagnose mode produces:
- A two-year arc table (the company's successive go-to-market postures)
- Diagnostic insights ("what we now know")
- Decisions the board can move the needle on (Q1, Q2, Q3, ... typically 4-6 questions)
- Three frames to say out loud at the next board meeting
- Anticipated board pushbacks and how to handle them

Save the full memo to `context_YYYYMMDD/summaries/gstack_office_hours_diagnose.md` (and to the `WORKINGS_BASE` path defined in `config.py` as `YYYYMMDD-office-hours-board-prep.md` for the CEO-Office Hours skill to pick up).

The compressed version (one page) becomes **Page 3** of the report.

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

**Important: in-period filter.** The export script re-touches every note's mtime on each run, so filesystem `mtime > start_date` would let all ~2,000+ notes through. `consolidate_files.py` therefore uses a dedicated `consolidate_apple_notes()` function that filters on:

1. The `YYYYMMDD-` filename prefix (the note's original creation date), AND
2. An optional `Updated: YYYY-MM-DD` / `Modified: YYYY-MM-DD` line near the top of the note body (catches old notes edited recently).

A note is included only if **either** its creation date OR its edit date is on or after `start_date`. Notes whose filename prefix is unparseable are skipped (with a count printed). This typically cuts the consolidated file from ~5 MB to ~200 KB and removes a huge amount of irrelevant historical noise from downstream agents.

### 2. Fireflies Download

Configure `FIREFLIES_DIR` in config.py to point to your Fireflies transcript archive.

### 3. Zoom Docs Download (per Zoom account)

Pull any new Zoom AI Companion meeting notes from `docs.zoom.us` into the same
transcripts folder using the `zoom-downloader` skill. **Each Zoom account must
be pulled separately** because each lives in its own Chrome profile and has its
own `_zm_*` session cookies. Identify the Chrome profile per account by opening
`chrome://version` while signed into each.

```bash
# Pull primary (work) Zoom account
python3 ~/.claude/skills/zoom-downloader/scripts/zoom_notes_downloader.py \
    --account-label work \
    --profile "Default" \
    --output-dir "$FIREFLIES_DIR"

# Pull secondary (personal) Zoom account
python3 ~/.claude/skills/zoom-downloader/scripts/zoom_notes_downloader.py \
    --account-label personal \
    --profile "Profile 1" \
    --output-dir "$FIREFLIES_DIR"
```

Each run keeps its own `state-<label>.json` (alongside the script) so per-account
download history does not collide. Add `--all` to force a full re-download for
that account. Add `--dry-run` to enumerate only.

**Known issue (Chrome 148+, 2026-05):** Zoom auth cookies are session-only and the headless run currently cannot authenticate. Until fixed, fall back to one of these per account:
- Use the `claude-in-chrome` MCP tools to browse `docs.zoom.us/recent` from the live authenticated Chrome session for each profile and save each transcript to `$FIREFLIES_DIR` as `YYYY-MM-DD_<title>.md`.
- Manually open `docs.zoom.us` in each Chrome profile and copy each transcript into the same folder with the same naming convention.

Either way, the files must land in `FIREFLIES_DIR` so `consolidate_files.py` picks them up alongside Fireflies `.txt` files. Tag the filename with the account if it matters for provenance (e.g. `2026-05-30_personal_<title>.md`).

### 4. Email Download
```bash
python3 ~/.claude/skills/monthly-report/scripts/EmailsDownload.py
```

---

## Phase 1b: Engineering Retro (Global)

Before synthesizing the report, gather a cross-project engineering retrospective to include shipping velocity, LOC, contributor activity, and AI session data.

### Run Global Retro

Invoke `/retro global 30d` (or match the reporting period length). This scans all active git repos and AI coding sessions on the machine.

### Save Retro Output

Save the retro output (the full narrative, not just the JSON snapshot) to the context folder:

```bash
# After /retro global completes, save its output
cp ~/.gstack/retros/global-$(date +%Y-%m-%d)-*.json "$CONTEXT_DIR/summaries/retro_global.json"
```

Also write the narrative summary to `$CONTEXT_DIR/summaries/retro_global_summary.md` so the synthesis agents can reference it alongside other sources.

### Use in Report

During Phase 4 synthesis, include the retro data as an additional source agent:

| Agent | Input Source | Output |
|-------|-------------|--------|
| Agent (retro) | summaries/retro_global_summary.md + retro_global.json | Engineering velocity section |

The board report should include a concise engineering velocity section covering: commits, LOC, active projects, contributor breakdown, AI-assisted %, and shipping streak. Use the retro's tweetable summary as the section lead-in.

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

### STOP: Confirm Start Date and Sections with User
Before proceeding to content generation:
- State the proposed **start date** (derived from the prior report's end date) and **end date**
- Ask the user to confirm or correct the start date (the prior report may not cover the full gap)
- List provisional section headings/topics
- **Wait for user approval of dates and sections before continuing**

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
| Agent 1 | consolidated_fireflies_*.txt (Fireflies + Zoom notes) | summaries/fireflies_summary.md |
| Agent 2 | consolidated_notes_*.txt | summaries/apple_notes_summary.md |
| Agent 3-N | consolidated_dir_*.txt | summaries/dir_N_summary.md |
| Agent N+1 | emails_*.txt | summaries/emails_summary.md |
| Agent N+2 | BoD docx + financials docx | summaries/bod_and_financials_summary.md |

**Model selection:** dispatch source-extraction agents with `model: haiku` — they're doing dated-fact extraction from large text, not reasoning. Reserve Sonnet/Opus for Phase 5 synthesis only. This typically cuts cost ~5-10x without affecting output quality.

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
- Include a **Table of Contents** at the front of the document (after title/metadata, before the first section)
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
