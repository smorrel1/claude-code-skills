#!/usr/bin/env python3
"""Does a reply land on a thread the recipient was actually on?

    python3 tests/test_threading.py            offline logic only
    python3 tests/test_threading.py --live     also check the 30 Sep 2026 case

On 30 Sep 2026 a draft was filed in an unrelated helpdesk thread and quoted
that ticket to someone who had never been on it. The chain was: the latest
traffic with that person was a message the user had addressed to THEMSELVES
with twenty people in Bcc, so re-deriving "the correspondent" from its To
header returned one of the user\'s own addresses, and the reply was redirected
to whatever they had last exchanged with themselves.

The offline cases cover the logic with invented addresses. --live re-checks
real messages and needs both a token and tests/live-cases.local.json (
gitignored), so it is opt-in and no real address appears in this file.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import gmail_utils as g  # noqa: E402


class FakeService:
    """Just enough Gmail to exercise the guards: messages, threads, profile."""

    def __init__(self, messages, threads, me="me@example.org"):
        self._m, self._t, self._me = messages, threads, me

    def users(self):
        return self

    def getProfile(self, userId=None):
        return _Exec({"emailAddress": self._me})

    def messages(self):
        return _Part(self._m)

    def threads(self):
        return _Part(self._t)


class _Part:
    def __init__(self, data):
        self._data = data

    def get(self, userId=None, id=None, format=None, metadataHeaders=None):
        return _Exec(self._data[id])


class _Exec:
    def __init__(self, value):
        self._v = value

    def execute(self):
        return self._v


def headers(**kw):
    return {"payload": {"headers": [{"name": k, "value": v} for k, v in kw.items()]}}


def main():
    bad = []

    # 1. Self-addressed message: no correspondent can be derived, so the
    #    redirect must leave the target alone rather than guess.
    msg = dict(headers(**{"From": "me@example.org",
                          "To": "me.other@example.net",
                          "Subject": "EJR Publication live", "Date": "Tue, 14 Apr 2026"}),
               internalDate="1776000000000", threadId="t1")
    svc = FakeService({"m1": msg}, {})
    g._SELF_EMAIL_CACHE.clear()
    # Both invented addresses belong to the user, which is the whole point of
    # the case: a self-addressed message yields no correspondent to follow.
    real_self = g.self_addresses
    g.self_addresses = lambda _s: {"me@example.org", "me.other@example.net"}
    out = g.redirect_replyto_to_latest(svc, "m1")
    g.self_addresses = real_self
    if out != "m1":
        bad.append("self-addressed message should not redirect, got %r" % out)

    # 2. Every configured address counts as self, gmail/googlemail included.
    mine = g.self_addresses(svc)   # the real one, reading config.json
    if not mine:
        bad.append("self_addresses returned nothing; config.json unreadable?")
    if any(x.endswith("@gmail.com") for x in mine) and not any(
            x.endswith("@googlemail.com") for x in mine):
        bad.append("googlemail twin missing for a gmail address")

    # 3. Participation check: the recipient must appear on a NON-DRAFT message.
    thread_with = {"messages": [
        dict(headers(**{"From": "them@example.com", "To": "me@example.org"}),
             labelIds=["INBOX"])]}
    thread_without = {"messages": [
        dict(headers(**{"From": "helpdesk@example.edu", "To": "me.other@example.net"}),
             labelIds=["INBOX"])]}
    # ...and a draft naming the recipient must NOT vouch for the thread, or the
    # misfiled draft justifies the very thread it should not be in.
    thread_draft_only = {"messages": [
        dict(headers(**{"From": "helpdesk@example.edu", "To": "me.other@example.net"}),
             labelIds=["INBOX"]),
        dict(headers(**{"From": "me@example.org", "To": "them@example.com"}),
             labelIds=["DRAFT"])]}
    for name, thread, want in (("recipient on the thread", thread_with, True),
                               ("recipient absent", thread_without, False),
                               ("only a draft names them", thread_draft_only, False)):
        svc = FakeService({"m1": {"threadId": "t1"}}, {"t1": thread})
        got = g.thread_includes(svc, "m1", "them@example.com")
        if got is not want:
            bad.append("%s: thread_includes returned %s, wanted %s" % (name, got, want))

    print("offline: 3 scenario(s) checked")

    if "--live" in sys.argv:
        # Real addresses and message ids live in a gitignored file, so this
        # repo carries none. Shape:
        #   {"address": "...", "wrong_thread_message_id": "..."}
        import json
        case_file = Path(__file__).resolve().parent / "live-cases.local.json"
        if not case_file.exists():
            print("live: skipped, no %s" % case_file.name)
        else:
            case = json.loads(case_file.read_text())
            addr = case["address"]
            g.CURRENT_ACCOUNT = case.get("account", "work")
            svc = g.get_gmail_service()
            latest = g.find_latest_thread_message(svc, addr)
            if g.redirect_replyto_to_latest(svc, latest) != latest:
                bad.append("live: redirect still moves off the correct thread")
            if not g.thread_includes(svc, latest, addr):
                bad.append("live: their own latest thread should include them")
            if g.thread_includes(svc, case["wrong_thread_message_id"], addr):
                bad.append("live: the unrelated thread should NOT include them")
            print("live: the 30 Sep 2026 case re-checked")

    for b in bad:
        print("FAIL " + b)
    print("%d failure(s)" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
