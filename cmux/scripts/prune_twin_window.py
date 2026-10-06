#!/usr/bin/env python3
"""Clear the duplicate window a cmux relaunch can leave behind.

A relaunch sometimes restores the saved window AND rebuilds another for the
resumed sessions. The rebuilt one holds the live sessions; the restored one
holds bare shells printing "This agent session is already running in process N",
and every session ends up bound to two panels. On 6 Oct 2026 that was 74
duplicate workspaces and 142 double bindings.

    prune_twin_window.py --window window:2            dry run, changes nothing
    prune_twin_window.py --window window:2 --apply    close the proven twins

Every workspace must pass ALL of these before it is closed:

  1. Its screen, read at that moment, shows no running Claude (no "esc to
     interrupt", no spinner, no auto-mode footer).
  2. Its screen POSITIVELY looks like a shell prompt. An unreadable or blank
     screen is never treated as safe: a surface that is not materialised reads
     as empty, which would otherwise look exactly like a bare shell.
  3. No live claude process is bound to its panel, by CMUX_PANEL_ID.
  4. Every session id it carries is also bound in the window being kept, so
     closing this copy cannot orphan a conversation.

What it will NOT do, learned the hard way on 6 Oct:

  - It never closes a workspace holding a BROWSER pane. Several of them held
    pages opened by hand, which are content rather than duplication. Where a
    workspace mixes a duplicate terminal with browser panes, only the terminal
    pane is closed, with --apply, and the workspace is left for you to move.
  - It never closes the last surface in a workspace: cmux refuses, then spawns
    a fresh shell, which looks like the job failed.
  - Anything it cannot prove is reported and left alone.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

CMUX = "/Applications/cmux.app/Contents/Resources/bin/cmux"
SESSIONS = os.path.expanduser("~/.claude/sessions")
STATE = os.path.expanduser(
    "~/Library/Application Support/cmux/session-com.cmuxterm.app.json")
RUNNING = ("esc to interrupt", "⏵⏵", "✻", "✢", "⏺")
SHELLISH = ("➜", "$ ", "Last login", "already running in process", "(base)", "% ")


def cmux(*args, timeout=30):
    try:
        p = subprocess.run([CMUX, *args], capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.TimeoutExpired):
        return ""


def tree():
    """[(window, workspace_ref, title, [(surface_ref, kind)])] from the live tree."""
    rows, window, ws = [], None, None
    for line in cmux("tree", "--all").splitlines():
        m = re.search(r'window (window:\d+)', line)
        if m and 'workspace' not in line:
            window = m.group(1)
            continue
        m = re.search(r'workspace (workspace:\d+) "([^"]*)"', line)
        if m:
            ws = [window, m.group(1), m.group(2), []]
            rows.append(ws)
            continue
        m = re.search(r'surface (surface:\d+) \[(\w+)\]', line)
        if m and ws:
            ws[3].append((m.group(1), m.group(2)))
    return rows


def live_panels():
    """panel id -> pid, for every running Claude."""
    out = {}
    for f in glob.glob(os.path.join(SESSIONS, "*.json")):
        try:
            rec = json.load(open(f))
            pid = int(rec["pid"])
            os.kill(pid, 0)
        except (ValueError, KeyError, OSError, json.JSONDecodeError):
            continue
        env = subprocess.run(["ps", "eww", "-p", str(pid)],
                             capture_output=True, text=True).stdout
        m = re.search(r"CMUX_PANEL_ID=([0-9A-Fa-f-]{36})", env)
        if m:
            out[m.group(1).upper()] = pid
    return out


def state_bindings(keep_window_index=0):
    """(sessions bound in the window being kept, title -> [workspace dicts])."""
    try:
        d = json.load(open(STATE))
    except (OSError, ValueError):
        return set(), {}
    keep = set()
    for ws in d["windows"][keep_window_index]["tabManager"]["workspaces"]:
        for p in ws.get("panels", []):
            a = (p.get("terminal") or {}).get("agent") or {}
            if a.get("sessionId"):
                keep.add(a["sessionId"])
    by_title = {}
    for wi in range(len(d["windows"])):
        if wi == keep_window_index:
            continue
        for ws in d["windows"][wi]["tabManager"]["workspaces"]:
            t = ws.get("customTitle") or ws.get("processTitle") or "?"
            by_title.setdefault(t, []).append(ws)
    return keep, by_title


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", required=True, help="the duplicate window, e.g. window:2")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    panels = live_panels()

    # Refuse the window that holds the live sessions. Pointed at it, every test
    # passes for a bare shell whose session is bound in the same window, and it
    # proposed closing five of Stephen's own workspaces on 6 Oct 2026.
    rows = tree()
    live_per_window = {}
    for window, ref, _title, _surfaces in rows:
        scr = ""
        live_per_window.setdefault(window, 0)
    for f in glob.glob(os.path.join(SESSIONS, "*.json")):
        try:
            rec = json.load(open(f))
            os.kill(int(rec["pid"]), 0)
        except (ValueError, KeyError, OSError, json.JSONDecodeError):
            continue
    # Count live Claude panels per window from the tree's own titles: a window
    # whose workspaces are running Claude shows the markers on screen.
    busiest, best = None, -1
    for window in sorted({w for w, _r, _t, _s in rows}):
        n = sum(1 for w, r, _t, _s in rows if w == window
                and any(x in cmux("read-screen", "--workspace", r, "--lines", "6")
                        for x in RUNNING))
        live_per_window[window] = n
        if n > best:
            busiest, best = window, n
    if a.window == busiest and best > 0:
        sys.exit("Refusing: %s holds %d running Claude session(s), so it is the window\n"
                 "to KEEP, not the duplicate. Pass the other window."
                 % (a.window, best))
    if len(live_per_window) < 2:
        sys.exit("Refusing: there is only one window, so there is no duplicate to prune.")

    keep_sessions, by_title = state_bindings()
    closed = kept = panes = 0

    for window, ref, title, surfaces in tree():
        if window != a.window:
            continue
        why = []
        kinds = [k for _s, k in surfaces]
        scr = cmux("read-screen", "--workspace", ref, "--lines", "12")
        if any(s in scr for s in RUNNING):
            why.append("a Claude is running on this screen")
        if not any(s in scr for s in SHELLISH):
            why.append("screen does not read as a shell prompt")
        for ws in by_title.get(title, []):
            for p in ws.get("panels", []):
                if str(p.get("id", "")).upper() in panels:
                    why.append("live claude pid %s in this panel"
                               % panels[str(p.get("id", "")).upper()])
                sid = ((p.get("terminal") or {}).get("agent") or {}).get("sessionId")
                if sid and sid not in keep_sessions:
                    why.append("session %s is not bound in the window being kept" % sid[:8])

        if "browser" in kinds:
            # Browser panes are content. Close only a duplicate terminal pane
            # inside, and leave the workspace itself for a human to move.
            terms = [s for s, k in surfaces if k == "terminal"]
            print("BROWSER %-13s %-46s keeps %d browser pane(s)"
                  % (ref, title[:46], kinds.count("browser")))
            for s in terms:
                detail = cmux("read-screen", "--surface", s, "--lines", "8")
                if any(x in detail for x in RUNNING) or not any(x in detail for x in SHELLISH):
                    print("        keeping %s, it is not a bare shell" % s)
                    continue
                print("        duplicate terminal pane %s%s"
                      % (s, "" if a.apply else " (dry run)"))
                if a.apply:
                    cmux("close-surface", "--workspace", ref, "--surface", s)
                    panes += 1
                    time.sleep(0.4)
            kept += 1
            continue

        if why:
            kept += 1
            print("KEEP    %-13s %-46s %s" % (ref, title[:46], "; ".join(sorted(set(why)))[:60]))
            continue

        print("CLOSE   %-13s %s" % (ref, title[:60]))
        if a.apply:
            r = cmux("workspace", "close", "--workspace", ref)
            if "Pinned" in r:
                cmux("workspace-action", "--action", "unpin", "--workspace", ref)
                time.sleep(0.3)
                r = cmux("workspace", "close", "--workspace", ref)
            if "Error" in r:
                print("        FAILED: %s" % r.strip()[:80])
                continue
            time.sleep(0.4)
        closed += 1

    print("\n%d workspace(s) %s, %d kept, %d duplicate pane(s) %s."
          % (closed, "closed" if a.apply else "to close", kept, panes,
             "closed" if a.apply else "to close"))
    if not a.apply:
        print("Dry run. Re-run with --apply.")
    else:
        print("Move anything still in %s into the window you are keeping, then\n"
              "close it with: cmux close-window --window %s" % (a.window, a.window))
    return 0


if __name__ == "__main__":
    sys.exit(main())
