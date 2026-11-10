#!/usr/bin/env python3
"""Number and colour every cmux workspace by its category.

Each category gets a number 1 to 9 and one readable colour. The number goes
on the front of the workspace title ("3 Q4 Fundraise") so the sidebar sorts
and scans by category, and the colour makes the grouping visible at a glance.

    colour_index.py                 show the before and after table, change nothing
    colour_index.py --apply         rename and recolour
    colour_index.py --apply --colours-only
    colour_index.py --apply --numbers-only
    colour_index.py --legend        print the legend
    colour_index.py --note          write the legend to the 'cmux colour key' note

Dry run is the default, deliberately: this touches all 82 workspaces at once
and the titles are Stephen's own shorthand.

Two safety rules:
  - A title that already starts with the right number is left exactly alone,
    so running this twice changes nothing and cannot stack "3 3 Q4".
  - A colour Stephen has already set that matches the category's colour is
    left alone, per his instruction to keep existing colours where they match.

This must only run AFTER the router resolves by session id and ignores the
leading digit, which `tests/test_routing.py` pins down. Otherwise renaming
every workspace breaks every caller that still uses the old name.
"""

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import agent_registry as A  # noqa: E402

CMUX = "/Applications/cmux.app/Contents/Resources/bin/cmux"

# Number, colour name and hex per category. Chosen to stay distinct on the
# dark sidebar and to keep Stephen's existing meanings where he already had
# one: red stayed engineering, green stayed clinical, blue stayed business.
SCHEME = {
    "coding":      (1, "Red",        "#C0392B"),
    "deployments": (2, "Orange",     "#D35400"),
    "clinical":    (3, "Green",      "#196F3D"),
    "sales":       (4, "Teal",       "#117A65"),
    "fundraising": (5, "Blue",       "#1565C0"),
    "corporate":   (6, "Purple",     "#6C3483"),
    "finance":     (7, "Olive",      "#7D6608"),
    "personal":    (8, "Magenta",    "#AD1457"),
    "tooling":     (9, "Slate",      "#4A5C18"),
}

BELONGS = {
    "coding": "repos, builds, CI, the viewer and GUI themselves",
    "deployments": "customer installs, demo VMs, on-site setup, DICOM nodes",
    "clinical": "papers, grants, studies, regulatory science",
    "sales": "OEM, distributors, channel, pricing, prospects",
    "fundraising": "investors, rounds, cap table, board decks",
    "corporate": "legal, company secretarial, board, resolutions, patents",
    "finance": "accounting, Xero, tax, payroll, billing",
    "personal": "family, health, school, travel",
    "tooling": "the agents, skills, hooks and scheduled jobs themselves",
}

LEAD = re.compile(r"^\s*([1-9])[\s.)-]+")   # categories are 1 to 9 only


def bare(title):
    return LEAD.sub("", (title or "").strip()).strip()


def cmux(*args):
    try:
        p = subprocess.run([CMUX, *args], capture_output=True, text=True, timeout=25)
        return p.returncode == 0, (p.stdout + p.stderr).strip()
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)


def current_colours():
    """What colour each workspace has right now, from cmux's state file."""
    state = os.path.expanduser(
        "~/Library/Application Support/cmux/session-com.cmuxterm.app.json")
    out = {}
    try:
        data = json.load(open(state))
    except Exception:
        return out
    for win in data.get("windows", []):
        for w in win.get("tabManager", {}).get("workspaces", []):
            title = (w.get("customTitle") or w.get("processTitle")
                     or w.get("title") or "")
            out[title.strip()] = w.get("customColor")
    return out


def plan():
    """Rows of (agent, new title, new colour, what would change)."""
    reg = A.load()
    colours = current_colours()
    rows = []
    for a in reg.get("agents", {}).values():
        cat = a.get("category", "unknown")
        if cat not in SCHEME:
            rows.append((a, a["title"], None, "skipped, category %s" % cat))
            continue
        num, _name, hexcode = SCHEME[cat]
        stem = bare(a["title"])
        new_title = "%d %s" % (num, stem)
        have_colour = colours.get(a["title"].strip())
        changes = []
        if a["title"].strip() != new_title:
            changes.append("rename")
        if (have_colour or "").upper() != hexcode:
            changes.append("colour")
        rows.append((a, new_title, hexcode,
                     ", ".join(changes) if changes else "already correct"))
    rows.sort(key=lambda r: (SCHEME.get(r[0].get("category"), (99,))[0],
                             bare(r[0]["title"]).lower()))
    return rows


