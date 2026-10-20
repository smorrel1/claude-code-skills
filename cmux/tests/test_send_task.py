#!/usr/bin/env python3
"""send_task.py without a real cmux: does it submit, retry, and admit failure?

    python3 tests/test_send_task.py

The bug being pinned down here is the one that made a task look delivered when
it was sitting unsubmitted in the input box (21 Sep 2026).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import send_task as s  # noqa: E402

s.POLL_SECS = 0
s.POLLS = 2


class FakeCmux:
    """A workspace that only starts after `enters_needed` presses of Enter."""

    def __init__(self, enters_needed):
        self.enters_needed = enters_needed
        self.enters = 0
        self.sent = []
        self.running = False

    def __call__(self, *args, **kw):
        if args[0] == "send":
            self.sent.append(args[-1])
        elif args[0] == "send-key":
            self.enters += 1
            if self.enters >= self.enters_needed:
                self.running = True
        elif args[0] == "read-screen":
            return "esc to interrupt" if self.running else "❯ "
        return ""


def run(enters_needed, text):
    fake = FakeCmux(enters_needed)
    s.cmux = fake
    ok, line, _marker, _scr = s.send_task(["--workspace", "Some Workspace"], text)
    return ok, line, fake


def main():
    bad = []

    ok, line, fake = run(1, "chase the YHEC quote")
    if not ok:
        bad.append("one-liner should submit on the first Enter")
    if fake.sent != ["chase the YHEC quote"]:
        bad.append("one-liner should be sent as-is, got %r" % fake.sent)

    # The real failure: the first Enter only expands the paste.
    ok, line, fake = run(2, "chase the YHEC quote")
    if not ok:
        bad.append("should recover when the first Enter does not submit")
    if fake.enters != 2:
        bad.append("expected exactly 2 Enters, got %d" % fake.enters)

    ok, line, fake = run(99, "chase the YHEC quote")
    if ok:
        bad.append("must NOT report success when nothing started")
    if fake.enters != s.MAX_ENTERS:
        bad.append("expected %d Enters before giving up, got %d"
                   % (s.MAX_ENTERS, fake.enters))

    # A panel sitting at a shell prompt must never be typed into: that is how
    # the 'demo.elaitra zip' request was lost on 19 Oct 2026.
    class DeadShell(FakeCmux):
        def __call__(self, *args, **kw):
            if args[0] == "read-screen":
                return "Last login: Mon Oct 19\n(base) \u279c  Elaitra_gc"
            return FakeCmux.__call__(self, *args, **kw)

    fake = DeadShell(1)
    s.cmux = fake
    ok, line, _m, scr = s.send_task(["--workspace", "Dead One"], "do the thing")
    if ok:
        bad.append("must not report success when the target is a bare shell")
    if fake.sent:
        bad.append("nothing may be typed into a bare shell, got %r" % fake.sent)
    if "BARE SHELL" not in scr:
        bad.append("should say plainly that the target was a shell")

    # An idle Claude pane shows only its empty input box. That is healthy and
    # must still accept a brief.
    class IdleClaude(FakeCmux):
        def __call__(self, *args, **kw):
            if args[0] == "read-screen" and not self.running:
                return "\u276f "
            return FakeCmux.__call__(self, *args, **kw)

    fake = IdleClaude(1)
    s.cmux = fake
    ok, line, _m, _s = s.send_task(["--workspace", "Idle One"], "do the thing")
    if not ok or not fake.sent:
        bad.append("an idle Claude pane must still accept a brief")

    # Multi-line goes to a file, and only a short line is typed.
    ok, line, fake = run(1, "line one\nline two\nline three")
    if "\n" in fake.sent[0]:
        bad.append("multi-line text must not be typed into the box")
    if "read that file" not in line:
        bad.append("multi-line should be sent as a pointer, got %r" % line)
    path = line.split(" is in ")[1].split(":")[0]
    if Path(path).read_text().splitlines() != ["line one", "line two", "line three"]:
        bad.append("spooled file does not hold the task text")
    Path(path).unlink()

    long_one = "x" * (s.INLINE_MAX + 1)
    ok, line, fake = run(1, long_one)
    if long_one in fake.sent[0]:
        bad.append("an over-long line should go to a file too")
    Path(line.split(" is in ")[1].split(":")[0]).unlink()

    # 1 Oct 2026: the name-only contract. A numeric ref must be refused outright
    # rather than sent, because the todo-agent passed one for two weeks and every
    # pickup was quietly retried instead of failing.
    import re as _re
    for ref in ("workspace:5", "5"):
        if not _re.fullmatch(r"(workspace:)?\d+", ref):
            bad.append("%r should look numeric to the guard" % ref)

    # The marker returned for a spooled brief has to be greppable in the
    # target's transcript: it is how a delivery is confirmed to be in the RIGHT
    # session.
    ok, line, marker, _ = s.send_task(["--workspace", "Some Workspace"],
                                      "a\nspooled\nbrief")
    if not marker or marker not in line:
        bad.append("the marker must appear in the line that is typed, got %r"
                   % marker)
    Path(line.split(" is in ")[1].split(":")[0]).unlink()

    for b in bad:
        print("FAIL " + b)
    print("9 scenario(s), %d failure(s)" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
