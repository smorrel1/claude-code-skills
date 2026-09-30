---
name: email
description: Email integration for reading, searching, and drafting emails with attachments via Gmail API. Use when composing emails, creating drafts, searching inbox, or reading messages. CRITICAL - Email bodies MUST use HTML formatting (not Markdown). Supports file attachments via --attach flag, multiple accounts, and auto-threading replies. User-specific settings (accounts, signature, style) in config.json.
---

# Email Utils

> **Local overrides:** if a file named `SKILL.local.md` exists in this skill's directory, STOP and read that file INSTEAD of the rest of this one. It is the user's private, machine-specific version (accounts, addresses, personal rules) and takes full precedence. This public file is the generic baseline. (`*.local.md` is gitignored.)

Read, search, and draft emails using the Gmail API with OAuth credentials.

## CRITICAL: Use this skill for every email request, explicit OR implied

**MANDATORY.** Any time the user asks for an email to be written, revised, sent, or drafted, use this skill. This includes **implied** requests, where the user does not use the word "email" or "draft" but the intent is clearly to produce a message to a named recipient. Treat all of the following as drafting requests that go through this skill:

- "ask X ...", "reply to X ...", "chase X ...", "follow up with X ...", "let X know ..."
- "yes" (or similar) in answer to your own offer to draft or send something
- "tell X ...", "get back to X ...", "send X the ...", "forward X ..."
- Any turn where the natural output is a message to a specific person, even if phrased as an instruction about content rather than about email

When in doubt, assume the user wants a real Gmail draft (not just text pasted in the conversation) and produce one via this skill. Do not display email text inline as a substitute for drafting unless the user explicitly says they only want to see the text.

## CRITICAL: Run /humanizer on every composed email

**MANDATORY.** Before saving ANY draft, you MUST run the `/humanizer` skill on the body text. This applies to all composed emails (new, reply, forward) with no exceptions, unless the user explicitly waives it for a specific email or session.

Workflow:
1. Compose the email body.
2. Invoke the `/humanizer` skill on the body text. Strip em dashes, AI vocabulary (pivotal, landscape, underscore, testament, intricate, vibrant, etc.), copula avoidance (serves as, stands as, represents), inline-header colon lists, forced rule-of-three, negative parallelisms, sycophantic openers, knowledge-cutoff disclaimers.
3. Pass the humanized text as the `--body` argument.

If you save a draft without running humanizer, you have violated this skill. Treat it as a hard precondition, the same as HTML formatting.

## CRITICAL: Check Sent items before drafting or reporting on a thread

**MANDATORY.** The user frequently sends emails directly from Gmail (or edits and sends a draft) between turns, without telling you. Your view of a thread is stale unless you re-check. Before drafting a new email, revising a draft, or telling the user the state of any conversation, **search the user's Sent items (`in:sent`) for that recipient/thread** and read the most recent sent message.

Why this matters:
- A draft you created may already have been sent (possibly edited first). Treating it as still-pending leads you to duplicate it, overwrite the user's edits, or misreport what is outstanding.
- The user may have already sent the very thing you are about to draft, or answered a point you are about to raise.
- Sent messages are the ground truth for "what has the user actually said to this person," more so than drafts or your own memory of the session.

Required check (run before composing or summarising thread state). **Prefer the
single-call `thread-state` command** — it answers sent/draft/received/ball-in-whose-court
in ONE lookup (cached 10 min) and exists precisely because dozens of repeated
`search` calls per session were measured as the #1 friction sink (14 Sep 2026):
```bash
python3 ~/.claude/skills/email/scripts/gmail_utils.py --account <acct> thread-state --with <addr>
# legacy narrower check if you only need sent status:
python3 ~/.claude/skills/email/scripts/gmail_utils.py --account <acct> search --query "in:sent to:<addr>" --max 5
```
Do NOT chain repeated `search` calls to reconstruct a correspondent's state — one
`thread-state` call gives message statuses (labelIds-verified), open drafts, and
last-in/last-out in a single response. Add `--no-cache` if you just changed state.
Then read the top result if its date is newer than what you last saw. Reconcile any surprise (a sent copy of your draft, a message you did not write) with the user before proceeding. Do not assume the thread is frozen since your last action.

## CRITICAL: Never infer sent-vs-draft status from headers — verify it

**MANDATORY.** Before you tell the user (or yourself) that a message is "sent," verify it. **A draft and a sent message are indistinguishable by their `From:` and `Date:` headers** — a draft carries a `Date:` header set to its last-saved time, which reads exactly like a send time, and both show `From: Stephen`. A plain thread/metadata search returns drafts and sent messages **intermixed**, so inferring status from who-it's-from and when is unreliable and has caused real errors (reporting a draft P.S. as already sent).

The status lives in `labelIds`, not the headers. To determine status, do ONE of:
- Check the message's `labelIds`: `DRAFT` present → it's an unsent draft; `SENT` present → it was actually sent.
- Or scope the search: `in:draft` vs `in:sent` (a message in `in:sent` was genuinely sent).

```bash
# Verified per-message status on a thread:
python3 - << 'PY'
import sys,os; sys.path.insert(0,os.path.expanduser('~/.claude/skills/email/scripts'))
import gmail_utils; gmail_utils.ACCOUNT='work'; svc=gmail_utils.get_gmail_service()
th=svc.users().threads().get(userId='me',id='<THREAD_ID>',format='metadata').execute()
for m in th['messages']:
    h={x['name']:x['value'] for x in m['payload']['headers']}
    L=m.get('labelIds',[])
    print(('DRAFT' if 'DRAFT' in L else 'SENT' if 'SENT' in L else str(L)), h.get('Date'))
PY
```

