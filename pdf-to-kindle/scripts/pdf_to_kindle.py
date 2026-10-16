#!/usr/bin/env python3
"""
PDF to Kindle - Extract text from PDFs and send to Kindle.

Usage:
    python3 pdf_to_kindle.py extract --input doc.pdf --output doc.txt
    python3 pdf_to_kindle.py to-epub --input doc.txt --output doc.epub --title "Title"
    python3 pdf_to_kindle.py send --input doc.epub --title "Title"
    python3 pdf_to_kindle.py full --input doc.pdf --title "Title"
"""

import argparse
import subprocess
import sys
import os
import tempfile
from pathlib import Path

# Kindle configuration
KINDLE_EMAIL = os.environ.get("KINDLE_EMAIL", "your-kindle-email@kindle.com")
GMAIL_SCRIPT = os.path.expanduser("~/.claude/skills/email/scripts/gmail_utils.py")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kindle_cover import make_cover, tables_to_lists  # noqa: E402


def extract_text(input_path: str, output_path: str, preserve_columns: bool = False, output_format: str = "txt") -> str:
    """Extract text from PDF using pymupdf."""
    try:
        import fitz  # pymupdf
    except ImportError:
        print("Error: pymupdf not installed. Run: pip install pymupdf")
        sys.exit(1)

    doc = fitz.open(input_path)
    all_text = []

    for page_num, page in enumerate(doc):
        if preserve_columns:
            # Two-column layout detection
            blocks = page.get_text("blocks")
            page_width = page.rect.width
            midpoint = page_width / 2

            left_blocks = []
            right_blocks = []

            for block in blocks:
                x0, y0, x1, y1, text, block_no, block_type = block
                if block_type == 0:  # Text block
                    center_x = (x0 + x1) / 2
                    if center_x < midpoint:
                        left_blocks.append((y0, text))
                    else:
                        right_blocks.append((y0, text))

            # Sort by vertical position
            left_blocks.sort(key=lambda x: x[0])
            right_blocks.sort(key=lambda x: x[0])

            # Combine: left column first, then right
            page_text = "\n".join([b[1] for b in left_blocks])
            page_text += "\n\n"
            page_text += "\n".join([b[1] for b in right_blocks])
        else:
            page_text = page.get_text()

        all_text.append(page_text)

    page_count = len(doc)
    doc.close()

    full_text = "\n\n---\n\n".join(all_text)

    # Wide tables reflow into confetti on a Kindle, so they become lists.
    full_text = tables_to_lists(full_text, style='plain')

    # Convert to requested format
    if output_format == "html":
        full_text = text_to_html(full_text, Path(input_path).stem)
    elif output_format == "md":
        full_text = text_to_markdown(full_text)

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    print(f"Extracted {page_count} pages to {output_path}")
    return output_path


