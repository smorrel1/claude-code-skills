#!/usr/bin/env python3
"""
Normalize Word document special characters to standard Unicode equivalents.
This fixes issues with find-and-replace operations that fail due to
non-standard characters (smart quotes, em dashes, etc.) in .docx files.
"""

import sys
from pathlib import Path

def normalize_word_chars(text):
    """
    Convert Word's special characters to standard Unicode equivalents.

    Args:
        text: String containing Word special characters

    Returns:
        String with normalized characters
    """
    replacements = {
        # Smart quotes
        '\u201c': '"',  # Left double quotation mark
        '\u201d': '"',  # Right double quotation mark
        '\u2018': "'",  # Left single quotation mark
        '\u2019': "'",  # Right single quotation mark
        '\u201b': "'",  # Single high-reversed-9 quotation mark

        # Dashes
        '\u2013': '-',  # En dash
        '\u2014': '-',  # Em dash
        '\u2212': '-',  # Minus sign

        # Spaces
        '\u00a0': ' ',  # Non-breaking space
        '\u202f': ' ',  # Narrow no-break space
        '\u2009': ' ',  # Thin space

        # Other punctuation
        '\u2026': '...',  # Horizontal ellipsis
        '\u2022': '*',    # Bullet
        '\u00b7': '*',    # Middle dot

        # Arrows
        '\u2192': '->',   # Rightwards arrow
        '\u21d2': '=>',   # Rightwards double arrow
        '\u2190': '<-',   # Leftwards arrow

        # Mathematical
        '\u2248': '~=',   # Almost equal to
        '\u00d7': 'x',    # Multiplication sign
        '\u00f7': '/',    # Division sign
        '\u2264': '<=',   # Less-than or equal to
        '\u2265': '>=',   # Greater-than or equal to
    }

    for old_char, new_char in replacements.items():
        text = text.replace(old_char, new_char)

    return text


def main():
    """Main function to handle command-line usage."""
    if len(sys.argv) < 2:
        print("Usage: fix_docx_chars.py <text>")
        print("\nExample:")
        print('  fix_docx_chars.py "This has "smart quotes" and — dashes"')
        print("\nOr use in a pipe:")
        print('  echo "Text with — special chars" | python3 fix_docx_chars.py -')
        sys.exit(1)

    # Read from stdin if argument is '-'
    if sys.argv[1] == '-':
        text = sys.stdin.read()
    else:
        text = ' '.join(sys.argv[1:])

    normalized = normalize_word_chars(text)
    print(normalized)


if __name__ == '__main__':
    main()
