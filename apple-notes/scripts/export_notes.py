#!/usr/bin/env python3
"""
Export all Apple Notes to markdown files.
Notes are saved organized by folder with date-prefixed filenames.
Preserves text structure with proper line breaks and markdown formatting.
"""

import sqlite3
from pathlib import Path
from datetime import datetime
import re
import gzip


def read_varint(data, pos):
    """Read a protobuf varint from data at position pos."""
    result = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        result |= (b & 0x7f) << shift
        pos += 1
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def extract_text_from_protobuf(data):
    """
    Extract the main text content from Apple Notes protobuf format.
    The text is stored as a single string in field 2 of the nested structure.
    """
    if data is None:
        return None

    try:
        # Decompress if gzip
        if len(data) >= 2 and data[:2] == b'\x1f\x8b':
            data = gzip.decompress(data)

        # Parse outer message
        pos = 0
        text_content = None

        while pos < len(data):
            if pos >= len(data):
                break

            # Read tag
            tag, pos = read_varint(data, pos)
            field_num = tag >> 3
            wire_type = tag & 0x7

            if wire_type == 0:  # Varint
                _, pos = read_varint(data, pos)
            elif wire_type == 2:  # Length-delimited
                length, pos = read_varint(data, pos)
                value = data[pos:pos+length]
                pos += length

                # Field 2 at outer level is the document
                if field_num == 2 and len(value) > 100:
                    # Parse inner document
                    inner_pos = 0
                    while inner_pos < len(value):
                        inner_tag, inner_pos = read_varint(value, inner_pos)
                        inner_field = inner_tag >> 3
                        inner_wire = inner_tag & 0x7

                        if inner_wire == 0:
                            _, inner_pos = read_varint(value, inner_pos)
                        elif inner_wire == 2:
                            inner_len, inner_pos = read_varint(value, inner_pos)
                            inner_value = value[inner_pos:inner_pos+inner_len]
                            inner_pos += inner_len

                            # Field 3 is the text content block
                            if inner_field == 3 and len(inner_value) > 50:
                                # Parse text content block
                                text_pos = 0
                                while text_pos < len(inner_value):
                                    text_tag, text_pos = read_varint(inner_value, text_pos)
                                    text_field = text_tag >> 3
                                    text_wire = text_tag & 0x7

                                    if text_wire == 0:
                                        _, text_pos = read_varint(inner_value, text_pos)
                                    elif text_wire == 2:
                                        text_len, text_pos = read_varint(inner_value, text_pos)
                                        text_value = inner_value[text_pos:text_pos+text_len]
                                        text_pos += text_len

                                        # Field 2 is the actual text string
                                        if text_field == 2:
                                            try:
                                                decoded = text_value.decode('utf-8')
                                                # This is our text content!
                                                if len(decoded) > 10 and decoded.isprintable() or '\n' in decoded:
                                                    text_content = decoded
                                                    break
                                            except:
                                                pass
                                    else:
                                        break

                                if text_content:
                                    break
                        else:
                            break

                    if text_content:
                        break
            elif wire_type == 5:  # 32-bit
                pos += 4
            elif wire_type == 1:  # 64-bit
                pos += 8
            else:
                break

        return text_content
    except Exception as e:
        return None


def decode_note_content(data):
    """
    Decode note content from the ZICNOTEDATA table.
    First tries protobuf extraction, falls back to regex extraction.
    """
    if data is None:
        return None

    # Try protobuf extraction first
    text = extract_text_from_protobuf(data)
    if text and len(text.strip()) > 10:
        return text.strip()

    # Fallback: regex-based extraction
    try:
        if len(data) >= 2 and data[:2] == b'\x1f\x8b':
            data = gzip.decompress(data)

        decoded = data.decode('utf-8', errors='ignore')
        readable_parts = re.findall(r'[\x20-\x7E\n\r\t]+', decoded)

        cleaned_parts = []
        garbage_streak = 0
        for part in readable_parts:
            part = part.strip()
            if len(part) <= 3:
                continue

            text_chars = sum(1 for c in part if c.isalnum() or c in ' .,!?:;\'-')
            is_garbage = False

            if len(part) > 0:
                ratio = text_chars / len(part)

                if len(part) < 10:
                    alpha_ratio = sum(1 for c in part if c.isalnum() or c == ' ') / len(part)
                    if alpha_ratio < 0.7:
                        is_garbage = True
                    elif ' ' not in part and len(part) < 8 and not part.isalpha():
                        is_garbage = True

                if ratio < 0.6:
                    is_garbage = True
                elif len(part) < 15 and ratio < 0.75:
                    is_garbage = True
                elif re.match(r'^[A-Za-z0-9+/=_\-]{10,}$', part) and ' ' not in part:
                    is_garbage = True
                elif '\t' in part and len(part) < 30:
                    is_garbage = True
                elif len(part) < 20 and part.endswith(('h', '(')):
                    is_garbage = True
                elif part[0] in '!+,<>{}[]' and len(part) < 15:
                    is_garbage = True

            if is_garbage:
                garbage_streak += 1
                if garbage_streak >= 3:
                    break
            else:
                garbage_streak = 0
                if not re.match(r'^[A-Za-z]{1,2}$', part):
                    cleaned_parts.append(part)

        if cleaned_parts:
            seen = set()
            unique_parts = []
            for part in cleaned_parts:
                if part not in seen:
                    seen.add(part)
                    unique_parts.append(part)
            return '\n'.join(unique_parts)

        return decoded.strip()
    except Exception as e:
        return f"[Could not decode: {e}]"


