---
name: apple-notes
description: Export Apple Notes to markdown files. Fast Python-based exporter that reads directly from the Notes SQLite database, preserving folder structure and formatting. Use when you need to search or analyze Apple Notes content.
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
python3 scripts/export_notes.py -o ~/Dropbox/AppleNotesExport
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

## Notes

- Reads from `~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite`
- Requires macOS (Apple Notes database location)
- Handles gzip-compressed and protobuf-encoded note content
- Skips notes marked for deletion
- Skips image-only notes (e.g., "Pasted Graphic.png")
- Duplicate filenames get numeric suffixes
