#!/usr/bin/env python3
"""Job class and context per cmux workspace, and routing that uses them.

The Chief of Staff kept delegating by idleness alone, so work landed wherever
a session happened to be quiet. On 26 Oct 2026 the Tom Soker follow-up, a
relationship email, went to "parghi conn & f/u, mac demo", a code session
sitting in ~/code/PythonGUI. The information needed to avoid that was already
on screen: Stephen colours that workspace red, the colour he uses for
engineering.

So this reads what is already there rather than inventing a new taxonomy:

  1. Stephen's own colour coding in cmux's state file, which is the most
     reliable signal because he maintains it by hand.
  2. references/registry-durable.md, which already carries topic and key
     contacts per workspace.
  3. The title and working directory, for the 34 workspaces with no colour.

    workspace_class.py                      the table, class per workspace
    workspace_class.py --refresh            rebuild the cache and context file
    workspace_class.py --route "<task>"     rank candidates for this task
    workspace_class.py --classify "<task>"  just say which class the task is
    workspace_class.py --json

Routing scores class match first, then named contacts and topic words, and
only then idleness. Idleness breaks ties; it no longer decides.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
STATE = os.path.expanduser(
    "~/Library/Application Support/cmux/session-com.cmuxterm.app.json")
DURABLE = os.path.join(SKILL, "references", "registry-durable.md")
CONTEXT = os.path.join(SKILL, "references", "workspace-context.md")
CACHE = os.path.join(SKILL, "state", "workspace-classes.json")

# Stephen's colours, read off his own workspaces on 26 Oct 2026. He maintains
# these by hand, which makes them the best signal available; the names are
# descriptions of what he already groups together, not a scheme imposed here.
COLOUR_CLASS = {
    "#1565C0": "business",     # CFO, CEO plans, BoD, EIS, business case, Plan A
    "#C0392B": "code",         # PythonGUI, GPU split, OEM integration, MSI builds
    "#922B21": "code",         # demo.elaitra zip CI
    "#196F3D": "clinical",     # NYP, KCH, Clarity CLIP FDA, abstracts, study power
    "#7D6608": "personal",     # personal finances, health, Bedford
    "#880E4F": "comms",        # Sutter and Emily, travel planning
    "#4A5C18": "sales",        # Pricing, DeepLook negotiation
    "#AD1457": "tooling",      # skills marketplace
}

# Fallback for an uncoloured workspace. Checked in order, first hit wins, so
# the more specific patterns come first.
TITLE_RULES = [
    ("tooling", r"ai tools|skills?|cmux|claude|tooling|registry|agent"),
    ("code", r"code|gui|ohif|viewer|ci\b|deploy|vm|gpu|docker|merge|msi|"
             r"nuitka|integration|api|repo|build|bug"),
    ("legal", r"patent|legal|nda|ip\b|trademark|involvenc|insolven|articles|sha\b"),
    ("finance", r"accountant|cfo|financ|xero|tax|invoice|payroll|bookkeep|eis\b"),
    ("fundraise", r"fundrais|round|investor|seed|vc\b|term sheet|cap table|bod\b|"
                  r"board|alchemist|sfc\b"),
    ("clinical", r"nyp|kch|gstt|kcl|nihr|i4i|grant|study|trial|abstract|paper|"
                 r"fda|mhra|ce mark|clinical|radiolog|reader"),
    ("sales", r"pricing|nego|customer|prospect|deal|partner|oem|distributor|"
              r"carpl|deeplook|clarity|sectra|ferrum|mevis|rsna"),
    ("personal", r"personal|health|bedford|oscar|family|travel|holiday|home"),
    ("comms", r"email|comms|follow.?up|f/u|outreach|call prep|intro|linkedin|"
              r"speaking|pr\b|press"),
]

CWD_RULES = [
    ("code", r"/code/|PositionMapping|PythonGUI|webmammoviewer|ViewFinder"),
    ("tooling", r"\.claude|/skills"),
    ("personal", r"Dropbox/Documents"),
    ("business", r"sm_elaitra"),
]

# Which classes may take which work. A task class maps to the classes of
# workspace that can properly hold it, best first.
COMPATIBLE = {
    "comms": ["comms", "sales", "business", "fundraise", "clinical"],
    "sales": ["sales", "comms", "business"],
    "fundraise": ["fundraise", "business", "comms"],
    "legal": ["legal", "business"],
    "finance": ["finance", "business"],
    "clinical": ["clinical", "business"],
    "code": ["code", "tooling"],
    "tooling": ["tooling", "code"],
    "personal": ["personal"],
    "business": ["business", "fundraise", "finance", "comms"],
}

# Classes that must never silently receive another class's work. A content
# email in a code session is the failure this whole module exists to stop.
INCOMPATIBLE = {
    ("comms", "code"), ("comms", "tooling"),
    ("sales", "code"), ("sales", "tooling"),
    ("fundraise", "code"), ("fundraise", "tooling"),
    ("legal", "code"), ("legal", "tooling"),
    ("personal", "code"), ("personal", "tooling"),
    ("code", "personal"), ("code", "comms"),
}

TASK_RULES = [
    ("comms", r"\b(email|draft a? ?reply|reply to|follow.?up|chase|write to|"
              r"thank|intro(duce|duction)?|outreach|message|letter|call prep)\b"),
    ("legal", r"\b(patent|nda|contract|agreement|articles|clause|counsel|"
              r"trademark|licen[cs]e)\b"),
    ("finance", r"\b(invoice|xero|vat|tax|payroll|bookkeep|reconcil|expense|"
                r"statement|accounts?)\b"),
    ("fundraise", r"\b(investor|round|seed|term sheet|cap table|valuation|"
                  r"subscription|board pack|bod)\b"),
    ("clinical", r"\b(grant|nihr|i4i|study|trial|abstract|ethics|irb|protocol|"
                 r"radiolog|reader|fda|mhra|510\(k\))\b"),
    ("code", r"\b(bug|fix|deploy|build|compile|refactor|test|script|repo|"
             r"commit|merge|docker|vm|gpu|ci\b|stack ?trace|error)\b"),
    ("tooling", r"\b(skill|cmux|hook|launchd|registry|agent|todo.?agent)\b"),
    ("personal", r"\b(oscar|school|bedford|health|dentist|holiday|flight|"
                 r"personal)\b"),
]


def workspaces():
    """Title, colour and cwd for every workspace in cmux's state file."""
    out = []
    data = json.load(open(STATE))
    for win in data.get("windows", []):
        for w in win.get("tabManager", {}).get("workspaces", []):
            title = (w.get("customTitle") or w.get("processTitle")
                     or w.get("title") or "(untitled)")
            out.append({"title": title.strip(),
                        "colour": w.get("customColor"),
                        "cwd": w.get("currentDirectory") or ""})
    return out


