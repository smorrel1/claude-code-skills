#!/usr/bin/env python3
"""Verify, and where safe restore, every Claude Code session in cmux, by SESSION ID.

Never "the newest conversation in this directory". Many workspaces share a cwd
(one shared documents folder above all), so anything directory-based attaches the wrong
conversation. On 9 Sep 2026 bare `claude --continue` did exactly that and bound
seven conversations into two workspaces each.

Ground truth, both sources written by the tools themselves, no screen scraping:

  WANTED   cmux's state file records, per terminal panel, the Claude sessionId it
           should resume (terminal.agent.sessionId, with a resumeBinding that runs
           `claude --resume <id>`). Present from cmux 0.64.x; the older build
           recorded no session ids at all.
  RUNNING  Claude Code writes ~/.claude/sessions/<pid>.json with the sessionId that
           process really is. The process environment carries CMUX_PANEL_ID, which
           ties it to one panel.

Each bound panel lands in exactly one bucket:

  CORRECT       the process in this panel is the session bound to it.
  NOT RUNNING   bound, transcript on disk, no process anywhere. Restorable: the
                script types `cmux restore claude <id>` into that panel, which is
                cmux's own resume command and refuses to start a second copy.
  HELD ELSEWHERE  the session runs in a DIFFERENT panel. Never started here, since
                that is precisely the collision. Reported with the holder's name.
  WRONG SESSION a different session runs in this panel. Reported, never touched.
  NO TRANSCRIPT the transcript is deleted, so it cannot be resumed. Reported.

cmux 0.64.23 already auto-resumes by session id on relaunch, so after a restart the
normal result is all CORRECT and this script is a verifier. It only acts on NOT
RUNNING, and only with --apply.

    restart_sessions.py            report only
    restart_sessions.py --apply    also restore NOT RUNNING panels
"""
import argparse
import glob
import json
import os
import re
import subprocess
import time
from collections import Counter

CMUX = "/Applications/cmux.app/Contents/Resources/bin/cmux"
STATE = os.path.expanduser("~/Library/Application Support/cmux/session-com.cmuxterm.app.json")
PREV = STATE.replace(".json", "-previous.json")  # cmux's copy of the state before the last relaunch
SESSIONS = os.path.expanduser("~/.claude/sessions")
PROJECTS = os.path.expanduser("~/.claude/projects")


def cmux(*args, timeout=20):
    try:
        p = subprocess.run([CMUX, *args], capture_output=True, text=True, timeout=timeout)
        return p.stdout + p.stderr
    except (subprocess.TimeoutExpired, OSError):
        return ""


def wanted(path=STATE):
    """panel id -> {title, session, cwd} from cmux's state file."""
    out = {}
    data = json.load(open(path))
    for w in data.get("windows", []):
        for ws in w.get("tabManager", {}).get("workspaces", []):
            title = ws.get("customTitle") or ws.get("title") or ws.get("processTitle") or "(untitled)"
            for p in ws.get("panels", []):
                t = p.get("terminal") or {}
                a = t.get("agent") or {}
                if a.get("kind", "claude") != "claude" or not a.get("sessionId"):
                    continue
                out[str(p.get("id", "")).upper()] = {
                    "title": title, "session": a["sessionId"],
                    "cwd": a.get("workingDirectory") or t.get("workingDirectory")}
    return out


def running():
    """panel id -> session id, from live processes' own session records."""
    out = {}
    for f in glob.glob(os.path.join(SESSIONS, "*.json")):
        try:
            rec = json.load(open(f))
            pid = int(rec["pid"])
            os.kill(pid, 0)  # alive?
        except (ValueError, KeyError, OSError, json.JSONDecodeError):
            continue
        env = subprocess.run(["ps", "eww", "-p", str(pid)], capture_output=True, text=True).stdout
        m = re.search(r"CMUX_PANEL_ID=([0-9A-Fa-f-]{36})", env)
        if m:
            out[m.group(1).upper()] = rec.get("sessionId")
    return out


