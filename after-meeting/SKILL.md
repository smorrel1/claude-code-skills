---
name: after-meeting
description: Post-meeting automation. Exports Apple Notes, finds the meeting note and Zoom/Fireflies transcript, writes a structured summary, appends it to the Apple Note, drafts follow-up emails, and saves the transcript to Google Drive. Trigger with /after-meeting <name or time>.
---

# After-Meeting Skill

Automate everything that happens after a meeting ends: find the notes and transcript, write a summary, update the Apple Note, draft emails, and archive the transcript.

## Trigger

```
/after-meeting Jorge
/after-meeting 10am
/after-meeting with Sally
/after-meeting David Bodne 2pm
```

Arguments can be a person's name, a time, or both. All are used to locate the correct meeting.

---

## Step-by-Step Workflow

### Step 1 — Export Apple Notes

Run the export script to refresh the local markdown cache:

```bash
python3 ~/.claude/skills/apple-notes/scripts/export_notes.py
```

Default output: `~/Desktop/AppleNotesExport/`

### Step 2 — Find the Relevant Apple Note

Search the exported notes for today's date and any names/keywords from the arguments:

```bash
# Today's date in YYYYMMDD format
TODAY=$(date +%Y%m%d)

# Search by date prefix across all exported folders
find ~/Desktop/AppleNotesExport -name "${TODAY}-*.md" | head -20

# Also search note bodies for the attendee name
grep -ril "Jorge" ~/Desktop/AppleNotesExport --include="*.md" | grep "$TODAY"
```

If multiple notes match, show the list and ask Stephen to confirm which one.

Note titles typically follow the format: `YYYYMMDD-Person Name.md` or `YYYYMMDD-Meeting Topic.md`

### Step 3 — Find the Zoom Transcript

Check three sources in order:

#### 3a. Local Zoom Recordings (~/Documents/Zoom/)

Zoom saves recordings in folders named `YYYY-MM-DD HH.MM.SS Meeting Title`:

```bash
TODAY_DASH=$(date +%Y-%m-%d)
ls ~/Documents/Zoom/ | grep "^$TODAY_DASH"
```

Inside each folder, look for transcript files:
- `meeting_saved_new_chat.txt` (Zoom in-meeting chat)
- `*.vtt` (WebVTT transcript if cloud recording was enabled)
- `audio_transcript.txt` or similar

If a time argument was given (e.g., "10am"), match folder names containing that hour.

#### 3b. Fireflies Transcripts (Dropbox)

```
~/Library/CloudStorage/Dropbox/sm_elaitra/transcripts/
```

Files are named `YYYY-MM-DD_Meeting Title.txt`. Search:

```bash
TODAY_DASH=$(date +%Y-%m-%d)
ls ~/Library/CloudStorage/Dropbox/sm_elaitra/transcripts/ | grep "^$TODAY_DASH"
```

Also search by attendee name if date search returns nothing:

```bash
grep -ril "Jorge" ~/Library/CloudStorage/Dropbox/sm_elaitra/transcripts/ | grep "$TODAY_DASH"
```

#### 3c. Zoom Docs (docs.zoom.us)

The `zoom_notes_downloader.py` script at `~/git/zoom_downloader/zoom_notes_downloader.py` can pull transcripts from Zoom Docs.

**Important constraint:** This script uses Selenium with the Chrome user profile and requires Chrome to be fully closed before running (exclusive profile access). If Chrome is open, the script will fail.

Options when Chrome is open:
1. Ask Stephen: "Chrome is open. Should I close it to run the Zoom downloader, or would you prefer I open docs.zoom.us in the browser for you to find the transcript manually?"
2. Alternatively, use the `agent-browse` skill to navigate to `https://docs.zoom.us/recent` and locate today's meeting note.

If Chrome is closed or Stephen agrees to close it:

```bash
cd ~/git/zoom_downloader
python3 zoom_notes_downloader.py
```

The script saves transcripts to:
```
~/Library/CloudStorage/GoogleDrive-stephen.morrell@elaitra.com/Shared drives/Elaitra_gc/agendas-minutes-notes/
```

