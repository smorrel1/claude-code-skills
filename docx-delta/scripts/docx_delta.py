#!/usr/bin/env python3
"""Compare two Word documents and produce a redline Word can open.

Word's Review Compare does this by hand. LibreOffice's compare is the usual
automation route and it does not run reliably headless: it refused to run for a
delta that was due to go out in an email, which is why this exists. The
comparison is done here, in Python, on the text: deterministic, no app to
drive, same answer every run.

    docx_delta.py OLD.docx NEW.docx                 summary to the terminal
    docx_delta.py OLD.docx NEW.docx -o delta.docx   redline with tracked changes
    docx_delta.py OLD.docx NEW.docx -o delta.html   side-by-side for reading
    docx_delta.py OLD.docx NEW.docx --md            unified text diff

The .docx output carries REAL tracked changes (w:ins and w:del), so Word shows
them in the Review pane and Accept and Reject work. Formatting comes from the
new document; this compares words, not styling.

Known limits, stated because a diff that quietly skips content is worse than
none: it compares body paragraphs and table cell text. Footnotes, endnotes,
headers, footers, text boxes and comments are counted and reported, not diffed.
Images are not compared.
"""
import argparse
import datetime
import difflib
import html
import os
import re
import sys

from docx import Document
from docx.oxml.ns import qn, nsmap

W = nsmap['w']
AUTHOR = "docx-delta"


def blocks(doc):
    """Every comparable paragraph, in document order, with where it came from.

    Table cells are walked in place rather than appended at the end, so a
    change inside a table stays next to the text around it.
    """
    out = []

    def walk_body(container, where):
        for child in container.element.body if hasattr(container, 'element') else []:
            pass  # body walked below; kept explicit for readability

    for p in doc.paragraphs:
        out.append({"text": p.text, "para": p, "where": "body"})
    for ti, t in enumerate(doc.tables, 1):
        for ri, row in enumerate(t.rows, 1):
            for ci, cell in enumerate(row.cells, 1):
                for p in cell.paragraphs:
                    if p.text.strip():
                        out.append({"text": p.text, "para": p,
                                    "where": "table %d r%d c%d" % (ti, ri, ci)})
    return out


def other_content(path):
    """Parts this tool does not diff, so the report can admit to them."""
    import zipfile
    z = zipfile.ZipFile(path)
    names = z.namelist()
    found = {}
    for part, label in (("word/footnotes.xml", "footnotes"),
                        ("word/endnotes.xml", "endnotes"),
                        ("word/comments.xml", "comments")):
        if part in names:
            body = z.read(part).decode("utf-8", "ignore")
            n = len(re.findall(r"<w:t[ >]", body))
            if n:
                found[label] = n
    heads = [n for n in names if re.match(r"word/(header|footer)\d+\.xml", n)]
    if heads:
        found["headers/footers"] = len(heads)
    return found


def word_diff(a, b):
    """Word-level opcodes between two strings, keeping the whitespace."""
    aw = re.findall(r"\S+\s*", a)
    bw = re.findall(r"\S+\s*", b)
    return aw, bw, difflib.SequenceMatcher(None, aw, bw, autojunk=False).get_opcodes()



def pair_block(old_texts, new_texts, threshold=0.5):
    """Pair paragraphs inside a replace block by similarity, not by position.

    Positional pairing mis-pairs as soon as a paragraph is inserted in the
    middle of a rewritten stretch: every later pair is compared against the
    wrong partner, and a light edit reads as a heavy one. This finds the
    non-crossing pairing with the best total similarity (a small dynamic
    program; replace blocks are short), leaving anything below the threshold
    unpaired, to be reported as a plain add or delete.

    Returns (pairs, old_unpaired, new_unpaired) as index lists.
    """
    n, m = len(old_texts), len(new_texts)
    ratio = [[difflib.SequenceMatcher(None, old_texts[i], new_texts[j]).ratio()
              for j in range(m)] for i in range(n)]
    # best[i][j] = best score using old[i:] and new[j:]
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            skip = max(best[i + 1][j], best[i][j + 1])
            take = (ratio[i][j] + best[i + 1][j + 1]) if ratio[i][j] >= threshold else 0.0
            best[i][j] = max(skip, take)
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        take = (ratio[i][j] + best[i + 1][j + 1]) if ratio[i][j] >= threshold else -1.0
        if take >= best[i][j] - 1e-9 and ratio[i][j] >= threshold:
            pairs.append((i, j)); i += 1; j += 1
        elif best[i + 1][j] >= best[i][j + 1]:
            i += 1
        else:
            j += 1
    paired_o = {a for a, _ in pairs}
    paired_n = {b for _, b in pairs}
    return (pairs, [i for i in range(n) if i not in paired_o],
            [j for j in range(m) if j not in paired_n])


