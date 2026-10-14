#!/usr/bin/env python3
"""Can an instruction be ticked off after an unconfirmed delivery?

    python3 tests/test_delivery_bookkeeping.py

The 14 Oct 2026 failure: a busy Chief of staff queues a brief behind the task it
is already running, so no assistant turn follows inside the confirmation window.
The delivery was recorded nowhere, which had two consequences. The job resent the
same instruction every few minutes, four times for one of them, each resend
adding another copy to the queue. And `mark <id>` answered "Unknown instruction
id", so the work could be done and still not be ticked off.

Nothing here touches Apple Notes or cmux: it drives the state file only.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import todo_agent as t  # noqa: E402


def fresh_state(tmp):
    t.STATE = Path(tmp) / "seen.json"
    return {"delivered": {}, "attempts": {}, "last_try": {}, "pending": {}}


def main():
    bad = []
    tmp = tempfile.mkdtemp(prefix="todo-agent-test-")
    ident = "abc123def456"

    # 1. A sent-but-unconfirmed instruction leaves a pending record carrying
    #    everything mark needs: the text, the note and the occurrence.
    state = fresh_state(tmp)
    state["pending"][ident] = {"text": "order the repeat prescription",
                               "note": "To Do", "note_id": "x-coredata://note/p1",
                               "occurrence": 3, "first_tried": "2026-10-14 09:15",
                               "workspace": "Chief of staff"}
    state["attempts"][ident] = 3
    t.save_state(state)

    reloaded = t.load_state()
    if ident not in reloaded.get("pending", {}):
        bad.append("a pending record must survive a save and load")

    # 2. mark promotes it: pending -> delivered, attempts cleared. This is the
    #    behaviour that used to print "Unknown instruction id".
    rec = reloaded["delivered"].get(ident)
    if rec is None:
        rec = reloaded.get("pending", {}).get(ident)
        if rec:
            rec = dict(rec, handed_over=rec.get("first_tried"), started=True)
            reloaded["delivered"][ident] = rec
            reloaded["pending"].pop(ident, None)
            reloaded["attempts"].pop(ident, None)
            t.save_state(reloaded)

    after = t.load_state()
    if ident not in after["delivered"]:
        bad.append("mark should promote a pending instruction to delivered")
    else:
        d = after["delivered"][ident]
        for field in ("text", "note_id", "occurrence"):
            if field not in d:
                bad.append("the promoted record lost %r, which mark needs to "
                           "find the line in the note" % field)
        if d.get("handed_over") != "2026-10-14 09:15":
            bad.append("the promoted record should keep the time it was first sent")
    if ident in after.get("pending", {}):
        bad.append("a promoted instruction must leave pending")
    if ident in after.get("attempts", {}):
        bad.append("a promoted instruction must stop being retried")

    # 3. An id nobody has ever seen is still unknown, so a typo does not
    #    silently invent a record.
    if "nosuchid00000" in after["delivered"] or "nosuchid00000" in after.get("pending", {}):
        bad.append("an unknown id must stay unknown")

    for b in bad:
        print("FAIL " + b)
    print("3 scenario(s), %d failure(s)" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
