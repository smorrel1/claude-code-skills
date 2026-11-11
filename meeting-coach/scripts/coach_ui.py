#!/usr/bin/env python3
"""The coach's screen and its question channel.

Stephen could not use the coach during a call on 10 and 11 Nov: the terminal
carried far too much text, lines wrapped and scrolled as he was trying to
read, he did not know the hotkeys, and he could not find where to type a
question. Nothing was wrong with the advice, only with where it appeared.

So the terminal stops being the interface:

  - Alerts go to a page, ~/coach-alerts.html, in its own Safari window. The
    newest is one line in very large type; the three before it sit underneath,
    small and grey. The page refreshes itself, so nothing has to be clicked.
  - Questions are typed into an Apple Note called "Ask coach", polled every
    15 seconds. A note is somewhere he already has open, and it does not
    steal focus from the call.
  - The terminal prints a single heartbeat line, so he can see it is alive
    without reading it.

    coach_ui.py init                  write the page, open it, show the how-to
    coach_ui.py alert "<one line>"    put an alert on the page
    coach_ui.py watch                 poll the note, print new questions
    coach_ui.py watch --once          one poll, for tests
    coach_ui.py demo <transcript>     replay a recorded transcript into the page
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

# Overridable so a test or a rehearsal cannot clobber the page a LIVE call is
# writing to. Found the hard way on 11 Nov 2026: the i4i interview coach was
# updating ~/coach-alerts.html while this was being built.
PAGE = os.path.expanduser(os.environ.get("COACH_PAGE", "~/coach-alerts.html"))
STATE = os.path.expanduser(os.environ.get("COACH_UI_STATE", "~/.coach/ui-state.json"))
NOTE = "Ask coach"
POLL_SECS = 15
KEEP = 4          # the big one plus three underneath

HOW_TO = [
    "Questions: type into the Apple Note \"Ask coach\". Picked up within 15s.",
    "Answers and alerts appear here, biggest line is the newest.",
    "Press a in the answer_key terminal to answer the last question aloud.",
    "This page refreshes itself. Leave it on a second screen.",
    "Nothing to read in the terminal: it only shows a heartbeat.",
]


def load():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"alerts": [], "seen_question": ""}


def save(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w"))


def render(alerts, starting=False):
    def esc(t):
        return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    top = esc(alerts[0]["text"]) if alerts else (
        "Coach ready. Type a question into the Apple Note \"Ask coach\".")
    old = "".join('<div class="old"><span class="t">%s</span> %s</div>'
                  % (a["at"], esc(a["text"])) for a in alerts[1:KEEP])
    # Always on, not only at the start. Stephen's complaint was that he did
    # not know the hotkeys or where to type; a reminder that disappears the
    # moment the first alert lands does not fix that. It is small, grey and
    # pinned to the bottom, so it costs nothing while being there when needed.
    if True:
        how = ('<div id="how"><b>How to use</b>'
               + "".join("<div>%d. %s</div>" % (i, esc(h))
                         for i, h in enumerate(HOW_TO, 1)) + "</div>")
    return """<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="5"><title>Coach</title>