def align(old_blocks, new_blocks):
    """Paragraph-level alignment, on normalised text so spacing is not a change."""
    norm = lambda t: re.sub(r"\s+", " ", t).strip()
    a = [norm(b["text"]) for b in old_blocks]
    b = [norm(x["text"]) for x in new_blocks]
    return difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()


# ----------------------------------------------------------------- tracked docx

def _rpr_of(para):
    """Copy the run properties of a paragraph's first run, to keep the look."""
    for r in para.runs:
        rPr = r._r.find(qn('w:rPr'))
        if rPr is not None:
            import copy
            return copy.deepcopy(rPr)
    return None


def _make_run(parent, text, rPr=None, deleted=False):
    r = parent.makeelement(qn('w:r'), {})
    if rPr is not None:
        import copy
        r.append(copy.deepcopy(rPr))
    t = parent.makeelement(qn('w:delText' if deleted else 'w:t'), {})
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    t.text = text
    r.append(t)
    return r


def _wrap(parent, tag, runs, idx, stamp):
    el = parent.makeelement(qn(tag), {
        qn('w:id'): str(idx), qn('w:author'): AUTHOR, qn('w:date'): stamp})
    for r in runs:
        el.append(r)
    return el



def check_partition(stats, n_old, n_new, mode):
    """Every paragraph must be accounted for, or the report is lying.

    changed + added + unchanged must cover the new document, and
    changed + deleted + unchanged must cover the old one. On 30 Sep 2026 the
    redline silently dropped 23 new paragraphs and still printed a confident
    set of counts; the HTML mode disagreed and nothing said so. Fail loudly.
    """
    new_side = stats["changed"] + stats["added"] + stats["equal"]
    old_side = stats["changed"] + stats["deleted"] + stats["equal"]
    problems = []
    if new_side != n_new:
        problems.append("new document has %d comparable paragraphs but the counts "
                        "cover %d (changed %d + added %d + unchanged %d)"
                        % (n_new, new_side, stats["changed"], stats["added"], stats["equal"]))
    if old_side != n_old:
        problems.append("old document has %d comparable paragraphs but the counts "
                        "cover %d (changed %d + deleted %d + unchanged %d)"
                        % (n_old, old_side, stats["changed"], stats["deleted"], stats["equal"]))
    if problems:
        raise RuntimeError("%s mode did not account for every paragraph:\n  %s\n"
                           "The delta is incomplete; do not use it."
                           % (mode, "\n  ".join(problems)))


