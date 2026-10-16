---
name: pdf-to-kindle
description: Extract text from PDFs and send to Kindle for comfortable reading. Use when the user wants to (1) send a PDF to Kindle, (2) convert a PDF for Kindle reading, (3) extract text from a PDF and email it to Kindle, or (4) read a document/paper/book on their Kindle device.
---

# PDF to Kindle

Extract text from PDFs and send to Kindle.

## Prerequisites

- pymupdf: `pip install pymupdf`
- Pillow: `pip install pillow` (cover image)
- Calibre: `brew install calibre`
- Gmail skill configured

## Quick Start

```bash
# One-step workflow
python3 scripts/pdf_to_kindle.py full --input document.pdf --title "Document Title"

# With two-column layout preservation (for academic papers)
python3 scripts/pdf_to_kindle.py full --input paper.pdf --title "Paper Title" --preserve-columns

# Cover subtitle lines: reference, project, date (up to three)
python3 scripts/pdf_to_kindle.py full --input budget.pdf --title "i4i BUDGET" \
  --subtitle NIHR523689 --subtitle ViewFinder --subtitle "16 Oct 2026"
```

## Every EPUB gets a title cover (standing default, 16 Oct 2026)

Send-to-Kindle gives a coverless document the same generic DOC icon as every
other one, so the library becomes unusable. `scripts/kindle_cover.py` therefore
draws a 1600x2560 cover for every EPUB: deep blue (#0d47a1), the title in white
Arial Bold, and up to three smaller subtitle lines. Nothing has to be passed for
this to happen.

| # | Option | Description |
|---|--------|-------------|
| 1 | `--subtitle` | A subtitle line, repeatable up to three times |
| 2 | `--cover FILE` | Use this image instead of the drawn cover |
| 3 | `--no-cover` | Skip the cover (back to the generic icon) |

Draw one on its own, for any other EPUB or for pandoc:

```bash
python3 scripts/kindle_cover.py --title "i4i BUDGET" \
  --subtitle NIHR523689 --subtitle "16 Oct 2026" --output cover.jpg
pandoc book.md -o book.epub --epub-cover-image=cover.jpg
```

Calibre's equivalent, which is what this skill uses, is `ebook-convert ... --cover cover.jpg`.

## Wide tables become lists

Stephen reads about ten words to a line on the Kindle, so a table of more than
three columns reflows into unreadable fragments. Extraction rewrites any such
Markdown table into one labelled block per row, and leaves two and
three-column tables alone. `kindle_cover.tables_to_lists(text)` does this and
can be imported by any other skill that builds an EPUB.

## Commands

| Command | Purpose |
|---------|---------|
| `full` | Complete workflow: extract → EPUB → send |
| `extract` | Extract text from PDF |
| `to-epub` | Convert text/HTML to EPUB |
| `send` | Send file to Kindle |

## Extract Options

| Option | Description |
|--------|-------------|
| `--preserve-columns` | Handle two-column academic paper layouts |
| `--format` | Output format: txt, html, or md |

## Kindle Configuration

- **Email**: Set via `KINDLE_EMAIL` env var (your Send to Kindle address)
- **Sender**: Your Gmail account approved in Amazon settings
- **Limits**: 50 MB (Amazon), 25 MB (Gmail)
