---
name: apple-notes
description: Export Apple Notes to markdown files AND edit/append to existing notes. Use when you need to search, analyze, or modify Apple Notes content.
---

# Apple Notes Exporter

Fast Python script to export all Apple Notes to markdown files. Reads directly from the Notes SQLite database, much faster than GUI-based exporters.

## Never rewrite a note that is open on screen (11 Nov 2026)

Notes crashed twice on 11 Nov, at 10:55 and 15:22, with the same uncaught
exception inside an AppleScript command: `replaceCharactersInRange:withString:
nil argument`, then "Out of bounds" in the text storage. Each came about a
minute after a session ran `set body of n to (body of n) & html` to append to a
note Stephen had open. Rewriting the whole text under a live editor leaves the
editor pointing into text that no longer exists.

**Rules for every session:**

1. Never hand-write `set body of ...` in osascript. Use
   `scripts/write_note.py set` or `append`, or `from write_note import set_body, append`.
2. `append` writes in place only when the note is NOT on screen; if it is,
   the addition goes into a separate note named "<title>, addendum HH:MM".
3. `set_body` refuses an open note outright (`NoteOpen`).
4. Every write takes one machine-wide lock (`~/.claude/notes-write.lock`),
   checks Notes answers within 8 seconds, and backs off and retries.
   The todo-agent uses the same lock and defers its writes to a later cycle.
5. An addition over 15 KB is saved as a file in
   `Dropbox/Documents/notes-overflow/` and the note gets a one-line pointer.
6. Never poll a note for input. Use a local file or the coach terminal.

## Usage

```bash
python3 scripts/export_notes.py [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--output, -o` | Output directory (default: ~/Desktop/AppleNotesExport) |

### Examples

```bash
# Export to default location (~/Desktop/AppleNotesExport)
python3 scripts/export_notes.py

# Export to custom directory
python3 scripts/export_notes.py --output ~/Documents/notes-backup

# Export to a Dropbox folder for cloud access
python3 scripts/export_notes.py -o ~/Library/CloudStorage/Dropbox/AppleNotesExport
```

## Output Structure

Notes are organized by folder with date-prefixed filenames:

```
AppleNotesExport/
├── Notes/
│   ├── 20250113-Meeting notes.md
│   └── 20250110-Project ideas.md
├── Work/
│   ├── 20250112-Q1 Planning.md
│   └── 20250108-Team sync.md
└── Personal/
    └── 20250111-Shopping list.md
```

## Markdown Format

Each exported note includes:

- Title as H1 header
- Created/Modified dates
- Folder name
- Body content with:
  - Bullet points and numbered lists preserved
  - Checkboxes formatted as `- [ ]` or `- [x]`
  - Short standalone lines detected as section headers

## Cross-Machine Access (Dropbox)

The canonical shared export lives at:

| Machine | Path |
|---------|------|
| **macOS (source)** | `~/Library/CloudStorage/Dropbox/AppleNotesExport` |
| **Ubuntu** | `~/Dropbox/AppleNotesExport` |

**On macOS:** always export to the Dropbox path so Ubuntu has access:
```bash
python3 scripts/export_notes.py -o ~/Library/CloudStorage/Dropbox/AppleNotesExport
```

**On Ubuntu:** read exported notes from `~/Dropbox/AppleNotesExport`. Do not attempt to run the export script on Ubuntu (no Apple Notes database). Use `grep -ril` to search notes content.

## Notes

- Reads from `~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite`
- Requires macOS (Apple Notes database location)
- Handles gzip-compressed and protobuf-encoded note content
- Skips notes marked for deletion
- Skips image-only notes (e.g., "Pasted Graphic.png")
- Re-exporting overwrites previously exported files (no duplicate suffixes)

## Writing Back to Apple Notes

Edit existing notes directly via JXA (no skill script needed):

```bash
osascript -l JavaScript -e '
var Notes = Application("Notes");
var allNotes = Notes.notes();
for (var i = 0; i < allNotes.length; i++) {
  if (allNotes[i].name() === "NOTE TITLE HERE") {
    var body = allNotes[i].body();
    // body is HTML - modify with string replace, concatenation, etc.
    // Use &amp; for &, <br> for newlines
    allNotes[i].body = body;
    break;
  }
}
'
```

- Note bodies are **HTML**, not plain text
- Find by `name()`, modify `body()`, assign back
- Can also create new notes: `Notes.defaultAccount.defaultFolder.notes.push(Notes.Note({name: "Title", body: "<html>content</html>"}))`
