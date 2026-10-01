#!/usr/bin/env python3
"""Bulk-restore Claude sessions into their cmux panels after a bad relaunch.

Extends restart_sessions.py: that script's --apply only fixes NOT RUNNING panels
(still bound in the CURRENT state file). After a relaunch that DROPS bindings
(seen 17 Sep 2026: 67 of 76 bindings lost), the current state no longer knows
what belonged where; only session-com.cmuxterm.app-previous.json does. This
script restores those LOST BINDING panels too, by session id, never by cwd.

Safety properties:
  - Only acts on a panel that exists in the current state AND has no current
    agent binding AND whose previous session is not running anywhere AND whose
    transcript exists. Everything else is reported, never touched.
  - A session previously bound to TWO panels is restored only where --pick
    says (sid8=panel-id-prefix or sid8=title-substring); otherwise skipped and
    reported. Restoring the same conversation twice caused the 9/16 Sep messes.
  - Uses cmux's own `cmux restore claude <id>` typed into the panel, which
    refuses to start a copy already running elsewhere, so it cannot collide.
  - If a send fails because the panel's surface is not materialized (workspace
    not viewed since relaunch), it select-workspaces it into existence, waits,
    and retries once.

Usage:
    restore_bindings.py                 dry-run: print the plan
    restore_bindings.py --apply         execute
    restore_bindings.py --apply --pick 0fd5f37d="Partner negotiation" ...
    restore_bindings.py --apply --delay 3 --limit 10
"""
import argparse
import re
import subprocess
import sys
import time

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from restart_sessions import CMUX, PREV, STATE, cmux, running, transcripts, wanted  # noqa: E402


def workspace_ref_by_title(title):
    """Map a workspace title to its current cmux ref via tree --all."""
    out = cmux("tree", "--all")
    for line in out.splitlines():
        m = re.search(r"(workspace:\d+)\s+(.*)", line)
        if m and title.strip() in m.group(2):
            return m.group(1)
    return None


def send_restore(panel, sid, title):
    r = cmux("send", "--surface", panel, "cmux restore claude %s" % sid)
    if "not found" in r.lower():
        ref = workspace_ref_by_title(title)
        if not ref:
            return "FAILED: surface not materialized and workspace %r not in tree" % title
        cmux("select-workspace", "--workspace", ref)
        time.sleep(4)
        r = cmux("send", "--surface", panel, "cmux restore claude %s" % sid)
        if "not found" in r.lower():
            return "FAILED: surface still not found after select-workspace %s" % ref
    time.sleep(0.7)
    cmux("send-key", "--surface", panel, "Enter")
    return "restore issued"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--pick", action="append", default=[],
                    help='sid8="panel-id-prefix or title substring" for duplicate sessions')
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    picks = dict(p.split("=", 1) for p in a.pick)

    cur, run, tx = wanted(), running(), transcripts()
    try:
        prev = wanted(PREV)
    except (OSError, ValueError):
        prev = {}
    live_sids = set(run.values())

    # All panels present in the current cmux, bound or not (a LOST BINDING
    # panel has no agent entry, so wanted() misses it; walk the raw file).
    import json, os  # noqa: E401
    cur_panels = {}
    data = json.load(open(STATE))
    for w in data.get("windows", []):
        for ws in w.get("tabManager", {}).get("workspaces", []):
            t = ws.get("customTitle") or ws.get("title") or ws.get("processTitle") or "(untitled)"
            for p in ws.get("panels", []):
                if (p.get("terminal") or {}) != {} or "terminal" in p:
                    cur_panels[str(p.get("id", "")).upper()] = t

    # Candidates: NOT RUNNING (current binding, no process) + LOST BINDING
    # (previous binding, panel now unbound).
    cands = []
    for panel, w in cur.items():
        if run.get(panel) is None and w["session"] not in live_sids and w["session"] in tx:
            cands.append((panel, w["session"], w["title"], "not-running"))
    bound_now = set(cur)
    for panel, w in prev.items():
        sid = w["session"]
        if panel in bound_now or panel not in cur_panels:
            continue  # rebound to something else, or panel gone
        if run.get(panel):
            continue  # a process (fresh session) occupies it
        if sid in live_sids:
            continue  # conversation already running elsewhere; human decision
        if sid not in tx:
            continue  # transcript deleted
        cands.append((panel, sid, cur_panels[panel], "lost-binding"))

    # Duplicate sessions across candidate panels -> --pick or skip.
    by_sid = {}
    for c in cands:
        by_sid.setdefault(c[1], []).append(c)
    plan, skipped = [], []
    for sid, group in by_sid.items():
        if len(group) == 1:
            plan.append(group[0])
            continue
        want8 = picks.get(sid[:8])
        chosen = [c for c in group if want8 and (c[0].startswith(want8.upper()) or want8 in c[2])]
        if len(chosen) == 1:
            plan.append(chosen[0])
            skipped += [("duplicate, lost to pick", c) for c in group if c != chosen[0]]
        else:
            skipped += [("duplicate, no/ambiguous --pick %s" % sid[:8], c) for c in group]
    if a.limit:
        plan, deferred = plan[: a.limit], plan[a.limit:]
        skipped += [("beyond --limit", c) for c in deferred]

    plan.sort(key=lambda c: c[2].lower())
    for panel, sid, title, kind in plan:
        if not a.apply:
            print("PLAN  %-14s %-60s %s" % (kind, title[:60], sid[:8]))
            continue
        res = send_restore(panel, sid, title)
        print("%-8s %-60s %s  %s" % ("OK" if res == "restore issued" else "FAIL", title[:60], sid[:8], res))
        time.sleep(a.delay)
    for why, (panel, sid, title, kind) in skipped:
        print("SKIP  %-60s %s  %s" % (title[:60], sid[:8], why))
    print("\n%d planned, %d skipped.%s" % (len(plan), len(skipped),
          "" if a.apply else "  Re-run with --apply to execute."))
    if a.apply and plan:
        print("Verify in ~60s:  python3 restart_sessions.py")


if __name__ == "__main__":
    main()
