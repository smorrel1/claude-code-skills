---
name: email
description: Email integration for reading, searching, and drafting emails with attachments via Gmail API. Use when composing emails, creating drafts, searching inbox, or reading messages. CRITICAL - Email bodies MUST use HTML formatting (not Markdown). Supports file attachments via --attach flag, multiple accounts, and auto-threading replies. User-specific settings (accounts, signature, style) in config.json.
---

# Email Utils

Read, search, and draft emails using the Gmail API with OAuth credentials.

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

**When you tell the user about a draft you have just created, or refer back to one you created earlier, identify it by `timestamp + recipient + subject`** (e.g. *"the 17:25 draft to Alice re Q2 planning"*), **not by the raw Gmail draft ID** (e.g. `r-3022724062169744130`). The IDs the API returns are long, opaque and not searchable in the Gmail UI, so they make it hard for the user to find the right draft. Keep the ID available internally for `delete-draft` and for tracking, but do not lead user-facing text with it.

The same applies when asking the user to discard a superseded draft: describe it by **time created, recipient, subject and attachment count**, so the user can identify it in their Drafts folder. A small table is often the clearest format when there are several drafts to disambiguate.

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
