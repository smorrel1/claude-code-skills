#!/usr/bin/env python3
"""Does the delta account for every paragraph, in both modes?

    python3 tests/test_delta.py

The case that matters is a replace block whose new side is LONGER: one old
paragraph rewritten into three. Until 30 Sep 2026 the redline marked the first
of the three and left the other two as plain text, unmarked and uncounted, so a
reader saw new material as unchanged and the docx counts disagreed with the HTML.
"""
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import docx_delta as dd  # noqa: E402
from docx import Document  # noqa: E402


def build(path, paragraphs):
    d = Document()
    for p in paragraphs:
        d.add_paragraph(p)
    d.save(path)


def ins_text(path):
    x = zipfile.ZipFile(path).read('word/document.xml').decode()
    return " ".join("".join(re.findall(r'<w:t[^>]*>([^<]*)<', m.group(0)))
                    for m in re.finditer(r'<w:ins\b.*?</w:ins>', x, re.S))


def del_text(path):
    x = zipfile.ZipFile(path).read('word/document.xml').decode()
    return " ".join("".join(re.findall(r'<w:delText[^>]*>([^<]*)<', m.group(0)))
                    for m in re.finditer(r'<w:del\b.*?</w:del>', x, re.S))


CASES = [
    ("one paragraph rewritten into three", [
        "Opening paragraph that does not change.",
        "The pilot will run at three sites in London.",
        "Closing paragraph that does not change.",
    ], [
        "Opening paragraph that does not change.",
        "The pilot will run at four sites in London.",
        "Two of the sites are teaching hospitals.",
        "The fourth site joins in the second year.",
        "Closing paragraph that does not change.",
    ]),
    ("three paragraphs collapsed into one", [
        "Alpha stays.",
        "First of three that merge.",
        "Second of three that merge.",
        "Third of three that merge.",
        "Omega stays.",
    ], [
        "Alpha stays.",
        "All three merged into this single sentence.",
        "Omega stays.",
    ]),
    ("pure insertion at the end", [
        "Only paragraph.",
    ], [
        "Only paragraph.",
        "A brand new tail paragraph.",
    ]),
    ("pure deletion", [
        "Kept.",
        "Removed entirely.",
    ], [
        "Kept.",
    ]),
    ("no differences at all", [
        "Identical one.",
        "Identical two.",
    ], [
        "Identical one.",
        "Identical two.",
    ]),
]


def main():
    bad = []
    tmp = tempfile.mkdtemp(prefix="docx-delta-test-")
    for name, old_paras, new_paras in CASES:
        old = os.path.join(tmp, "old.docx")
        new = os.path.join(tmp, "new.docx")
        out = os.path.join(tmp, "delta.docx")
        build(old, old_paras)
        build(new, new_paras)

        # Both modes must agree, and check_partition must accept both. A
        # mismatch raises inside these calls, which is the point.
        try:
            html_stats, rows = dd.html_report(old, new, None, stats_only=True)
            docx_stats = dd.redline_docx(old, new, out)
        except RuntimeError as exc:
            bad.append("%s: %s" % (name, exc))
            continue

        if html_stats != docx_stats:
            bad.append("%s: html %s != docx %s" % (name, html_stats, docx_stats))

        # Every paragraph the HTML calls added must be inside w:ins, and every
        # deleted one inside w:del. This is what the old code got wrong.
        ins, dele = ins_text(out), del_text(out)
        for kind, _where, o, n in rows:
            if kind == "added" and n.strip() and n.strip()[:50] not in ins:
                bad.append("%s: added paragraph not marked w:ins: %r" % (name, n[:50]))
            if kind == "deleted" and o.strip() and o.strip()[:50] not in dele:
                bad.append("%s: deleted paragraph not marked w:del: %r" % (name, o[:50]))

        print("%-38s changed %d  added %d  deleted %d  unchanged %d"
              % (name, docx_stats["changed"], docx_stats["added"],
                 docx_stats["deleted"], docx_stats["equal"]))

    # The partition check itself must fail when the counts are wrong, otherwise
    # it is decoration.
    try:
        dd.check_partition({"changed": 1, "added": 0, "deleted": 0, "equal": 1}, 2, 5, "unit")
        bad.append("check_partition accepted counts that do not cover the new document")
    except RuntimeError:
        pass

    for b in bad:
        print("FAIL " + b)
    print("\n%d case(s), %d failure(s)" % (len(CASES) + 1, len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
