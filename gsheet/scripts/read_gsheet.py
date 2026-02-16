#!/usr/bin/env python3
"""Read Google Sheets data using existing OAuth credentials."""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
except ImportError:
    print("Installing required packages...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q",
                          "google-auth", "google-auth-oauthlib", "google-api-python-client"])
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request

# Paths to OAuth credentials (use Gmail skill credentials)
GMAIL_SKILL_DIR = Path.home() / ".claude/skills/gmail"
TOKEN_PATH = GMAIL_SKILL_DIR / "token.json"
CLIENT_SECRETS_PATH = GMAIL_SKILL_DIR / "credentials.json"

# Scopes needed for Sheets API (full access for read/write)
SHEETS_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


def extract_spreadsheet_id(url_or_id: str) -> str:
    """Extract spreadsheet ID from URL or return as-is if already an ID."""
    # Match Google Sheets URL pattern
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', url_or_id)
    if match:
        return match.group(1)
    # Assume it's already an ID
    return url_or_id


def get_credentials() -> Credentials:
    """Load and refresh OAuth credentials, re-authenticating if sheets scope is missing."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRETS_PATH.exists():
        raise FileNotFoundError(f"Client secrets not found at {CLIENT_SECRETS_PATH}. Copy from Gmail skill.")

    creds = None
    gsheet_token_path = GMAIL_SKILL_DIR / "gsheet_token.json"

    # Try to load existing gsheet-specific token
    if gsheet_token_path.exists():
        with open(gsheet_token_path) as f:
            token_data = json.load(f)

        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes", SHEETS_SCOPES)
        )

    # If no valid credentials, run OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("Sheets API access required. Opening browser for authorization...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRETS_PATH), SHEETS_SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else SHEETS_SCOPES
        }
        with open(gsheet_token_path, 'w') as f:
            json.dump(token_data, f)

    return creds


def list_sheets(spreadsheet_id: str) -> list:
    """List all sheet names in a spreadsheet."""
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)

    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = spreadsheet.get('sheets', [])

    return [sheet['properties']['title'] for sheet in sheets]


def get_sheet_info(spreadsheet_id: str) -> list:
    """Get sheet names and IDs."""
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)

    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = spreadsheet.get('sheets', [])

    return [(sheet['properties']['title'], sheet['properties']['sheetId']) for sheet in sheets]


def reorder_sheets(spreadsheet_id: str, sheet_order: list) -> None:
    """Reorder sheets to match the given order."""
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)

    # Get current sheet info
    sheet_info = get_sheet_info(spreadsheet_id)
    sheet_name_to_id = {name: sid for name, sid in sheet_info}

    # Build batch update requests
    requests = []
    for index, sheet_name in enumerate(sheet_order):
        if sheet_name in sheet_name_to_id:
            requests.append({
                'updateSheetProperties': {
                    'properties': {
                        'sheetId': sheet_name_to_id[sheet_name],
                        'index': index
                    },
                    'fields': 'index'
                }
            })
        else:
            print(f"Warning: Sheet '{sheet_name}' not found, skipping")

    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': requests}
        ).execute()
        print(f"Reordered {len(requests)} sheet(s)")


def move_sheet_to_front(spreadsheet_id: str, sheet_name: str) -> None:
    """Move a specific sheet to the first position."""
    sheet_info = get_sheet_info(spreadsheet_id)
    current_order = [name for name, _ in sheet_info]

    if sheet_name not in current_order:
        raise ValueError(f"Sheet '{sheet_name}' not found in spreadsheet")

    # Remove and insert at front
    current_order.remove(sheet_name)
    new_order = [sheet_name] + current_order

    reorder_sheets(spreadsheet_id, new_order)


def read_sheet(spreadsheet_id: str, sheet_name: str = None, range_spec: str = None) -> dict:
    """
    Read data from a Google Sheet.

    Args:
        spreadsheet_id: The spreadsheet ID or URL
        sheet_name: Optional sheet name (defaults to first sheet)
        range_spec: Optional range like "A1:D10" or "1:5" for rows

    Returns:
        dict with 'headers', 'rows', and 'raw' data
    """
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)

    # Build range string
    if sheet_name and range_spec:
        range_str = f"'{sheet_name}'!{range_spec}"
    elif sheet_name:
        range_str = f"'{sheet_name}'"
    elif range_spec:
        range_str = range_spec
    else:
        range_str = None

    if range_str:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_str
        ).execute()
    else:
        # Get first sheet
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        first_sheet = spreadsheet['sheets'][0]['properties']['title']
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{first_sheet}'"
        ).execute()

    values = result.get('values', [])

    if not values:
        return {'headers': [], 'rows': [], 'raw': []}

    headers = values[0] if values else []
    rows = values[1:] if len(values) > 1 else []

    return {
        'headers': headers,
        'rows': rows,
        'raw': values
    }


def update_cell(spreadsheet_id: str, sheet_name: str, cell: str, value: str) -> dict:
    """
    Update a single cell in a Google Sheet.

    Args:
        spreadsheet_id: The spreadsheet ID or URL
        sheet_name: Sheet name
        cell: Cell reference like "A1" or "B5"
        value: Value to write

    Returns:
        dict with update result
    """
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)

    range_str = f"'{sheet_name}'!{cell}"

    result = service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_str,
        valueInputOption='USER_ENTERED',
        body={'values': [[value]]}
    ).execute()

    return result


def update_range(spreadsheet_id: str, sheet_name: str, range_spec: str, values: list) -> dict:
    """
    Update a range of cells in a Google Sheet.

    Args:
        spreadsheet_id: The spreadsheet ID or URL
        sheet_name: Sheet name
        range_spec: Range like "A1:D5"
        values: 2D list of values

    Returns:
        dict with update result
    """
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)

    range_str = f"'{sheet_name}'!{range_spec}"

    result = service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_str,
        valueInputOption='USER_ENTERED',
        body={'values': values}
    ).execute()

    return result


def get_sheet_id(spreadsheet_id: str, sheet_name: str) -> int:
    """Get the sheet ID for a given sheet name."""
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)

    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in spreadsheet.get('sheets', []):
        if sheet['properties']['title'] == sheet_name:
            return sheet['properties']['sheetId']

    raise ValueError(f"Sheet '{sheet_name}' not found")


def insert_row(spreadsheet_id: str, sheet_name: str, after_row: int, values: list = None) -> dict:
    """
    Insert a new row after the specified row number.

    Args:
        spreadsheet_id: The spreadsheet ID
        sheet_name: Sheet name
        after_row: Row number after which to insert (1-indexed)
        values: Optional list of values to populate the new row

    Returns:
        dict with result
    """
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)

    sheet_id = get_sheet_id(spreadsheet_id, sheet_name)

    # Insert empty row
    request = {
        'insertDimension': {
            'range': {
                'sheetId': sheet_id,
                'dimension': 'ROWS',
                'startIndex': after_row,  # 0-indexed, so after_row (1-indexed) becomes the insert point
                'endIndex': after_row + 1
            },
            'inheritFromBefore': True
        }
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={'requests': [request]}
    ).execute()

    # If values provided, populate the new row
    if values:
        new_row_num = after_row + 1
        range_str = f"'{sheet_name}'!A{new_row_num}"
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_str,
            valueInputOption='USER_ENTERED',
            body={'values': [values]}
        ).execute()

    return {'inserted_after_row': after_row, 'new_row': after_row + 1}


def find_row_by_value(spreadsheet_id: str, sheet_name: str, search_column: str, search_value: str) -> int:
    """
    Find the row number containing a specific value in a column.

    Args:
        spreadsheet_id: The spreadsheet ID
        sheet_name: Sheet name
        search_column: Column letter (e.g., "A", "B")
        search_value: Value to search for (partial match)

    Returns:
        Row number (1-indexed) or -1 if not found
    """
    data = read_sheet(spreadsheet_id, sheet_name)

    # Determine column index
    col_index = ord(search_column.upper()) - ord('A')

    for i, row in enumerate(data['raw']):
        if col_index < len(row):
            if search_value.lower() in str(row[col_index]).lower():
                return i + 1  # 1-indexed row number

    return -1


def format_as_markdown_table(data: dict) -> str:
    """Format sheet data as a markdown table."""
    if not data['headers']:
        return "No data found."

    headers = data['headers']
    rows = data['rows']

    # Calculate column widths
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))
            else:
                widths.append(len(str(cell)))

    # Build table
    lines = []

    # Header row
    header_cells = [str(h).ljust(widths[i]) for i, h in enumerate(headers)]
    lines.append("| " + " | ".join(header_cells) + " |")

    # Separator
    lines.append("| " + " | ".join(["-" * w for w in widths[:len(headers)]]) + " |")

    # Data rows
    for row in rows:
        cells = []
        for i in range(len(headers)):
            cell = str(row[i]) if i < len(row) else ""
            cells.append(cell.ljust(widths[i]))
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def append_row(spreadsheet_id: str, sheet_name: str, values: list) -> dict:
    """
    Append a new row at the end of the sheet.

    Args:
        spreadsheet_id: The spreadsheet ID
        sheet_name: Sheet name
        values: List of values for the new row

    Returns:
        dict with result
    """
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)

    range_str = f"'{sheet_name}'!A:A"

    result = service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=range_str,
        valueInputOption='USER_ENTERED',
        insertDataOption='INSERT_ROWS',
        body={'values': [values]}
    ).execute()

    return result


def batch_update_cells(spreadsheet_id: str, sheet_name: str, updates: list) -> dict:
    """
    Update multiple cells in a single batch.

    Args:
        spreadsheet_id: The spreadsheet ID
        sheet_name: Sheet name
        updates: List of dicts with 'cell' and 'value' keys, e.g., [{'cell': 'A1', 'value': 'hello'}]

    Returns:
        dict with result
    """
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)

    data = []
    for update in updates:
        data.append({
            'range': f"'{sheet_name}'!{update['cell']}",
            'values': [[update['value']]]
        })

    result = service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            'valueInputOption': 'USER_ENTERED',
            'data': data
        }
    ).execute()

    return result


def main():
    parser = argparse.ArgumentParser(description="Read and write Google Sheets")
    parser.add_argument("spreadsheet", help="Spreadsheet URL or ID")
    parser.add_argument("--sheet", "-s", help="Sheet name (default: first sheet)")
    parser.add_argument("--range", "-r", help="Range to read (e.g., 'A1:D10' or '1:5')")
    parser.add_argument("--list-sheets", "-l", action="store_true", help="List all sheet names")
    parser.add_argument("--move-to-front", "-m", help="Move specified sheet to first position")
    parser.add_argument("--format", "-f", choices=["json", "markdown", "csv"], default="markdown",
                       help="Output format (default: markdown)")
    parser.add_argument("--rows", type=int, help="Limit to first N rows (after header)")
    parser.add_argument("--edit", "-e", help="Cell to edit (e.g., 'A1', 'B5')")
    parser.add_argument("--value", "-v", help="Value to write to cell (use with --edit)")
    parser.add_argument("--find", help="Find row containing this value in first column")
    parser.add_argument("--find-col", default="A", help="Column to search in (default: A)")
    parser.add_argument("--insert-row", type=int, help="Insert new row after this row number")
    parser.add_argument("--row-values", help="Comma-separated values for new row (use with --insert-row or --append)")
    parser.add_argument("--append", action="store_true", help="Append a new row at end of sheet")
    parser.add_argument("--batch-edit", help="JSON array of cell updates, e.g., '[{\"cell\":\"A1\",\"value\":\"x\"}]'")

    args = parser.parse_args()

    spreadsheet_id = extract_spreadsheet_id(args.spreadsheet)

    try:
        # Handle batch edit
        if args.batch_edit:
            sheet = args.sheet or list_sheets(spreadsheet_id)[0]
            updates = json.loads(args.batch_edit)
            result = batch_update_cells(spreadsheet_id, sheet, updates)
            print(f"Updated {result.get('totalUpdatedCells', 0)} cell(s)")
            return

        # Handle append row
        if args.append and args.row_values:
            sheet = args.sheet or list_sheets(spreadsheet_id)[0]
            values = [v.strip() for v in args.row_values.split(',')]
            result = append_row(spreadsheet_id, sheet, values)
            print(f"Appended row to '{sheet}'")
            return

        # Handle insert row
        if args.insert_row:
            sheet = args.sheet or list_sheets(spreadsheet_id)[0]
            values = None
            if args.row_values:
                values = [v.strip() for v in args.row_values.split(',')]
            result = insert_row(spreadsheet_id, sheet, args.insert_row, values)
            print(f"Inserted row at {result['new_row']} in '{sheet}'")
            return

        if args.find:
            sheet = args.sheet or list_sheets(spreadsheet_id)[0]
            row = find_row_by_value(spreadsheet_id, sheet, args.find_col, args.find)
            if row > 0:
                print(f"Found '{args.find}' at row {row} in sheet '{sheet}'")
            else:
                print(f"'{args.find}' not found in column {args.find_col}")
            return

        if args.edit and args.value is not None:
            sheet = args.sheet or list_sheets(spreadsheet_id)[0]
            result = update_cell(spreadsheet_id, sheet, args.edit, args.value)
            print(f"Updated {result.get('updatedCells', 0)} cell(s) in '{sheet}'!{args.edit}")
            return

        if args.move_to_front:
            move_sheet_to_front(spreadsheet_id, args.move_to_front)
            print(f"Moved '{args.move_to_front}' to first position")
            return

        if args.list_sheets:
            sheets = list_sheets(spreadsheet_id)
            print("Sheets in this spreadsheet:")
            for i, name in enumerate(sheets, 1):
                print(f"  {i}. {name}")
            return

        data = read_sheet(spreadsheet_id, args.sheet, args.range)

        # Apply row limit
        if args.rows and data['rows']:
            data['rows'] = data['rows'][:args.rows]
            data['raw'] = [data['headers']] + data['rows']

        if args.format == "json":
            print(json.dumps(data, indent=2))
        elif args.format == "csv":
            import csv
            import io
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerows(data['raw'])
            print(output.getvalue())
        else:  # markdown
            print(format_as_markdown_table(data))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
