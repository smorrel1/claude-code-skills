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

<p>Here is a <b>bold point</b> and our <a href="https://doi.org/10.1016/j.ejrad.2025.112356">published study</a>.</p>

<p>Key materials attached:</p>
<ol>
<li>Our <a href="https://doi.org/example">peer-reviewed paper</a> in the EJR</li>
<li>Product overview (attached)</li>
<li><a href="https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K223501">FDA clearance</a> summary</li>
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
python3 ~/.claude/skills/email/scripts/gmail_utils.py --account kcl draft --to "..." --subject "..." --body "..."

# Wrong - will error with "unrecognized arguments"
python3 ~/.claude/skills/email/scripts/gmail_utils.py draft --account kcl --to "..."
```

Default account is `elaitra`. Available accounts: `elaitra`, `gmail`, `kcl`.

## KCL Email Account (stephen.morrell@kcl.ac.uk) - Special Handling

**KCL uses Microsoft/Outlook and does not support OAuth app registration for personal use.** The `--account kcl` flag routes through a Gmail token that only sees forwarded/copied messages, NOT the full KCL mailbox.

**To read KCL emails, query the local Mac Mail SQLite database directly:**

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
WHERE sa.address LIKE '%person@kcl.ac.uk%'
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
WHERE ra.address LIKE '%person@kcl.ac.uk%'
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

# Find all KCL addresses (useful for finding someone's exact email)
sqlite3 "$DB" "
SELECT DISTINCT a.address, a.comment
FROM addresses a
WHERE a.address LIKE '%kcl.ac.uk%'
ORDER BY a.comment
LIMIT 50;
"
```

**Key schema notes:**
- `messages.sender` is a foreign key to `addresses.ROWID`
- `messages.subject` is a foreign key to `subjects.ROWID`
- `recipients` table: `message` -> messages.ROWID, `address` -> addresses.ROWID
- `addresses` table: `address` (email), `comment` (display name)

**Limitations:** The local DB is read-only. You cannot draft or send KCL emails this way. For drafting KCL emails, use `--account elaitra` or `--account gmail` and tell the user to forward/copy from their KCL Outlook manually, or draft in a text block for the user to paste into Outlook.

**When to use local DB vs Gmail API for KCL:**
- **Searching/reading KCL emails:** Always use the local Mac Mail SQLite database
- **Drafting emails TO a KCL contact:** Use `--account elaitra` (sends from stephen.morrell@elaitra.com)

**CRITICAL: Shell escaping breaks HTML tags in --body.** Angle brackets (`<p>`, `<br>`, `<a href=...>`) get mangled by bash when passed directly on the command line. **Always use a Python subprocess wrapper** to pass the body argument, not a raw Bash tool call:

```python
import subprocess
body = "<p>Hi,</p><p>Your HTML body here.</p>"
cmd = ["python3", "/Users/stephenmorrell/.claude/skills/email/scripts/gmail_utils.py", "draft", "--to", "x@y.com", "--subject", "Test", "--body", body]
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

## Workflow for Follow-up Emails

1. Read `config.json` to get account names and search order
2. Search for recent emails from the contact **(use `in:sent` or `in:inbox` to EXCLUDE drafts)**
3. Read the most recent thread to get the **message ID** and context. **CRITICAL: Verify the message is a SENT or RECEIVED message, NOT a draft.** Drafts have empty or missing "To" fields and subject "(No Subject)". Never use a draft message ID for `--reply-to`, as the draft's unsent content will be included in the quoted reply chain, potentially exposing work-in-progress or stashed arguments to the recipient.
4. **Default: use `--reply-to MESSAGE_ID`** to create a properly threaded reply with quoted history
5. Apply style preferences from config (greeting, tone, signature)
6. Save as draft in Gmail for the user to review and send

**Reply threading guidance:**
- Default to `--reply-to` with the message ID when replying to existing conversations
- This ensures proper threading and includes the quoted email chain automatically
- **You do not need to hunt for the latest message yourself.** The skill auto-redirects any `--reply-to` to the most recent non-draft message with that correspondent, so a reply always lands on the live conversation even if you pass an older message ID. The simplest reliable pattern is `draft --to <person>` (no `--reply-to`): it threads onto their newest in/out message automatically. Watch for the "Redirecting..." notice to confirm where the reply landed.
- **CRITICAL: Auto-redirect picks the most recent message with the RECIPIENT, not the most recent message in the intended THREAD.** When a person appears in multiple threads (e.g. as a CC on one thread and as the primary recipient on another), auto-redirect may land on the wrong thread. **When replying to a specific message in a specific thread, always use `--reply-to <message_id> --keep-thread`** to force the reply into the correct thread. This is especially important when the person is CC'd on other recent conversations.
- Use `--new` when the user specifies starting a fresh thread, or when clearly starting an unrelated conversation
- Use `--keep-thread` only to deliberately reply inside a specific older thread (e.g. continuing a distinct sub-topic) when newer unrelated traffic with the contact exists, **OR when replying to a specific message and you need to prevent auto-redirect from landing on the wrong thread**
- **`@kindle.com` recipients are auto-detected and never threaded** — Amazon ingests each Send-to-Kindle email independently, and threaded replies render as "Re: (No Subject)" in the Gmail Sent folder. The skill skips the auto-thread lookup whenever the recipient address ends in `@kindle.com`.

## Send-to-Kindle Workflow

Stephen's Send-to-Kindle address is stored in `~/.claude/projects/-home-mhutel-Dropbox-Documents/memory/kindle.md`. To deliver a document:

1. Generate the file in a Kindle-supported format: PDF, EPUB, DOCX, RTF, TXT, HTM/HTML, JPG, PNG, GIF, BMP, or MOBI. EPUB and MOBI reflow on small screens — prefer those for prose over PDF.
2. `send --account gmail --to "stephen.morrell_FDnf9R@kindle.com" --subject "<title>" --body "<short HTML description>" --attach <file>` — auto-threading is skipped for kindle.com, so the subject lands cleanly.
3. The sending address (e.g. `stephen.morrell@gmail.com`) must be on Stephen's Kindle Approved Personal Document Email List at amazon.co.uk → Manage Your Content and Devices → Preferences → Personal Document Settings. If a send seems to vanish, that's the first thing to check.
4. Size limit: 50 MB per email. Split larger files.
- **CRITICAL: When using `--reply-to`, the "To" field is auto-filled from the original message's "From" field.** If the message you're replying to was SENT BY the user (not received), the reply will be addressed back to the user themselves. To avoid this: either (a) use the message ID of a message FROM the intended recipient, or (b) explicitly pass `--to recipient@example.com` to override the auto-fill. Always check who sent the message you're replying to before using `--reply-to`.
- **CRITICAL: NEVER use a draft message as a `--reply-to` target.** The draft's unsent content will appear in the quoted reply chain, potentially exposing stashed/work-in-progress text to the recipient. Red flags that a message is a draft: empty "To" field, subject "(No Subject)", or it appears in `in:draft` search results. Always search `in:sent` or `in:inbox` when looking for reply targets.

## Notes

- Credentials auto-refresh when expired
- Uses gmail.compose and gmail.readonly scopes
- Drafts are saved to your authenticated Gmail account
- First run opens browser for OAuth authorization
- Token files are stored per account (e.g., `token_<account>.json`)