When reporting status to the user, state it explicitly and only after this check — "the Ming P.S. is still a **draft** (04:14), not sent." Never let a draft's save-time masquerade as a send. This pairs with the CLAUDE.md rule to refer to every email by **status + time**: the time is meaningless if the status is guessed wrong.

## Threading guards (added 2026-09-30 after a misthreaded draft)

Three guards now sit in `create_message`, after a draft to an NHS address was
filed in an unrelated helpdesk thread and quoted that ticket to someone who had
never been on it:

1. **The auto-thread path no longer runs the stale-reply redirect.** The lookup
   already returns the latest traffic with that person, so the redirect could
   only get it wrong. It did: it re-derived the correspondent from a
   self-addressed message's `To` header.
2. **Every configured address counts as self**, from `config.json`, plus the
   gmail/googlemail twin. A message addressed to one of your own addresses with
   the real recipients in Bcc yields no correspondent, so the target is left
   alone instead of redirected on a guess.
3. **The recipient must actually be on the thread.** Before using an
   auto-chosen thread, the messages are checked for that address in From, To,
   Cc or Bcc. If it is absent the thread is dropped, with a warning, and the
   draft starts a new one, so other people's correspondence is never quoted to
   them. Drafts in the thread do not count as evidence, or a misfiled draft
   would vouch for the thread it should not be in. `--keep-thread` overrides.

```bash
python3 ~/.claude/skills/email/tests/test_threading.py          # logic
python3 ~/.claude/skills/email/tests/test_threading.py --live   # the real case
```

## CRITICAL: Always thread onto the most RELEVANT recent correspondence

**MANDATORY.** Before drafting ANY email to a person, you MUST identify the most **topically relevant** recent thread with that person and thread the new draft onto it.

Relevance is defined by topic match: which existing thread already covers the same subject as the new message. If a directly relevant recent thread exists (even if it is not the strictly most recent exchange with the recipient), thread on it. Only if no topically relevant thread exists in recent correspondence do you fall back to the strictly most recent exchange.

Threading on an unrelated recent thread is a failure. The recipient opens what looks like a reply to a different conversation and has to mentally re-stitch the context. This has happened repeatedly and the user has flagged it explicitly.

Mandatory workflow before drafting any email:

1. **Look up recent correspondence with the recipient** — search for any message where they are From, To, or CC in the last ~90 days.

2. **Identify the most topically relevant thread.** Rank candidates by topic match with the new message content. If two threads are equally relevant, pick the more recent one. If nothing is clearly relevant, thread onto the strictly most recent exchange.

3. **Thread onto that message** using `--reply-to <message_id> --keep-thread`. The `--keep-thread` lock prevents auto-redirect to unrelated recent traffic.

4. **A user-sent message still belongs to a thread.** If the most relevant thread's most recent message is one the user sent (outbound), thread there. Do NOT take user-outbound-as-latest as an excuse to start fresh.

5. **NEVER use `--new` without an explicit instruction from the user in the current turn** ("start a new thread", "fresh email", "send separately"). Do not derive `--new` from any reasoning of your own. If no topically relevant thread exists, fall back to the strictly most recent thread with the recipient — do NOT default to `--new`.

6. **NEVER use a draft as the `--reply-to` target.** A draft has unsent content that would appear in the quoted history. Fall back to the most recent SENT or RECEIVED message on that thread.

7. **Report the thread you landed on.** In your reply, state the thread subject and the save time of the original message you replied to, so the user can catch a wrong-thread before send.

