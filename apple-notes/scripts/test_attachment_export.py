#!/usr/bin/env python3
"""Regression test: notes whose content is a saved screenshot/link attachment
must export with the source URL and text, not a bare placeholder.

Exports to a temp dir and checks three known screenshot-only notes.
Run: python3 test_attachment_export.py
"""
import sys, os, tempfile, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export_notes

CASES = [
    ("*Andrej Karpathy (@karpathy).md", "x.com/karpathy", "programming has changed"),
    ("*Simon Willison (@simonw).md", "x.com/simonw", "vibe-coding"),
    ("*Auto review open claw Pete Steinberger.md", "x.com/steipete", "autoreview"),
]

failures = []
with tempfile.TemporaryDirectory() as td:
    export_notes.main(output_dir=td)
    print()
    for pattern, want_url, want_text in CASES:
        hits = glob.glob(os.path.join(td, "**", pattern), recursive=True)
        if not hits:
            failures.append(pattern); print(f"  FAIL  {pattern}: not exported"); continue
        content = open(hits[0], encoding="utf-8").read()
        url_ok = want_url in content
        text_ok = want_text.lower() in content.lower()
        status = "PASS" if (url_ok and text_ok) else "FAIL"
        if status == "FAIL":
            failures.append(pattern)
        print(f"  {status}  {os.path.basename(hits[0])}: url={url_ok} text={text_ok}")

print(f"\n{'FAIL' if failures else 'PASS'}: {len(failures)} failures")
sys.exit(1 if failures else 0)