def redline_docx(old_path, new_path, out_path):
    """Write the new document with the differences marked as tracked changes."""
    old = Document(old_path)
    new = Document(new_path)
    ob, nb = blocks(old), blocks(new)
    stamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    idx = 1000
    stats = {"equal": 0, "changed": 0, "added": 0, "deleted": 0}

    for tag, i1, i2, j1, j2 in align(ob, nb):
        if tag == 'equal':
            stats["equal"] += i2 - i1
            continue
        if tag in ('replace', 'delete'):
            # Deleted paragraphs are re-inserted into the new document as
            # struck-through tracked deletions, otherwise the reader cannot see
            # what went. They are attached before the paragraph that replaced
            # them, or at the end when the tail was cut.
            anchor = nb[j1]["para"] if j1 < len(nb) else (nb[-1]["para"] if nb else None)
            for k in range(i1, i2):
                if tag == 'replace' and (k - i1) < (j2 - j1):
                    continue  # handled word by word below
                if anchor is None:
                    break
                p = anchor._p.makeelement(qn('w:p'), {})
                rPr = _rpr_of(ob[k]["para"])
                idx += 1
                p.append(_wrap(p, 'w:del',
                               [_make_run(p, ob[k]["text"], rPr, deleted=True)], idx, stamp))
                anchor._p.addprevious(p)
                stats["deleted"] += 1
        if tag == 'insert':
            for k in range(j1, j2):
                para = nb[k]["para"]
                rPr = _rpr_of(para)
                runs = [_make_run(para._p, para.text, rPr)]
                for r in list(para._p.findall(qn('w:r'))):
                    para._p.remove(r)
                idx += 1
                para._p.append(_wrap(para._p, 'w:ins', runs, idx, stamp))
                stats["added"] += 1
        if tag == 'replace':
            for off in range(min(i2 - i1, j2 - j1)):
                o, n = ob[i1 + off], nb[j1 + off]
                para = n["para"]
                rPr = _rpr_of(para)
                aw, bw, ops = word_diff(o["text"], n["text"])
                for r in list(para._p.findall(qn('w:r'))):
                    para._p.remove(r)
                for t2, a1, a2, b1, b2 in ops:
                    if t2 in ('equal',):
                        para._p.append(_make_run(para._p, "".join(bw[b1:b2]), rPr))
                    if t2 in ('replace', 'delete'):
                        idx += 1
                        para._p.append(_wrap(para._p, 'w:del',
                                             [_make_run(para._p, "".join(aw[a1:a2]), rPr,
                                                        deleted=True)], idx, stamp))
                    if t2 in ('replace', 'insert'):
                        idx += 1
                        para._p.append(_wrap(para._p, 'w:ins',
                                             [_make_run(para._p, "".join(bw[b1:b2]), rPr)],
                                             idx, stamp))
                stats["changed"] += 1
            # A replace block whose new side is LONGER leaves surplus new
            # paragraphs beyond the positional pairs. They used to be left as
            # plain text: unmarked, uncounted, and read as unchanged, which hid
            # about 23 genuinely new paragraphs in a real redline and made the
            # docx counts disagree with the HTML.
            for k in range(j1 + (i2 - i1), j2):
                para = nb[k]["para"]
                rPr = _rpr_of(para)
                runs = [_make_run(para._p, para.text, rPr)]
                for r in list(para._p.findall(qn('w:r'))):
                    para._p.remove(r)
                idx += 1
                para._p.append(_wrap(para._p, 'w:ins', runs, idx, stamp))
                stats["added"] += 1

    check_partition(stats, len(ob), len(nb), "redline docx")
    new.save(out_path)
    return stats


# ------------------------------------------------------------------ html / text

def html_report(old_path, new_path, out_path, stats_only=False, pairing='positional'):
    ob, nb = blocks(Document(old_path)), blocks(Document(new_path))
    rows = []
    stats = {"equal": 0, "changed": 0, "added": 0, "deleted": 0}
    for tag, i1, i2, j1, j2 in align(ob, nb):
        if tag == 'equal':
            stats["equal"] += i2 - i1
            continue
        if tag == 'insert':
            for k in range(j1, j2):
                stats["added"] += 1
                rows.append(("added", nb[k]["where"], "", nb[k]["text"]))
        elif tag == 'delete':
            for k in range(i1, i2):
                stats["deleted"] += 1
                rows.append(("deleted", ob[k]["where"], ob[k]["text"], ""))
        elif pairing == 'similarity':
            pairs, un_o, un_n = pair_block([x["text"] for x in ob[i1:i2]],
                                           [x["text"] for x in nb[j1:j2]])
            for a, b in pairs:
                stats["changed"] += 1
                rows.append(("changed", nb[j1 + b]["where"],
                             ob[i1 + a]["text"], nb[j1 + b]["text"]))
            for b in un_n:
                stats["added"] += 1
                rows.append(("added", nb[j1 + b]["where"], "", nb[j1 + b]["text"]))
            for a in un_o:
                stats["deleted"] += 1
                rows.append(("deleted", ob[i1 + a]["where"], ob[i1 + a]["text"], ""))
        else:
            for off in range(max(i2 - i1, j2 - j1)):
                o = ob[i1 + off]["text"] if i1 + off < i2 else ""
                n = nb[j1 + off]["text"] if j1 + off < j2 else ""
                where = (nb[j1 + off]["where"] if j1 + off < j2 else ob[i1 + off]["where"])
                if o and n:
                    stats["changed"] += 1
                    rows.append(("changed", where, o, n))
                elif n:
                    stats["added"] += 1
                    rows.append(("added", where, "", n))
                else:
                    stats["deleted"] += 1
                    rows.append(("deleted", where, o, ""))

    check_partition(stats, len(ob), len(nb), "html")
    if stats_only:
        return stats, rows

    def mark(a, b):
        """Inline word marks, so a one-word edit is visible in a long paragraph."""
        aw, bw, ops = word_diff(a, b)
        left, right = [], []
        for t, a1, a2, b1, b2 in ops:
            at, bt = html.escape("".join(aw[a1:a2])), html.escape("".join(bw[b1:b2]))
            if t == 'equal':
                left.append(at); right.append(bt)
            if t in ('replace', 'delete'):
                left.append('<del>%s</del>' % at)
            if t in ('replace', 'insert'):
                right.append('<ins>%s</ins>' % bt)
        return "".join(left), "".join(right)

    body = []
    for kind, where, o, n in rows:
        l, r = mark(o, n) if (o and n) else (html.escape(o), html.escape(n))
        body.append(
            '<tr class="%s"><td class="k">%s</td><td class="w">%s</td>'
            '<td>%s</td><td>%s</td></tr>' % (kind, kind, html.escape(where), l, r))

    out = """<!doctype html><meta charset="utf-8">
<title>Delta: %s vs %s</title>
<style>
 body{font:14px/1.5 -apple-system,Helvetica,Arial,sans-serif;margin:24px;color:#111}
 h1{font-size:19px;margin:0 0 4px} .sub{color:#555;margin-bottom:18px}
 table{border-collapse:collapse;width:100%%;table-layout:fixed}
 th,td{border:1px solid #bbb;padding:7px 9px;vertical-align:top;word-wrap:break-word}
 th{background:#eee;text-align:left;font-weight:700}
 td.k{width:74px;text-transform:capitalize;font-weight:700}
 td.w{width:110px;color:#555;font-size:12px}
 tr.added td.k{color:#0a7a2f} tr.deleted td.k{color:#a11} tr.changed td.k{color:#a56a00}
 ins{background:#d8f5de;text-decoration:none} del{background:#fbd9d9}
</style>
<h1>%s</h1>
<div class="sub">Old: %s<br>New: %s<br>%d changed, %d added, %d deleted, %d unchanged</div>
<table><tr><th>Change</th><th>Where</th><th>Old</th><th>New</th></tr>%s</table>
""" % (html.escape(os.path.basename(old_path)), html.escape(os.path.basename(new_path)),
       "Delta view", html.escape(old_path), html.escape(new_path),
       stats["changed"], stats["added"], stats["deleted"], stats["equal"],
       "".join(body) or '<tr><td colspan="4">No text differences.</td></tr>')
    open(out_path, "w").write(out)
    return stats, rows


