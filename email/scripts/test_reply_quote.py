#!/usr/bin/env python3
"""Regression test: reply quoting must include ONLY the parent message body.

Guards against the full-thread quoting bug (fixed 2026-08-26): drafts built
with --reply-to stacked every message in the Gmail threadId as nested quotes,
so Outlook-embedded chains (From:/Sent:/To: blocks) duplicated - one draft
contained the same email 3x ("wavelet server" x9 instead of x3).

Run: python3 test_reply_quote.py  (no network, no drafts created)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gmail_utils

PHRASE = "wavelet server"

# Parent message as an Outlook correspondent sends it: its own new content
# plus the embedded chain they saw, repeated From:/Sent:/To: blocks included.
parent_html = f"""<div>Thanks Stephen, the {PHRASE} config looks right.</div>
<div>From: Stephen Morrell<br>Sent: Monday, July 20, 2026<br>To: Marcus Brothers</div>
<div>We moved the {PHRASE} to the new rack; the {PHRASE} IP is unchanged.</div>"""

parent = {
    'id': 'fake-parent', 'from': 'Marcus Brothers <mbrothers@radsource.us>',
    'date': 'Mon, 27 Jul 2026 13:27:00 +0000', 'subject': 'Re: Elaitra add on',
    'body': gmail_utils._html_to_plain(parent_html), 'body_html': parent_html,
}

failures = []
def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f": {detail}" if not cond and detail else ""))
    if not cond: failures.append(name)

parent_count = parent_html.lower().count(PHRASE)
check("fixture sanity: phrase x3 in parent", parent_count == 3, f"got {parent_count}")

quoted_html = gmail_utils.format_quoted_reply_html(parent)
quoted_plain = gmail_utils.format_quoted_reply(parent)

# Phrase count in the quote must EQUAL the parent's own count - nothing
# trimmed from the parent, nothing added from other thread messages.
n_html = quoted_html.lower().count(PHRASE)
n_plain = quoted_plain.lower().count(PHRASE)
check("HTML quote preserves parent verbatim (phrase count equal)", n_html == parent_count, f"got {n_html}, want {parent_count}")
check("plain quote preserves parent verbatim (phrase count equal)", n_plain == parent_count, f"got {n_plain}, want {parent_count}")

# Exactly ONE attribution line added (ours), the embedded Outlook chain untouched.
check("exactly one 'wrote:' attribution added (HTML)", quoted_html.count("wrote:") == 1, f"got {quoted_html.count('wrote:')}")
check("embedded Outlook From:/Sent: chain untouched", "Sent: Monday, July 20, 2026" in quoted_html)

# The full-thread machinery must stay dead.
for sym in ("format_full_thread_quote_html", "format_full_thread_quote_plain",
            "get_thread_history", "_strip_prior_quotes_plain", "_strip_prior_quotes_html"):
    check(f"removed symbol absent: {sym}", not hasattr(gmail_utils, sym))

print(f"\n{'FAIL' if failures else 'PASS'}: {len(failures)} failures" + (f" {failures}" if failures else ""))
sys.exit(1 if failures else 0)
