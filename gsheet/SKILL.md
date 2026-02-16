---
name: gsheet
description: Read and write Google Sheets data including specific sheets and ranges. Auto-triggers when user shares a Google Sheets URL (docs.google.com/spreadsheets). Supports listing sheets, reading/writing cells, inserting rows, batch updates, and outputting as markdown tables.
---

# Google Sheets Reader/Writer

Read and write Google Sheets data using Python with OAuth credentials.

## Usage

```bash
python3 scripts/read_gsheet.py <url-or-id> [options]
```

## Read Options

| Option | Description |
|--------|-------------|
| `--sheet, -s` | Sheet name (default: first sheet) |
| `--range, -r` | Cell range like `A1:D10` or row range like `1:5` |
| `--list-sheets, -l` | List all sheet names in the spreadsheet |
| `--format, -f` | Output format: `markdown` (default), `json`, or `csv` |
| `--rows N` | Limit output to first N data rows |
| `--find VALUE` | Find row containing VALUE |
| `--find-col COL` | Column to search in (default: A) |

## Write Options

| Option | Description |
|--------|-------------|
| `--edit CELL` | Cell to edit (e.g., 'A1', 'B5') |
| `--value VALUE` | Value to write (use with --edit) |
| `--insert-row N` | Insert new row after row N |
| `--append` | Append new row at end of sheet |
| `--row-values "a,b,c"` | Comma-separated values for new row |
| `--batch-edit JSON` | Batch update cells with JSON array |

## Examples

### Reading

```bash
# List all sheets
python3 scripts/read_gsheet.py "https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit" --list-sheets

# Read first 10 rows of a specific sheet
python3 scripts/read_gsheet.py "SPREADSHEET_ID" --sheet "Sheet1" --rows 10

# Read a specific range
python3 scripts/read_gsheet.py "SPREADSHEET_ID" --sheet "Sheet1" --range "A1:E20"

# Find a row containing a value
python3 scripts/read_gsheet.py "SPREADSHEET_ID" --sheet "Contacts" --find "john@example.com" --find-col D

# Output as JSON
python3 scripts/read_gsheet.py "SPREADSHEET_ID" --format json
```

### Writing

```bash
# Edit a single cell
python3 scripts/read_gsheet.py "SPREADSHEET_ID" -s "Sheet1" --edit "B5" --value "Updated value"

# Insert a new row after row 10 with values
python3 scripts/read_gsheet.py "SPREADSHEET_ID" -s "Sheet1" --insert-row 10 --row-values "Col1,Col2,Col3,Col4"

# Append a row at the end
python3 scripts/read_gsheet.py "SPREADSHEET_ID" -s "Sheet1" --append --row-values "New,Row,Data"

# Batch update multiple cells at once
python3 scripts/read_gsheet.py "SPREADSHEET_ID" -s "Sheet1" --batch-edit '[{"cell":"A1","value":"Hello"},{"cell":"B1","value":"World"}]'
```

## Notes

- Uses OAuth credentials from `~/.claude/skills/gmail/credentials.json`
- First run will prompt for Google Sheets API authorization in browser
- Credentials are cached in `~/.claude/skills/gmail/gsheet_token.json`
- Full read/write access via `spreadsheets` scope