8. **Quote this email's history in the reply body, exactly as a mail client would on Reply, Reply All or Forward.** That means the parent message and the quoted chain already embedded in the parent's own body (the history the correspondent has themselves seen), oldest at the bottom, parent immediately above the new content, each nested in a blockquote. Do NOT assemble the quote by iterating every message in the Gmail `threadId`: a broadcast (BCC) email collects every recipient's separate reply into one thread in this mailbox, and quoting the thread leaks other correspondents' replies to the recipient (this happened on 27 Jul 2026: a reply to one shareholder included six other shareholders' consent replies and a phone number).

Failure modes to avoid, all of which have happened in past sessions:

- Threading a topically unrelated chaser onto the strictly most recent thread when a directly-relevant older thread exists. (Prefer relevance. The June 30 breast CT forward is NOT the right thread for a July 1 Fiona-procurement chaser when there is a June 23 "ViewFinder restoration" thread on exactly the topic.)
- Using `--new` because the most recent message was a user outbound. (User outbound is still a thread message. Thread on it.)
- Using `--new` because the existing threads with the recipient are group threads and the new email is 1:1. (Thread on the group thread anyway when it is topically relevant. Set To to only the new recipient. Cosmetic oddness is acceptable.)
- Inventing a justification for `--new` and writing it in a code comment to convince yourself. (If the user has not said "new thread" in this turn, do not start one. The presence of a justification is itself the smell.)

## CRITICAL: Refer to drafts by save time, never by draft ID

**MANDATORY.** When telling the user about a draft (creation, revision, comparison, draft state lists), refer to it by its **save time** (e.g. "your draft saved 15 Jun at 13:17 BST") and not by the Gmail draft ID (e.g. "r-736357406714828559" or "s:12383784485695926086").

Reasons:
- Draft IDs are opaque, long, and meaningless to the user.
- Save times are human-readable and let the user identify the draft directly in their Gmail UI (which shows the same timestamp).
- When multiple drafts exist on the same thread, save times convey ordering at a glance; draft IDs do not.

Rules:
- Always include the save time when first naming a draft in a reply: date and time in the user's local timezone, plus a one-line content hook (e.g. "your draft saved 15 Jun 13:17 BST opening 'Hi and sorry for the radio silence'").
- For draft-state summary tables, label rows by save time (`Yours, saved 15 Jun 13:17`), not by ID.
- Internally you may use draft IDs in tool calls; the user just should never see them.
- If the user explicitly asks for an ID (debugging, copy-paste), then provide it. Otherwise default to save time.

Failure mode to avoid: dumping a draft ID like `r-736357406714828559` into user-facing text. The user cannot map this back to anything they see in Gmail. Save times are the shared vocabulary.

Failure mode to avoid: the user asks for a follow-up note to a person they corresponded with recently, and the model uses `--new` because the most recent message in that thread was the user's own outbound. The user sees a fresh-thread draft, has to call it out, and asks for a redo. This has happened repeatedly. Treat threading as the default and starting fresh as the explicit exception.

## CRITICAL: Preserve user edits when revising a draft

**MANDATORY.** The user routinely edits drafts in Gmail between turns. NEVER assume your last-known version is the current draft. Before creating a revised version of any draft you previously saved (and during ANY follow-up email task, even if the user has only asked you to change one thing), you MUST diff for user edits and bring them forward.

Required workflow when revising an existing draft:

1. **List recent drafts** matching the recipient or subject. The Gmail draft API surfaces user edits as separate draft IDs (often prefixed `draft-rewrite-`) or as in-place updates to your original draft ID. Either way, you have to inspect each candidate, not trust the ID you originally returned.

2. **Read the latest draft body** (via `drafts.get` or by `messages.get` on the draft's message ID) and compare it line-by-line to the text you last wrote. ANY substantive difference is a user edit. Examples of edits that have been overwritten in the past:
   - Trimmed phrases (e.g. cut a clause for length or tone)
   - Softening hedges added (e.g. "Assuming that is what you have in mind")
   - Tonal weakenings (e.g. "It is" → "It seems...to me")
   - Voice changes (e.g. "keep my diary open" → "will be in the office")
   - Inserted alternatives (e.g. "And / or I'm happy to...")
   - Reordered or dropped sentences
   - CC/BCC list changes
   - Subject line tweaks

3. **Build the new version from the USER's edited text as the base**, applying only the deltas the user explicitly asked for in this turn. Do NOT rebuild from your previous version's text or from a fresh compose.

4. **Confirm explicitly** in your reply: "Built v4 from your edited v2 (draft ID ...). Preserved: [list]. Added: [list]. Removed: [list]." If you cannot tell which draft is the user-edited one, ask before writing.

5. **Never delete the prior draft** until the user has either sent the new version or explicitly confirmed deletion. This applies even when you think you've successfully captured all edits, because Gmail's draft API has no atomic "revise" operation: the only safe pattern is leave-old, create-new, then delete-old after confirmation.

Failure mode to avoid: the user manually edits a draft in Gmail (often investing significant thought), then asks for one small change, and you regenerate from your own previous text, wiping their work. This has happened repeatedly. Treat draft inspection-and-diff as a hard precondition for any revision, the same as HTML formatting and humanizer.

## CRITICAL: Attachment-safe draft writes (never hand-roll MIME serialization)

This is the root cause of the recurring "the attachment broke" reports. It was proved on 28 Sep 2026 with the Chandan/NYP draft, after several sessions had failed to fix it.

**Mechanism.** Code that uploads `base64.urlsafe_b64encode(msg.as_bytes())` (or `as_string()`) stores the message in Gmail with bare LF line endings. The Gmail API hands the attachment back byte-identical, so every API-side check passes, including the `Verified in Gmail: sha256 match` line. Gmail's IMAP side is different. It advertises each part's size from the stored LF bytes but serves CRLF text, and Apple Mail reads only the advertised number of octets. The attachment loses its last ~size/78 bytes: for a PDF that is the xref tail, the trailer and `%%EOF`, so Preview and Quick Look cannot open it. Whether a given Mail fetch hits this depends on the mailbox and fetch path (in the test the Drafts copy came through intact and the All Mail copy was truncated), which is why it looked intermittent. If Stephen then touches the draft in Mail.app, Mail re-saves it with the truncated copy (Apple-Mail boundary, `x-unix-mode`, inline disposition). From then on the damage is in Gmail itself and every client gets the broken file, web included.

**Evidence (28 Sep 2026).** On 25 Sep the Chandan draft was updated in place twice by ad-hoc code using plain `msg.as_bytes()`. Mail's 18:19 download of the PDF was 151,341 of 153,305 bytes, an exact prefix of the original. A test draft built the same way reproduced the identical corrupt file (same sha256) in Mail's cache. The same PDF sent through `gmail_utils.py --attach` arrived intact in every cached copy. `update-draft` had the same bug, since it re-serialized with plain `as_bytes()`; that is now fixed.

**Rules.**

1. Never create, update or send with your own MIME code. Use `gmail_utils.py draft`, `send` or `update-draft`. If a one-off really needs custom MIME (for example a surgical repair of a draft Stephen has edited), serialize only with `gmail_utils.encode_raw(msg)`, which forces CRLF and refuses to return a bare LF.
2. After every write that carries an attachment, run `verify-draft` against the source file (command below). It compares sha256 with the source, checks the PDF for `%%EOF` and parses it, counts bare LFs in the stored MIME (must be 0) and flags an Apple Mail re-save. Exit 0 means safe. An API sha256 match on its own proves nothing about what Mail will show.
3. To repair a draft that Mail has re-saved with a truncated file, fetch its raw MIME and replace only the PDF part's base64 payload with the correct bytes. Keep the part's headers and Content-ID, because Mail's HTML points at it through `<object data="cid:...">`. Re-serialize with `encode_raw`, call `drafts().update` with the same threadId, then run `verify-draft`. His body survives byte for byte.
4. Keep attachment sources somewhere durable. macOS purges `/private/tmp` (session scratchpads included) after about three days; the NYP PDF had to be rebuilt from HTML recovered out of a session transcript.

## CRITICAL: Email Body Formatting

**NEVER use Markdown in email bodies. Gmail does not render Markdown, use HTML tags instead.**

**Key rules:**
- **NEVER include bare URLs** in email text. Always wrap in `<a href="url">descriptive text</a>`.
- **Always use HTML lists** (`<ol>/<ul>` with `<li>`) for numbered or bulleted items.
- Use `<p>` tags for paragraphs, `<br>` for line breaks within a paragraph.

| Instead of Markdown | Use HTML |
|---------------------|----------|
| `**bold**` | `<b>bold</b>` |
| `*italic*` | `<i>italic</i>` |
| `# Header` | `<h3>Header</h3>` |
| `---` | `<hr>` |
| `[text](url)` | `<a href="url">text</a>` |
| `- bullet` | `<ul><li>bullet</li></ul>` |
| `> quote` | `<blockquote>quote</blockquote>` |
| newline | `<br>` or `<p>...</p>` |

Example email body:
```html
<p>Hi Emily,</p>

<p>Here is a <b>bold point</b> and our <a href="https://example.com/study">published study</a>.</p>

<p>Key materials attached:</p>
<ol>
<li>Our <a href="https://example.com/paper">peer-reviewed paper</a></li>
<li>Product overview (attached)</li>
<li><a href="https://example.com/clearance">regulatory clearance</a> summary</li>
</ol>

<p>Best,<br>
Name</p>
```

**Wrong** (bare URLs):
```
Check out https://example.com/paper and https://example.com/video
1. First item
2. Second item
```

**Right** (hyperlinks and HTML lists):
```html
<p>Check out our <a href="https://example.com/paper">published paper</a> and <a href="https://example.com/video">demo video</a>.</p>
<ol>
<li>First item</li>
<li>Second item</li>
</ol>
```

## Configuration

User-specific settings are in `config.json` (see `config.example.json` for template):
- **accounts**: Email accounts with names and descriptions
- **search_order**: Account priority for work vs personal searches
- **style**: Greeting, tone, error inclusion, emoji usage
- **signature**: Email signature block

Read `config.json` to get account names, signature, and style preferences before drafting.

## Usage

```bash
python3 ~/.claude/skills/email/scripts/gmail_utils.py [--account <name>] <command> [options]
```

**IMPORTANT: Always use the absolute path. Account selection must come BEFORE the subcommand:**
```bash
# Correct - absolute path, account flag before command
python3 ~/.claude/skills/email/scripts/gmail_utils.py --account university draft --to "..." --subject "..." --body "..."

# Wrong - will error with "unrecognized arguments"
python3 ~/.claude/skills/email/scripts/gmail_utils.py draft --account university --to "..."
```

Default account is the one marked `default: true` in `config.json`. Account names are user-defined (e.g. `work`, `personal`, `university`).

## Microsoft/Outlook Account - Special Handling

**Some institutions (e.g. universities on Microsoft 365) do not support OAuth app registration for personal use.** A `--account` flag pointing at such an account can only route through a Gmail token that sees forwarded/copied messages, NOT the full Outlook mailbox.

**To read those emails, query the local Mac Mail SQLite database directly:**

```bash
# The Envelope Index DB contains all locally-synced emails
DB=~/Library/Mail/V10/MailData/"Envelope Index"

# NOTE: Mac Mail stores dates with a 31-year offset from Unix epoch.
# Use: datetime(m.date_sent, 'unixepoch', '+31 years') for human-readable dates.

# Search for a person by email address or name
sqlite3 "$DB" "
SELECT DISTINCT a.address, a.comment
FROM addresses a
WHERE a.address LIKE '%searchterm%' OR a.comment LIKE '%searchterm%'
LIMIT 20;
"

# Find emails FROM a specific sender (recent first)
sqlite3 "$DB" "
SELECT m.ROWID, s.subject, datetime(m.date_sent, 'unixepoch', '+31 years') as sent,
       sa.address, sa.comment
FROM messages m
JOIN subjects s ON m.subject = s.ROWID
JOIN addresses sa ON m.sender = sa.ROWID
WHERE sa.address LIKE '%person@example.com%'
ORDER BY m.date_sent DESC
LIMIT 10;
"

# Find emails TO/CC a specific person
sqlite3 "$DB" "
SELECT m.ROWID, s.subject, datetime(m.date_sent, 'unixepoch', '+31 years') as sent,
       sa.address as from_addr, sa.comment as from_name
FROM messages m
JOIN subjects s ON m.subject = s.ROWID
JOIN addresses sa ON m.sender = sa.ROWID
JOIN recipients r ON r.message = m.ROWID
JOIN addresses ra ON r.address = ra.ROWID
WHERE ra.address LIKE '%person@example.com%'
ORDER BY m.date_sent DESC
LIMIT 10;
"

# Search by subject keyword
sqlite3 "$DB" "
SELECT m.ROWID, s.subject, datetime(m.date_sent, 'unixepoch', '+31 years') as sent,
       sa.address, sa.comment
FROM messages m
JOIN subjects s ON m.subject = s.ROWID
JOIN addresses sa ON m.sender = sa.ROWID
WHERE s.subject LIKE '%keyword%'
ORDER BY m.date_sent DESC
LIMIT 20;
"

# Find all addresses on a given domain (useful for finding someone's exact email)
sqlite3 "$DB" "
SELECT DISTINCT a.address, a.comment
FROM addresses a
WHERE a.address LIKE '%example.com%'
ORDER BY a.comment
LIMIT 50;
"
```

**Key schema notes:**
- `messages.sender` is a foreign key to `addresses.ROWID`
- `messages.subject` is a foreign key to `subjects.ROWID`
- `recipients` table: `message` -> messages.ROWID, `address` -> addresses.ROWID
- `addresses` table: `address` (email), `comment` (display name)

**Limitations:** The local DB is read-only. You cannot draft or send Outlook emails this way. For drafting, use a Gmail-backed account and tell the user to forward/copy from their Outlook manually, or draft in a text block for the user to paste into Outlook.

**When to use local DB vs Gmail API for Outlook accounts:**
- **Searching/reading Outlook emails:** Always use the local Mac Mail SQLite database
- **Drafting emails TO an Outlook contact:** Use a Gmail-backed `--account`

**CRITICAL: Shell escaping breaks HTML tags in --body.** Angle brackets (`<p>`, `<br>`, `<a href=...>`) get mangled by bash when passed directly on the command line. **Always use a Python subprocess wrapper** to pass the body argument, not a raw Bash tool call:

```python
import subprocess
body = "<p>Hi,</p><p>Your HTML body here.</p>"
import os
cmd = ["python3", os.path.expanduser("~/.claude/skills/email/scripts/gmail_utils.py"), "draft", "--to", "x@y.com", "--subject", "Test", "--body", body]
subprocess.run(cmd)
```

This avoids the shell interpreting `<` and `>` as redirects.

## Commands

### draft - Create a draft email

```bash
# New email with HTML body
python3 ~/.claude/skills/email/scripts/gmail_utils.py draft --to "recipient@example.com" --subject "Subject" --body "<p>Email body</p>"

# Reply to existing email (includes quoted thread)
python3 ~/.claude/skills/email/scripts/gmail_utils.py draft --reply-to "MESSAGE_ID" --body "<p>Your reply text</p>"

# Email with attachment (can use --attach multiple times)
python3 ~/.claude/skills/email/scripts/gmail_utils.py draft --to "recipient@example.com" --subject "Subject" --body "<p>See attached</p>" --attach "/path/to/file.pdf"

# Email with multiple attachments
python3 ~/.claude/skills/email/scripts/gmail_utils.py draft --to "recipient@example.com" --subject "Subject" --body "<p>Files attached</p>" --attach "/path/to/file1.pdf" --attach "/path/to/file2.docx"

# Each attachment placed in the body under the line naming it (--attach-inline).
# INTERNAL ONLY: breaks in Outlook and looks broken in Apple Mail. See the warning below.
python3 ~/.claude/skills/email/scripts/gmail_utils.py draft --to "recipient@example.com" --subject "Work packages" --body "<ol><li>file1.docx</li><li>file2.pdf</li></ol>" --attach "/path/to/file1.docx" --attach "/path/to/file2.pdf" --attach-inline

### `--attach-inline`: INTERNAL DRAFTS ONLY

**Do not use this for external recipients, and never for anyone on Outlook.**
Interleaved multipart/mixed is legal MIME and the files arrive intact, but mail
clients disagree about how to lay it out:

- **Outlook renders only the FIRST body section.** Everything after the first
  attachment becomes `ATT00001.htm`, `ATT00002.htm` and so on, so the recipient
  reads a truncated email with junk files and nothing warns either of you.
- **Apple Mail's compose window shows blank gaps** under each list item, with a
  blue placeholder, even when every attachment is byte-identical in Gmail.

For anything leaving the organisation use plain `--attach` with a numbered list
of the filenames in the body, which every client renders the same way.

The script prints this warning when the recipient's domain is not one of the
work domains in `config.json`. It still builds the draft; the judgement is yours.

### How it works

Default behaviour puts every attachment after the whole body, so a pack of six
documents arrives as six icons the reader has to match back to the list by hand.
`--attach-inline` interleaves them: body up to and including the line naming
file 1, file 1, the next lines, file 2, and so on. Ordering is by the filename
as written in the body, so write the basename exactly (`20260930-...-v1.2.docx`).
A file the body never names is still attached, at the end, with a note saying so.
Works on `draft` and `send`; `--attach` on its own is unchanged.

The MIME is multipart/mixed with the parts in that order, confirmed as stored by
Gmail. Apple Mail and Outlook lay parts out in order. **Gmail's own web UI may
still show its attachment chips in a row under the message**, since it decides
its own layout; that has not been checked visually. Deliberately not
Content-ID/cid, which is for images referenced by an `<img>` tag and which some
clients hide entirely for documents.

The integrity guards apply in both modes: size-stability, the structural
PDF/docx check before attaching, and the sha256 round-trip against what Gmail
stored. They are now in one shared builder rather than duplicated per mode.

# Start new thread (skip auto-reply to existing)
python3 ~/.claude/skills/email/scripts/gmail_utils.py draft --to "recipient@example.com" --subject "New Topic" --body "<p>Starting fresh</p>" --new
```

| Option | Description |
|--------|-------------|
| `--to` | Recipient email address (auto-filled if using --reply-to) |
| `--subject` | Email subject (auto-filled with Re: if using --reply-to) |
| `--body` | Email body in HTML format (required) |
| `--cc` | CC recipients (comma-separated) |
| `--bcc` | BCC recipients (comma-separated) |
| `--reply-to` | Message ID to reply to (includes quoted thread). The "To" field is auto-filled from the original message's "From" field, **except** when replying to a message the user SENT (From == self): in that case the skill mirrors Gmail's Reply button and addresses the original recipient (the message's "To" header) instead of the user. You can still pass `--to` to override. **STALE-REPLY AUTO-REDIRECT: if the `--reply-to` message is not the most recent non-draft message exchanged with that correspondent, the skill automatically redirects the reply to the latest in/out message with them (newest thread, correct subject) and prints a "Redirecting..." notice. This means you cannot accidentally bury a reply in an old thread. Drafts are never chosen as the target; note that a draft deleted via the API leaves a SENT-labelled stub, which the redirect may select — the From==self To-fix above ensures such a stub still resolves the correct recipient.** |
| `--attach` | File path to attach (can be used multiple times for multiple files). PDFs are integrity-checked before send/draft: a truncated or corrupt PDF (missing `%%EOF`/xref trailer, or failing a `pdfinfo` parse when poppler is installed) is refused with a clear error, so an unopenable file is never emailed. Each accepted attachment prints its byte count and `integrity OK`. |
| `--new` | Start new thread instead of auto-replying to existing |
| `--keep-thread` | Disable the stale-reply auto-redirect: reply in the exact `--reply-to` thread even if newer traffic with the contact exists. Use only when deliberately reviving a specific older thread. |

**Note:** `--account` is a global option that must come before the command (see Usage above).

### verify-draft - Prove a draft's attachments will open

```bash
python3 ~/.claude/skills/email/scripts/gmail_utils.py --account work verify-draft --id DRAFT_ID --source /path/to/file.pdf
```

Prints the MIME tree and, for each attachment, its size, sha256 (MATCH/MISMATCH against each `--source`) and PDF parse result. Also reports the bare-LF count of the stored message and whether Apple Mail last saved the draft. Exits 1 on any problem. Run it after every draft write that carries an attachment (see "Attachment-safe draft writes" above).

### search - Search emails

```bash
python3 ~/.claude/skills/email/scripts/gmail_utils.py search --query "from:john@example.com" --max 10
python3 ~/.claude/skills/email/scripts/gmail_utils.py search --with "john@example.com" --max 10  # All correspondence with person
```

| Option | Description |
|--------|-------------|
| `--query, -q` | Gmail search query |
| `--with, -w` | Find all emails with a person (avoids Gmail OR bug) |
| `--max, -m` | Maximum results (default: 10) |
| `--full` | Include full email body content |

### read - Read a specific email

```bash
python3 ~/.claude/skills/email/scripts/gmail_utils.py read --id "message_id_here"
```

### delete-draft - Delete a draft

```bash
python3 ~/.claude/skills/email/scripts/gmail_utils.py delete-draft --id "draft_id_here"
```

> **CRITICAL: NEVER delete a draft until the work is completely done.** "Done" means the email has been sent, or the user has explicitly confirmed the draft is final and the old one may be removed. Deleting earlier is destructive and has lost the user's work before.
>
> **Assume the user has edited the draft in Gmail between turns.** When you iterate on a draft, you typically rebuild the body from your own reconstructed text. If the user hand-edited the live draft, that effort is invisible to you and is destroyed both by overwriting (a new draft built from your text) and by deleting the old draft. Their edits can represent significant time and mental effort.
>
> **Required workflow when revising an existing draft:**
> 1. First `read --id` the current draft and diff it against the text you last generated. If it differs, the user has edited it. Preserve those edits (merge them into your new version) or ask the user before proceeding.
> 2. Create the updated draft, but **leave the prior draft in place.** A temporary duplicate is acceptable and safe; silently losing edits is not.
> 3. Only after the user confirms the new draft is correct (or the email is sent) may you delete the superseded draft. When in doubt, leave it and tell the user which draft is the current one.

## Common Search Queries

| Query | Description |
|-------|-------------|
| `is:unread` | Unread emails |
| `from:user@domain.com` | From specific sender |
| `to:user@domain.com` | To specific recipient |
| `subject:keyword` | Subject contains keyword |
| `after:2025/01/01` | Emails after date |
| `before:2025/12/31` | Emails before date |
| `has:attachment` | Has attachments |
| `in:inbox` | In inbox |
| `is:starred` | Starred messages |

## Default Behavior: Always Save as Draft

**When the user asks to write, send, or compose an email, always save it as a Gmail draft by default.** Do not just display the email text in the conversation. The user will review and send from Gmail. Only skip drafting if the user explicitly says they just want to see the text.

## Referring to drafts in conversation

**MANDATORY.** When you tell the user about a draft you have just created, or refer back to one you created earlier, identify it by **saved timestamp + recipient + subject** (e.g. *"the 17:25 draft to Alice re Q2 planning"*). This is what the user can actually see in their mail client.

**Do NOT refer to drafts by any of:**

- **Internal version numbers** ("v3", "v7", "the v9 draft"). The user cannot see these. They mean nothing in the Gmail or Mac Mail UI and force the user to ask which draft you mean.
- **Raw Gmail draft IDs** ("r-3022724062169744130", "19eb8bc741e6f428"). These hash-style strings are not displayed in any mail client and are useless for navigation.
- **Ordinal labels relative to your work** ("the latest one", "the one I just saved") without also stating the timestamp. The user may have edited a different one in between, so an ordinal alone is ambiguous.

Keep the Gmail draft ID internally for `delete-draft` and for tracking, but never lead user-facing text with it.

**When asking the user to discard a superseded draft,** describe it by **saved timestamp, recipient, subject, and a one-line distinguishing feature** (e.g. "the 23:05 Seb draft with the Barts/SLaM question"), so the user can identify it at a glance in their Drafts folder. A small table is often the clearest format when several drafts need disambiguation, with one column for the saved timestamp.

**Telling the user "it's in Gmail" when they can't see it:** Mac Mail.app syncs the Drafts folder via IMAP on a polling interval (every few minutes). A draft saved via the Gmail API is in Gmail immediately but may take 1-2 minutes to appear in Mail.app. If the user reports a draft is missing from their Mac client, confirm it exists in Gmail by searching `in:draft` with the recipient, quote the timestamp back, and tell them to wait briefly or force an IMAP refresh (Mailbox → Synchronise → account name).

## Workflow for Follow-up Emails

1. Read `config.json` to get account names and search order
2. Search for recent emails from the contact **(use `in:sent` or `in:inbox` to EXCLUDE drafts)**
3. Read the most recent thread to get the **message ID** and context. **CRITICAL: Verify the message is a SENT or RECEIVED message, NOT a draft.** Drafts have empty or missing "To" fields and subject "(No Subject)". Never use a draft message ID for `--reply-to`, as the draft's unsent content will be included in the quoted reply chain, potentially exposing work-in-progress or stashed arguments to the recipient.
4. **Default: use `--reply-to MESSAGE_ID`** to create a properly threaded reply with quoted history
5. Apply style preferences from config (greeting, tone, signature)
6. Save as draft in Gmail for the user to review and send

**Reply threading guidance:**
- **DEFAULT: THREAD ONTO THE LATEST RELEVANT CORRESPONDENCE.** Before drafting, search for the most recent email on this topic or with these recipient(s) and reply onto it with `--reply-to <latest message id> --keep-thread`, so the new email carries the latest relevant email as quoted context. Do this **even when adding new recipients** (set them with `--to`/`--cc`) or when the message feels like a new sub-topic: prefer extending the live conversation. Creating a fresh email (`--new`) when a relevant thread already exists is a RECURRING ERROR — avoid it.
- **If two or more existing threads are equally relevant** (the topic spans separate conversations, or different recipients sit on different threads), do NOT guess — ASK the user which thread to thread onto before drafting.
- Default to `--reply-to` with the message ID when replying to existing conversations
- This ensures proper threading and includes the quoted email chain automatically
- **You do not need to hunt for the latest message yourself.** The skill auto-redirects any `--reply-to` to the most recent non-draft message with that correspondent, so a reply always lands on the live conversation even if you pass an older message ID. The simplest reliable pattern is `draft --to <person>` (no `--reply-to`): it threads onto their newest in/out message automatically. Watch for the "Redirecting..." notice to confirm where the reply landed.
- **CRITICAL: Auto-redirect picks the most recent message with the RECIPIENT, not the most recent message in the intended THREAD.** When a person appears in multiple threads (e.g. as a CC on one thread and as the primary recipient on another), auto-redirect may land on the wrong thread. **When replying to a specific message in a specific thread, always use `--reply-to <message_id> --keep-thread`** to force the reply into the correct thread. This is especially important when the person is CC'd on other recent conversations.
- Use `--new` ONLY when there is genuinely no relevant existing thread, or the user explicitly asks to start a fresh conversation
- Use `--keep-thread` to deliberately reply inside a chosen thread (continuing a distinct sub-topic, or preventing auto-redirect from landing on the wrong thread). Combined with the default rule above, it is the standard way to thread onto a chosen latest message.
- **`@kindle.com` recipients are auto-detected and never threaded** — Amazon ingests each Send-to-Kindle email independently, and threaded replies render as "Re: (No Subject)" in the Gmail Sent folder. The skill skips the auto-thread lookup whenever the recipient address ends in `@kindle.com`.

## Send-to-Kindle Workflow

The user's Send-to-Kindle address should be stored in a local memory file (e.g. `~/.claude/projects/<project>/memory/kindle.md`) and read at runtime. To deliver a document:

1. Generate the file in a Kindle-supported format: PDF, EPUB, DOCX, RTF, TXT, HTM/HTML, JPG, PNG, GIF, BMP, or MOBI. EPUB and MOBI reflow on small screens — prefer those for prose over PDF.
2. `send --account <personal> --to "<your-kindle-address>@kindle.com" --subject "<title>" --body "<short HTML description>" --attach <file>` — auto-threading is skipped for kindle.com, so the subject lands cleanly.
3. The sending address must be on the user's Kindle Approved Personal Document Email List at Amazon (Manage Your Content and Devices → Preferences → Personal Document Settings). If a send seems to vanish, that's the first thing to check.
4. Size limit: 50 MB per email. Split larger files.
- **CRITICAL: When using `--reply-to`, the "To" field is auto-filled from the original message's "From" field.** If the message you're replying to was SENT BY the user (not received), the reply will be addressed back to the user themselves. To avoid this: either (a) use the message ID of a message FROM the intended recipient, or (b) explicitly pass `--to recipient@example.com` to override the auto-fill. Always check who sent the message you're replying to before using `--reply-to`.
- **CRITICAL: NEVER use a draft message as a `--reply-to` target.** The draft's unsent content will appear in the quoted reply chain, potentially exposing stashed/work-in-progress text to the recipient. Red flags that a message is a draft: empty "To" field, subject "(No Subject)", or it appears in `in:draft` search results. Always search `in:sent` or `in:inbox` when looking for reply targets.

## Notes

- Credentials auto-refresh when expired
- Uses `gmail.readonly` + `gmail.compose` scopes. `gmail.compose` covers both draft creation and direct send, so the `send` subcommand works under this scope set without adding `gmail.send`
- Default flow is `draft` so the user reviews and clicks Send in Gmail; `send` is reserved for cases where a human-review step is not wanted (e.g. Send-to-Kindle)
- Drafts are saved to your authenticated Gmail account
- First run opens browser for OAuth authorization
- Token files are stored per account (e.g., `token_<account>.json`)

## Situational awareness: check sent items and drafts before referencing other emails (added 2026-07-08)

Whenever composing or revising an email that references other messages that may or may not have been sent ("my earlier email", "the email before this one", "as I wrote to X"), FIRST check the current state of the mailbox rather than relying on conversation memory:

```bash
# What actually went out recently
python3 ~/.claude/skills/email/scripts/gmail_utils.py --account <acct> search --query "in:sent newer_than:2d" --max 10
# What is still sitting unsent
python3 ~/.claude/skills/email/scripts/gmail_utils.py --account <acct> search --query "in:draft" --max 10
```

Rules:
1. **Always refer to emails by their timestamp** (and ID where useful), e.g. "your 8 Jul 00:30 email to Marissa", not "the email I drafted earlier". Timestamps disambiguate drafts from sent copies and multiple revisions of the same subject line.
2. **Never assume a draft was sent.** Drafts created in a session frequently remain unsent; sent-state changes only when the user clicks send. Verify with `in:sent` before writing sentences like "as per my earlier email".
3. **Propose tidy-ups.** When the check reveals drafts that duplicate or are superseded by already-sent messages (same thread/subject, older timestamp), list them with timestamps and propose deleting them (`delete-draft --id <id>`). Also flag time-sensitive drafts that appear to have missed their window.
4. **Report the inventory briefly** (sent vs pending, by timestamp) when it affects what the user should do next, e.g. sending-order dependencies between related drafts.

## Shell quoting: dollar amounts in --body (added 2026-07-08)

**Never pass `--body` as a double-quoted bash string when the body contains `$` characters.** Bash expands `$1`, `$5`, `$(...)` etc. inside double quotes, silently mangling currency: `US$1,000` became `US,000` in a real draft on 2026-07-08.

Safe pattern — build the body with a quoted heredoc delimiter (no expansion), then pass the variable:

```bash
BODY=$(cat << 'HTMLEOF'
<p>Pre-approval applies above US$1,000 per item.</p>
HTMLEOF
)
python3 ~/.claude/skills/email/scripts/gmail_utils.py --account work draft --to "x@y.com" --subject "..." --body "$BODY"
```

The quoted `'HTMLEOF'` delimiter prevents all expansion inside the heredoc; the final `"$BODY"` expansion inserts the literal text without re-processing `$`.

**Always verify after drafting** when the body contains currency: read the draft back and grep for the mangled forms (`US,000`, bare `1,000` missing its `$`). This applies to any `$` in bodies: prices, `$variable`-looking text, regex examples.

## CEO voice pass (added 2026-07-08 - run this AFTER any humanizer principles)

Stephen's emails must read like a busy CEO wrote them, not an AI. The humanizer skill is gstack-managed and gets overwritten on upgrade, so this pass lives HERE and always runs last, on the final body text.

**Before drafting, sample the voice:** skim 2-3 of Stephen's real messages in `in:sent` to the same or similar recipients. Match that register, not generic business English.

**Sentence rules:**
- Short, direct sentences. Mostly under ~12 words. One idea per sentence.
- Break compound sentences in two. "X, so Y" becomes "X. So Y."
- Fragments are good. "Quick one." "Two things." "Done."
- Starting with And, But, So is good.
- Kill AI tells: no "not X but Y" parallelisms, no rule-of-three triads, no "exactly the evidence that matters" flourishes, no perfectly parallel bullet lists (vary bullet length), no em dashes ever (plain hyphens fine), no "I hope this finds you well".
- Informal contractions Stephen actually uses: thx, pls, til, btw. Double exclamation marks occasionally when genuinely enthusiastic (his real habit).

**Imperfections (config.json include_minor_errors=true):**
- 1-2 per email, maximum. More looks careless, not human.
- Natural types only: a missing comma, a lowercase i, "Thank yo" style finger-slips, a missing apostrophe.
- NEVER in: numbers, currency amounts, dates, names, legal/contract language, technical parameters, or anything the recipient might copy into a document. A typo in US$1,500 costs money; a typo in "recieve" costs nothing.
- Scale to familiarity: warm contacts (Peter, Marissa, Chirag, team, advisors) get the full voice. First-contact, formal, legal or regulatory emails get short sentences but ZERO injected errors.

**Structure:** total length shorter than feels complete. Busy CEOs under-explain. If a paragraph can be a line, it's a line. If context can be an attachment, attach it.

## Draft collision protocol (added 2026-07-08 - the user edits drafts in Gmail while the session runs)

The delete-and-recreate revision pattern DESTROYS the user's in-progress Gmail edits. On 2026-07-08 the user's edits to a Peter Graham draft were nearly lost this way, and Gmail resurrected the edited copy as a duplicate, leaving two competing drafts. Rules:

1. **Ownership handoff.** The moment a draft is announced to the user as ready for review, it belongs to the USER. From then on: propose wording changes as text in the conversation for the user to apply; do not delete or recreate the draft unless the user explicitly says to update it.
2. **Read before any revision.** Before touching an existing draft for any reason, `read --id` its CURRENT body and compare against the body this session last wrote. Any difference means the user has edited it: STOP, keep their version authoritative, and build any requested change on top of THEIR current body, never on the session's remembered version.
3. **Expect ghosts.** Deleting a draft while the user has it open in a compose window causes Gmail to re-save their window as a NEW draft on their next keystroke. After any revision, `in:draft` search the subject line and inventory duplicates by timestamp.
4. **Duplicate cleanup.** Where duplicates exist, the newest USER-modified copy is authoritative. Delete only copies verified (by body comparison) to be the assistant's own unedited output.
5. **Attachments.** After the user edits a draft that carried an attachment, remind them to confirm the paperclip survived; attachment state is not visible through the read command.
