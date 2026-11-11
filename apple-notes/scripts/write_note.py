#!/usr/bin/env python3
"""Write an Apple Note without blowing up its font sizes.

Apple Notes multiplies EVERY explicit font-size by 1.2 when a body is set, and
the effect compounds: each whole-body write makes the note permanently worse.
Stephen's To Do note went 158 -> 228 -> 274 -> 329 -> 474 -> 569 -> 683 -> 820px
across several weeks, one write at a time, because the documented recipe here
was a bare JXA `note.body = html`. 820px headings are about eleven lines tall.

So every write goes through set_body() below, which pre-shrinks each size by the
same 1.2 so the round trip lands where it started, and clamps anything above the
cap (48px, Stephen's stated ceiling for titles, 23 Sep 2026). 16px is Notes' own
default and a fixed point, so it is left alone.

    write_note.py list                                  notes and their max size
    write_note.py show   --note <id|name fragment>      print the body HTML
    write_note.py set    --note <...> --file body.html  replace the body, safely
    write_note.py append --note <...> --file add.html   add to the end, safely
    write_note.py normalise --note <...> [--cap 48]     clamp runaway sizes
    write_note.py normalise --all [--dry-run]           clamp every note

Every write backs up the previous body to backups/ first.

As a library:  from write_note import get_body, set_body
"""
import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
BACKUPS = SKILL / "backups"
NOTES_SCALE = 1.2       # what Notes multiplies every explicit size by on import
NOTES_DEFAULT_PX = 16   # ...except this one, its default, left untouched
CAP_PX = 48             # Stephen, 23 Sep 2026: 48 is the max for titles