def legend_text():
    lines = ["cmux colour key", ""]
    lines.append("Every workspace carries its category number at the front of "
                 "the name and the category colour. New workspaces get both "
                 "when created. Drift is checked hourly.")
    lines.append("")
    reg = A.load()
    for cat, (num, name, hexcode) in sorted(SCHEME.items(), key=lambda kv: kv[1][0]):
        examples = [bare(x["title"]) for x in reg.get("agents", {}).values()
                    if x.get("category") == cat][:2]
        lines.append("%d  %s  %s (%s)" % (num, A.CATEGORY_LABEL[cat], name, hexcode))
        lines.append("    %s" % BELONGS[cat])
        lines.append("    e.g. %s" % (", ".join(examples) or "none yet"))
        lines.append("")
    lines.append("Rules: a ~/code session does code tasks. An sm_elaitra "
                 "session does business tasks. Tooling and debugging go to "
                 "'my ai tools'.")
    return "\n".join(lines)


def write_note(text, name="cmux colour key"):
    """Create or replace the Apple Note holding the legend."""
    body = text.replace("&", "&amp;").replace("<", "&lt;")
    body = "<div>" + body.replace("\n", "</div><div>") + "</div>"
    script = '''
    on run argv
      set theBody to item 1 of argv
      tell application "Notes"
        tell folder "Notes"
          if (exists note "%s") then
            set body of note "%s" to theBody
            return "updated"
          else
            make new note with properties {name:"%s", body:theBody}
            return "created"
          end if
        end tell
      end tell
    end run''' % (name, name, name)
    p = subprocess.run(["osascript", "-e", script, body],
                       capture_output=True, text=True, timeout=60)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--colours-only", action="store_true")
    ap.add_argument("--numbers-only", action="store_true")
    ap.add_argument("--legend", action="store_true")
    ap.add_argument("--note", action="store_true")
    a = ap.parse_args()

    if a.legend:
        print(legend_text())
        return 0
    if a.note:
        ok, msg = write_note(legend_text())
        print("Apple Note 'cmux colour key': %s" % (msg if ok else "FAILED " + msg))
        return 0 if ok else 1

    rows = plan()
    todo = [r for r in rows if r[3] not in ("already correct",) and not r[3].startswith("skipped")]

    print("%-3s %-40s -> %-42s %-9s %s"
          % ("#", "now", "after", "colour", "change"))
    for agent, new_title, hexcode, change in rows:
        num = SCHEME.get(agent.get("category"), ("-",))[0]
        print("%-3s %-40s -> %-42s %-9s %s"
              % (num, agent["title"][:40], new_title[:42], hexcode or "-", change))
    print("\n%d workspace(s), %d would change, %d already correct"
          % (len(rows), len(todo), len(rows) - len(todo)))

    if not a.apply:
        print("\nDry run. Nothing was changed. Re-run with --apply.")
        return 0

    renamed = recoloured = failed = 0
    for agent, new_title, hexcode, change in rows:
        ref = agent.get("workspace_ref")
        if not ref or change.startswith("skipped") or change == "already correct":
            continue
        if "rename" in change and not a.colours_only:
            ok, msg = cmux("rename-workspace", "--workspace", ref, new_title)
            renamed += ok
            failed += (not ok)
            if not ok:
                print("rename failed for %s: %s" % (agent["title"], msg[:80]))
        if "colour" in change and not a.numbers_only:
            ok, msg = cmux("workspace-action", "--action", "set-color",
                           "--workspace", ref, "--color", hexcode)
            recoloured += ok
            failed += (not ok)
            if not ok:
                print("colour failed for %s: %s" % (agent["title"], msg[:80]))
    print("\nrenamed %d, recoloured %d, failed %d" % (renamed, recoloured, failed))
    print("Re-run agent_registry.py --write so the registry picks up the new titles.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
