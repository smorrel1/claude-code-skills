#!/usr/bin/env python3
"""Send a task to a cmux workspace and PROVE it was submitted.

`cmux send` puts text in the target's input box; it does not submit it. Enter
submits, except when it does not: a multi-line paste arrives as a block with a
"paste again to expand" hint and the first Enter only expands it. The task then
sits in the box looking delivered. Seen twice on 21 Sep 2026, and the reason the
cmux skill has said "ALWAYS re-read the screen after ~8s" since 8 Sep.

Two defences, because the retry alone has never been enough:

1. SEND ONE LINE. Anything multi-line, or longer than INLINE_MAX, is written to
   a file and the workspace is sent a single short line pointing at it. A
   one-line send has no paste hint and submits on the first Enter.
2. VERIFY, THEN RETRY. Poll the screen for a running session; press Enter again
   up to MAX_ENTERS times; exit non-zero with the last screen if it never
   started, so the caller can report a failure instead of assuming success.

    send_task.py --workspace workspace:4 "chase the YHEC quote"
    send_task.py --workspace workspace:4 --file /path/to/brief.md
    echo "long brief..." | send_task.py --workspace workspace:4 -

Arrival is not proof of work either. On 30 Sep 2026 the IUK session took a brief
and did nothing, because its usage credits were exhausted: the screen looked
delivered and the sender reported success. So delivery is confirmed in the
TARGET'S OWN TRANSCRIPT: the marker phrase must appear in a user entry there
(which also catches a brief landing in the wrong session after a reorder), and an
assistant turn must follow it. An API error entry, or a screen mentioning a usage
limit, credits, a rate limit or /login, is a FAILED delegation to re-route.

Exit 0 = confirmed: the brief is in that session's transcript and it has started.
Exit 1 = not submitted, or never confirmed; nothing was assumed.
Exit 2 = arrived but the session cannot work it (usage limit, API error). Pick the
         next idle candidate from idle_rank.py and say which session failed.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CMUX = "/Applications/cmux.app/Contents/Resources/bin/cmux"
SPOOL = os.path.expanduser("~/.claude/skills/cmux/state/tasks")
INLINE_MAX = 300       # longer than this goes to a file, even on one line
MAX_ENTERS = 3
POLL_SECS = 2
POLLS = 6              # 12s of looking before deciding it did not start

RUNNING = ("esc to interrupt", "⏺", "✻", "✢")
PROJECTS = os.path.expanduser("~/.claude/projects")
CONFIRM_SECS = 75          # point 9: about 60s, plus slack for a slow first turn

# Point 8: a session that cannot work the brief. Screen text, lowercased.
BLOCKED = ("usage limit", "out of credits", "credit balance", "rate limit",
           "overloaded", "please run /login", "upgrade to")


def resolve_workspace(name):
    """Turn a workspace NAME into its current ref. Names, never numbers.

    Numbers drift on every reorder, and twice now a brief has landed in the
    wrong session off a stale one: 29 Sep (a grants brief into a finance session) and
    30 Sep (an email-tooling report into "health personal"). Stephen's rule,
    30 Sep 2026: always address a workspace by name.

    Matching is case-insensitive, exact first, then unique substring. Anything
    ambiguous or unknown exits rather than guessing, and prints the candidates.
    """
    import idle_rank
    rows = idle_rank.collect()
    titles = {}
    for r in rows:
        titles.setdefault(r.get("workspace") or "", r)
    want = name.strip().lower()
    exact = [t for t in titles if t.lower() == want]
    if len(exact) == 1:
        return titles[exact[0]]["workspace_ref"], exact[0]
    part = [t for t in titles if want in t.lower()]
    if len(part) == 1:
        return titles[part[0]]["workspace_ref"], part[0]
    if not part:
        sys.exit("No workspace named %r. Open workspaces:\n%s"
                 % (name, "\n".join("    " + t for t in sorted(titles) if t)))
    sys.exit("%d workspaces match %r. Use the full name:\n%s"
             % (len(part), name, "\n".join("    " + t for t in sorted(part))))


def session_for(workspace=None, surface=None):
    """Which Claude conversation is bound to the panel being addressed.

    Resolved live from the cmux tree and state file, never from a cached number:
    workspace ids drift on every reorder, and on 29 Sep 2026 a brief meant for the
    grants session landed in a finance session off a stale id.
    """
    try:
        import idle_rank
        rows = idle_rank.collect()
    except Exception as exc:                        # noqa: BLE001
        print("warning: could not resolve the target session (%s); falling back "
              "to screen-only verification." % exc)
        return None
    for r in rows:
        if surface and r["surface_ref"] == surface:
            return r
    for r in rows:
        if workspace and r["workspace_ref"] == workspace and r["focused"]:
            return r
    for r in rows:
        if workspace and r["workspace_ref"] == workspace:
            return r
    return None


def transcript_path(session_id):
    hits = glob.glob(os.path.join(PROJECTS, "*", "%s.jsonl" % session_id))
    return hits[0] if hits else None


def entries(path):
    out = []
    try:
        blob = open(path, "rb").read()
    except OSError:
        return out
    for line in blob.splitlines():
        line = line.strip()
        if not line.startswith(b"{"):
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def is_prompt(e):
    """A real prompt, not a tool result.

    Tool results are also type "user", and a delegation's own output quotes the
    marker back, so matching any user entry would let a session confirm itself.
    """
    if e.get("type") != "user":
        return False
    content = (e.get("message") or {}).get("content")
    if isinstance(content, list):
        return not any(isinstance(c, dict) and c.get("type") == "tool_result"
                       for c in content)
    return True


def entry_text(e):
    msg = e.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            (c.get("text") or c.get("name") or "") for c in content
            if isinstance(c, dict))
    return ""


def confirm(target, row, marker, deadline):
    started_at = time.time()
    """Points 5, 7, 8, 9: the brief is in THIS session and it has started.

    Returns (status, detail) where status is one of "running", "blocked",
    "arrived-idle", "unknown".
    """
    if not row or not row.get("session_full"):
        return "unknown", "no session bound to that panel"
    path = transcript_path(row["session_full"])
    if not path:
        return "unknown", "no transcript for session %s" % row["session"]

    seen_marker = False
    while time.time() < deadline:
        # Whole file, not a tail window: a busy session can append hundreds of
        # entries between the brief arriving and the check.
        es = entries(path)
        at = None
        for i, e in enumerate(es):
            if marker and is_prompt(e) and marker in entry_text(e):
                at = i
        if at is not None:
            seen_marker = True
            after = es[at + 1:]
            for e in after:
                if e.get("isApiErrorMessage"):
                    return "blocked", ("API error after the brief: %s"
                                       % entry_text(e)[:160])
        else:
            after = []
        scr = screen(target)
        low = scr.lower()
        hit = next((b for b in BLOCKED if b in low), None)
        if hit:
            return "blocked", "screen says %r" % hit
        if seen_marker:
            # Point 7: an assistant turn AFTER the brief, not just its arrival.
            if any(e.get("type") == "assistant" for e in after):
                return "running", ("assistant turn after the brief in %s"
                                   % os.path.basename(path))
            if any(m in scr for m in RUNNING):
                return "running", "spinner up, brief seen in its transcript"
        time.sleep(3)

    if seen_marker:
        return "arrived-idle", ("brief is in %s but no assistant turn inside %ds"
                                % (os.path.basename(path),
                                   round(time.time() - started_at)))
    return "unknown", ("marker %r never appeared in %s, so it may have landed in "
                       "another panel" % (marker, os.path.basename(path)))


def cmux(*args, timeout=30):
    """Call cmux, tolerating the socket going unresponsive under load."""
    for _ in range(3):
        try:
            r = subprocess.run([CMUX] + list(args), capture_output=True,
                               text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            time.sleep(2)
            continue
        if r.returncode == 0 or "Broken pipe" not in (r.stderr or ""):
            return (r.stdout or "") + (r.stderr or "")
        time.sleep(2)
    return ""


def screen(target):
    return cmux("read-screen", *target, "--lines", "16")


def started(target):
    """Sampled over several seconds: a fast task can finish before one look."""
    scr = ""
    for _ in range(POLLS):
        scr = screen(target)
        if any(s in scr for s in RUNNING):
            return True, scr
        time.sleep(POLL_SECS)
    return False, scr


def slugify(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(words[:5]) or "task"


def spool(text, slug=None):
    """Park a long or multi-line task in a file and return its path.

    Named <date>-<slug>-brief.md so the spool is still readable a week later.
    """
    os.makedirs(SPOOL, exist_ok=True)
    stem = "%s-%s" % (datetime.now().strftime("%Y%m%d"), slug or slugify(text))
    path = os.path.join(SPOOL, "%s-brief.md" % stem)
    if os.path.exists(path):
        path = os.path.join(SPOOL, "%s-%s-brief.md"
                            % (stem, datetime.now().strftime("%H%M%S")))
    with open(path, "w") as f:
        f.write(text.rstrip() + "\n")
    return path


def send_task(target, text, slug=None):
    """Returns (submitted, line, marker, screen). The marker is the phrase to
    grep for in the target's transcript to prove the brief reached it."""
    text = text.strip()
    if "\n" in text or len(text) > INLINE_MAX:
        path = spool(text, slug)
        marker = os.path.basename(path).replace("-brief.md", "")
        line = ("Task for you, the full brief is in %s: read that file and act "
                "on it now (marker: %s)." % (path, marker))
    else:
        line = text
        marker = text[:60]

    cmux("send", *target, line)
    time.sleep(1)
    for attempt in range(MAX_ENTERS):
        cmux("send-key", *target, "Enter")
        time.sleep(3)
        ok, scr = started(target)
        if ok:
            return True, line, marker, scr
        # Still sitting in the input box, so Enter did not submit it. Pressing
        # Enter at an empty prompt is a no-op, so a spare press costs nothing.
    return False, line, marker, scr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", metavar="NAME",
                    help="workspace NAME (not a number). Numbers drift on every "
                         "reorder and have misrouted briefs twice")
    ap.add_argument("--surface")
    ap.add_argument("--window")
    ap.add_argument("--file", help="read the task text from this file")
    ap.add_argument("--slug", help="name the spooled brief file")
    ap.add_argument("--no-confirm", action="store_true",
                    help="skip transcript confirmation (screen proof only)")
    ap.add_argument("text", nargs="?", help='task text, or - for stdin')
    a = ap.parse_args()

    if not (a.workspace or a.surface):
        sys.exit("Give --workspace NAME or --surface.")

    if a.workspace:
        if re.fullmatch(r"(workspace:)?\d+", a.workspace.strip()):
            sys.exit("Address the workspace by NAME, not %r. Numbers drift on every\n"
                     "reorder; on 30 Sep 2026 a brief went to \"health personal\"\n"
                     "because workspace:6 had changed hands since it was looked up.\n"
                     "Run:  cmux tree --all | grep 'workspace workspace:'" % a.workspace)
        a.workspace, resolved_title = resolve_workspace(a.workspace)
        print("workspace %r -> %s" % (resolved_title, a.workspace))
    target = []
    for flag, val in (("--workspace", a.workspace), ("--surface", a.surface),
                      ("--window", a.window)):
        if val:
            target += [flag, val]

    if a.file:
        text = open(a.file).read()
    elif a.text == "-" or a.text is None:
        text = sys.stdin.read()
    else:
        text = a.text
    if not text.strip():
        sys.exit("Nothing to send.")

    row = None if a.no_confirm else session_for(a.workspace, a.surface)
    if row:
        print("target: %s  %s %s  session %s  idle %sh"
              % (row["workspace"], row["workspace_ref"], row["surface_ref"],
                 row["session"], row["idle_hours"]))

    ok, line, marker, scr = send_task(target, text, a.slug)
    where = a.workspace or a.surface
    if not ok:
        print("NOT SUBMITTED to %s after %d Enter(s). Nothing is running there.\n"
              "Line: %s\nLast screen:\n%s"
              % (where, MAX_ENTERS, line[:90], scr))
        return 1
    if a.no_confirm:
        print("DELIVERED to %s (unconfirmed): %s" % (where, line[:90]))
        return 0

    status, detail = confirm(target, row, marker, time.time() + CONFIRM_SECS)
    label = row["workspace"] if row else where
    if status == "running":
        print("CONFIRMED: %s is working it (%s)" % (label, detail))
        return 0
    if status == "blocked":
        print("FAILED at %s: it took the brief but cannot work it. %s\n"
              "Re-route: take the next candidate from idle_rank.py and tell the "
              "Chief of staff which session failed and why." % (label, detail))
        return 2
    print("UNCONFIRMED at %s: %s\nLast screen:\n%s" % (label, detail, scr))
    return 1


if __name__ == "__main__":
    sys.exit(main())
