#!/usr/bin/env python3
"""Find cmux panels that have fallen back to a bare shell, and restart Claude.

After a cmux relaunch a workspace can come back as a plain zsh prompt with no
Claude attached, while cmux still records which session the panel should hold.
The panel looks alive, so a brief sent there is typed into the shell, which
answers "zsh: no matches found: (marker ...)" and the work is silently lost. A
session-to-session request to 'demo.elaitra zip' disappeared that way on 19 Oct.

cmux's own `cmux restore claude <id>` is the documented cure and it times out:
dead panels across 16 to 20 Oct still carry the words "Error: Command timed
out" on screen. Typing `claude --resume <id>` in the panel worked every time,
so that is what this does.

    check_dead_sessions.py                 report only
    check_dead_sessions.py --apply         revive what is safe to revive
    check_dead_sessions.py --lost-briefs   list briefs that landed in a shell
    check_dead_sessions.py --json          machine-readable, for other scripts

Verdicts:
  OK               Claude is running and bound to the panel it should be in.
  DEAD             a shell prompt, no Claude. Revivable.
  ASLEEP           cmux has not materialised the surface since its relaunch.
                   Not broken, and not ours to poke: viewing it wakes it.
  DUPLICATE        the session already runs in another panel. Reported, never
                   started a second time and never closed. Stephen's call.
  NO TRANSCRIPT    the conversation is gone, so --resume has nothing to open.

Never uses `claude --continue`, which forks a fresh copy of the wrong session.
Never closes, merges or touches a panel that is running.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from restart_sessions import CMUX, cmux, wanted, running, transcripts  # noqa: E402

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(SKILL, "state")
LOG = os.path.join(STATE_DIR, "dead-sessions.log")
TASKS = os.path.join(STATE_DIR, "tasks")

# A shell prompt on the last line. oh-my-zsh prints "(base) ➜  dirname" with
# the glyph in the MIDDLE and the directory last, so anchoring to the end of
# the line finds nothing: match the glyph wherever it sits.
# Deliberately NOT "❯": that is Claude's own empty input box as well as some
# shells' prompt, so matching it marks every idle Claude pane dead. Caught by
# tests/test_send_task.py on 20 Oct 2026, which drives an idle pane showing
# exactly "❯ ". The real dead panels here wear oh-my-zsh's "(base) ➜ dir".
PROMPT = re.compile(r"(?:➜|\(base\)|\$\s|%\s|#\s)")
# Claude's own furniture. Any of these means the pane is Claude's, not a shell.
# Claude's own furniture. "auto mode on" and the mode indicator sit in the
# status line of every running pane, which the box-drawing characters alone
# do not catch. Note "❯" is Claude's input marker too, not only a shell
# prompt, so this list is always consulted BEFORE the prompt test.
CLAUDE_UI = ("esc to interrupt", "? for shortcuts", "Welcome back", "│",
             "╭", "╰", "Context left", "bypass permissions",
             "auto mode on", "shift+tab to cycle", "⏵⏵", "────")
NO_SURFACE = ("Failed to read terminal text", "surface not found",
              "Terminal surface not found")
# What a brief looks like when the shell, not Claude, received it.
SWALLOWED = re.compile(r"zsh: no matches found|command not found: Task|"
                       r"zsh: parse error|no matches found: \(marker")


def screen(panel, lines=14):
    return cmux("read-screen", "--surface", panel, "--lines", str(lines))


def classify(text):
    """What is this panel showing?"""
    if not text.strip() or any(x in text for x in NO_SURFACE):
        return "ASLEEP"
    if any(x in text for x in CLAUDE_UI):
        return "OK"
    tail = [ln for ln in text.rstrip().split("\n") if ln.strip()]
    if tail and PROMPT.search(tail[-1]):
        return "DEAD"
    return "UNCLEAR"


def looks_like_shell(panel):
    """True when the panel is sitting at a shell prompt. Used by send_task."""
    return classify(screen(panel)) == "DEAD"


def survey():
    """One pass over every bound panel. Returns a list of rows."""
    want, run, tx = wanted(), running(), transcripts()
    where = {}
    for panel, sid in run.items():
        where.setdefault(sid, []).append(panel)

    rows = []
    for panel, w in sorted(want.items(), key=lambda kv: kv[1]["title"]):
        sid, title = w["session"], w["title"]
        if run.get(panel) == sid:
            rows.append(dict(verdict="OK", title=title, session=sid,
                             panel=panel, cwd=w["cwd"], note=""))
            continue

        text = screen(panel)
        state = classify(text)
        note = ""
        if state == "DEAD":
            if where.get(sid):
                others = [want.get(p, {}).get("title", "an unbound panel")
                          for p in where[sid]]
                state, note = "DUPLICATE", "already running in: " + ", ".join(others)
            elif sid not in tx:
                state, note = "NO TRANSCRIPT", "transcript deleted, cannot resume"
            elif "Command timed out" in text:
                note = "cmux restore timed out here"
        if SWALLOWED.search(text):
            note = (note + "; " if note else "") + "a brief was typed into the shell"
        rows.append(dict(verdict=state, title=title, session=sid, panel=panel,
                         cwd=w["cwd"], note=note,
                         swallowed=bool(SWALLOWED.search(text))))
    return rows


def revive(row, wait=75):
    """Type `claude --resume <id>` into the dead panel and check it took.

    Resuming a long conversation can take the better part of a minute, so
    poll rather than sleep once: a single 12 second check called five healthy
    revivals failures on 20 Oct 2026.
    """
    panel, sid, cwd = row["panel"], row["session"], row["cwd"]
    # One line, quoted path: these cwds live under Dropbox and carry spaces.
    cmd = 'cd "%s" && claude --resume %s' % (cwd, sid) if cwd else \
          'claude --resume %s' % sid
    cmux("send", "--surface", panel, cmd)
    cmux("send-key", "--surface", panel, "Enter")
    deadline = time.time() + wait
    while time.time() < deadline:
        time.sleep(5)
        after = screen(panel, 20)
        if any(x in after for x in CLAUDE_UI):
            return True, "Claude is back"
        if "No conversation found" in after:
            return False, "resume refused: no such conversation"
    return False, "no Claude prompt after %ds" % wait


def lost_briefs(days=5):
    """Briefs that landed in a shell, from the panels and the task files.

    Two sources: what is still on a dead panel's screen, and brief files in
    state/tasks written in the window, whose marker never reached a session.
    """
    found = []
    for row in survey():
        if row.get("swallowed"):
            text = screen(row["panel"], 40)
            for m in re.finditer(r"marker[:\s]+([0-9a-z-]+)", text):
                found.append({"target": row["title"], "marker": m.group(1),
                              "source": "on screen in a dead shell"})
    # A brief that arrived leaves its marker in the receiving session's
    # transcript, which is how send_task confirms delivery. So a recent brief
    # whose marker appears in NO transcript never reached a Claude: either it
    # was typed into a shell, or it was never submitted. Listing every brief
    # file instead, as the first cut did, just prints the whole spool.
    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    for name in (sorted(os.listdir(TASKS)) if os.path.isdir(TASKS) else []):
        path = os.path.join(TASKS, name)
        try:
            if datetime.fromtimestamp(os.path.getmtime(path)) < cutoff:
                continue
        except OSError:
            continue
        marker = name.replace("-brief.md", "")
        recent.append((name, path, marker))

    if recent:
        # Only transcripts touched since the oldest brief can contain these
        # markers, and that cuts the search from every transcript ever (tens
        # of gigabytes, which times out) to the handful that matter.
        files = subprocess.run(
            ["find", os.path.expanduser("~/.claude/projects"), "-name", "*.jsonl",
             "-mtime", "-%d" % (days + 1)],
            capture_output=True, text=True, timeout=120).stdout.split("\n")
        files = [f for f in files if f.strip()]
        seen = set()
        for i in range(0, len(files), 200):           # keep the argv short
            grep = subprocess.run(
                ["grep", "-hoF"] + sum([["-e", m] for _, _, m in recent], [])
                + files[i:i + 200],
                capture_output=True, text=True, timeout=300)
            seen.update(grep.stdout.split())
        for name, path, marker in recent:
            if marker in seen:
                continue
            when = datetime.fromtimestamp(os.path.getmtime(path))
            found.append({"target": "(never arrived)", "marker": marker,
                          "source": "%s, written %s" % (name, when.strftime("%a %d %b %H:%M"))})
    return found


def log(line):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(LOG, "a") as f:
        f.write("%s  %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), line))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="revive the DEAD panels")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lost-briefs", action="store_true",
                    help="list briefs that were typed into a shell")
    ap.add_argument("--quiet", action="store_true",
                    help="print nothing unless something was revived or failed")
    a = ap.parse_args()

    if a.lost_briefs:
        items = lost_briefs()
        print(json.dumps(items, indent=1) if a.json else
              "\n".join("%-44s %-36s %s" % (x["target"][:44], x["marker"], x["source"])
                        for x in items) or "nothing swallowed in the window")
        return 0

    rows = survey()
    revived, failed = [], []
    if a.apply:
        for row in rows:
            if row["verdict"] != "DEAD":
                continue
            ok, why = revive(row)
            (revived if ok else failed).append((row["title"], why))
            row["verdict"] = "REVIVED" if ok else "REVIVE FAILED"
            row["note"] = why
            log("%s %s %s (%s)" % ("revived" if ok else "FAILED",
                                   row["title"], row["session"][:8], why))

    if a.json:
        print(json.dumps(rows, indent=1))
        return 0

    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    interesting = [r for r in rows if r["verdict"] != "OK"]

    if not a.quiet or revived or failed:
        width = max((len(r["title"]) for r in interesting), default=20)
        for r in sorted(interesting, key=lambda r: (r["verdict"], r["title"])):
            print("%-14s %-*s  %s  %s" % (r["verdict"], width, r["title"][:width],
                                          r["session"][:8], r["note"]))
        print("\n" + ", ".join("%s %d" % (k, v) for k, v in sorted(counts.items())))

    log("checked %d panels: %s%s" % (
        len(rows), ", ".join("%s %d" % (k, v) for k, v in sorted(counts.items())),
        "" if not a.apply else " | revived %d, failed %d" % (len(revived), len(failed))))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
