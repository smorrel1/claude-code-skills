#!/usr/bin/env python3
"""Make a Kindle cover that says what the document is.

Without a cover, Send-to-Kindle shelves everything under the same generic DOC
icon, so a library of them is unreadable at a glance. Every EPUB this toolbox
builds therefore gets a plain title cover: deep blue, the title in white Arial
Bold, and up to three smaller subtitle lines (reference, project, date).

    python3 kindle_cover.py --title "i4i BUDGET" \
        --subtitle "NIHR523689" --subtitle "ViewFinder" --subtitle "16 Oct 2026" \
        --output cover.jpg

Or from Python:

    from kindle_cover import make_cover
    make_cover("i4i BUDGET", ["NIHR523689", "16 Oct 2026"], "cover.jpg")

Returns the path, or None if PIL is missing or the draw fails. Callers treat
None as "carry on without a cover", never as a reason to stop: a book with a
dull icon still beats no book.

Also here: `tables_to_lists`, which turns wide Markdown tables into lists.
Stephen reads about ten words to a line on the Kindle, so a six-column table
reflows into unreadable confetti.
"""
import argparse
import re
import sys

W, H = 1600, 2560
BG = (13, 71, 161)            # #0d47a1
BAND = (33, 118, 243)         # lighter rule top and bottom
INK = (255, 255, 255)
SUB_INK = (226, 234, 250)
BOLD = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
MARGIN = 150


def _fit(draw, text, font_path, start, min_size, max_lines, width):
    """Largest size at which `text` wraps into <= max_lines lines."""
    from PIL import ImageFont
    size = start
    while size > min_size:
        font = ImageFont.truetype(font_path, size)
        lines = _wrap(draw, text, font, width)
        if len(lines) <= max_lines:
            return font, lines, size
        size -= 8
    font = ImageFont.truetype(font_path, min_size)
    return font, _wrap(draw, text, font, width), min_size


def _wrap(draw, text, font, width):
    lines, cur = [], ''
    for word in text.split():
        trial = (cur + ' ' + word).strip()
        if draw.textlength(trial, font=font) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def make_cover(title, subtitles=None, output_path='cover.jpg'):
    """Draw a 1600x2560 title cover. Returns output_path, or None on failure."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Warning: PIL not installed, so no cover image "
              "(pip install pillow)", file=sys.stderr)
        return None

    subtitles = [s for s in (subtitles or []) if s and s.strip()][:3]
    try:
        cover = Image.new('RGB', (W, H), BG)
        draw = ImageDraw.Draw(cover)
        draw.rectangle([0, 0, W, 48], fill=BAND)
        draw.rectangle([0, H - 48, W, H], fill=BAND)

        block_w = W - 2 * MARGIN
        tfont, tlines, tsize = _fit(draw, title or 'Document', BOLD,
                                    170, 70, 4, block_w)
        title_h = int(tsize * 1.22)

        sub_blocks = []
        if subtitles:
            sfont, _, ssize = _fit(draw, max(subtitles, key=len), BOLD,
                                   80, 44, 1, block_w)
            for s in subtitles:
                sub_blocks.extend(_wrap(draw, s, sfont, block_w))
            sub_h = int(ssize * 1.35)
        else:
            sfont, sub_h = None, 0

        total = len(tlines) * title_h + (90 + len(sub_blocks) * sub_h
                                         if sub_blocks else 0)
        # Sit the block in the upper half: a Kindle library shows the top of
        # the cover largest in the carousel.
        y = max(240, int(H * 0.42) - total // 2)

        for line in tlines:
            draw.text(((W - draw.textlength(line, font=tfont)) / 2, y),
                      line, font=tfont, fill=INK)
            y += title_h
        if sub_blocks:
            y += 90
            for line in sub_blocks:
                draw.text(((W - draw.textlength(line, font=sfont)) / 2, y),
                          line, font=sfont, fill=SUB_INK)
                y += sub_h

        cover.save(output_path, 'JPEG', quality=92)
        return output_path
    except Exception as e:
        print("Warning: could not draw the cover (%s), carrying on without "
              "one" % e, file=sys.stderr)
        return None


_ROW = re.compile(r'^\s*\|.*\|\s*$')
_RULE = re.compile(r'^\s*\|[\s:\-|]+\|\s*$')


def _cells(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def tables_to_lists(text, max_cols=3, style='markdown'):
    """Rewrite Markdown pipe tables of more than `max_cols` columns as lists.

    A wide table on a Kindle wraps every cell onto its own ragged line and the
    column it belonged to is lost. One block per row, labelled, reads instead.
    Narrow tables (two or three columns) survive the small screen, so they are
    left alone. `style` is 'markdown' (row label in bold) or 'plain', for a
    pipeline that hands the text straight to a converter and would print the
    asterisks literally.
    """
    out, i, lines = [], 0, text.split('\n')
    while i < len(lines):
        if (_ROW.match(lines[i]) and i + 1 < len(lines)
                and _RULE.match(lines[i + 1])):
            header = _cells(lines[i])
            j = i + 2
            rows = []
            while j < len(lines) and _ROW.match(lines[j]):
                rows.append(_cells(lines[j]))
                j += 1
            if len(header) > max_cols:
                # Stephen's tables start with a '#' row-number column. The
                # number alone is a useless heading, so it prefixes the next
                # column instead and both drop out of the detail list.
                numbered = header and header[0].strip('.').lower() in (
                    '#', 'no', 'num', 'item no', 'row')
                skip = 2 if numbered and len(header) > 1 else 1
                for row in rows:
                    if numbered and len(row) > 1:
                        label = '%s. %s' % (row[0], row[1])
                    else:
                        label = row[0] if row else ''
                    label = label.strip() or '-'
                    out.append('**%s**' % label if style == 'markdown'
                               else label)
                    out.append('')
                    for name, value in zip(header[skip:], row[skip:]):
                        if value:
                            out.append('- %s: %s' % (name, value))
                    out.append('')
                i = j
                continue
        out.append(lines[i])
        i += 1
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser(description="Draw a Kindle title cover")
    ap.add_argument('--title', '-t', required=True)
    ap.add_argument('--subtitle', '-s', action='append', default=[],
                    help='repeatable, up to three lines')
    ap.add_argument('--output', '-o', default='cover.jpg')
    a = ap.parse_args()
    path = make_cover(a.title, a.subtitle, a.output)
    if not path:
        return 1
    print(path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