def osa(script, timeout=120):
    r = subprocess.run(["osascript", "-e", script], capture_output=True,
                       text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError("osascript failed: %s" % r.stderr.strip()[:300])
    return r.stdout.rstrip("\n")


# Scoped to the "Notes" folder: an unscoped `every note` also walks Recently
# Deleted, which returns deleted copies under the same names and is 60% slower.
LIST = '''
tell application "Notes"
  set out to {}
  repeat with n in notes of folder "Notes"
    set end of out to (id of n) & "\\t" & (name of n)
  end repeat
  set AppleScript's text item delimiters to linefeed
  return out as text
end tell
'''


def notes():
    out = []
    for line in osa(LIST).splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            out.append({"id": parts[0], "name": parts[1]})
    return out


def resolve(ref):
    """A note id, or a unique fragment of a note's name."""
    if ref.startswith("x-coredata://"):
        return {"id": ref, "name": osa('tell application "Notes" to return name '
                                       'of note id "%s"' % ref)}
    hits = [n for n in notes() if ref.lower() in n["name"].lower()]
    if not hits:
        sys.exit("No note matches %r." % ref)
    if len(hits) > 1:
        sys.exit("%d notes match %r. Use the id:\n%s" % (
            len(hits), ref, "\n".join("  %s  %s" % (n["id"], n["name"]) for n in hits)))
    return hits[0]


def get_body(note_id):
    return osa('tell application "Notes" to return body of note id "%s"' % note_id)


def sizes(html):
    return sorted({int(m.group(1)) for m in re.finditer(r"font-size: (\d+)px", html)})


def cap_fonts(html, ceiling):
    """Clamp sizes as STORED. Apply before deflate_fonts, never after."""
    return re.sub(r"font-size: (\d+)px",
                  lambda m: "font-size: %dpx" % min(int(m.group(1)), ceiling), html)


def deflate_fonts(html):
    """Pre-shrink so Notes' 1.2x import scaling lands each size back home."""
    def fix(m):
        px = int(m.group(1))
        if px == NOTES_DEFAULT_PX:
            return m.group(0)
        return "font-size: %dpx" % max(1, round(px / NOTES_SCALE))
    return re.sub(r"font-size: (\d+)px", fix, html)


# ---------------------------------------------------------------------------
# Crash safety, added 11 Nov 2026.
#
# Notes crashed twice that day, at 10:55 and 15:22, with the same uncaught
# exception inside an AppleScript command:
#     -[__NSCFString replaceCharactersInRange:withString:]: nil argument
#     NSMutableRLEArray objectAtIndex:effectiveRange:: Out of bounds
# Each came about a minute after a session ran
#     set body of n to (body of n) & html
# to append to a note that was OPEN ON SCREEN ("i4i interview 11 Nov", then
# "Walker CLIP call 11 Nov", the second followed by `show n`). Replacing the
# whole text of a note under a live editor and cursor leaves the editor
# holding ranges into text that no longer exists, and Notes falls over.
#
# So every write now: takes one machine-wide lock, so two sessions never
# write at once; checks Notes answers at all, and backs off if it does not;
# refuses to rewrite a note that is selected or in its own window; and keeps
# bodies to a sane size.
# ---------------------------------------------------------------------------
import fcntl
import os
import time
from contextlib import contextmanager

LOCK = Path(os.path.expanduser("~/.claude/notes-write.lock"))
MAX_ADD = 15_000        # bytes of HTML appended in one go; more goes to a file
OVERFLOW = Path(os.path.expanduser(
    "~/Library/CloudStorage/Dropbox/Documents/notes-overflow"))


class NotesBusy(RuntimeError):
    """Notes is not answering. Never write into a hung Notes."""


class NoteOpen(RuntimeError):
    """The target note is on screen, so rewriting it could crash Notes."""


@contextmanager
def notes_lock(wait=60):
    """One writer at a time, across every session and script on this Mac."""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    fh = open(LOCK, "w")
    deadline = time.time() + wait
    while True:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.time() > deadline:
                fh.close()
                raise NotesBusy("another Notes write held the lock for %ds" % wait)
            time.sleep(0.5)
    try:
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def responsive(timeout=8):
    """Does Notes answer a trivial question within a few seconds?"""
    try:
        r = subprocess.run(["osascript", "-e", 'tell application "Notes" to return 1'],
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def open_note_ids():
    """Ids of notes on screen: the selection, plus any separate note windows."""
    script = '''
tell application "Notes"
  set out to {}
  try
    repeat with n in (get selection)
      set end of out to id of n
    end repeat
  end try
  try
    repeat with w in windows
      set wn to name of w
      if wn is not "Notes" then
        repeat with n in (every note whose name is wn)
          set end of out to id of n
        end repeat
      end if
    end repeat
  end try
  set AppleScript's text item delimiters to linefeed
  return out as text
end tell'''
    try:
        return set(osa(script, timeout=15).split("\n")) - {""}
    except Exception:
        return set()


def guarded(fn, *args, attempts=3, **kw):
    """Run a Notes call with the lock, a liveness check and backoff."""
    delay = 2
    for i in range(attempts):
        with notes_lock():
            if not responsive():
                err = NotesBusy("Notes is not responding; not writing")
            else:
                try:
                    return fn(*args, **kw)
                except (NoteOpen, NotesBusy):
                    raise
                except Exception as exc:     # transient AppleScript failure
                    err = exc
        if i < attempts - 1:
            time.sleep(delay)
            delay *= 2
    raise err


def set_body(note_id, body, tag="write", cap=CAP_PX, allow_open=False):
    """THE only safe way to write a note body. See the crash note above."""
    return guarded(_set_body, note_id, body, tag, cap, allow_open)


def append(ref, html, tag="append"):
    """Add to the end of a note, safely.

    If the note is on screen, the addition goes into a NEW note named after
    it instead of rewriting the open one. If the addition is large, the full
    text is saved as a file and the note gets a short pointer to it.
    """
    note = resolve(ref)
    if len(html.encode()) > MAX_ADD:
        OVERFLOW.mkdir(parents=True, exist_ok=True)
        path = OVERFLOW / ("%s-%s.html" % (datetime.now().strftime("%Y%m%d-%H%M%S"),
                                           re.sub(r"[^\w-]+", "-", note["name"])[:40]))
        path.write_text(html)
        html = ("<div>Long addition saved as a file (%d KB): %s</div>"
                % (len(html.encode()) // 1024, path))
    if note["id"] in open_note_ids():
        name = "%s, addendum %s" % (note["name"], datetime.now().strftime("%H:%M"))
        guarded(lambda: osa('''
tell application "Notes"
  make new note at folder "Notes" with properties {name:"%s", body:(read (POSIX file "%s") as «class utf8»)}
end tell''' % (name.replace('"', "'"), _tmpfile(html))))
        return "note was open, so wrote a separate note: %s" % name
    set_body(note["id"], get_body(note["id"]) + html, tag)
    return "appended to %s" % note["name"]


def _tmpfile(text):
    BACKUPS.mkdir(exist_ok=True)
    p = BACKUPS / ("%s-tmp.html" % datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    p.write_text(text)
    return p


def _set_body(note_id, body, tag="write", cap=CAP_PX, allow_open=False):
    if not allow_open and note_id in open_note_ids():
        raise NoteOpen("that note is open on screen; rewriting it can crash "
                       "Notes. Use append(), which writes a separate note, or "
                       "close it first.")
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


def normalise(note, cap, dry_run):
    body = get_body(note["id"])
    over = [s for s in sizes(body) if s > cap]
    print("%-46s max %4dpx  over cap: %s"
          % (note["name"][:46], max(sizes(body) or [0]), over or "none"))
    if not over or dry_run:
        return bool(over)
    set_body(note["id"], body, "normalise", cap=cap)
    print("   now: %s" % sizes(get_body(note["id"])))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["list", "show", "set", "append", "normalise"])
    ap.add_argument("--note")
    ap.add_argument("--file")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--cap", type=int, default=CAP_PX)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.command == "list":
        for n in notes():
            print("%-46s %s" % (n["name"][:46], max(sizes(get_body(n["id"])) or [0])))
        return 0

    if a.command == "normalise" and a.all:
        hit = 0
        for n in notes():
            if normalise(n, a.cap, a.dry_run):
                hit += 1
        print("\n%d note(s) above the %dpx cap.%s"
              % (hit, a.cap, " Dry run, nothing written." if a.dry_run else ""))
        return 0

    if not a.note:
        sys.exit("Give --note <id or name fragment>.")
    note = resolve(a.note)

    if a.command == "append":
        if not a.file:
            sys.exit("Give --file with the HTML to add.")
        print(append(a.note, Path(a.file).read_text()))
        return 0

    if a.command == "show":
        print(get_body(note["id"]))
    elif a.command == "normalise":
        normalise(note, a.cap, a.dry_run)
    elif a.command == "set":
        if not a.file:
            sys.exit("Give --file <body.html>.")
        set_body(note["id"], Path(a.file).read_text(), "set", cap=a.cap)
        print("Wrote %s. Sizes now: %s" % (note["name"], sizes(get_body(note["id"]))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
