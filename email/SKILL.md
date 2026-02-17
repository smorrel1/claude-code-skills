---
name: email
description: Email integration for reading, searching, and drafting emails with attachments via Gmail API. Use when composing emails, creating drafts, searching inbox, or reading messages. CRITICAL - Email bodies MUST use HTML formatting (not Markdown). Supports file attachments via --attach flag, multiple accounts, and auto-threading replies. User-specific settings (accounts, signature, style) in config.json.
---

# Email Utils

Read, search, and draft emails using the Gmail API with OAuth credentials.

## CRITICAL: Email Body Formatting

**NEVER use Markdown in email bodies. Gmail does not render Markdown - use HTML tags instead.**

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

<p>Here is a <b>bold point</b> and a <a href="https://example.com">link</a>.</p>

<h3>Key Items</h3>
<ul>
<li>First point</li>
<li>Second point</li>
</ul>

<p>Best,<br>
Name</p>
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
python3 scripts/gmail_utils.py <command> [options]
```

**Account selection**: Use `--account <name>` where name matches a key in config.json accounts.

## Commands

### draft - Create a draft email

```bash
# New email with HTML body
python3 scripts/gmail_utils.py draft --to "recipient@example.com" --subject "Subject" --body "<p>Email body</p>"

# Reply to existing email (includes quoted thread)
python3 scripts/gmail_utils.py draft --reply-to "MESSAGE_ID" --body "<p>Your reply text</p>"

# Email with attachment (can use --attach multiple times)
python3 scripts/gmail_utils.py draft --to "recipient@example.com" --subject "Subject" --body "<p>See attached</p>" --attach "/path/to/file.pdf"

# Email with multiple attachments
python3 scripts/gmail_utils.py draft --to "recipient@example.com" --subject "Subject" --body "<p>Files attached</p>" --attach "/path/to/file1.pdf" --attach "/path/to/file2.docx"

# Start new thread (skip auto-reply to existing)
python3 scripts/gmail_utils.py draft --to "recipient@example.com" --subject "New Topic" --body "<p>Starting fresh</p>" --new
```

| Option | Description |
|--------|-------------|
| `--to` | Recipient email address (auto-filled if using --reply-to) |
| `--subject` | Email subject (auto-filled with Re: if using --reply-to) |
| `--body` | Email body in HTML format (required) |
| `--cc` | CC recipients (comma-separated) |
| `--bcc` | BCC recipients (comma-separated) |
| `--reply-to` | Message ID to reply to (includes quoted thread) |
| `--attach` | File path to attach (can be used multiple times for multiple files) |
| `--new` | Start new thread instead of auto-replying to existing |
| `--account` | Account name from config.json (default: first work account) |

### search - Search emails

```bash
python3 scripts/gmail_utils.py search --query "from:john@example.com" --max 10
python3 scripts/gmail_utils.py search --with "john@example.com" --max 10  # All correspondence with person
```

| Option | Description |
|--------|-------------|
| `--query, -q` | Gmail search query |
| `--with, -w` | Find all emails with a person (avoids Gmail OR bug) |
| `--max, -m` | Maximum results (default: 10) |
| `--full` | Include full email body content |

### read - Read a specific email

```bash
python3 scripts/gmail_utils.py read --id "message_id_here"
```

### delete-draft - Delete a draft

```bash
python3 scripts/gmail_utils.py delete-draft --id "draft_id_here"
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

## Workflow for Follow-up Emails

1. Read `config.json` to get account names and search order
2. Search for recent emails from the contact (in sent AND inbox)
3. Read the most recent thread to get the **message ID** and context
4. **Default: use `--reply-to MESSAGE_ID`** to create a properly threaded reply with quoted history
5. Apply style preferences from config (greeting, tone, signature)
6. Review the draft in Gmail before sending

**Reply threading guidance:**
- Default to `--reply-to` with the message ID when replying to existing conversations
- This ensures proper threading and includes the quoted email chain automatically
- Use `--new` when the user specifies starting a fresh thread, or when clearly starting an unrelated conversation

## Notes

- Credentials auto-refresh when expired
- Uses gmail.compose and gmail.readonly scopes
- Drafts are saved to your authenticated Gmail account
- First run opens browser for OAuth authorization
- Token files are stored per account (e.g., `token_<account>.json`)