If the script ran successfully and saved a file there for today, use that file as the transcript.

#### Transcript Priority

Use whichever source has the most complete content:
1. Fireflies `.txt` (usually fullest transcript with speaker labels and timestamps)
2. Zoom Docs (AI-generated summary + transcript)
3. Local Zoom `.vtt` or chat file

### Step 4 — Generate the Meeting Summary

Read the Apple Note and transcript content, then produce a structured summary. Follow Stephen's writing preferences: no em dashes, warm and clear tone.

**Summary structure (use HTML for Apple Notes body):**

```html
<h2>Meeting Summary — [Date] with [Attendee(s)]</h2>

<h3>Key Topics Discussed</h3>
<ul>
  <li>[Topic 1]</li>
  <li>[Topic 2]</li>
</ul>

<h3>Decisions Made</h3>
<ul>
  <li>[Decision 1]</li>
</ul>

<h3>Follow-Up Actions</h3>
<b>Stephen:</b>
<ul>
  <li>[Action 1]</li>
</ul>
<b>[Other person]:</b>
<ul>
  <li>[Action 1]</li>
</ul>

<h3>What Went Well</h3>
<ul>
  <li>[Observation]</li>
</ul>

<h3>How to Improve Next Time</h3>
<ul>
  <li>[Suggestion]</li>
</ul>
```

Keep each section concise. Bullet points, not paragraphs. Specific and actionable.

### Step 5 — Append Summary to Apple Note

Use AppleScript (NOT JXA — JXA causes -600 errors on this machine) to append the summary HTML to the existing Apple Note.

Find the note by its exact title (from Step 2), then append:

```bash
osascript << 'APPLESCRIPT'
tell application "Notes"
  set targetNote to missing value
  repeat with n in every note
    if name of n contains "TARGET_TITLE_HERE" then
      set targetNote to n
      exit repeat
    end if
  end repeat
  if targetNote is not missing value then
    set currentBody to body of targetNote
    set summaryHTML to "<br><br><h2>Meeting Summary...</h2>..."
    set body of targetNote to currentBody & summaryHTML
  end if
end tell
APPLESCRIPT
```

**AppleScript HTML rules:**
- Use `<br>` for newlines (not `\n`)
- Use `<b>...</b>` for bold
- Use `<h2>`, `<h3>` for headers
- Use `<ul><li>...</li></ul>` for bullet lists
- Escape any `&` as `&amp;` and `"` carefully within AppleScript strings

If the note title is ambiguous or not found, show a list of today's notes and ask Stephen to confirm the exact title.

### Step 6 — Append Transcript to Apple Note

**Size check first:**

- If the transcript is under ~5,000 words, append the full text as a collapsible section at the bottom of the note.
- If over ~5,000 words, append a header noting the transcript location (file path or Google Drive link) instead of the full text.

For the full-text case, wrap in a summary section:

```html
<br><br><h2>Full Transcript</h2>
<p><i>Source: Fireflies / Zoom Docs / Local recording</i></p>
<p>[transcript text here, with <br> replacing newlines]</p>
```

For the link-only case:

```html
<br><br><h2>Full Transcript</h2>
<p>Transcript too long to embed. Saved at:</p>
<p>[file path or Google Drive link]</p>
```

### Step 7 — Draft Follow-Up Emails

For each action item assigned to Stephen that involves an external person, or any explicit "send email" action items from the transcript:

1. Load the `email` skill.
2. Draft using the `elaitra` account by default (or whichever account is contextually appropriate).
3. Apply Stephen's email style: no em dashes, warm and professional, contractions OK, no exclamation marks.
4. If the recipient is a sales prospect, follow the ViewFinder cold outreach style from the CLAUDE.md Sales Playbook.