def norm(title):
    """Loose title key: drop status glyphs, case and extra spaces."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s/&:.-]", " ", title)).strip().lower()


def durable_rows():
    """Topic and contacts per title, from the hand-written registry."""
    rows = {}
    if not os.path.exists(DURABLE):
        return rows
    for line in open(DURABLE, errors="ignore"):
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0].lower() == "title":
            continue
        rows[norm(cells[0])] = {"topic": cells[1],
                                "contacts": cells[2] if cells[2] != "—" else "",
                                "notes": cells[4] if len(cells) > 4 else ""}
    return rows


def classify_workspace(ws, durable):
    """The job class of a workspace, and why."""
    colour = (ws.get("colour") or "").upper()
    if colour in COLOUR_CLASS:
        return COLOUR_CLASS[colour], "colour %s" % colour
    hay = norm(ws["title"])
    row = durable.get(hay)
    if row:
        hay = hay + " " + row["topic"].lower()
    for cls, pat in TITLE_RULES:
        if re.search(pat, hay):
            return cls, "title"
    for cls, pat in CWD_RULES:
        if re.search(pat, ws.get("cwd") or ""):
            return cls, "cwd"
    return "unknown", "no signal"


def classify_task(text):
    """The job class a piece of work belongs to."""
    t = text.lower()
    for cls, pat in TASK_RULES:
        if re.search(pat, t):
            return cls
    return "unknown"


def build():
    """Class plus context for every workspace."""
    durable = durable_rows()
    rows = []
    for ws in workspaces():
        cls, why = classify_workspace(ws, durable)
        row = durable.get(norm(ws["title"]), {})
        rows.append({"title": ws["title"], "class": cls, "why": why,
                     "colour": ws.get("colour"), "cwd": ws.get("cwd"),
                     "topic": row.get("topic", ""),
                     "contacts": row.get("contacts", "")})
    return rows


def save(rows):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump({"generated": datetime.now().isoformat(timespec="minutes"),
               "workspaces": rows}, open(CACHE, "w"), indent=1)
    with open(CONTEXT, "w") as f:
        f.write("# Workspace context (generated)\n\n")
        f.write("Generated by `scripts/workspace_class.py --refresh`. Do not "
                "edit: the hand-written half is `registry-durable.md`.\n\n")
        f.write("Class comes from Stephen's own colour coding where he has set "
                "one, since he maintains that by hand, and from the title, "
                "topic and working directory otherwise.\n\n")
        f.write("| # | Workspace | Class | From | Topic | Key contacts |\n")
        f.write("|---|---|---|---|---|---|\n")
        for i, r in enumerate(sorted(rows, key=lambda r: (r["class"], r["title"])), 1):
            f.write("| %d | %s | **%s** | %s | %s | %s |\n"
                    % (i, r["title"][:46], r["class"], r["why"],
                       (r["topic"] or "")[:60], (r["contacts"] or "")[:50]))


def load():
    if os.path.exists(CACHE):
        try:
            return json.load(open(CACHE))["workspaces"]
        except Exception:
            pass
    return build()


def words(text):
    return {w for w in re.findall(r"[a-z][a-z'-]{2,}", text.lower())}


def score(task, row, idle_hours):
    """How well this workspace suits this task. Higher is better.

    Class first, then who and what the workspace already knows about, then
    idleness. Idleness used to be the whole ranking, which is how an email
    about a person ended up in a session about a build.
    """
    tcls = classify_task(task)
    wcls = row.get("class", "unknown")
    pts, why = 0.0, []

    if tcls != "unknown":
        if wcls == tcls:
            pts += 100
            why.append("class match (%s)" % tcls)
        elif wcls in COMPATIBLE.get(tcls, []):
            pts += 40
            why.append("compatible class (%s for %s)" % (wcls, tcls))
        elif (tcls, wcls) in INCOMPATIBLE:
            pts -= 500
            why.append("WRONG CLASS (%s task, %s session)" % (tcls, wcls))
        else:
            pts -= 20
            why.append("class mismatch (%s vs %s)" % (tcls, wcls))

    # Named people are the strongest content signal there is: a follow-up to
    # Tom Soker belongs wherever Tom Soker is already known.
    contacts = row.get("contacts", "") or ""
    names = {n.strip().lower() for n in re.split(r"[,;()]", contacts) if len(n.strip()) > 3}
    tl = task.lower()
    hits = [n for n in names if n and n in tl]
    if hits:
        pts += 60 * len(hits)
        why.append("knows %s" % ", ".join(sorted(hits)[:2]))

    overlap = words(task) & words(row.get("topic", "") + " " + row.get("title", ""))
    overlap -= {"the", "and", "for", "with", "this", "that", "please", "elaitra"}
    if overlap:
        pts += 8 * min(len(overlap), 5)
        why.append("topic: " + ", ".join(sorted(overlap)[:3]))

    if idle_hours is not None:
        pts += min(idle_hours, 12) * 1.5       # tie-breaker only
    return pts, why, tcls


def route(task, top=5, include_busy=False):
    rows = load()
    try:
        sys.path.insert(0, HERE)
        import idle_rank
        live = {r["workspace"]: r for r in idle_rank.collect()}
    except Exception as exc:
        print("warning: could not read live idleness (%s); ranking on class and "
              "context alone" % exc, file=sys.stderr)
        live = {}

    scored = []
    for r in rows:
        l = live.get(r["title"], {})
        if l.get("busy") and not include_busy:
            continue
        pts, why, tcls = score(task, r, l.get("idle_hours"))
        scored.append({"workspace": r["title"], "class": r["class"],
                       "score": round(pts, 1), "why": why,
                       "idle_hours": l.get("idle_hours"),
                       "workspace_ref": l.get("workspace_ref"),
                       "task_class": tcls})
    scored.sort(key=lambda s: -s["score"])
    return scored[:top]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--route")
    ap.add_argument("--classify")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--conflicts", action="store_true",
                    help="workspaces whose colour and title disagree")
    a = ap.parse_args()

    if a.conflicts:
        # Worth looking at by eye. Some are harmless (a finance workspace
        # coloured with the business blue), but a few are genuinely mixed:
        # "parghi conn & f/u, mac demo" is coloured for engineering and titled
        # for follow-ups, and does both, which is exactly why an email landed
        # in it. Either split such a workspace or recolour it.
        rows = []
        for ws in workspaces():
            col = (ws.get("colour") or "").upper()
            if col not in COLOUR_CLASS:
                continue
            by_title = next((c for c, p in TITLE_RULES
                             if re.search(p, norm(ws["title"]))), None)
            if by_title and by_title != COLOUR_CLASS[col]:
                rows.append((ws["title"], COLOUR_CLASS[col], by_title))
        print("%d workspace(s) where the colour and the title disagree.\n"
              "The colour wins, because Stephen sets it by hand.\n" % len(rows))
        for t, c, ti in rows:
            print("  %-42s colour=%-10s title suggests=%s" % (t[:42], c, ti))
        return 0

    if a.classify:
        print(classify_task(a.classify))
        return 0
    if a.route:
        res = route(a.route, a.top)
        if a.json:
            print(json.dumps(res, indent=1))
            return 0
        print("task class: %s\n" % (res[0]["task_class"] if res else "unknown"))
        for i, r in enumerate(res, 1):
            print("%d. %-34s %-10s score %-7s %s"
                  % (i, r["workspace"][:34], r["class"], r["score"],
                     "; ".join(r["why"])[:70]))
        return 0

    rows = build()
    if a.refresh:
        save(rows)
        print("wrote %s and %s" % (os.path.basename(CACHE), os.path.basename(CONTEXT)))
    if a.json:
        print(json.dumps(rows, indent=1))
        return 0
    counts = {}
    for r in rows:
        counts[r["class"]] = counts.get(r["class"], 0) + 1
    for cls, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print("%-10s %d" % (cls, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
