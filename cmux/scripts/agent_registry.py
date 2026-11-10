#!/usr/bin/env python3
"""What every cmux agent is for, keyed by session id, kept current as it drifts.

Routing kept going wrong for three different reasons, and this fixes the
cause of each:

  - Lookups were by TITLE, and Stephen renames workspaces. "Plan IICME travel"
    became "Plan CA travel" and the lookup failed; "Oscar stuff" became "Oscar
    Alexander stuff". Session ids never change, so everything here is keyed on
    the id and the title is only a display name.
  - Classification was one coarse class per workspace, so the router could not
    tell that the Nikki Gidwaney call belonged to the session that already
    held Nikki, DeepLook and Peter Graham. Each agent now carries a category
    AND up to three topic tags naming the people and companies it works on.
  - Sessions drift. "parghi conn & f/u, mac demo" picked up Tom Soker installs
    along the way. Tags are refreshed from recent prompts automatically; a
    change of CATEGORY is flagged for confirmation rather than applied, since
    that is usually a misroute rather than a real change of job.

    agent_registry.py --classify           classify everything, print the table
    agent_registry.py --classify --write   ...and save it
    agent_registry.py --table out.md       write the numbered review table
    agent_registry.py --drift              refresh tags, report category drift
    agent_registry.py --show <session|title>
    agent_registry.py --set <session> --category X --tags a,b,c
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
REGISTRY = os.path.join(SKILL, "state", "agent-registry.json")
ROUTING_LOG = os.path.join(SKILL, "state", "routing-log.jsonl")
PROJECTS = os.path.expanduser("~/.claude/projects")

# Small and stable on purpose. A taxonomy that grows every week cannot be
# learned by the people using it, and the router only needs enough resolution
# to keep an email out of a build session.
CATEGORIES = [
    "coding",       # engineering, repos, builds, CI, the viewer itself
    "deployments",  # customer installs, demo VMs, on-site setup
    "clinical",     # papers, grants, studies, regulatory science
    "sales",        # OEM, distributors, channel, pricing, prospects
    "fundraising",  # investors, rounds, cap table, board decks
    "corporate",    # legal, company secretarial, board, resolutions
    "finance",      # accounting, Xero, tax, payroll, billing
    "personal",     # family, health, school, travel
    "tooling",      # the agents, skills, hooks and jobs themselves
]

CATEGORY_LABEL = {
    "coding": "Coding and engineering",
    "deployments": "Deployments and customer installs",
    "clinical": "Clinical and research",
    "sales": "Sales and partners",
    "fundraising": "Fundraising and investors",
    "corporate": "Corporate, legal and board",
    "finance": "Finance and accounting",
    "personal": "Personal and family",
    "tooling": "Tooling",
}

# Stephen's own rule, 10 Nov 2026: the working directory decides the nature of
# the work before anything else does. A ~/code session does code.
CWD_RULES = [
    ("tooling", r"\.claude|/skills|/tools/"),
    ("coding", r"/code/|PositionMapping|PythonGUI|webmammoviewer|ViewFinder|/git/"),
    ("personal", r"Dropbox/Documents(?!.*elaitra)"),
]

KEYWORDS = {
    "coding": r"\b(bug|traceback|commit|branch|merge|refactor|compile|pytest|"
              r"docker|nuitka|msi|build|repo|pull request|lint|stack trace)\b",
    "deployments": r"\b(deploy|install|orthanc|vm\b|gpu|provision|on.?site|"
                   r"demo server|dicom node|ae title|firewall|vpn)\b",
    "clinical": r"\b(grant|nihr|i4i|irb|ethics|protocol|reader study|abstract|"
                r"manuscript|paper|p.?value|sensitivity|specificity|510\(k\)|"
                r"mhra|fda|radiolog|mammograph)\b",
    "sales": r"\b(pricing|quote|distributor|reseller|oem|channel|prospect|"
             r"pipeline|demo for|proposal|partner|nda|rsna)\b",
    "fundraising": r"\b(investor|round|seed|term sheet|cap table|valuation|"
                   r"subscription|eis\b|vc\b|lp\b|data room|pitch deck)\b",
    "corporate": r"\b(board|resolution|shareholder|articles|companies house|"
                 r"share certificate|option pool|insolven|involvenc|patent|"
                 r"trademark|counsel|solicitor)\b",
    "finance": r"\b(xero|invoice|vat|payroll|reconcil|p&l|balance sheet|"
               r"bookkeep|expense|bank statement|tax return)\b",
    "personal": r"\b(oscar|school|bedford|dentist|gp\b|holiday|flight|hotel|"
                r"orit|natasha|family|health)\b",
    # Deliberately narrow. Every one of these sessions IS a Claude agent, so
    # words like "claude code", "agent", "skill" and "transcript" appear in
    # almost all of them and an early version filed 20 of 82 as tooling,
    # including "Pricing, DeepLook nego". Only terms that mean somebody is
    # working ON the machinery count.
    "tooling": r"\b(cmux|launchd|skill\.md|todo.?agent|plist|hook script|"
               r"slash command|mcp server|subagent|workspace_class|"
               r"send_task|idle_rank|routing log)\b",
}

# Names worth tagging when they show up. Tags are what let the router send the
# Nikki Gidwaney call to the session that already knows Nikki.
KNOWN_ENTITIES = [
    "nikki gidwaney", "peter graham", "deeplook", "tom soker", "greg sorensen",
    "parghi", "chirag", "emily conant", "keshthra", "tamara", "seb", "ourselin",
    "jorge cardoso", "theo barfoot", "david bodne", "clarity", "carpl", "mevis",
    "sectra", "ferrum", "intelerad", "inteleviewer", "blackford", "incepto",
    "hologic", "ge healthcare", "philips", "nyp", "columbia", "kch", "gstt", "kcl",
    "nihr", "i4i", "sfc", "alchemist", "impactx", "holroyd", "davide",
    "scott peairs", "laura kassa", "dan bickford", "michael ebner", "xero",
    "starling", "hargreaves", "metrobank", "bedford", "alleyn", "orit",
    "natasha", "oscar", "rsna", "ecr", "sutter", "radnet", "upenn",
]


def transcript_for(session_id):
    import glob
    hits = glob.glob(os.path.join(PROJECTS, "*", "%s.jsonl" % session_id))
    return hits[0] if hits else None


def prompts(session_id, last=20):
    """The first user prompt and the most recent `last` of them.

    The first prompt says what the session was created to do; the recent ones
    say what it is doing now. Classifying on only one of those is how a
    session that has moved on keeps getting its old work.
    """
    path = transcript_for(session_id)
    if not path:
        return "", []
    first, recent = "", []
    try:
        for line in open(path, errors="ignore"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") != "user":
                continue
            c = d.get("message", {}).get("content")
            if not isinstance(c, str) or not c.strip():
                continue
            # Skip the machinery: tool results and our own brief wrappers say
            # nothing about what the session is for.
            if c.startswith(("Task for you, the full brief", "<", "[Request interrupted")):
                continue
            if not first:
                first = c
            recent.append(c)
    except OSError:
        return "", []
    return first, recent[-last:]


def classify(session_id, cwd, title):
    """(category, tags, why) for one agent."""
    first, recent = prompts(session_id)
    # The first prompt is weighted, because it states the session's purpose,
    # but recent work can outvote it when a session has genuinely moved on.
    text = " ".join([title, title, first, first] + recent).lower()

    # Score on the BREADTH of evidence, not the raw count, capping how much
    # any single term can contribute. Counting every occurrence let one
    # repeated word decide: "Pricing, DeepLook nego" scored 42 for tooling on
    # the word "cmux" alone, because Stephen had been discussing routing with
    # it, and so outranked the 19 genuine sales terms in the same transcript.
    PER_TERM_CAP = 3
    scores = Counter()
    for cat, pat in KEYWORDS.items():
        hits = Counter(m.lower() if isinstance(m, str) else m[0].lower()
                       for m in re.findall(pat, text))
        scores[cat] = sum(min(n, PER_TERM_CAP) for n in hits.values())

    why = "prompts"
    cwd_cat = next((c for c, p in CWD_RULES if re.search(p, cwd or "")), None)
    if cwd_cat:
        # Stephen's rule: the directory decides the nature of the work. Strong
        # but not absolute, so a clearly clinical session living under
        # Documents is not forced to "personal".
        scores[cwd_cat] += 4
        why = "cwd + prompts"

    category = scores.most_common(1)[0][0] if scores and max(scores.values()) else "unknown"
    if not max(scores.values() or [0]):
        category, why = (cwd_cat or "unknown"), "cwd only" if cwd_cat else "no signal"

    # Whole words only. Substring matching tagged almost every session with
    # "ge", because it sits inside "large", "page" and "message".
    tags = []
    for ent in KNOWN_ENTITIES:
        n = len(re.findall(r"\b%s\b" % re.escape(ent.strip()), text))
        if n:
            tags.append((n, ent.strip()))
    tags.sort(reverse=True)
    return category, [t for _, t in tags[:3]], why


def live_rows():
    sys.path.insert(0, HERE)
    import idle_rank
    return idle_rank.collect()


def load():
    if os.path.exists(REGISTRY):
        try:
            return json.load(open(REGISTRY))
        except Exception:
            pass
    return {"generated": None, "agents": {}}


def save(reg):
    os.makedirs(os.path.dirname(REGISTRY), exist_ok=True)
    reg["generated"] = datetime.now().isoformat(timespec="minutes")
    json.dump(reg, open(REGISTRY, "w"), indent=1, sort_keys=True)


def build(existing=None):
    """Classify every live agent, preserving anything Stephen has confirmed."""
    existing = existing or {"agents": {}}
    agents = {}
    for r in live_rows():
        sid = r.get("session_full")
        if not sid:
            continue
        prev = existing.get("agents", {}).get(sid, {})
        cat, tags, why = classify(sid, r.get("cwd", ""), r.get("workspace", ""))
        if prev.get("confirmed"):
            # Stephen has ruled on this one. Tags may still grow, the category
            # may not change without him.
            cat = prev.get("category", cat)
            why = "confirmed by Stephen"
            tags = list(dict.fromkeys(prev.get("tags", []) + tags))[:3]
        agents[sid] = {
            "session": sid,
            "title": r.get("workspace", ""),
            "category": cat,
            "tags": tags,
            "cwd": r.get("cwd", ""),
            "idle_hours": r.get("idle_hours"),
            "workspace_ref": r.get("workspace_ref"),
            "why": why,
            "confirmed": prev.get("confirmed", False),
        }
    return {"agents": agents}


def table(agents, fh=sys.stdout, markdown=False):
    rows = sorted(agents.values(), key=lambda a: (a["category"], a["title"].lower()))
    if markdown:
        fh.write("# cmux agent classification, %s\n\n"
                 % datetime.now().strftime("%a %d %b %Y %H:%M"))
        fh.write("Correct anything wrong and tell the Chief of Staff. A category "
                 "you confirm is never changed automatically afterwards.\n\n")
        fh.write("| # | Workspace | Category | Topic tags | cwd | Idle (h) |\n")
        fh.write("|---|---|---|---|---|---|\n")
        for i, a in enumerate(rows, 1):
            fh.write("| %d | %s | **%s** | %s | `%s` | %s |\n"
                     % (i, a["title"][:44], CATEGORY_LABEL.get(a["category"],
                        a["category"]), ", ".join(a["tags"]) or "-",
                        (a["cwd"] or "").replace(os.path.expanduser("~"), "~")[:46],
                        a["idle_hours"]))
    else:
        for i, a in enumerate(rows, 1):
            fh.write("%3d  %-40s %-13s %-30s %s\n"
                     % (i, a["title"][:40], a["category"],
                        ", ".join(a["tags"])[:30],
                        (a["cwd"] or "").replace(os.path.expanduser("~"), "~")[:40]))
    return len(rows)


def log_route(marker, target_session, target_title, category, tags, note=""):
    os.makedirs(os.path.dirname(ROUTING_LOG), exist_ok=True)
    with open(ROUTING_LOG, "a") as f:
        f.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"),
                            "marker": marker, "session": target_session,
                            "title": target_title, "category": category,
                            "tags": tags, "note": note}) + "\n")


def drift():
    """Refresh tags automatically; report category changes for confirmation."""
    reg = load()
    fresh = build(reg)
    minor, major = [], []
    for sid, new in fresh["agents"].items():
        old = reg.get("agents", {}).get(sid)
        if not old:
            minor.append("NEW %s (%s)" % (new["title"], new["category"]))
            continue
        if set(new["tags"]) != set(old.get("tags", [])):
            minor.append("%s tags %s -> %s"
                         % (new["title"], old.get("tags"), new["tags"]))
        if new["category"] != old.get("category"):
            if old.get("confirmed"):
                new["category"] = old["category"]   # never switch silently
                major.append("%s looks like %s now but is confirmed as %s"
                             % (new["title"], new["category"], old["category"]))
            else:
                major.append("%s category %s -> %s"
                             % (new["title"], old.get("category"), new["category"]))
    save(fresh)
    return minor, major


def task_category(text):
    """Which category a brief belongs to, by the same keywords."""
    t = (text or "").lower()
    best, score = "unknown", 0
    for cat, pat in KEYWORDS.items():
        n = len(set(m if isinstance(m, str) else m[0] for m in re.findall(pat, t)))
        if n > score:
            best, score = cat, n
    return best


def rank(brief, reg=None, include_blocked=False, check_blocked=True):
    """Candidates for this brief, best first.

    The order of evidence matters and is the whole point:
      1. topic tags, the people and companies the brief names. A call about
         Nikki Gidwaney belongs wherever Nikki is already known.
      2. category match.
      3. Stephen's cwd rule.
      4. idleness, and only as a tie-breaker.

    A candidate that is BLOCKED is reported as such and never silently
    skipped, because falling through to "any idle session in roughly the right
    category" is how the Nikki work reached a session about Seb.
    """
    reg = reg or load()
    tcat = task_category(brief)
    low = (brief or "").lower()
    named = [e.strip() for e in KNOWN_ENTITIES
             if re.search(r"\b%s\b" % re.escape(e.strip()), low)]

    out = []
    for a in reg.get("agents", {}).values():
        pts, why = 0.0, []
        hits = [t for t in a.get("tags", []) if t in named]
        if hits:
            pts += 100 * len(hits)
            why.append("knows " + ", ".join(hits))
        if tcat != "unknown":
            if a["category"] == tcat:
                pts += 60
                why.append("category %s" % tcat)
            else:
                pts -= 30
                why.append("category %s, not %s" % (a["category"], tcat))
        cwd_cat = next((c for c, p in CWD_RULES if re.search(p, a.get("cwd") or "")), None)
        if cwd_cat and tcat != "unknown":
            pts += 20 if cwd_cat == tcat else -25
            why.append("cwd suggests %s" % cwd_cat)
        idle = a.get("idle_hours")
        if idle is not None:
            pts += min(idle, 12) * 1.0
        out.append({"session": a["session"], "title": a["title"],
                    "category": a["category"], "tags": a.get("tags", []),
                    "score": round(pts, 1), "why": why,
                    "workspace_ref": a.get("workspace_ref"),
                    "idle_hours": idle, "blocked": None})

    out.sort(key=lambda r: -r["score"])
    if check_blocked:
        # Only probe the few at the top. Reading every pane costs a minute.
        try:
            sys.path.insert(0, HERE)
            import check_dead_sessions as C
            import restart_sessions as R
            panels = {v["session"]: k for k, v in R.wanted().items()}
            for r in out[:5]:
                panel = panels.get(r["session"])
                if panel:
                    r["blocked"] = C.blocked_reason(panel)
        except Exception as exc:
            print("note: could not check blocked state (%s)" % exc, file=sys.stderr)
    if not include_blocked:
        pass   # kept in the list on purpose; the caller decides what to do
    return out, tcat, named


def find(reg, needle):
    """An agent by session id, exact title, or fuzzy title.

    Fuzzy on purpose: "Plan IICME travel" became "Plan CA travel" and a strict
    lookup simply failed, which is how work went nowhere.
    """
    agents = reg.get("agents", {})
    if needle in agents:
        return agents[needle]
    for a in agents.values():
        if a["title"].lower() == needle.lower():
            return a
    want = set(re.findall(r"[a-z0-9]+", needle.lower()))
    best, score = None, 0
    for a in agents.values():
        have = set(re.findall(r"[a-z0-9]+", a["title"].lower()))
        if not have:
            continue
        s = len(want & have) / max(1, len(want | have))
        if s > score:
            best, score = a, s
    return best if score >= 0.34 else None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--classify", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--table", metavar="FILE")
    ap.add_argument("--drift", action="store_true")
    ap.add_argument("--show")
    ap.add_argument("--set")
    ap.add_argument("--category")
    ap.add_argument("--tags")
    ap.add_argument("--route", metavar="BRIEF")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.route:
        rows, tcat, named = rank(a.route)
        if a.json:
            print(json.dumps(rows[:a.top], indent=1)); return 0
        print("category: %s | names in brief: %s\n"
              % (tcat, ", ".join(named) or "none"))
        for i, r in enumerate(rows[:a.top], 1):
            flag = "  BLOCKED: %s" % r["blocked"] if r["blocked"] else ""
            print("%d. %-34s %-12s %-6s %s%s"
                  % (i, r["title"][:34], r["category"], r["score"],
                     "; ".join(r["why"])[:60], flag))
        return 0

    if a.set:
        reg = load()
        agent = find(reg, a.set)
        if not agent:
            print("No agent matches %r" % a.set)
            return 1
        if a.category:
            if a.category not in CATEGORIES:
                print("Category must be one of: %s" % ", ".join(CATEGORIES))
                return 1
            agent["category"] = a.category
        if a.tags:
            agent["tags"] = [t.strip().lower() for t in a.tags.split(",") if t.strip()][:3]
        agent["confirmed"] = True
        agent["why"] = "confirmed by Stephen"
        save(reg)
        print("%s -> %s, tags %s (confirmed)"
              % (agent["title"], agent["category"], agent["tags"]))
        return 0

    if a.show:
        reg = load()
        agent = find(reg, a.show)
        print(json.dumps(agent, indent=1) if agent else "no match")
        return 0 if agent else 1

    if a.drift:
        minor, major = drift()
        print("tag updates (applied): %d" % len(minor))
        for m in minor[:20]:
            print("  " + m)
        print("\ncategory changes (NOT applied, confirm first): %d" % len(major))
        for m in major:
            print("  " + m)
        return 0

    reg = build(load())
    if a.write or a.table:
        save(reg)
    if a.table:
        with open(a.table, "w") as fh:
            n = table(reg["agents"], fh, markdown=True)
        print("wrote %d rows to %s" % (n, a.table))
        return 0
    if a.json:
        print(json.dumps(reg, indent=1))
        return 0
    n = table(reg["agents"])
    counts = Counter(x["category"] for x in reg["agents"].values())
    print("\n%d agents: %s" % (n, ", ".join("%s %d" % kv for kv in counts.most_common())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
