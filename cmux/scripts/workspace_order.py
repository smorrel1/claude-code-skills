#!/usr/bin/env python3
"""Keep the workspace order across a cmux relaunch.

cmux does not reliably restore the order. Measured on 6 Oct 2026: the saved
state held one window of 78 workspaces, and the relaunch produced two. One was
the old window with the order intact but only bare shells in it; the other held
all 79 live sessions in a different order, a median of 4 places out and one
workspace 50 places from where it had been. The order a person builds over
weeks, most-used at the top, is lost every restart.

So snapshot it from outside. Titles are the key, never numbers: refs are
assigned at runtime and drift on every reorder.

    workspace_order.py snapshot            record the current order (cheap, ~1s)
    workspace_order.py restore             show what would move, change nothing
    workspace_order.py restore --apply     put it back
    workspace_order.py list                show the snapshots held

The restore deliberately does NOT use the newest snapshot. The snapshot job
runs every 30 seconds, so by the time anyone notices a scrambled relaunch the
newest snapshot IS the scramble. It uses the newest one taken before cmux
started, which is the last good order from the previous run.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time

CMUX = "/Applications/cmux.app/Contents/Resources/bin/cmux"
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(SKILL, "state", "order")
KEEP = 40                      # snapshots retained, about 20 minutes at 30s
MIN_WORKSPACES = 5             # below this, assume cmux is still starting up


def cmux(*args, timeout=30):
    try:
        p = subprocess.run([CMUX, *args], capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.TimeoutExpired):
        return ""


def live_order():
    """[(window_ref, workspace_ref, title)] in the order cmux shows them."""
    out, window = [], None
    for line in cmux("tree", "--all").splitlines():
        m = re.search(r'window (window:\d+)', line)
        if m and 'workspace' not in line:
            window = m.group(1)
            continue
        m = re.search(r'workspace (workspace:\d+) "([^"]*)"', line)
        if m and window:
            out.append((window, m.group(1), m.group(2)))
    return out


def pinned_titles():
    """Titles cmux has pinned, read from its own state file."""
    state = os.path.expanduser(
        "~/Library/Application Support/cmux/session-com.cmuxterm.app.json")
    try:
        d = json.load(open(state))
    except (OSError, ValueError):
        return set()
    out = set()
    for w in d.get("windows", []):
        for ws in w.get("tabManager", {}).get("workspaces", []):
            if ws.get("isPinned"):
                t = ws.get("customTitle") or ws.get("processTitle")
                if t:
                    out.add(t)
    return out


def cmux_started_at():
    """When the running cmux started, or None. The snapshot cut-off."""
    try:
        ps = subprocess.run(["ps", "-axo", "pid,lstart,comm"],
                            capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in ps.splitlines():
        if line.rstrip().endswith("/Applications/cmux.app/Contents/MacOS/cmux"):
            stamp = line.split(None, 1)[1].rsplit(None, 1)[0]
            for fmt in ("%a %d %b %H:%M:%S %Y", "%a %b %d %H:%M:%S %Y"):
                try:
                    return datetime.datetime.strptime(stamp.strip(), fmt).timestamp()
                except ValueError:
                    continue
    return None


def cmd_snapshot(a):
    rows = live_order()
    if len(rows) < MIN_WORKSPACES:
        print("only %d workspace(s) visible; not snapshotting over a good order"
              % len(rows))
        return 0
    pins = pinned_titles()
    data = {"at": time.time(),
            "windows": {},
            "pinned": sorted(pins)}
    for window, _ref, title in rows:
        data["windows"].setdefault(window, []).append(title)
    os.makedirs(STORE, exist_ok=True)
    path = os.path.join(STORE, datetime.datetime.now().strftime("%Y%m%d-%H%M%S.json"))
    with open(path, "w") as f:
        json.dump(data, f, indent=1)

    kept = sorted(os.listdir(STORE))
    for old in kept[:-KEEP]:
        os.remove(os.path.join(STORE, old))
    if not a.quiet:
        print("snapshot: %d workspace(s) across %d window(s) -> %s"
              % (len(rows), len(data["windows"]), os.path.basename(path)))
    return 0


def snapshots():
    if not os.path.isdir(STORE):
        return []
    out = []
    for n in sorted(os.listdir(STORE)):
        try:
            out.append((n, json.load(open(os.path.join(STORE, n)))))
        except ValueError:
            continue
    return out


def pick(before=None):
    """Newest snapshot older than `before` (cmux's start), else the newest."""
    snaps = snapshots()
    if not snaps:
        return None, None
    if before:
        older = [s for s in snaps if s[1].get("at", 0) < before]
        if older:
            return older[-1]
        return None, None
    return snaps[-1]


def cmd_list(_a):
    started = cmux_started_at()
    for name, snap in snapshots():
        when = datetime.datetime.fromtimestamp(snap.get("at", 0)).strftime("%d %b %H:%M:%S")
        side = "before this cmux" if started and snap["at"] < started else "this run"
        print("  %-22s %s  %3d workspace(s)  %s"
              % (name, when, sum(len(v) for v in snap["windows"].values()), side))
    if started:
        print("\ncmux started %s"
              % datetime.datetime.fromtimestamp(started).strftime("%d %b %H:%M:%S"))
    return 0


def cmd_restore(a):
    started = cmux_started_at()
    name, snap = pick(before=None if a.newest else started)
    if not snap:
        print("No snapshot from before this cmux started (%s).\n"
              "Nothing to restore from: with --newest it would use the current,\n"
              "possibly scrambled, order, which is not a restore."
              % (datetime.datetime.fromtimestamp(started).strftime("%d %b %H:%M")
                 if started else "unknown"))
        return 1

    rows = live_order()
    live_titles = [t for _w, _r, t in rows]
    by_window = {}
    for window, ref, title in rows:
        by_window.setdefault(window, []).append(title)

    moves = 0
    for window, titles in sorted(by_window.items()):
        # Prefer the snapshot's own list for this window; fall back to the
        # union, because a relaunch can split one window into two and the
        # titles still need an order.
        wanted = snap["windows"].get(window)
        if not wanted:
            wanted = [t for ts in snap["windows"].values() for t in ts]

        # Several bare shells share one title ("user@host: ~/some/path"), so a
        # title alone does not identify a workspace. Pair each wanted title
        # with the next unused workspace of that title, in order.
        remaining = list(titles)
        order, seen = [], {}
        for t in wanted:
            n = seen.get(t, 0)
            if titles.count(t) > n:
                order.append((t, n))
                seen[t] = n + 1
                remaining.remove(t)
        # Anything the snapshot never saw keeps its current relative position,
        # at the end.
        for t in remaining:
            n = seen.get(t, 0)
            order.append((t, n))
            seen[t] = n + 1

        def position(title, nth, seq):
            """Index of the nth workspace with this title in seq."""
            hit = -1
            for i, t in enumerate(seq):
                if t == title:
                    hit += 1
                    if hit == nth:
                        return i
            return -1

        out_of_place = [i for i, (t, n) in enumerate(order)
                        if position(t, n, titles) != i]
        if not a.apply:
            print("%s: %d workspace(s); %d would move"
                  % (window, len(titles), len(out_of_place)))
            for i, (t, n) in enumerate(order[:8]):
                at = position(t, n, titles)
                print("   %2d  %-50s%s" % (i, t[:50], "" if at == i else "  (now %d)" % at))
            continue

        for index, (title, nth) in enumerate(order):
            # Resolve the ref NOW: every reorder renumbers the ones after it,
            # so a ref read before the loop is wrong by the second move. Only
            # the workspaces at or after this index are still candidates, which
            # is what keeps duplicate titles from fighting over one ref.
            rows_now = [(w, r, t) for w, r, t in live_order() if w == window]
            hit, ref = -1, None
            for i, (_w, r, t) in enumerate(rows_now):
                if t == title and i >= index:
                    ref = r
                    break
            if not ref:
                continue
            cmux("reorder-workspace", "--workspace", ref, "--index", str(index))
            moves += 1

    print("\nsnapshot %s (%s)" % (name,
          datetime.datetime.fromtimestamp(snap["at"]).strftime("%d %b %H:%M:%S")))
    missing = [t for ts in snap["windows"].values() for t in ts if t not in live_titles]
    if missing:
        print("in the snapshot but not open now: %s" % ", ".join(m[:40] for m in missing[:6]))
    if a.apply:
        print("reordered %d workspace(s)." % moves)
    else:
        print("Dry run. Re-run with --apply to put the order back.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("snapshot", help="record the current order")
    s.add_argument("--quiet", action="store_true")
    s.set_defaults(func=cmd_snapshot)
    r = sub.add_parser("restore", help="put a previous order back")
    r.add_argument("--apply", action="store_true")
    r.add_argument("--newest", action="store_true",
                   help="use the newest snapshot even if it is from this run")
    r.set_defaults(func=cmd_restore)
    l = sub.add_parser("list", help="show the snapshots held")
    l.set_defaults(func=cmd_list)
    a = ap.parse_args()
    if not getattr(a, "func", None):
        ap.print_help()
        return 1
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