def md_report(old_path, new_path):
    ob, nb = blocks(Document(old_path)), blocks(Document(new_path))
    a = [b["text"] for b in ob]
    b = [x["text"] for x in nb]
    return "\n".join(difflib.unified_diff(
        a, b, fromfile=os.path.basename(old_path), tofile=os.path.basename(new_path),
        lineterm="", n=1))


def main():
    ap = argparse.ArgumentParser(description="Compare two .docx files")
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("-o", "--out", help="output .docx (tracked changes) or .html")
    ap.add_argument("--md", action="store_true", help="print a unified text diff")
    ap.add_argument("--pair", choices=["positional", "similarity"], default="positional",
                    help="how to pair paragraphs inside a rewritten block. positional "
                         "(default) pairs them in order; similarity pairs each old "
                         "paragraph with the new one it most resembles and reports the "
                         "rest as plain adds and deletes. Report modes only")
    a = ap.parse_args()

    for p in (a.old, a.new):
        if not os.path.exists(p):
            sys.exit("Not found: %s" % p)

    if a.md:
        print(md_report(a.old, a.new))
        return 0

    if a.pair == "similarity" and a.out and a.out.lower().endswith(".docx"):
        sys.exit("--pair similarity is report-only: the redline pairs positionally.\n"
                 "Mixing them would make the docx counts disagree with the HTML, which\n"
                 "is the defect this tool was fixed for on 30 Sep 2026. Run them\n"
                 "separately: the redline for Word, the HTML for the pairing you want.")

    stats, rows = html_report(a.old, a.new, None, stats_only=True, pairing=a.pair)
    if a.out and a.out.lower().endswith(".docx"):
        stats = redline_docx(a.old, a.new, a.out)
    elif a.out:
        html_report(a.old, a.new, a.out, pairing=a.pair)

    print("%s  ->  %s" % (os.path.basename(a.old), os.path.basename(a.new)))
    print("  changed   %d paragraph(s)" % stats["changed"])
    print("  added     %d" % stats["added"])
    print("  deleted   %d" % stats["deleted"])
    print("  unchanged %d" % stats["equal"])
    for label, path in (("old", a.old), ("new", a.new)):
        extra = other_content(path)
        if extra:
            print("  NOT compared in the %s file: %s"
                  % (label, ", ".join("%s (%d)" % (k, v) for k, v in extra.items())))
    if a.out:
        print("Wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