<style>
 body{font-family:-apple-system,Helvetica,Arial;margin:30px 34px;background:#111;color:#fff}
 /* One line, very large. He is glancing at this between sentences, so it
    has to be readable from a metre away without hunting for it. */
 #top{font-size:46px;line-height:1.22;font-weight:700;margin-bottom:30px}
 .old{font-size:16px;color:#8a8a8a;margin:7px 0;line-height:1.35}
 .old .t{color:#555}
 #how{position:fixed;bottom:26px;left:34px;font-size:13px;color:#6a6a6a;line-height:1.6}
 #how b{color:#999;display:block;margin-bottom:3px}
 #clock{font-size:12px;color:#555;position:fixed;bottom:10px;right:14px}
</style></head><body>
<div id="top">%s</div>
%s
%s
<div id="clock">%s</div>
</body></html>""" % (top, old, how, datetime.now().strftime("%H:%M:%S"))


def write_page(alerts, starting=False):
    with open(PAGE, "w") as f:
        f.write(render(alerts, starting))


def open_window():
    """Its own Safari window, not a tab buried behind the call."""
    script = '''
      tell application "Safari"
        make new document with properties {URL:"file://%s"}
        activate
      end tell''' % PAGE
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=30)


def note_body(name=NOTE):
    p = subprocess.run(
        ["osascript", "-e",
         'tell application "Notes" to tell folder "Notes" to '
         'if (exists note "%s") then return body of note "%s"' % (name, name)],
        capture_output=True, text=True, timeout=30)
    return p.stdout.strip()


def ensure_note(name=NOTE):
    subprocess.run(
        ["osascript", "-e",
         'tell application "Notes" to tell folder "Notes" to '
         'if not (exists note "%s") then make new note with properties '
         '{name:"%s", body:"<div>%s</div><div>Type a question on a new line.</div>"}'
         % (name, name, name)],
        capture_output=True, text=True, timeout=30)


def latest_question(body):
    """The last non-empty line of the note, which is the newest question.

    Apple Notes puts the title in the first div, so that is skipped. Anything
    already answered stays in the note as a record; only a CHANGE counts as a
    new question, which is handled by the caller.
    """
    import re
    text = re.sub(r"<[^>]+>", "\n", body or "")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    lines = [l for l in lines if l.lower() != NOTE.lower()]
    return lines[-1] if lines else ""


def cmd_alert(a):
    st = load()
    st["alerts"].insert(0, {"text": a.text, "at": datetime.now().strftime("%H:%M")})
    st["alerts"] = st["alerts"][:KEEP]
    save(st)
    # No page any more: the coach lives in one terminal window (coach_tui.py)
    # by Stephen's choice, 11 Nov 2026, and that window reads this state file.
    return 0


def cmd_init(a):
    st = {"alerts": [], "seen_question": ""}
    save(st)
    write_page([], starting=True)
    ensure_note()
    if not a.no_open:
        open_window()
    print("coach page: %s | questions: Apple Note %r" % (PAGE, NOTE))
    return 0


TRANSCRIPT = os.path.expanduser(os.environ.get("COACH_TRANSCRIPT",
                                               "~/live-transcript.jsonl"))
STALE_SECS = 60


def meeting_live():
    """True while the newest producer log says a transcript is live.

    The producer writes "transcript live" when Zoom starts a transcript and
    "transcript store cleared (meeting ended)" when it stops, so the last of
    those two lines says whether a call is in progress.
    """
    import glob
    logs = sorted(glob.glob(os.path.expanduser("~/.coach/*-zoom.log")),
                  key=os.path.getmtime)
    if not logs:
        return False
    state = False
    for line in open(logs[-1], errors="ignore"):
        if "transcript live" in line:
            state = True
        elif "store cleared" in line:
            state = False
    return state


def feed_stalled(now=None):
    """Seconds since the transcript last grew, if a live call has gone quiet.

    On 11 Nov 2026 Zoom stopped transcribing the i4i panel at 10:18 while the
    meeting ran to 10:31, and nothing said so: a silent coach looks exactly
    like a coach with nothing to say. A live meeting with no new line for a
    minute is the signal.
    """
    if not meeting_live():
        return None
    try:
        age = (now or time.time()) - os.path.getmtime(TRANSCRIPT)
    except OSError:
        return None
    return age if age >= STALE_SECS else None


def cmd_watch(a):
    """Poll the note. New questions go to stdout for the coach session."""
    st = load()
    last_beat = 0
    alarmed = False
    while True:
        stalled = feed_stalled()
        if stalled and not alarmed:
            cmd_alert(argparse.Namespace(
                text="TRANSCRIPT STOPPED %ds ago. Check the Zoom note: is it "
                     "open with Transcript on?" % stalled))
            print("ALARM: transcript stalled %ds" % stalled, flush=True)
            alarmed = True
        elif not stalled and alarmed:
            cmd_alert(argparse.Namespace(text="Transcript flowing again."))
            alarmed = False
        q = latest_question(note_body())
        if q and q != st.get("seen_question"):
            st["seen_question"] = q
            save(st)
            # stdout is what the coach session reads, so this is the only
            # thing that must be machine-clean.
            print("QUESTION: %s" % q, flush=True)
        now = time.time()
        if now - last_beat >= 60:
            # The heartbeat is the whole terminal interface. One line, so
            # nothing scrolls while he is trying to read the page.
            sys.stderr.write("\rcoach alive %s  alerts %d  "
                             % (datetime.now().strftime("%H:%M:%S"),
                                len(load().get("alerts", []))))
            sys.stderr.flush()
            last_beat = now
        if a.once:
            return 0
        time.sleep(POLL_SECS)


def cmd_demo(a):
    """Replay a recorded transcript through the page, to check it reads well."""
    st = {"alerts": [], "seen_question": ""}
    save(st)
    write_page([], starting=True)
    if not a.no_open:
        open_window()
    shown = 0
    for line in open(a.transcript, errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            text = (d.get("text") or "").strip()
            who = d.get("speaker") or ""
        except ValueError:
            text, who = line, ""
        if len(text) < 25:
            continue
        cmd_alert(argparse.Namespace(text="%s%s" % (who + ": " if who else "", text[:150])))
        shown += 1
        if shown >= a.count:
            break
        time.sleep(a.delay)
    print("replayed %d alerts to %s" % (shown, PAGE))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init"); i.add_argument("--no-open", action="store_true")
    i.set_defaults(func=cmd_init)

    al = sub.add_parser("alert"); al.add_argument("text")
    al.set_defaults(func=cmd_alert)

    w = sub.add_parser("watch"); w.add_argument("--once", action="store_true")
    w.set_defaults(func=cmd_watch)

    d = sub.add_parser("demo")
    d.add_argument("transcript")
    d.add_argument("--count", type=int, default=5)
    d.add_argument("--delay", type=float, default=1.0)
    d.add_argument("--no-open", action="store_true")
    d.set_defaults(func=cmd_demo)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
