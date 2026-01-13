---
name: gsheet
description: Read Google Sheets data including specific sheets and ranges. Auto-triggers when user shares a Google Sheets URL (docs.google.com/spreadsheets). Supports listing sheets, reading specific sheets by name, reading row ranges, and outputting as markdown tables. Use for any Google Sheets reading tasks.
---

# Google Sheets Reader

Read data from Google Sheets using Python with existing OAuth credentials.

## Usage

Run the script to read spreadsheet data:

```bash
python3 scripts/read_gsheet.py <url-or-id> [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--sheet, -s` | Sheet name to read (default: first sheet) |
| `--range, -r` | Cell range like `A1:D10` or row range like `1:5` |
| `--list-sheets, -l` | List all sheet names in the spreadsheet |
| `--format, -f` | Output format: `markdown` (default), `json`, or `csv` |
| `--rows N` | Limit output to first N data rows |

### Examples

```bash
# List all sheets
python3 scripts/read_gsheet.py "https://docs.google.com/spreadsheets/d/ABC123/edit" --list-sheets

# Read first 4 rows of "Primary List" sheet
python3 scripts/read_gsheet.py "https://docs.google.com/spreadsheets/d/ABC123/edit" --sheet "Primary List" --rows 4

# Read specific range
python3 scripts/read_gsheet.py "ABC123" --sheet "Sheet1" --range "A1:E10"

# Output as JSON
python3 scripts/read_gsheet.py "ABC123" --format json
```

## Workflow

When user shares a Google Sheets URL:

1. First run with `--list-sheets` to see available sheets
2. Read the requested sheet/range
3. Display results as markdown table

## Notes

- Uses OAuth credentials from MCP gdrive setup at `~/.nvm/versions/node/v24.12.0/lib/node_modules/`
- Credentials auto-refresh when expired
- Read-only access (drive.readonly scope)
