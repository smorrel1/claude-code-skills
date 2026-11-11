#!/usr/bin/env python3
"""Notes writes must not crash Notes. 11 Nov 2026: two crashes, each a minute
after a script rewrote the whole body of a note that was open on screen.

Runs entirely against fakes: no note is created, changed or deleted.
"""
import sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import write_note as W

calls = []
W.responsive = lambda timeout=8: True
W.get_body = lambda nid: "<div>old</div>"
W.resolve = lambda ref: {"id": "x-open" if "open" in ref else "x-closed", "name": ref}
W.open_note_ids = lambda: {"x-open"}
W.osa = lambda script, timeout=120: calls.append(script) or ""
bad = []

# 1. Rewriting an OPEN note is refused outright.
try:
    W.set_body("x-open", "<div>new</div>")
    bad.append("set_body on an open note must refuse")
except W.NoteOpen:
    pass

# 2. Appending to an open note writes a SEPARATE note, never touches the open one.
calls.clear()
msg = W.append("Walker CLIP call open", "<div>more</div>")
if "separate note" not in msg or any('set body of note id "x-open"' in c for c in calls):
    bad.append("append to an open note must make a separate note, got %r" % msg)

# 3. Appending to a closed note goes in place.
calls.clear()
msg = W.append("Some closed note", "<div>more</div>")
if not any('set body of note id "x-closed"' in c for c in calls):
    bad.append("append to a closed note should write in place")

# 4. A hung Notes is never written to.
W.responsive = lambda timeout=8: False
try:
    W.guarded(lambda: None, attempts=1)
    bad.append("must refuse to write when Notes is not responding")
except W.NotesBusy:
    pass
W.responsive = lambda timeout=8: True

# 5. A huge addition becomes a file plus a short pointer.
W.OVERFLOW = Path("/tmp/notes-overflow-test")
calls.clear()
W.append("Some closed note", "<div>" + "x" * 40000 + "</div>")
written = "".join(calls)
if "saved as a file" not in "".join(open(p).read() for p in W.BACKUPS.glob("*-append-new.html")) and "x" * 40000 in written:
    bad.append("a 40KB addition must not be written into the note whole")

# 6. Two writers never overlap.
inside, overlap = [0], [False]
def writer():
    with W.notes_lock():
        inside[0] += 1
        if inside[0] > 1: overlap[0] = True
        time.sleep(0.2)
        inside[0] -= 1
ts = [threading.Thread(target=writer) for _ in range(3)]
[t.start() for t in ts]; [t.join() for t in ts]
if overlap[0]:
    bad.append("the lock let two writers in at once")

for b in bad: print("FAIL " + b)
print("6 check(s), %d failure(s)" % len(bad))
sys.exit(1 if bad else 0)
