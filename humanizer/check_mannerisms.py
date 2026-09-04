#!/usr/bin/env python3
"""Deterministic check for AI mannerisms in a finished document.

The humanizer skill is 437 lines of judgement with nothing to run, so there was
no way to prove it had been applied. On 4 Sep 2026 a 5,228-word investor report
shipped with 'pivotal' five times and 'Stated once:' in the body, because the
skill was discussed but never invoked. This script closes that hole: it either
passes or it does not.

    python3 check_mannerisms.py <file.docx|.md|.txt|.html> [--quiet]

Exit 0 = clean. Exit 1 = banned terms or em dashes found; fix and re-run.
'watch' terms are reported but do not fail on their own: they are judgement
calls, and the count is what matters (one 'cadence' is fine, four is a tic).

Extend the term lists in mannerisms.json. Do not hard-code terms here.
"""
import argparse
import json
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TERMS = os.path.join(HERE, "mannerisms.json")


def extract(path):
    """Plain text from docx/md/txt/html. docx is a zip of XML, so strip tags."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf8", "replace")
        # Keep paragraph breaks so context snippets stay readable.
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml))
    text = open(path, encoding="utf8", errors="replace").read()
    if ext in (".html", ".htm"):
        text = re.sub(r"<[^>]+>", " ", text)
    return text


def mask_allowed(text, allow_phrases):
    """Blank out legitimate domain phrases so their words are not flagged.
    'robust PPIE' is real NIHR terminology; 'robust growth' is filler."""
    for p in sorted(allow_phrases, key=len, reverse=True):
        text = re.sub(re.escape(p), "#" * len(p), text, flags=re.I)
    return text


def find(text, entry, allow_phrases):
    term = entry["term"]
    local = mask_allowed(text, list(allow_phrases) + entry.get("allow", []))
    pat = re.escape(term)
    if term.isalpha():
        pat = r"\b" + pat + r"\b"
    hits = []
    for m in re.finditer(pat, local, re.I):
        hits.append(text[max(0, m.start() - 60):m.end() + 60].strip())
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--quiet", action="store_true", help="counts only, no context")
    a = ap.parse_args()

    cfg = json.load(open(TERMS))
    text = extract(a.path)
    allow = cfg.get("allow_phrases", [])
    words = len(text.split())

    print(f"{os.path.basename(a.path)}  ({words:,} words)\n")
    failed = False

    for label, key, fails in (("BANNED", "banned", True), ("WATCH", "watch", False)):
        rows = [(e, find(text, e, allow)) for e in cfg.get(key, [])]
        rows = [(e, h) for e, h in rows if h]
        if not rows:
            continue
        print(f"--- {label} " + ("(must fix)" if fails else "(judgement: check counts)"))
        for e, h in sorted(rows, key=lambda r: -len(r[1])):
            print(f"  {len(h):3d}  {e['term']!r}  - {e['why']}")
            if not a.quiet:
                for s in h[:3]:
                    print(f"        ...{s}...")
        if fails:
            failed = True
        print()

    if cfg.get("em_dash_check", True):
        n = text.count("—")
        if n:
            print(f"--- EM DASHES (must fix)\n  {n:3d}  '—'  - "
                  f"Stephen's CLAUDE.md forbids em dashes in all writing for him\n")
            failed = True

    if failed:
        print("RESULT: FAIL. Fix the banned items, then re-run.")
        return 1
    print("RESULT: PASS (no banned terms, no em dashes).")
    print("Watch-list counts above are still worth a human read.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