def transcripts():
    return {os.path.basename(f)[:-6] for f in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl"))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="restore NOT RUNNING panels")
    a = ap.parse_args()

    want, run, tx = wanted(), running(), transcripts()
    try:
        prev = wanted(PREV)
    except (OSError, ValueError):
        prev = {}
    where = {}
    for panel, sid in run.items():
        where.setdefault(sid, []).append(panel)

    rows = []
    for panel, w in want.items():
        sid = w["session"]
        here = run.get(panel)
        if here == sid:
            v, note = "CORRECT", ""
        elif here:
            owner = [x["title"] for x in want.values() if x["session"] == here]
            v, note = "WRONG SESSION", "running %s (bound to: %s)" % (here[:8], ", ".join(owner) or "nothing")
        elif where.get(sid):
            v, note = "HELD ELSEWHERE", "running in: " + ", ".join(
                want.get(p, {}).get("title", "unbound panel") for p in where[sid])
        elif sid not in tx:
            v, note = "NO TRANSCRIPT", "cannot resume, transcript deleted"
        else:
            v, note = "NOT RUNNING", ""
        rows.append((v, w["title"], sid, panel, note))

    # A session bound to TWO panels before the relaunch (fork leftovers from bare
    # `claude --continue`, 9 Sep 2026) resumes in only one of them; the other panel
    # silently loses its binding, so it never appears in `want` and the report above
    # says "all CORRECT". Compare with the pre-relaunch state to surface those.
    for panel, w in prev.items():
        if panel in want and want[panel]["session"] == w["session"]:
            continue
        holders = [want[p]["title"] for p in where.get(w["session"], []) if p in want]
        run_here = run.get(panel)
        if run_here and run_here != w["session"]:
            note = "now running a FRESH session %s here; %s" % (run_here[:8],
                   ("conversation lives in: " + ", ".join(holders)) if holders else "conversation not running anywhere")
        elif holders:
            note = "binding dropped at relaunch; conversation lives in: " + ", ".join(holders)
        elif w["session"] not in tx:
            note = "binding dropped at relaunch; transcript deleted, cannot resume"
        else:
            note = "binding dropped at relaunch; not running anywhere (cmux restore claude <id> in this panel)"
        if panel in want:  # rebound to a different (fresh) session at relaunch
            note = "REBOUND to fresh session %s at relaunch; original conversation %s" % (
                want[panel]["session"][:8], ("lives in: " + ", ".join(holders)) if holders else "not running anywhere")
        rows.append(("LOST BINDING", w["title"], w["session"], panel, note))

    dup = Counter(w["session"] for w in want.values())
    for panel, w in want.items():
        if dup[w["session"]] > 1:
            others = [x["title"] for p, x in want.items() if p != panel and x["session"] == w["session"]]
            rows.append(("DOUBLE BOUND", w["title"], w["session"], panel,
                         "also bound in: %s (next relaunch keeps only one; close the twin first)" % ", ".join(others)))

    order = ["LOST BINDING", "DOUBLE BOUND", "NOT RUNNING", "HELD ELSEWHERE", "WRONG SESSION", "NO TRANSCRIPT", "CORRECT"]
    rows.sort(key=lambda r: (order.index(r[0]), r[1]))
    width = max((len(r[1]) for r in rows), default=20)
    for v, title, sid, panel, note in rows:
        if v == "CORRECT":
            continue
        print("%-15s %-*s  %s  %s" % (v, width, title, sid[:8], note))

    restored = 0
    for v, title, sid, panel, note in rows:
        if v != "NOT RUNNING" or not a.apply:
            continue
        # cmux's own resume, typed into that panel's shell. cmux itself refuses to
        # start a copy that is already running anywhere, so this cannot collide.
        cmux("send", "--surface", panel, "cmux restore claude %s" % sid)
        cmux("send-key", "--surface", panel, "Enter")
        restored += 1
        time.sleep(2)

    c = Counter(r[0] for r in rows)
    print("\n%d bound Claude session(s): %s" % (len(rows), ", ".join(
        "%s %d" % (k, c[k]) for k in order if c[k])))
    if c["NOT RUNNING"] and not a.apply:
        print("Re-run with --apply to restore the NOT RUNNING ones by session id.")
    if restored:
        print("Restore issued for %d panel(s). Re-run without --apply in ~30s to confirm." % restored)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
