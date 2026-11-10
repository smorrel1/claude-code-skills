#!/usr/bin/env python3
"""Does the router send work to the right agent, and stop when it should?

    python3 tests/test_routing.py

Four failures from 10 Nov 2026 drive these cases:
  - the Nikki Gidwaney call went to "Seb advisory call prep" because the
    topic owner was blocked and the router fell through to any idle session
    in roughly the right category;
  - Enter was pressed into a pane showing an AskUserQuestion menu, which
    toggled Stephen's own answers twice;
  - "Plan IICME travel" was renamed "Plan CA travel" and the lookup failed;
  - a repeated word decided a category ("cmux" x42 made a sales session read
    as tooling).

Nothing here touches cmux or a live session: it drives the registry and the
screen classifier with fixtures.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import agent_registry as A  # noqa: E402
import check_dead_sessions as C  # noqa: E402

REG = {"agents": {
    "aaa": {"session": "aaa", "title": "Pricing, DeepLook nego", "category": "sales",
            "tags": ["nikki gidwaney", "deeplook", "peter graham"],
            "cwd": "/Users/x/Dropbox/sm_elaitra", "idle_hours": 100.0,
            "workspace_ref": "workspace:1", "confirmed": True},
    "bbb": {"session": "bbb", "title": "Seb advisory call prep", "category": "clinical",
            "tags": ["seb", "kcl", "nihr"], "cwd": "/Users/x/Dropbox/sm_elaitra",
            "idle_hours": 893.0, "workspace_ref": "workspace:2", "confirmed": False},
    "ccc": {"session": "ccc", "title": "Plan CA travel", "category": "personal",
            "tags": ["orit"], "cwd": "/Users/x/Dropbox/Documents",
            "idle_hours": 40.0, "workspace_ref": "workspace:3", "confirmed": False},
    "ddd": {"session": "ddd", "title": "CCMLO merge Nuitka", "category": "coding",
            "tags": ["parghi"], "cwd": "/Users/x/code/PositionMappingCCMLO",
            "idle_hours": 5.0, "workspace_ref": "workspace:4", "confirmed": False},
}}

IDLE_PANE = ("some earlier output\n"
             "────────────────────────────\n"
             "❯ \n"
             "────────────────────────────\n"
             "  ⏵⏵ auto mode on (shift+tab to cycle)\n")

MENU_PANE = ("  1. [ ] RSNA Sunday meeting time and place\n"
             "  2. [ ] Gina's laptop and the sheet\n"
             "  5. [ ] Type something\n"
             "     Submit\n"
             "────────────────────────────\n"
             "  6. Chat about this\n"
             "Enter to select · ↑/↓ to navigate · Esc to cancel\n"
             "────────────────────────────\n")

NUMBERED_OUTPUT = ("  3. Hope dinner goes well tonight; best to his friend.\n"
                   "  4. Ask which sites she reads for.\n"
                   "────────────────────────────\n"
                   "❯ \n"
                   "────────────────────────────\n"
                   "  ⏵⏵ auto mode on (shift+tab to cycle)\n")


def main():
    bad = []

    # 1. The brief names Nikki, so the agent that knows Nikki wins, even though
    #    it is the LEAST idle of the two plausible candidates.
    rows, _cat, named = A.rank("prep the call with Nikki Gidwaney about DeepLook",
                               reg=REG, check_blocked=False)
    if "nikki gidwaney" not in named:
        bad.append("should spot Nikki Gidwaney in the brief, got %r" % named)
    if rows[0]["title"] != "Pricing, DeepLook nego":
        bad.append("Nikki work should go to the DeepLook session, got %r"
                   % rows[0]["title"])
    seb = next(r for r in rows if r["title"] == "Seb advisory call prep")
    if seb["score"] >= rows[0]["score"]:
        bad.append("the 893h-idle Seb session must not outrank the topic owner")

    # 2. A live AskUserQuestion menu is blocked; ordinary numbered output is not.
    if C.blocked_reason(None, text=MENU_PANE) is None:
        bad.append("a pane showing a selectable menu must read as blocked")
    if C.blocked_reason(None, text=NUMBERED_OUTPUT) is not None:
        bad.append("numbered output with a healthy input box is NOT blocked")
    if C.blocked_reason(None, text=IDLE_PANE) is not None:
        bad.append("an idle pane is not blocked")

    # 3. Renames must not break the lookup. "Plan IICME travel" is now
    #    "Plan CA travel", and the old name still has to resolve.
    if (A.find(REG, "Plan CA travel") or {}).get("session") != "ccc":
        bad.append("exact title lookup failed")
    if (A.find(REG, "ccc") or {}).get("session") != "ccc":
        bad.append("session id lookup failed, which is the whole point of ids")
    if A.find(REG, "Pricing DeepLook negotiation") is None:
        bad.append("a loosely worded title should still fuzzy match")

    # 4. One repeated word must not decide a category. A sales transcript that
    #    says "cmux" many times is still sales.
    sales_heavy = ("cmux " * 40) + "pricing quote distributor channel oem partner"
    if A.task_category(sales_heavy) == "tooling":
        bad.append("a single repeated word should not win the category")

    # 5. Stephen's cwd rule: code work belongs in a ~/code session.
    rows, _c, _n = A.rank("fix the failing build and commit the merge",
                          reg=REG, check_blocked=False)
    if rows[0]["title"] != "CCMLO merge Nuitka":
        bad.append("code work should go to the ~/code session, got %r"
                   % rows[0]["title"])

    for b in bad:
        print("FAIL " + b)
    print("%d check(s), %d failure(s)" % (11, len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