def format_as_markdown(text):
    """
    Convert plain text to markdown format.
    Detects and formats:
    - Numbered lists (1. 2. etc.)
    - Bullet points (various symbols)
    - Indented sub-items
    - Short standalone lines as headers
    """
    if not text:
        return text

    lines = text.split('\n')
    formatted_lines = []
    prev_was_blank = True

    for i, line in enumerate(lines):
        original_line = line
        stripped = line.strip()

        if not stripped:
            formatted_lines.append('')
            prev_was_blank = True
            continue

        # Count leading whitespace for indentation
        leading_spaces = len(line) - len(line.lstrip())
        indent_level = leading_spaces // 4 if leading_spaces > 0 else (1 if line.startswith('\t') else 0)

        # Detect bullet points
        bullet_match = re.match(r'^[\t ]*([•\-\*○▪▸►◦‣⁃])\s*(.+)$', line)
        if bullet_match:
            bullet, content = bullet_match.groups()
            indent = '  ' * indent_level
            formatted_lines.append(f'{indent}- {content}')
            prev_was_blank = False
            continue

        # Detect numbered lists
        number_match = re.match(r'^[\t ]*(\d+)[.\)]\s*(.+)$', line)
        if number_match:
            num, content = number_match.groups()
            indent = '  ' * indent_level
            formatted_lines.append(f'{indent}{num}. {content}')
            prev_was_blank = False
            continue

        # Detect lettered lists
        letter_match = re.match(r'^[\t ]*([a-zA-Z])[.\)]\s*(.+)$', line)
        if letter_match and len(stripped) > 3:
            letter, content = letter_match.groups()
            indent = '  ' * indent_level
            formatted_lines.append(f'{indent}- {content}')
            prev_was_blank = False
            continue

        # Detect checkbox items
        checkbox_match = re.match(r'^[\t ]*\[([xX ])\]\s*(.+)$', line)
        if checkbox_match:
            check, content = checkbox_match.groups()
            indent = '  ' * indent_level
            checkbox = '[x]' if check.lower() == 'x' else '[ ]'
            formatted_lines.append(f'{indent}- {checkbox} {content}')
            prev_was_blank = False
            continue

        # Short lines that look like headers/section titles
        if (prev_was_blank and
            len(stripped) < 60 and
            not stripped.endswith((',', '.', ':', ';', '?', '!')) and
            not stripped.startswith(('http', 'www', '@', '#')) and
            re.match(r'^[A-Z]', stripped) and
            i > 0):
            next_line = lines[i+1].strip() if i+1 < len(lines) else ''
            if not next_line or len(next_line) > len(stripped):
                formatted_lines.append(f'## {stripped}')
                prev_was_blank = False
                continue

        # Regular line - preserve indentation for sub-items
        if indent_level > 0:
            indent = '  ' * indent_level
            formatted_lines.append(f'{indent}{stripped}')
        else:
            formatted_lines.append(stripped)

        prev_was_blank = False

    return '\n'.join(formatted_lines)


def sanitize_filename(name):
    """Create a safe filename from a note title."""
    if not name:
        return "Untitled"
    # Remove or replace invalid characters
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', ' ', name)
    name = name.strip()
    # Limit length
    if len(name) > 100:
        name = name[:100]
    return name if name else "Untitled"