**Email drafting rules:**
- **Always save as a Gmail draft** using the email skill. Never just display email text in the conversation without saving it.
- **Pin commitments to specific deadlines.** If someone promised something in the meeting, the email must state what they promised and by when (use "today", "by Monday", "by EOD Friday", not vague language like "when you can").
- **Frame around demo.elaitra.com** for sales/deployment emails. The cloud demo removes IT infrastructure, governance, and installation blockers. Radiologists experiencing the value themselves is the fastest path to commercial deployment.
- **Request same-day escalation** for remaining blockers: "If any blockers remain, please surface them to me same day so I can help unblock."
- **Don't just acknowledge problems** (e.g., "I know sales cycles are long"). Always follow with a concrete countermeasure (e.g., "we compensate by getting radiologists to experience the value themselves immediately via demo.elaitra.com").
- **CC relevant stakeholders.** Search sent emails (`in:sent`) to the same person/org from the last 7 days to find who else was on the thread. Match the CC list.
- **Use `--new` flag** when starting a new topic. Use `--reply-to` only when continuing an existing thread. Never auto-thread onto unrelated conversations.

### Step 7b — Print Meeting Feedback

After drafting emails, print to the terminal (not the Apple Note) an honest assessment of how Stephen could have done better in the meeting. Be specific, reference actual moments from the transcript. Cover:
- Where he was too vague when he should have been specific
- Where he let the other party deflect without pinning a commitment
- Where he spent too long on a topic vs moving on
- Tactical improvements for next time

### Step 8 — Save Transcript to Google Drive

Save the transcript as a markdown file to the shared Google Drive agendas-minutes-notes folder:

```
~/Library/CloudStorage/GoogleDrive-stephen.morrell@elaitra.com/Shared drives/Elaitra_gc/agendas-minutes-notes/
```

File naming convention: `YYYYMMDD-HHMM-Zoom-Person-Context.md` (e.g., `20260514-1109-Zoom-Mahima-Carpl.md`)

**Do NOT include company names that could be confused** (e.g., use "Carpl" not "Ferrum" if the person works at Carpl Health).

If the Zoom downloader already saved the file there (Step 3c), confirm it exists and skip re-saving. Otherwise write the file using the Read/Write tools.

---

## Error Handling and Edge Cases

| Situation | Handling |
|-----------|----------|
| No Apple Note found for today | List all notes from the last 3 days, ask Stephen to identify the right one |
| No transcript found anywhere | Proceed with summary from Apple Note alone; flag that no transcript was found |
| Multiple transcripts found | List them and ask which to use |
| Chrome is open when trying zoom_notes_downloader.py | Offer: close Chrome, use browser automation (agent-browse), or skip Zoom Docs |
| Note title has special characters | Use `contains` matching in AppleScript rather than exact equality |
| Transcript is over 10,000 words | Save to file only, link from note |
| Email recipient unknown | Ask Stephen for the email address before drafting |

---

## Output Checklist

When done, confirm each completed item:

- [ ] Apple Notes exported
- [ ] Meeting note found: `[note title]`
- [ ] Transcript found: `[source and filename]`
- [ ] Summary written and appended to Apple Note
- [ ] Transcript appended / linked in Apple Note
- [ ] Follow-up email drafts created: `[list recipients]`
- [ ] Transcript saved to Google Drive: `[filename]`

---

## File Paths Reference

| Resource | Path |
|----------|------|
| Apple Notes export script | `~/.claude/skills/apple-notes/scripts/export_notes.py` |
| Apple Notes export output | `~/Desktop/AppleNotesExport/` |
| Zoom local recordings | `~/Documents/Zoom/` |
| Transcripts (Fireflies + Zoom) | `~/Library/CloudStorage/Dropbox/sm_elaitra/transcripts/` |
| Zoom Docs downloader | `~/git/zoom_downloader/zoom_notes_downloader.py` |
| Google Drive agendas folder | `~/Library/CloudStorage/GoogleDrive-stephen.morrell@elaitra.com/Shared drives/Elaitra_gc/agendas-minutes-notes/` |

---

## Notes on AppleScript vs JXA

Always use **AppleScript** (classic OSA) for Notes operations on this machine. JXA (JavaScript for Automation) returns `-600` errors and is unreliable. The syntax for running AppleScript inline is:

```bash
osascript << 'APPLESCRIPT'
tell application "Notes"
  ...
end tell
APPLESCRIPT
```

Not:
```bash
osascript -l JavaScript -e '...'   # DO NOT USE - causes -600 errors
```
