#!/usr/bin/env python3
"""What fires, what does not, and where the tick lands.

    python3 tests/test_trigger.py

Nothing here touches Apple Notes: these are pure string cases. The point is the
19 Sep 2026 change that made the @ optional, because dropping it puts the
trigger one word away from ordinary prose about Claude.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import todo_agent as t  # noqa: E402

FIRES = [
    ("@claude: draft the Alice reply", "draft the Alice reply"),
    ("@Claude draft the Alice reply", "draft the Alice reply"),
    ("Claude: draft the Alice reply", "draft the Alice reply"),
    ("claude draft the Alice reply", "draft the Alice reply"),
    ("- Claude, book the dentist", "book the dentist"),
    ("  • @claude get the costings from Annie", "get the costings from Annie"),
    ("1. Claude: send the Raj quote", "send the Raj quote"),
    ("CLAUDE: REVIEW the budget", "REVIEW the budget"),
    # No @, no punctuation, but the next word is an imperative.
    ("claude review the lay summary", "review the lay summary"),
    # An @ line is trusted whatever follows it, as it always was.
    ("@claude the IDS needs its NPL", "the IDS needs its NPL"),
]

QUIET = [
    # Prose about the tool, which the note is full of.
    "Claude Code is available as a CLI in the terminal",
    "claude sessions keep dying after the update",
    "Claude agents should get CXO titles",
    "Claude AI pricing went up",
    # The trigger must OPEN the line.
    "ask @claude to do this",
    "How to give me work here: start any bullet with @claude and then the "
    "instruction, anywhere in this note.",
    # Nothing to do.
    "@claude",
    "Claude:",
    # A bare name with no verb and no punctuation.
    "Claude tools",
    "claude and codex both reviewed it",
]


def main():
    bad = []
    for line, want in FIRES:
        got = t.trigger_match(line)
        if got != want:
            bad.append("should fire: %r -> %r, wanted %r" % (line, got, want))
    for line in QUIET:
        got = t.trigger_match(line)
        if got is not None:
            bad.append("should stay quiet: %r -> %r" % (line, got))

    # A tick must land at the end of its own bullet, and the scan and the mark
    # must agree on which bullet that is.
    body = ('<div><b>Strategy</b></div><ul class="Apple-dash-list">'
            '<li><span>Claude: send the Raj quote</span></li>'
            '<li><span>Claude Code is a CLI</span></li>'
            '<li><span>@claude: book the dentist</span></li></ul>')
    spans = [x for x in t.line_spans(body) if t.trigger_match(x[0])]
    if len(spans) != 2:
        bad.append("line_spans found %d trigger lines, wanted 2" % len(spans))
    else:
        at = spans[1][1]
        marked = body[:at] + " " + t.DONE_MARK + " done (10:30)" + body[at:]
        # At the end of that bullet: after its content, before the </li>.
        if "book the dentist</span> ✅ done (10:30)</li>" not in marked:
            bad.append("tick landed in the wrong place: %r" % marked)

    for b in bad:
        print("FAIL " + b)
    print("%d case(s), %d failure(s)" % (len(FIRES) + len(QUIET) + 2, len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