def main(output_dir=None):
    """
    Export all Apple Notes to markdown files.

    Args:
        output_dir: Optional output directory. Defaults to ~/Desktop/AppleNotesExport
    """
    # Connect to the Notes database
    db_path = Path.home() / "Library/Group Containers/group.com.apple.notes/NoteStore.sqlite"

    if not db_path.exists():
        print(f"Error: Notes database not found at {db_path}")
        print("This script only works on macOS with Apple Notes installed.")
        return

    # Create export directory
    if output_dir:
        export_dir = Path(output_dir).expanduser()
    else:
        export_dir = Path.home() / "Desktop" / "AppleNotesExport"

    export_dir.mkdir(parents=True, exist_ok=True)
    print(f"Export directory: {export_dir}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all folders (ICFolder entities have Z_ENT = 14, use ZTITLE2)
    cursor.execute("""
        SELECT Z_PK, ZTITLE2
        FROM ZICCLOUDSYNCINGOBJECT
        WHERE Z_ENT = 14
        AND ZTITLE2 IS NOT NULL
    """)
    folders = {row[0]: row[1] for row in cursor.fetchall()}

    # Get all notes with their content
    # ICNote entities have Z_ENT = 11
    cursor.execute("""
        SELECT
            n.Z_PK,
            n.ZSNIPPET,
            n.ZFOLDER,
            datetime(n.ZMODIFICATIONDATE1 + 978307200, 'unixepoch') as mod_date,
            datetime(n.ZCREATIONDATE1 + 978307200, 'unixepoch') as create_date,
            nd.ZDATA,
            n.ZMERGEABLEDATA1
        FROM ZICCLOUDSYNCINGOBJECT n
        LEFT JOIN ZICNOTEDATA nd ON nd.ZNOTE = n.Z_PK
        WHERE n.Z_ENT = 11
        AND (n.ZMARKEDFORDELETION IS NULL OR n.ZMARKEDFORDELETION != 1)
        ORDER BY n.ZMODIFICATIONDATE1 DESC
    """)

    notes = cursor.fetchall()
    print(f"Found {len(notes)} notes to export")

    exported_count = 0
    failed_count = 0

    for note in notes:
        note_id, snippet, folder_id, mod_date, create_date, data, mergeable_data = note

        # Decode content to get real title (first line)
        decoded_content = None
        if data:
            decoded_content = decode_note_content(data)
        if not decoded_content and mergeable_data:
            decoded_content = decode_note_content(mergeable_data)

        # Extract title from first line of actual content
        if decoded_content:
            first_line = decoded_content.split('\n')[0].strip()
            title = first_line if first_line else "Untitled"
        elif snippet:
            title = snippet.split('\n')[0].strip() if snippet else "Untitled"
        else:
            title = "Untitled"

        if not title:
            title = "Untitled"

        # Clean title
        title = title.replace('\x00', '').strip()
        if not title or len(title) < 2:
            title = "Untitled"

        # Skip image-only notes
        if title.startswith('Pasted Graphic') or title.endswith('.png') or title.endswith('.jpg'):
            continue

        # Determine folder name
        folder_name = folders.get(folder_id, "Uncategorized")
        folder_name = sanitize_filename(folder_name)

        # Create folder directory
        note_folder = export_dir / folder_name
        note_folder.mkdir(exist_ok=True)

        # Create filename with date prefix YYYYMMDD-
        safe_title = sanitize_filename(title)

        date_prefix = ""
        if mod_date:
            try:
                date_prefix = mod_date[:10].replace("-", "") + "-"
            except:
                date_prefix = ""

        filename = f"{date_prefix}{safe_title}.md"
        filepath = note_folder / filename

        # Handle duplicate filenames
        counter = 1
        while filepath.exists():
            base_name = filename[:-3]
            filename = f"{base_name}_{counter}.md"
            filepath = note_folder / filename
            counter += 1

        # Build content
        content_parts = []
        content_parts.append(f"# {title}")
        content_parts.append("")
        content_parts.append(f"**Created:** {create_date}  ")
        content_parts.append(f"**Modified:** {mod_date}  ")
        content_parts.append(f"**Folder:** {folder_name}")
        content_parts.append("")
        content_parts.append("---")
        content_parts.append("")

        # Get body content (everything after first line which is the title)
        content_found = False

        if decoded_content:
            lines = decoded_content.split('\n')
            body = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ''
            if body:
                formatted_body = format_as_markdown(body)
                content_parts.append(formatted_body)
                content_found = True

        if not content_found and snippet:
            formatted_snippet = format_as_markdown(snippet)
            content_parts.append(formatted_snippet)
            content_found = True

        if not content_found:
            content_parts.append("[No content available]")

        # Write to file
        try:
            content = '\n'.join(content_parts)
            content = content.replace('\x00', '')
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            exported_count += 1
            print(f"Exported: {folder_name}/{filename}")
        except Exception as e:
            print(f"Failed to export '{title}': {e}")
            failed_count += 1

    conn.close()

    print(f"\n{'='*50}")
    print(f"Export complete!")
    print(f"Exported: {exported_count} notes")
    print(f"Failed: {failed_count} notes")
    print(f"Location: {export_dir}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Export Apple Notes to markdown files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 export_notes.py                      # Export to ~/Desktop/AppleNotesExport
  python3 export_notes.py --output ~/notes     # Export to custom directory
  python3 export_notes.py -o /tmp/notes        # Short form
        """
    )
    parser.add_argument(
        "--output", "-o",
        help="Output directory (default: ~/Desktop/AppleNotesExport)",
        default=None
    )

    args = parser.parse_args()
    main(output_dir=args.output)
