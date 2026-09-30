---
name: docx-delta
description: Compare two Word documents and produce a delta view, as a redline .docx with real tracked changes that Word's Review pane can accept or reject, a side-by-side HTML page, or a unified text diff. Use whenever asked what changed between two versions of a document, for a delta or redline or comparison or "track changes version" between drafts (v0.9 vs v1.0, a research plan, a contract, a board paper, a grant application), or when a delta needs to go in an email. Replaces Word's Review Compare feature and LibreOffice's compare, which does not run reliably headless.
---

# Word document delta

```bash
D=~/.claude/skills/docx-delta/scripts/docx_delta.py
python3 $D old.docx new.docx                      # counts, to the terminal
python3 $D old.docx new.docx -o delta.docx        # redline, tracked changes
python3 $D old.docx new.docx -o delta.html        # side-by-side, for reading
python3 $D old.docx new.docx --md                 # unified text diff
```

## Which output

- **`.docx`** when you or a recipient will work in Word. It is the new document
  with the differences as real `w:ins` and `w:del`, so Review shows them and Accept
  and Reject work. This is what Word's own Compare produces.
- **`.html`** when the delta is for reading or for an email. One row per change, old
  and new side by side, changed words marked within the paragraph so a single edited
  figure is visible in a long paragraph.
- **`--md`** when the answer is a quick "what moved" in the terminal.

Quote the counts it prints (changed, added, deleted, unchanged) when reporting, and
name the two files compared.

## Why not LibreOffice or Word

LibreOffice's compare is the obvious automation route and it does not run reliably
headless. It was built after LibreOffice's compare refused to run for a document delta
that was due to go out in an email, leaving a stale delta about to be sent. Driving Word
by AppleScript needs Word open and focused, which is no good in a background session.

This tool does the comparison in Python: paragraph alignment first, then word-level
inside each changed paragraph. Deterministic, no app to drive, same answer every run.

## What it does not compare

Say so when reporting; a diff that quietly skips content is worse than none.

- Body paragraphs and table cell text ARE compared.
- Footnotes, endnotes, comments, headers and footers are counted and named in the
  output, not diffed.
- Images, charts and styling are not compared. This is a text delta.

## Gotchas

- Paragraph alignment normalises whitespace, so re-wrapping alone is not a change.
- A heavily rewritten document can align as "everything changed". That is usually
  true rather than a failure, but check the HTML before quoting the number.
- The redline keeps the new document's formatting. It is a comparison artefact, not a
  version: name it `delta-...docx` and never let it into the version sequence.
- Both files must be `.docx`. Convert `.doc` first (`soffice --convert-to docx`).