def text_to_html(text: str, title: str = "Document") -> str:
    """Convert plain text to HTML."""
    # Escape HTML entities
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Convert line breaks to paragraphs
    paragraphs = text.split("\n\n")
    html_paragraphs = [f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip()]

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<title>{title}</title>
<style>
body {{ font-family: Georgia, serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
p {{ margin-bottom: 1em; }}
</style>
</head>
<body>
<h1>{title}</h1>
{"".join(html_paragraphs)}
</body>
</html>"""
    return html


def text_to_markdown(text: str) -> str:
    """Convert plain text to Markdown."""
    # Basic conversion - paragraphs separated by blank lines
    lines = text.split("\n")
    md_lines = []
    for line in lines:
        if line.strip() == "---":
            md_lines.append("\n---\n")
        else:
            md_lines.append(line)
    return "\n".join(md_lines)


def to_epub(input_path: str, output_path: str, title: str = "Document", author: str = "",
            subtitles=None, cover: str = None, no_cover: bool = False) -> str:
    """Convert text/HTML to EPUB using Calibre's ebook-convert.

    A cover is the default, not an option: without one Send-to-Kindle shelves
    every document under the same generic DOC icon and Stephen cannot tell one
    from another. `cover` supplies a ready-made image, otherwise a title cover
    is drawn. `no_cover` is the deliberate opt-out.
    """
    cmd = ["ebook-convert", input_path, output_path, "--title", title]
    if author:
        cmd.extend(["--authors", author])

    cover_tmp = None
    if not no_cover:
        if not cover:
            cover_tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
            cover = make_cover(title, subtitles or [], cover_tmp)
        if cover and os.path.exists(cover):
            cmd.extend(["--cover", cover])
        else:
            print("No cover image, so Kindle will show the generic icon",
                  file=sys.stderr)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error converting to EPUB: {result.stderr}")
            sys.exit(1)
        print(f"Created EPUB: {output_path}")
        return output_path
    except FileNotFoundError:
        print("Error: Calibre not installed. Run: brew install calibre")
        sys.exit(1)
    finally:
        if cover_tmp and os.path.exists(cover_tmp):
            try:
                os.remove(cover_tmp)
            except OSError:
                pass


def send_to_kindle(input_path: str, title: str) -> None:
    """Send file to Kindle using gmail skill."""
    if not os.path.exists(GMAIL_SCRIPT):
        print(f"Error: Gmail script not found at {GMAIL_SCRIPT}")
        sys.exit(1)

    subject = f"Kindle: {title}"
    body = f"Sending '{title}' to your Kindle."

    cmd = [
        "python3", GMAIL_SCRIPT,
        "--account", "gmail",
        "send",
        "--to", KINDLE_EMAIL,
        "--subject", subject,
        "--body", body,
        "--attach", input_path,
        "--new"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error sending to Kindle: {result.stderr}")
        sys.exit(1)

    print(f"Sent '{title}' to {KINDLE_EMAIL}")
    print(result.stdout)


def full_workflow(input_path: str, title: str, preserve_columns: bool = False,
                  subtitles=None, cover: str = None, no_cover: bool = False) -> None:
    """Complete workflow: extract -> convert to EPUB -> send to Kindle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Step 1: Extract text
        txt_path = os.path.join(tmpdir, "extracted.txt")
        extract_text(input_path, txt_path, preserve_columns=preserve_columns)

        # Step 2: Convert to EPUB
        # Use title as filename for better Kindle display
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
        epub_path = os.path.join(tmpdir, f"{safe_title}.epub")
        to_epub(txt_path, epub_path, title=title, subtitles=subtitles,
                cover=cover, no_cover=no_cover)

        # Step 3: Send to Kindle
        send_to_kindle(epub_path, title)


def main():
    parser = argparse.ArgumentParser(description="PDF to Kindle utility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Extract command
    extract_parser = subparsers.add_parser("extract", help="Extract text from PDF")
    extract_parser.add_argument("--input", "-i", required=True, help="Input PDF file")
    extract_parser.add_argument("--output", "-o", default="./extracted.txt", help="Output file")
    extract_parser.add_argument("--format", "-f", choices=["txt", "html", "md"], default="txt", help="Output format")
    extract_parser.add_argument("--preserve-columns", action="store_true", help="Preserve two-column layout")

    # To-EPUB command
    epub_parser = subparsers.add_parser("to-epub", help="Convert text/HTML to EPUB")
    epub_parser.add_argument("--input", "-i", required=True, help="Input text/HTML file")
    epub_parser.add_argument("--output", "-o", required=True, help="Output EPUB file")
    epub_parser.add_argument("--title", "-t", default="Document", help="Book title")
    epub_parser.add_argument("--author", "-a", default="", help="Author name")
    epub_parser.add_argument("--subtitle", "-s", action="append", default=[],
                             help="Cover subtitle line, repeatable (up to 3)")
    epub_parser.add_argument("--cover", help="Use this image as the cover instead "
                             "of a drawn title cover")
    epub_parser.add_argument("--no-cover", action="store_true",
                             help="Skip the cover (Kindle shows a generic icon)")

    # Send command
    send_parser = subparsers.add_parser("send", help="Send file to Kindle")
    send_parser.add_argument("--input", "-i", required=True, help="File to send")
    send_parser.add_argument("--title", "-t", required=True, help="Book title for email subject")

    # Full workflow command
    full_parser = subparsers.add_parser("full", help="Full workflow: extract -> EPUB -> send")
    full_parser.add_argument("--input", "-i", required=True, help="Input PDF file")
    full_parser.add_argument("--title", "-t", required=True, help="Book title")
    full_parser.add_argument("--preserve-columns", action="store_true", help="Preserve two-column layout")
    full_parser.add_argument("--subtitle", "-s", action="append", default=[],
                             help="Cover subtitle line, repeatable (up to 3)")
    full_parser.add_argument("--cover", help="Use this image as the cover instead "
                             "of a drawn title cover")
    full_parser.add_argument("--no-cover", action="store_true",
                             help="Skip the cover (Kindle shows a generic icon)")

    args = parser.parse_args()

    if args.command == "extract":
        extract_text(args.input, args.output, args.preserve_columns, args.format)
    elif args.command == "to-epub":
        to_epub(args.input, args.output, args.title, args.author,
                subtitles=args.subtitle, cover=args.cover, no_cover=args.no_cover)
    elif args.command == "send":
        send_to_kindle(args.input, args.title)
    elif args.command == "full":
        full_workflow(args.input, args.title, args.preserve_columns,
                      subtitles=args.subtitle, cover=args.cover,
                      no_cover=args.no_cover)


if __name__ == "__main__":
    main()
