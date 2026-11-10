#!/usr/bin/env python3
"""Record a misroute, so "that went to the wrong cmux" teaches the router.

    route_fix.py "<brief marker>" --to "<workspace>"
    route_fix.py "<marker>" --to "<workspace>" --tags "nikki gidwaney,deeplook"
    route_fix.py --log 20                     recent routing decisions

What it does, and deliberately does not do:
  - moves the brief's topic tags onto the workspace that SHOULD have had it,
    and marks that workspace confirmed, so the category is never switched
    automatically afterwards;
  - removes those tags from the workspace that wrongly received it, so the
    same mistake does not score well next time;
  - appends the correction to the routing log with Stephen's words.

It does not re-send the brief and it does not touch either session. Moving
the work is a separate decision, and a destructive one if the wrong session
has already started.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import agent_registry as A  # noqa: E402

TASKS = os.path.join(os.path.dirname(HERE), "state", "tasks")


def brief_text(marker):
    """The brief behind a marker, so its named people can be tagged."""
    for name in (marker + "-brief.md", marker):
        path = os.path.join(TASKS, name)
        if os.path.exists(path):
            try:
                return open(path, errors="ignore").read()
            except OSError:
                break
    return ""


def names_in(text):
    low = (text or "").lower()
    return [e.strip() for e in A.KNOWN_ENTITIES
            if re.search(r"\b%s\b" % re.escape(e.strip()), low)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("marker", nargs="?")
    ap.add_argument("--to", help="the workspace that SHOULD have had it")
    ap.add_argument("--from", dest="wrong", help="the one that wrongly got it; "
                    "taken from the routing log when omitted")
    ap.add_argument("--tags", help="comma separated, overrides what the brief names")
    ap.add_argument("--note", default="", help="Stephen's words, kept in the log")
    ap.add_argument("--log", type=int, metavar="N", help="show recent routing decisions")
    a = ap.parse_args()

    if a.log:
        if not os.path.exists(A.ROUTING_LOG):
            print("No routing log yet.")
            return 0
        lines = open(A.ROUTING_LOG, errors="ignore").read().strip().split("\n")
        for line in lines[-a.log:]:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            print("%s  %-34s %-12s %s%s"
                  % (d.get("at", "")[:16], (d.get("title") or "")[:34],
                     d.get("category", ""), ", ".join(d.get("tags", [])),
                     "  <- " + d["note"] if d.get("note") else ""))
        return 0

    if not a.marker or not a.to:
        ap.error("give a marker and --to")

    reg = A.load()
    right = A.find(reg, a.to)
    if not right:
        print("No agent matches %r. Titles change, so try part of it." % a.to)
        return 1

    tags = ([t.strip().lower() for t in a.tags.split(",")] if a.tags
            else names_in(brief_text(a.marker) or a.marker))
    tags = [t for t in tags if t][:3]

    wrong = A.find(reg, a.wrong) if a.wrong else None
    if not wrong:
        # Fall back to whoever the log says received this marker.
        if os.path.exists(A.ROUTING_LOG):
            for line in open(A.ROUTING_LOG, errors="ignore"):
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("marker") == a.marker:
                    wrong = reg.get("agents", {}).get(d.get("session"))

    # Stephen's correction outranks whatever was inferred, so the corrected
    # tags go to the FRONT. Appending them and then trimming to three kept the
    # first three and silently dropped the new ones, which made the first run
    # of this look like it had worked while changing nothing.
    moved = [t for t in tags if t not in right["tags"]]
    right["tags"] = list(dict.fromkeys(tags + right["tags"]))[:3]
    right["confirmed"] = True
    right["why"] = "confirmed by Stephen (misroute correction)"

    stripped = []
    if wrong and wrong["session"] != right["session"]:
        for t in tags:
            if t in wrong.get("tags", []):
                wrong["tags"].remove(t)
                stripped.append(t)

    A.save(reg)
    A.log_route(a.marker, right["session"], right["title"], right["category"],
                tags, note="CORRECTION: %s%s"
                % (a.note or "wrong cmux",
                   " (was %s)" % wrong["title"] if wrong else ""))

    print("%s is now the owner of: %s" % (right["title"], ", ".join(tags) or "(no names found)"))
    if moved:
        print("  tags added: %s" % ", ".join(moved))
    if wrong:
        print("  removed from %s: %s" % (wrong["title"], ", ".join(stripped) or "nothing"))
    else:
        print("  the wrong target was not identified; pass --from to strip its tags")
    print("Recorded in the routing log. The brief was NOT re-sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
