#!/usr/bin/env python3
"""Two-way channel between Stephen's Apple Notes To Do list and his cmux agents.

Outbound (prepend): meeting follow-ups and anything else an agent owes him go in
near the TOP of the note, immediately after the Strategy section, because the
list is long and he only reads the first page. Appending to the bottom, which is
what the after-meeting skill used to do, is much the same as not writing it down.

Inbound (scan): he writes "claude <instruction>" anywhere in a To Do note, with
or without the @. Every five minutes this reads the notes, finds new ones, and
hands each one to the Chief of Staff workspace to delegate or do. When the work
is finished the agent calls `mark`, which puts a tick and a time next to the
instruction in the note so he can see it was picked up.

House style, measured from his own note on 8 Sep 2026 rather than guessed:
  - Apple Notes multiplies every explicit font-size by 1.2 on import, and it
    COMPOUNDS across writes. All sizes are pre-deflated on the way out so a
    write is size-neutral. Headings are emitted at his 36px ceiling.
  - Nested list items are siblings AFTER </li>, not children inside it. Apple
    Notes rewrites the nested-inside form to the sibling form anyway.
  - Adjacent list blocks MERGE into the first one's type. Emit one list per
    section and nest inside it, never two lists back to back.

Commands:
  prepend --heading "..." --items items.json [--dry-run]
  scan [--dry-run]
  list
  mark <id> "outcome text"
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
STATE = SKILL / "state" / "seen-instructions.json"
BACKUPS = SKILL / "backups"
REGISTRY = Path.home() / ".claude" / "skills" / "cmux" / "references" / "registry.md"
CMUX = "/Applications/cmux.app/Contents/Resources/bin/cmux"
SEND_TASK = Path.home() / ".claude" / "skills" / "cmux" / "scripts" / "send_task.py"

HEADING_PX = 36   # Stephen's stated ceiling. Emitted as the STORED value;
                  # deflate_fonts() pre-shrinks it so Notes' 1.2x import
                  # scaling lands it back on exactly 36.
BODY_PX = 16
DONE_MARK = "✅"

# A bullet fires when it OPENS with "claude", with or without the @ (Stephen,
# 19 Sep 2026: dictation and the phone keyboard both swallow the @). The @ is
# unambiguous and always fires. Bare "claude" needs corroboration, because the
# note is full of prose ABOUT Claude and a heading like "Claude tools" must not
# hand anyone a task: either punctuation after the word, or an imperative verb
# next, and never a word from STOPWORDS.
TRIGGER = re.compile(r"^[\s\-*•–—]*(?:\d+[.)]\s*)?(?P<at>@)?claude\b[ \t]*"
                     r"(?P<punct>[:,\-–—])?[ \t]*(?P<rest>.*)$", re.I | re.S)

# The first word of a real instruction. Extend freely; a verb missing from here
# only means a bare-"claude" line is ignored, never that the wrong thing runs.
IMPERATIVES = {
    "add", "amend", "archive", "arrange", "ask", "book", "build", "buy",
    "cancel", "chase", "check", "compile", "confirm", "create", "delegate",
    "delete", "do", "draft", "email", "expand", "extract", "file", "fill",
    "find", "finish", "fix", "forward", "generate", "get", "give", "help",
    "import", "list", "look", "make", "mark", "merge", "move", "open", "order",
    "please", "port", "prep", "prepare", "print", "put", "read", "refresh",
    "remind", "reply", "research", "review", "run", "save", "schedule",
    "search", "send", "set", "share", "start", "stop", "summarise",
    "summarize", "tell", "update", "upload", "verify", "watch", "write",
}

# Words that make "Claude ..." prose rather than an instruction.
STOPWORDS = {"code", "opus", "sonnet", "haiku", "desktop", "ai", "session",
             "sessions", "agent", "agents", "skill", "skills", "is", "was",
             "can", "could", "should", "has", "have", "and", "or", "via",
             "said", "says", "thinks", "wrote", "keeps", "codes"}


def trigger_match(line):
    """The instruction text if this line opens with the trigger, else None."""
    m = TRIGGER.match(line.strip())
    if not m:
        return None
    rest = m.group("rest").strip(" :-–—")
    if not rest:
        return None
    first = re.split(r"[\s,.:;!?]+", rest, 1)[0].lower().strip("'’\"")
    if not m.group("at"):
        if first in STOPWORDS:
            return None
        if not m.group("punct") and first not in IMPERATIVES:
            return None
    return rest


BLOCK_END = re.compile(r"</li>|</div>|<br\s*/?>", re.I)


def line_spans(body):
    """(text, end offset) for each block-level line of a note's HTML.

    find_instructions and cmd_mark both walk this, so the Nth instruction the
    scan found is the Nth the tick lands on. They used to count differently:
    the scan over stripped text lines, cmd_mark over raw occurrences of the
    literal "@claude" in the HTML. That held together only while the trigger was
    one fixed string that never appeared inside a word.
    """
    out, pos = [], 0
    for m in BLOCK_END.finditer(body):
        text = strip_tags(body[pos:m.start()]).strip()
        if text:
            out.append((text, m.start()))
        pos = m.end()
    text = strip_tags(body[pos:]).strip()
    if text:
        out.append((text, len(body)))
    return out


COS_TITLE = "chief of staff"

NOTE_PREFIX = "To Do"
LOOKBACK_DAYS = 60
MAX_ATTEMPTS = 24      # fast retries (2h at the 5-min cadence) before backing off
STUCK_RETRY_SECS = 3600  # then hourly, forever, still reported every run
SETTLE_SECS = 120      # ignore a note edited more recently than this


# ---------------------------------------------------------------- AppleScript

def osa(script):
    r = subprocess.run(["osascript", "-e", script], capture_output=True,
                       text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError("osascript failed: %s" % r.stderr.strip()[:300])
    return r.stdout.rstrip("\n")


# Scoped to the "Notes" folder on purpose. An unscoped `every note` also walks
# Recently Deleted, which on 8 Sep 2026 returned three notes all called
# "To Do 8th Sept 2026." (two were deleted test copies), and it is 60% slower.
SELECT = '''
tell application "Notes"
  set out to {}
  repeat with n in (notes of folder "Notes" whose name starts with "%s")
    set end of out to (id of n) & "\\t" & ((modification date of n) as «class isot» as string) & "\\t" & (name of n)
  end repeat
  set AppleScript's text item delimiters to linefeed
  return out as text
end tell
''' % NOTE_PREFIX

DISCOVERY_CACHE = SKILL / "state" / "discovered-notes.json"
DISCOVERY_MAX_AGE = 3600   # seconds


def discover_notes(force=False):
    """Find every To Do note. Slow (about 14s), so cached for an hour.

    Apple Notes has no index for this query: it walks the folder and asks each
    note for its name over Apple Events. That is fine hourly and much too slow
    for something running every five minutes, which is why the scan works from
    the pinned note id (0.4s) and only falls back to discovery on a schedule.
    """
    if not force and DISCOVERY_CACHE.exists():
        try:
            c = json.loads(DISCOVERY_CACHE.read_text())
            if time.time() - c.get("at", 0) < DISCOVERY_MAX_AGE:
                return c["notes"]
        except (ValueError, KeyError):
            pass

    notes = []
    for line in osa(SELECT).splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        notes.append({"id": parts[0], "modified": parts[1], "name": parts[2]})
    notes.sort(key=lambda n: n["modified"], reverse=True)
    DISCOVERY_CACHE.parent.mkdir(exist_ok=True)
    DISCOVERY_CACHE.write_text(json.dumps({"at": time.time(), "notes": notes}, indent=1))
    return notes


def todo_notes():
    """The note the scan reads: the pinned one, and only that one.

    Stephen, 21 Sep 2026: pickups come from the current Mac list alone. Reading
    every recent To Do note meant the 17 Sep phone/Mac merge fired three
    instructions twice, once per copy, because ids hash on the note. The old
    behaviour (pinned note first, then any To Do note modified inside
    LOOKBACK_DAYS) is kept below for `target`, which still has to pick a note
    when the pin is missing or points at something deleted.
    """
    pinned = pinned_note()
    if pinned:
        return [pinned]
    return discovered_notes_fallback()


def pinned_note():
    if not PIN.exists():
        return None
    try:
        rec = json.loads(PIN.read_text())
    except (ValueError, KeyError):
        return None
    live = live_name(rec.get("id", ""))
    if live is None:
        return None
    # Refresh the cached name. Stephen retitles the note as the days roll over
    # ("To Do 9th Sept 2026 Mac" became "To Do 21st Sept 2026 Mac"), and a
    # stale copy here misled the 9 Sep diagnosis. Same note, same Core Data id,
    # so nothing in it re-fires on a rename.
    if live != rec.get("name"):
        rec["name"] = live
        PIN.write_text(json.dumps(rec, indent=1))
    return {"id": rec["id"], "name": live, "modified": ""}


def discovered_notes_fallback():
    """Candidates when there is no usable pin.

    Sorted by modification date, never by name: "To Do 10th Sept" sorts BEFORE
    "To Do 8th Sept" alphabetically, which would silently target last month's
    list.
    """
    out = []
    # Old To Do lists ("TO DO Old", "To Do 14 Jan") are archives, not inboxes.
    # Reading them costs half a second each and risks firing on stale text.
    cutoff = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    for n in discover_notes():
        if n["modified"] >= cutoff:
            out.append(n)
    return out


def get_body(note_id):
    return osa('tell application "Notes" to return body of note id "%s"' % note_id)


PIN = SKILL / "state" / "target-note.json"


def live_name(note_id):
    """Current name of a note, or None if it is gone."""
    try:
        return osa('tell application "Notes" to return name of note id "%s"' % note_id)
    except RuntimeError:
        return None


def note_exists(note_id):
    return live_name(note_id) is not None


def target_note():
    """The one note that writes are allowed to touch, pinned by Core Data id.

    Picking "the most recently modified To Do note" is not safe on its own.
    Apple Notes derives a note's NAME from the first line of its body, so any
    copy of the To Do list is instantly also called "To Do 8th Sept 2026." and,
    being newer, sorts above the original. During development on 8 Sep 2026 two
    test clones did exactly that and became the top two candidates.

    So: pin the id once, keep using it, and refuse to guess when two candidates
    share a name rather than risk writing 100KB into the wrong note.
    """
    if PIN.exists():
        try:
            rec = json.loads(PIN.read_text())
            if note_exists(rec["id"]):
                return rec
        except (ValueError, KeyError):
            pass

    cands = todo_notes()
    if not cands:
        raise SystemExit("No To Do note found in the last %d days." % LOOKBACK_DAYS)

    same_name = [c for c in cands if c["name"] == cands[0]["name"]]
    if len(same_name) > 1:
        raise SystemExit(
            "AMBIGUOUS: %d notes are called %r. Refusing to guess which is the real\n"
            "To Do list. Pin it explicitly:\n"
            "    todo_agent.py use-note <id-fragment>\n"
            "Candidates:\n%s" % (
                len(same_name), cands[0]["name"],
                "\n".join("    %s  modified %s" % (c["id"].rsplit("/", 1)[-1],
                                                   c["modified"]) for c in same_name)))

    rec = {"id": cands[0]["id"], "name": cands[0]["name"]}
    PIN.parent.mkdir(exist_ok=True)
    PIN.write_text(json.dumps(rec, indent=1))
    return rec


NOTES_SCALE = 1.2      # Apple Notes multiplies every explicit size on import
NOTES_DEFAULT_PX = 16  # ...except this one, which is the default and is left alone


def deflate_fonts(html):
    """Pre-shrink font sizes so Apple Notes' import scaling lands them back home.

    Apple Notes multiplies every explicit font-size by 1.2 when a body is set,
    and the effect COMPOUNDS: a 20px heading becomes 24, then 29, then 35, then
    42 across four writes. Measured on 8 Sep 2026. This is why Stephen's To Do
    note carries 158px headings and reads as overwhelming: it is the fossil
    record of about eight past whole-body rewrites by various agents.

    Writing a body without this correction makes his note permanently worse every
    single time. 16px is a fixed point (Notes treats it as the default) and is
    left untouched.
    """
    def fix(m):
        px = int(m.group(1))
        if px == NOTES_DEFAULT_PX:
            return m.group(0)
        return "font-size: %dpx" % max(1, round(px / NOTES_SCALE))
    return re.sub(r"font-size: (\d+)px", fix, html)


def cap_fonts(html, ceiling):
    """Clamp heading sizes to a ceiling, as stored (apply BEFORE deflate_fonts)."""
    def fix(m):
        px = int(m.group(1))
        return "font-size: %dpx" % min(px, ceiling)
    return re.sub(r"font-size: (\d+)px", fix, html)


def set_body(note_id, body, tag, cap=None):
    """Write a note body, keeping a timestamped copy of what was there before.

    The To Do note is 100KB of hand-curated work. Every write is backed up first
    so that a bad edit is an inconvenience rather than a loss. The new body goes
    via a file because AppleScript string literals cannot carry 100KB safely.
    """
    BACKUPS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    before = get_body(note_id)
    (BACKUPS / ("%s-%s-before.html" % (stamp, tag))).write_text(before)

    if cap:
        body = cap_fonts(body, cap)
    body = deflate_fonts(body)

    tmp = BACKUPS / ("%s-%s-new.html" % (stamp, tag))
    tmp.write_text(body)
    osa('''
tell application "Notes"
  set f to (POSIX file "%s")
  set newBody to (read f as «class utf8»)
  set body of note id "%s" to newBody
end tell
''' % (tmp, note_id))
    return before


# ------------------------------------------------------------------ HTML bits

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def span(text, px=BODY_PX, bold=False):
    inner = '<span style="font-size: %dpx">%s</span>' % (px, esc(text))
    return "<b>%s</b>" % inner if bold else inner


def render_section(heading, items, ordered=False):
    """One heading plus ONE list block. Sub-items nest as sibling lists.

    items: [{"text": str, "bold_lead": str|None, "children": [str, ...]}, ...]
    """
    tag = "ol" if ordered else 'ul class="Apple-dash-list"'
    close = "ol" if ordered else "ul"
    out = ['<div>%s%s</div>' % (span(heading, HEADING_PX, bold=True),
                                '<span style="font-size: %dpx"><br></span>' % BODY_PX)]
    out.append("<%s>" % tag)
    for it in items:
        lead = it.get("bold_lead")
        body = span(it["text"])
        cell = (span(lead, bold=True) + body) if lead else body
        out.append("<li>%s</li>" % cell)
        kids = it.get("children") or []
        if kids:
            out.append("<%s>" % tag)
            for k in kids:
                out.append("<li>%s</li>" % span(k))
            out.append("</%s>" % close)
    out.append("</%s>" % close)
    return "\n".join(out) + "\n"


def close_of_list(body, start):
    """Index just past the list element that begins at `start`, nesting aware."""
    depth, i = 0, start
    token = re.compile(r"</?(?:ul|ol)\b[^>]*>", re.I)
    while i < len(body):
        m = token.search(body, i)
        if not m:
            return len(body)
        depth += 1 if not m.group(0).startswith("</") else -1
        i = m.end()
        if depth == 0:
            return i
    return len(body)


def strategy_insert_point(body):
    """Where a new section goes: right after the Strategy heading and its list.

    Falls back to just below the note title if there is no Strategy section,
    which is still far better than the bottom.
    """
    m = re.search(r">\s*Strategy\s*<", body, re.I)
    if not m:
        first = re.search(r"</div>", body, re.I)
        return first.end() if first else 0

    end_div = body.find("</div>", m.end())
    pos = (end_div + len("</div>")) if end_div != -1 else m.end()

    nxt = re.compile(r"\S").search(body, pos)
    if nxt and re.match(r"<(ul|ol)\b", body[nxt.start():], re.I):
        pos = close_of_list(body, nxt.start())
    return pos


def insert_section(body, section):
    at = strategy_insert_point(body)
    return body[:at] + "\n" + section + body[at:]


# --------------------------------------------------------------- instructions

def strip_tags(html):
    txt = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    txt = re.sub(r"</(div|li|p|h\d)>", "\n", txt, flags=re.I)
    txt = re.sub(r"<[^>]+>", "", txt)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&nbsp;", " "), ("&quot;", '"'), ("&#39;", "'")):
        txt = txt.replace(a, b)
    return txt


def find_instructions(note):
    """Every unhandled instruction line, with the heading it sits under."""
    body = get_body(note["id"])
    found, heading = [], ""
    occurrence = 0
    for line, _end in line_spans(body):
        # The trigger must OPEN the bullet. Mentioning Claude mid-sentence, as
        # the note's own "how to use this" line does, is prose about the tool
        # rather than an instruction to it, and firing on that would hand the
        # Chief of Staff a fragment of its own documentation.
        instruction = trigger_match(line)
        if instruction is None:
            # Short, un-bulleted lines read as section headings.
            if len(line) < 70 and line[:1] not in "-*0123456789":
                heading = line
            continue
        # Counted over EVERY trigger line, ticked ones included, so that adding
        # a tick never shifts the index of the lines below it.
        idx = occurrence
        occurrence += 1
        if DONE_MARK in line:
            continue
        instruction = instruction.split(DONE_MARK)[0].strip()
        # Hash on the note's Core Data ID, never its NAME. Apple Notes takes the
        # name from the first line, so retitling "To Do 8th Sept" to "To Do 9th
        # Sept" silently changes every id in the note. On 9 Sep 2026 that, plus a
        # stale name cached in the pin file, meant one instruction was evaluated
        # under two different ids.
        ident = hashlib.sha1(
            ("%s|%s" % (note["id"], instruction)).encode("utf-8")).hexdigest()[:12]
        found.append({"id": ident, "note_id": note["id"], "note": note["name"],
                      "heading": heading, "text": instruction,
                      "occurrence": idx, "line": line})
    return found


def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except ValueError:
            pass
    return {"delivered": {}}


def save_state(s):
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(s, indent=1))


# ---------------------------------------------------------------------- cmux

def workspace_for(title_norm):
    # Live tree FIRST: workspace numbers are reassigned on every cmux restart
    # or reorder, and a stale registry sent every delivery to the wrong
    # workspace for two days after the 13 Sep 2026 reboot. The registry is
    # only a fallback for when the cmux socket is too congested to answer.
    out = cmux("tree", "--all").stdout
    for m in re.finditer(r'workspace (workspace:\d+) "([^"]*)"', out):
        t = re.sub(r"^[^0-9A-Za-z]+", "", m.group(2)).strip().lower()
        if t == title_norm:
            return m.group(1)
    if not REGISTRY.exists():
        return None
    for line in REGISTRY.read_text().splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        t = re.sub(r"^[^0-9A-Za-z]+", "", cells[2]).strip().lower()
        if t == title_norm:
            m = re.search(r"workspace:(\d+)", cells[1])
            if m:
                return "workspace:%s" % m.group(1)
    return None


class _Dead:
    """Stand-in result for a cmux call that never came back."""
    returncode = 1
    stdout = ""
    stderr = "cmux did not answer"


def cmux(*args, timeout=30):
    """Call cmux, tolerating a congested socket.

    cmux's socket goes unresponsive while several sessions are busy: on 8 Sep
    2026 `cmux tree` answered in 0.18s at 14:16 and was timing out at 15s by
    14:50. An unattended job must not hang or crash on that.
    """
    # Broken pipe (errno 32) comes back as rc!=0 with the error on stderr, not
    # as an exception. It is transient (socket congested while sessions are
    # busy), so retry a few times before giving up — without this, a busy
    # afternoon burned all 24 fast retries in 12 minutes on 14 Sep 2026.
    for attempt in range(3):
        try:
            r = subprocess.run([CMUX] + list(args), capture_output=True,
                               text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            r = _Dead()
        if r.returncode == 0 or "Broken pipe" not in (r.stderr or ""):
            return r
        time.sleep(2)
    return r


def deliver(ws, message):
    """Hand a message to a workspace and confirm it actually started.

    The message goes as ONE short line pointing at a file, because a multi-line
    paste arrives with a "paste again to expand" hint and the first Enter only
    expands it, leaving the task in the input box looking delivered. Shared with
    every other delegation through the cmux skill's send_task.py, so there is
    one implementation of "did it actually start" rather than three.
    """
    brief = SKILL / "state" / "pickups"
    brief.mkdir(parents=True, exist_ok=True)
    path = brief / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-pickup.md")
    path.write_text(message.rstrip() + "\n")
    try:
        r = subprocess.run(["/usr/bin/python3", str(SEND_TASK), "--workspace", ws,
                            "--file", str(path)], capture_output=True, text=True,
                           timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if r.returncode != 0:
        # Print what the target's screen actually showed. A delivery that failed
        # silently is the 9 Sep 2026 failure all over again.
        print((r.stdout or r.stderr or "").strip()[:400])
    return r.returncode == 0


PROMPT = """[Automatic pickup from Stephen's Apple Notes To Do list, {stamp}]

Stephen wrote this instruction under the heading "{heading}" in the note "{note}":

    {text}

Act on it as Chief of Staff: either do it yourself, or delegate it to the right
workspace and confirm the target session actually started. Route by the NATURE of
the task rather than its topic alone (tooling and pipeline bugs go to "my ai tools", not
to the content owner). Check the registry first:
    ~/.claude/skills/cmux/references/registry.md

When the work is done or delegated, record it back in the note so Stephen can see
it was picked up:
    python3 ~/.claude/skills/todo-agent/scripts/todo_agent.py mark {ident} "<short outcome>"

Standing rule: any email is saved as a DRAFT for Stephen to review. Never dispatch
one on the strength of this instruction alone."""


def cmd_scan(a):
    state = load_state()
    notes = todo_notes()
    if not notes:
        print("No To Do notes modified in the last %d days." % LOOKBACK_DAYS)
        return 0

    # Apple Notes saves as he types, so a scan can catch a half-written line.
    # On 9 Sep 2026 at 10:59 this fired on the single word "eve" while Stephen
    # was still typing "every day at midday...". Wait for the note to settle.
    settled = []
    for n in notes:
        try:
            mod = osa('tell application "Notes" to return (modification date of '
                      'note id "%s") as «class isot» as string' % n["id"])
            age = (datetime.now() - datetime.fromisoformat(mod)).total_seconds()
        except (RuntimeError, ValueError):
            age = SETTLE_SECS  # cannot tell, so do not hold it up
        if age < SETTLE_SECS:
            print("%s: '%s' edited %ds ago, waiting for it to settle"
                  % (datetime.now().strftime("%H:%M"), n["name"], int(age)))
            continue
        settled.append(n)

    pending = []
    for n in settled:
        for ins in find_instructions(n):
            if ins["id"] not in state["delivered"]:
                pending.append(ins)

    if not pending:
        print("%s: nothing new (%d note(s) scanned)"
              % (datetime.now().strftime("%H:%M"), len(notes)))
        return 0

    ws = workspace_for(COS_TITLE)
    if not ws:
        print("Chief of staff workspace not found in the registry. "
              "Run refresh_registry.py. Nothing handed over.")
        return 1

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    for ins in pending:
        msg = PROMPT.format(stamp=stamp, heading=ins["heading"] or "(no heading)",
                            note=ins["note"], text=ins["text"], ident=ins["id"])
        if a.dry_run:
            print("WOULD HAND TO %s [%s]: %s" % (ws, ins["id"], ins["text"][:90]))
            continue

        tries = state.setdefault("attempts", {})
        last = state.setdefault("last_try", {})
        n_so_far = tries.get(ins["id"], 0)
        if n_so_far > MAX_ATTEMPTS and time.time() - last.get(ins["id"], 0) < STUCK_RETRY_SECS:
            # Past the fast-retry window, so back off to hourly. Still reported
            # every run, because the whole point is that it must not go quiet.
            print("STUCK [%s] %d attempts, undelivered: %s"
                  % (ins["id"], n_so_far, ins["text"][:70]))
            continue
        last[ins["id"]] = time.time()
        ok = deliver(ws, msg)
        if not ok:
            # Keep retrying, and NEVER move a failed delivery into `delivered`.
            # The 9 Sep 2026 failure: cmux's socket returned "Broken pipe" all
            # morning, three attempts burned in fifteen minutes, the instruction
            # was filed as delivered-but-not-started, and every run afterwards
            # reported "nothing new". Stephen's request vanished silently while
            # the job looked healthy. A transient outage must not be able to do
            # that, so retries now run for hours, and an instruction that is
            # still stuck is shouted about on EVERY run until it goes through.
            tries = state.setdefault("attempts", {})
            tries[ins["id"]] = tries.get(ins["id"], 0) + 1
            n = tries[ins["id"]]
            if n <= MAX_ATTEMPTS:
                print("NOT STARTED [%s] %s  (attempt %d of %d, retrying)"
                      % (ins["id"], ins["text"][:70], n, MAX_ATTEMPTS))
            else:
                print("STUCK [%s] after %d attempts, still undelivered: %s"
                      % (ins["id"], n, ins["text"][:70]))
            continue
        state["delivered"][ins["id"]] = {
            "text": ins["text"], "note": ins["note"], "note_id": ins["note_id"],
            "occurrence": ins["occurrence"], "handed_over": stamp,
            "workspace": ws, "started": True}
        state.get("attempts", {}).pop(ins["id"], None)
        print("handed to %s [%s] %s" % (ws, ins["id"], ins["text"][:80]))
    if not a.dry_run:
        save_state(state)
        cmux("workspace-action", "--action", "pin", "--workspace", ws)
        cmux("reorder-workspace", "--workspace", ws, "--index", "0")
    return 0


def cmd_mark(a):
    state = load_state()
    rec = state["delivered"].get(a.ident)
    if not rec:
        print("Unknown instruction id %s" % a.ident)
        return 1
    body = get_body(rec["note_id"])

    # Same walk the scan used, so the Nth trigger line here is the Nth there.
    hits = [(text, end) for text, end in line_spans(body) if trigger_match(text)]
    # Prefer the line that still carries this instruction's own words. The
    # index is the fallback: it is only correct while the note's trigger lines
    # keep their order, and Stephen reorders this note constantly.
    want = (rec.get("text") or "")[:40].lower()
    at = None
    if want:
        matches = [(text, end) for text, end in hits if want in text.lower()]
        # The note usually carries the line twice: the live one and an older
        # ticked copy (the 17 Sep phone/Mac merge duplicated many). Prefer the
        # unticked one; a tick on the already-ticked copy tells him nothing.
        fresh = [end for text, end in matches if DONE_MARK not in text]
        if len(fresh) == 1:
            at = fresh[0]
        elif len(matches) == 1:
            at = matches[0][1]
    if at is None:
        idx = rec.get("occurrence", 0)
        # The index is a fallback and it goes stale the moment he edits the
        # note, which is constantly: on 19 Sep 2026 it put a Sysmex outcome on
        # the note's own "how to give me work here" line. Only trust it when
        # the line it points at still looks like this instruction.
        if idx >= len(hits) or want[:20] not in hits[idx][0].lower():
            print("Could not find that instruction in the note; it has been "
                  "edited or removed. Nothing written.")
            return 1
        at = hits[idx][1]
    stamp = datetime.now().strftime("%H:%M")
    tail = " %s %s (%s)" % (DONE_MARK, esc(a.outcome), stamp)
    # Land the tick at the END of the bullet. Splicing it straight after the
    # trigger word pushes the outcome in front of the instruction it refers to,
    # so the line reads back to front.
    new = body[:at] + tail + body[at:]
    set_body(rec["note_id"], new, "mark-" + a.ident)
    rec["done"] = stamp
    rec["outcome"] = a.outcome
    save_state(state)
    print("marked %s in %s" % (a.ident, rec["note"]))
    return 0


def cmd_list(_):
    state = load_state()
    notes = todo_notes()
    live = [i for n in notes for i in find_instructions(n)]
    print("%d open instruction(s) for claude:" % len(live))
    for i in live:
        seen = "picked up" if i["id"] in state["delivered"] else "NEW"
        print("  [%s] %-10s %s" % (i["id"], seen, i["text"][:88]))
    return 0


def cmd_target(_):
    note = target_note()
    print("Writes go to: %s\n  id %s" % (note["name"], note["id"]))
    return 0


def cmd_normalise(a):
    """Pull runaway heading sizes back down to the cap.

    Repairs the damage left by any writer that set the body without deflating
    first. Each such write multiplies every size by 1.2, so headings climb
    without limit: Stephen's note reached 228px by 9 Sep 2026.
    """
    note = target_note()
    body = get_body(note["id"])
    sizes = sorted({int(m.group(1)) for m in re.finditer(r"font-size: (\d+)px", body)})
    over = [s for s in sizes if s > a.cap]
    print("Note: %s" % note["name"])
    print("Sizes present: %s" % sizes)
    print("Above the %dpx cap: %s" % (a.cap, over or "none"))
    if not over:
        return 0
    if a.dry_run:
        print("Dry run. Re-run without --dry-run to clamp them.")
        return 0
    set_body(note["id"], body, "normalise", cap=a.cap)
    after = sorted({int(m.group(1)) for m in re.finditer(r"font-size: (\d+)px",
                                                        get_body(note["id"]))})
    print("Sizes now: %s" % after)
    return 0


def cmd_use_note(a):
    match = [n for n in todo_notes() if a.fragment in n["id"]]
    if len(match) != 1:
        print("%d notes match %r. Be more specific." % (len(match), a.fragment))
        for n in todo_notes():
            print("   %s  %s  %s" % (n["id"].rsplit("/", 1)[-1], n["modified"], n["name"]))
        return 1
    PIN.parent.mkdir(exist_ok=True)
    PIN.write_text(json.dumps({"id": match[0]["id"], "name": match[0]["name"]}, indent=1))
    print("Pinned: %s" % match[0]["name"])
    return 0


def cmd_prepend(a):
    items = json.loads(Path(a.items).read_text())
    section = render_section(a.heading, items, ordered=a.ordered)
    note = target_note()
    body = get_body(note["id"])
    new = insert_section(body, section)
    if a.dry_run:
        at = strategy_insert_point(body)
        print("Target note: %s" % note["name"])
        print("Insert at offset %d, just after the Strategy section." % at)
        print("--- context immediately before the insert ---")
        print(body[max(0, at - 240):at])
        print("--- would insert ---")
        print(section)
        return 0
    set_body(note["id"], new, "prepend")
    print("Added '%s' (%d items) to '%s', below Strategy."
          % (a.heading, len(items), note["name"]))
    return 0


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    pre = sub.add_parser("prepend")
    pre.add_argument("--heading", required=True)
    pre.add_argument("--items", required=True, help="JSON file of items")
    pre.add_argument("--ordered", action="store_true", help="numbered instead of dashed")
    pre.add_argument("--dry-run", action="store_true")
    pre.set_defaults(func=cmd_prepend)

    sc = sub.add_parser("scan")
    sc.add_argument("--dry-run", action="store_true")
    sc.set_defaults(func=cmd_scan)

    sub.add_parser("list").set_defaults(func=cmd_list)
    sub.add_parser("target").set_defaults(func=cmd_target)

    nm = sub.add_parser("normalise")
    nm.add_argument("--cap", type=int, default=HEADING_PX)
    nm.add_argument("--dry-run", action="store_true")
    nm.set_defaults(func=cmd_normalise)

    un = sub.add_parser("use-note")
    un.add_argument("fragment", help="part of the note id, e.g. p32054")
    un.set_defaults(func=cmd_use_note)

    mk = sub.add_parser("mark")
    mk.add_argument("ident")
    mk.add_argument("outcome")
    mk.set_defaults(func=cmd_mark)

    a = p.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
