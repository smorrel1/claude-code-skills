#!/usr/bin/env python3
"""Which To Do lines count as instructions to Claude?

    python3 tests/test_trigger_match.py

The 26 Oct 2026 failure: Stephen wrote

    17. Claude: can you log into Xero and complete my September financial
    statements and email to me for approval? Shout if you need logon help.

and it sat in the note for days. The line was addressed to Claude with an
explicit colon, but "can" is in the stopword list that exists to reject prose
like "Claude can code well", so the agent dropped it silently.

The rule now: a colon, comma or dash after "Claude", or a leading "@", means
the line is ADDRESSED, and an addressed line is an instruction whatever word
comes next. The stopword and imperative tests only apply to a bare mention.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import todo_agent as t  # noqa: E402

CASES = [
    # The exact line that was missed, numbered-list prefix and all.
    ("17. Claude: can you log into Xero and complete my September financial "
     "statements and email to me for approval? Shout if you need logon help.",
     True, "the 26 Oct Xero line"),

    # Addressed, so the following word does not matter.
    ("Claude: can you chase the YHEC quote", True, "colon plus 'can'"),
    ("Claude, could you book the flight", True, "comma plus 'could'"),
    ("Claude - is the draft ready", True, "dash plus 'is'"),
    ("5) claude, please book the flight", True, "numbered, comma, polite"),
    ("@claude can you do this", True, "at-form needs no imperative"),

    # Bare mention plus an imperative verb is still an instruction.
    ("- claude draft the reply", True, "bullet plus imperative"),
    ("claude chase Keshthra", True, "plain imperative"),

    # Prose about Claude, with no colon. Must stay ignored.
    ("Claude can code well", False, "prose, stopword 'can'"),
    ("Claude is a tool", False, "prose, stopword 'is'"),
    ("I think Claude should do it", False, "mid-sentence mention"),
    ("Claude sessions keep dying", False, "prose, stopword 'sessions'"),

    # Nothing to act on.
    ("claude", False, "bare trigger, no instruction"),
    ("Claude:", False, "addressed but empty"),
]


def main():
    bad = []
    for line, want, why in CASES:
        got = t.trigger_match(line) is not None
        if got != want:
            bad.append("%s: expected %s, got %s for %r" % (why, want, got, line[:60]))

    # The instruction text must come back without the trigger and punctuation,
    # because it is what the delegate session is told to do.
    text = t.trigger_match("17. Claude: can you log into Xero and complete my "
                           "September financial statements")
    if not text or not text.lower().startswith("can you log into xero"):
        bad.append("the instruction text should start at the real request, got %r"
                   % (text or "")[:60])

    for b in bad:
        print("FAIL " + b)
    print("%d case(s), %d failure(s)" % (len(CASES) + 1, len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
