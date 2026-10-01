#!/usr/bin/env python3
"""Regenerate registry.md from the live cmux tree, so it can never drift.

The old registry.md was written by hand and keyed on workspace NUMBER. cmux
renumbers constantly: every delegation moves the new task to the top, and the
numbers move with it. The file carried a standing instruction to re-reconcile it
by hand before every lookup, which is an admission that it was wrong by default.
On 8 Sep 2026 it claimed workspace:1 was "Plan A & Involvency" when workspace:1
was "Chief of staff" and Plan A had become workspace:5.

The fix is to stop writing the volatile half:

  registry-durable.md   hand-written, keyed on workspace TITLE, which survives
                        renumbering. Topic, contacts, session id, hard-won notes.
  registry.md           GENERATED. Never edit. Live tree joined onto the durable
                        notes by title.

Titles that no longer appear in the tree are not deleted; they drop into a
"not currently open" section, so a closed workspace loses its slot rather than
its history.

  refresh_registry.py            regenerate
  refresh_registry.py --check    exit 1 if regeneration would change the file
"""
import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CMUX = "/Applications/cmux.app/Contents/Resources/bin/cmux"
REF = Path(__file__).resolve().parent.parent / "references"
DURABLE = REF / "registry-durable.md"
OUT = REF / "registry.md"

WS_RE = re.compile(r'workspace workspace:(\d+)\s+"([^"]*)"')
SURF_RE = re.compile(r'surface surface:(\d+)\s+\[(\w+)\]\s+"([^"]*)"')
TTY_RE = re.compile(r'tty=(\S+)')

# Braille frames are cmux's spinner: that surface is mid-task.
SPINNER = set("⠀⠁⠂⠃⠄⠅⠆⠇⠈⠉"
              "⠊⠋⠌⠍⠎⠏⠐⠑⠒⠓"
              "⠔⠕⠖⠗⠘⠙⠚⠛⠦⠧"
              "⠶⠷⠻⠼⠽⠾⠿")


def norm(title):
    """Match titles across cosmetic drift: status glyphs, case, spacing."""
    t = re.sub(r"^[^0-9A-Za-z]+", "", title or "").strip().lower()
    return re.sub(r"\s+", " ", t)


class TreeUnavailable(Exception):
    """cmux did not answer. Common: its socket congests while sessions are busy."""


def read_tree(timeout=25):
    try:
        out = subprocess.run([CMUX, "tree", "--all"], capture_output=True,
                             text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TreeUnavailable(str(exc))
    if out.returncode != 0:
        raise TreeUnavailable("exit %d: %s" % (out.returncode, out.stderr.strip()[:200]))

    workspaces, cur = [], None
    for line in out.stdout.splitlines():
        m = WS_RE.search(line)
        if m:
            cur = {"num": int(m.group(1)), "title": m.group(2),
                   "surfaces": [], "ttys": [], "busy": False}
            workspaces.append(cur)
            continue
        if cur is None:
            continue
        s = SURF_RE.search(line)
        if s:
            label = s.group(3)
            cur["surfaces"].append(label)
            if label[:1] in SPINNER:
                cur["busy"] = True
        t = TTY_RE.search(line)
        if t and t.group(1) not in cur["ttys"]:
            cur["ttys"].append(t.group(1))
    return workspaces


def read_durable():
    """Parse the hand-written table. Blank file is fine, it just means no notes."""
    rows = {}
    if not DURABLE.exists():
        return rows
    for line in DURABLE.read_text().splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5 or cells[0].lower() == "title":
            continue
        rows[norm(cells[0])] = {"title": cells[0], "topic": cells[1],
                                "contacts": cells[2], "session": cells[3],
                                "notes": cells[4]}
    return rows


def build(workspaces, durable):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = []
    L.append("# Workspace Registry")
    L.append("")
    L.append("**GENERATED FILE. Do not edit.** Regenerate with "
             "`python3 ~/.claude/skills/cmux/scripts/refresh_registry.py`.")
    L.append("Hand-written topic, contacts and notes live in `registry-durable.md`, "
             "keyed on workspace TITLE because numbers are reassigned on every reorder.")
    L.append("")
    L.append("Live as of %s. Order below is cmux order, top of the queue first." % stamp)
    L.append("")
    L.append("| # | Workspace | Title | State | Topic | Key contacts | Session ID | Notes |")
    L.append("|---|---|---|---|---|---|---|---|")

    seen = set()
    for i, ws in enumerate(workspaces, 1):
        key = norm(ws["title"])
        seen.add(key)
        d = durable.get(key, {})
        state = "running" if ws["busy"] else "idle"
        tty = ", ".join(ws["ttys"]) or "-"
        notes = d.get("notes", "")
        notes = ("%s; %s" % (tty, notes)) if notes else tty
        L.append("| %d | workspace:%d | %s | %s | %s | %s | %s | %s |" % (
            i, ws["num"], ws["title"] or "-", state,
            d.get("topic", "-") or "-", d.get("contacts", "-") or "-",
            d.get("session", "-") or "-", notes))

    closed = [d for k, d in sorted(durable.items()) if k not in seen]
    L.append("")
    L.append("## Not currently open")
    L.append("")
    if not closed:
        L.append("None. Every workspace with durable notes is open.")
    else:
        L.append("These have durable notes but no live workspace. Reopen before "
                 "delegating; do NOT guess a number for them.")
        L.append("")
        L.append("| Title | Topic | Key contacts | Session ID | Notes |")
        L.append("|---|---|---|---|---|")
        for d in closed:
            L.append("| %s | %s | %s | %s | %s |" % (
                d["title"], d["topic"], d["contacts"], d["session"], d["notes"]))
    L.append("")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the file is stale, change nothing")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--soft", action="store_true",
                    help="if cmux does not answer, keep the existing file and "
                         "exit 0 (for the scheduled job)")
    a = ap.parse_args()

    try:
        # cmux gives up on its own after about 15s when the socket is busy.
        # The scheduled job should not burn that every five minutes, so it
        # abandons the attempt sooner and keeps the file it already has.
        tree = read_tree(timeout=8 if a.soft else 25)
    except TreeUnavailable as exc:
        # Keep the last good registry rather than truncating it. A slightly
        # stale table is recoverable; an empty one silently breaks every lookup
        # and every delegation that resolves a name to a workspace number.
        msg = "cmux did not answer (%s). registry.md left as it was." % exc
        if a.soft:
            print(msg)
            return 0
        print(msg, file=sys.stderr)
        return 2

    text = build(tree, read_durable())
    old = OUT.read_text() if OUT.exists() else ""

    if a.check:
        if text != old:
            print("registry.md is stale")
            return 1
        print("registry.md is current")
        return 0

    if text != old:
        OUT.write_text(text)
        if not a.quiet:
            print("registry.md refreshed (%d workspaces)" % text.count("| workspace:"))
    elif not a.quiet:
        print("registry.md already current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
