---
name: apple-notes
description: Export Apple Notes to markdown files AND edit/append to existing notes. Use when you need to search, analyze, or modify Apple Notes content.
---

# Apple Notes Exporter

Fast Python script to export all Apple Notes to markdown files. Reads directly from the Notes SQLite database, much faster than GUI-based exporters.

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
