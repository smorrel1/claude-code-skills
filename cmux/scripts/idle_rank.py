#!/usr/bin/env python3
"""Rank cmux panels by how long their Claude has been idle.

Delegation used to pick a target by topic ownership alone, which repeatedly
landed work on a session that was mid-task on something else. Stephen's rule
(30 Sep 2026): prefer a session idle for the last few hours, avoid clashing
with live subjects, and ask when in doubt.

Idleness is the timestamp on the LAST ENTRY inside the Claude transcript bound
to the panel (`terminal.agent.sessionId` in the cmux state file -> the matching
~/.claude/projects/*/<sessionId>.jsonl). Not the file's mtime: a bulk
`restore_bindings.py` pass rewrites every transcript, so on 30 Sep 2026 sixty-one
sessions all read as exactly 54h idle off mtime while their real last turns ran
anywhere from 14 to 25 Sep. mtime is only the fallback when no timestamp parses.

Busy is read off the panel's screen: "esc to interrupt" is the only reliable
marker. The braille spinner in a cmux label is not, because cmux paints it into
the workspace TITLE rather than the surface label, and some titles contain one
already. A read-screen costs about 0.14s, so every candidate is checked by
default; `--fast` skips it and ranks on idleness alone.

Everything is resolved from `cmux tree --all` at call time. Workspace numbers
drift on every reorder (a brief for a grants session landed in a finance session on
29 Sep 2026 off a cached number), so the ref printed here is only good for the
next few seconds: pipe it straight into send_task.py, never into a note.

    idle_rank.py                      # all panels, idlest first
    idle_rank.py --min-idle 2         # only 2h+ idle
    idle_rank.py --match grant deck   # only workspaces whose title matches
    idle_rank.py --top 5              # just the five idlest
    idle_rank.py --fast               # skip the busy screen check
    idle_rank.py --json
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from glob import glob
from pathlib import Path

CMUX = "/Applications/cmux.app/Contents/Resources/bin/cmux"
STATE = os.path.expanduser(
    "~/Library/Application Support/cmux/session-com.cmuxterm.app.json")
PROJECTS = os.path.expanduser("~/.claude/projects")

WS_RE = re.compile(r'workspace workspace:(\d+)\s+"([^"]*)"')
PANE_RE = re.compile(r'pane pane:(\d+)')
SURF_RE = re.compile(r'surface surface:(\d+)\s+\[(\w+)\]\s+"([^"]*)"')
TTY_RE = re.compile(r'tty=(\S+)')

# cmux paints one of these braille frames as the first character of a surface
# label while that surface's agent is working. "✳" is the resting glyph.
SPINNER = set("⠀⠁⠂⠃⠄⠅⠆⠇⠈⠉⠊⠋⠌⠍⠎⠏⠐⠑⠒⠓"
              "⠔⠕⠖⠗⠘⠙⠚⠛⠦⠧⠶⠷⠻⠼⠽⠾⠿")


def tree():
    """Live workspace -> pane -> surface layout, in cmux queue order."""
    try:
        r = subprocess.run([CMUX, "tree", "--all"], capture_output=True,
                           text=True, timeout=25)
    except (OSError, subprocess.TimeoutExpired) as exc:
        sys.exit("cmux tree did not answer (%s). It congests while sessions are "
                 "busy; retry in a minute rather than using a cached number." % exc)
    if r.returncode != 0:
        sys.exit("cmux tree exit %d: %s" % (r.returncode, r.stderr.strip()[:200]))

    out, ws, pane = [], None, None
    for line in r.stdout.splitlines():
        m = WS_RE.search(line)
        if m:
            ws = {"num": int(m.group(1)), "title": m.group(2), "surfaces": []}
            out.append(ws)
            pane = None
            continue
        if ws is None:
            continue
        p = PANE_RE.search(line)
        if p:
            pane = int(p.group(1))
        s = SURF_RE.search(line)
        if s:
            t = TTY_RE.search(line)
            ws["surfaces"].append({
                "surface": int(s.group(1)), "pane": pane,
                "kind": s.group(2), "label": s.group(3),
                "tty": t.group(1) if t else None,
                "focused": "[focused]" in line or "◀ active" in line,
                "spinner": s.group(3)[:1] in SPINNER,
            })
    return out


def state_panels():
    """customTitle -> [panel dicts], in layout order, from the cmux state file."""
    try:
        wss = json.load(open(STATE))["windows"][0]["tabManager"]["workspaces"]
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print("warning: cmux state file unreadable (%s); no session ids, so no "
              "idleness ranking." % exc, file=sys.stderr)
        return []
    out = []
    for w in wss:
        panels = []
        for pn in w.get("panels", []):
            agent = (pn.get("terminal") or {}).get("agent") or {}
            panels.append({
                "id": pn.get("id"),
                "tty": (pn.get("ttyName") or "").split("/")[-1] or None,
                "title": pn.get("title"),
                "session": agent.get("sessionId"),
                "cwd": pn.get("directory") or agent.get("workingDirectory"),
                "focused": pn.get("id") == w.get("focusedPanelId"),
            })
        out.append({"title": w.get("customTitle") or "", "panels": panels})
    return out


TS_RE = re.compile(rb'"timestamp":"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+)Z"')
TAIL = 65536


def last_turn(path):
    """Epoch of the last entry in a transcript, from the file's own timestamps.

    Falls back to mtime only when nothing parses, and says which it used, because
    mtime lies after a bulk restore.
    """
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - TAIL))
            found = TS_RE.findall(fh.read())
        if found:
            iso = found[-1].decode()
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
            return dt.timestamp(), "turn"
        return os.path.getmtime(path), "mtime"
    except (OSError, ValueError):
        return None, None


def transcripts():
    """sessionId -> (epoch of last turn, source), across every project dir."""
    idx = {}
    for path in glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        sid = Path(path).stem
        when, src = last_turn(path)
        if when is None:
            continue
        if when > idx.get(sid, (0, ""))[0]:
            idx[sid] = (when, src)
    return idx


def norm(t):
    t = re.sub(r"^[^0-9A-Za-z]+", "", t or "").strip().lower()
    return re.sub(r"\s+", " ", t)


def bind(surfaces, panels):
    """Match tree surfaces to state panels: by tty, then title, then position.

    A workspace with two panes can hold one busy Claude and one idle one, so the
    surface ref matters: a send addressed to the workspace lands in its focused
    pane, which may be the wrong Claude.
    """
    left, taken = list(panels), set()
    for s in surfaces:
        hit = None
        if s["tty"]:
            hit = next((p for i, p in enumerate(left)
                        if i not in taken and p["tty"] == s["tty"]), None)
        if hit is None:
            hit = next((p for i, p in enumerate(left)
                        if i not in taken and norm(p["title"]) == norm(s["label"])), None)
        if hit is None:
            hit = next((p for i, p in enumerate(left) if i not in taken), None)
        if hit is not None:
            taken.add(left.index(hit))
        s["panel"] = hit or {}
    return surfaces


def screen_busy(ws, surface):
    try:
        r = subprocess.run([CMUX, "read-screen", "--workspace", "workspace:%d" % ws,
                            "--surface", "surface:%d" % surface, "--lines", "12"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return "esc to interrupt" in (r.stdout or "")


def collect():
    stamp = time.time()
    tr, st, tx = tree(), state_panels(), transcripts()
    by_title = {}
    for w in st:
        by_title.setdefault(norm(w["title"]), []).append(w)

    rows = []
    for order, w in enumerate(tr):
        cand = by_title.get(norm(w["title"]), [])
        panels = cand.pop(0)["panels"] if cand else []
        for s in bind(w["surfaces"], panels):
            if s["kind"] != "terminal":
                continue
            sid = s["panel"].get("session")
            mt, src = tx.get(sid, (None, None)) if sid else (None, None)
            rows.append({
                "workspace": w["title"],
                "workspace_ref": "workspace:%d" % w["num"],
                "surface_ref": "surface:%d" % s["surface"],
                "pane_ref": "pane:%s" % s["pane"],
                "order": order,
                "session": (sid or "")[:8] or None,
                "session_full": sid,
                "idle_hours": None if not mt else round((stamp - mt) / 3600.0, 1),
                "idle_source": src,
                "busy": bool(s["spinner"]),
                "busy_source": "label" if s["spinner"] else "unchecked",
                "focused": s["focused"] or s["panel"].get("focused", False),
                "cwd": s["panel"].get("cwd"),
                "label": s["label"],
                "panes_in_workspace": len(w["surfaces"]),
            })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-idle", type=float, default=0.0,
                    help="only panels idle at least this many hours")
    ap.add_argument("--match", nargs="*", default=[],
                    help="only workspaces whose title contains any of these")
    ap.add_argument("--fast", action="store_true",
                    help="skip the per-panel busy screen check (~0.14s each)")
    ap.add_argument("--top", type=int, default=0, metavar="N",
                    help="print only the N idlest rows")
    ap.add_argument("--all", action="store_true",
                    help="include busy panels and panels with no transcript")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rows = collect()
    if a.match:
        pats = [m.lower() for m in a.match]
        rows = [r for r in rows if any(p in r["workspace"].lower() for p in pats)]
    rows = [r for r in rows
            if r["idle_hours"] is None or r["idle_hours"] >= a.min_idle]
    if not a.all:
        rows = [r for r in rows if r["idle_hours"] is not None]

    if not a.fast:
        for r in rows:
            b = screen_busy(int(r["workspace_ref"].split(":")[1]),
                            int(r["surface_ref"].split(":")[1]))
            if b is not None:
                r["busy"], r["busy_source"] = b, "screen"
    if not a.all:
        rows = [r for r in rows if not r["busy"]]
    rows.sort(key=lambda r: (r["busy"], -1e9 if r["idle_hours"] is None
                             else -r["idle_hours"]))
    if a.top:
        rows = rows[:a.top]

    if a.json:
        print(json.dumps(rows, indent=1))
        return 0

    print("%-7s %-5s %-38s %-13s %-10s %-8s %-5s %s" %
          ("IDLE", "BUSY", "WORKSPACE", "WS REF", "SURFACE", "SESSION",
           "PANES", "CWD"))
    for r in rows:
        print("%-7s %-5s %-38s %-13s %-10s %-8s %-5s %s" % (
            "?" if r["idle_hours"] is None else ("%.1fh" % r["idle_hours"]),
            "yes" if r["busy"] else "no",
            r["workspace"][:38],
            r["workspace_ref"],
            r["surface_ref"],
            r["session"] or "-",
            r["panes_in_workspace"],
            (r["cwd"] or "").replace(os.path.expanduser("~"), "~")[-42:]))
    if not rows:
        print("(nothing matched; try --all)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
