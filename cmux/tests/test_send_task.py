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
    ok, line, _ = s.send_task(["--workspace", "workspace:9"], text)
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

    for b in bad:
        print("FAIL " + b)
    print("5 scenario(s), %d failure(s)" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
