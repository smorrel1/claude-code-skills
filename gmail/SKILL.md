---
name: gmail
description: Gmail integration for reading, searching, and drafting emails. Supports creating draft emails, searching with Gmail query syntax, and reading full email content.
---

# Gmail Utils

Read, search, and draft emails using the Gmail API with OAuth credentials.

## Usage

Run the script to interact with Gmail:

```bash
python3 scripts/gmail_utils.py <command> [options]
```

## Commands

### draft - Create a draft email

```bash
# New email
python3 scripts/gmail_utils.py draft --to "recipient@example.com" --subject "Subject" --body "Email body"

# Reply to existing email (includes quoted thread)
python3 scripts/gmail_utils.py draft --reply-to "MESSAGE_ID" --body "Your reply text"

# Email with attachment
python3 scripts/gmail_utils.py draft --to "recipient@example.com" --subject "Subject" --body "See attached" --attach "/path/to/file.pdf"

# Email with multiple attachments
python3 scripts/gmail_utils.py draft --to "recipient@example.com" --subject "Subject" --body "Files attached" --attach "/path/to/file1.pdf" --attach "/path/to/file2.docx"
```

Options:
| Option | Description |
|--------|-------------|
| `--to` | Recipient email address (auto-filled if using --reply-to) |
| `--subject` | Email subject (auto-filled with Re: if using --reply-to) |
| `--body` | Email body text (required) |
| `--cc` | CC recipients (comma-separated) |
| `--bcc` | BCC recipients (comma-separated) |
| `--reply-to` | Message ID to reply to (includes quoted thread below) |
| `--attach` | File path to attach (can be used multiple times) |
| `--new` | Start new thread instead of auto-replying to existing |

### search - Search emails

```bash
python3 scripts/gmail_utils.py search --query "from:john@example.com" --max 10
```

Options:
| Option | Description |
|--------|-------------|
| `--query, -q` | Gmail search query (required) |
| `--max, -m` | Maximum results (default: 10) |
| `--full` | Include full email body content |

### read - Read a specific email

```bash
python3 scripts/gmail_utils.py read --id "message_id_here"
```

Options:
| Option | Description |
|--------|-------------|
| `--id` | Email message ID (required) |

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

## Examples

```bash
# Create a draft email
python3 scripts/gmail_utils.py draft \
  --to "recipient@example.com" \
  --subject "Meeting Request" \
  --body "Let's schedule a meeting to discuss the project."

# Create a draft with attachment
python3 scripts/gmail_utils.py draft \
  --to "recipient@example.com" \
  --subject "Document for review" \
  --body "Please find the document attached." \
  --attach "/path/to/document.pdf"

# Search for recent emails from a contact
python3 scripts/gmail_utils.py search --query "from:john@example.com" --max 5 --full

# Search unread emails with attachments
python3 scripts/gmail_utils.py search --query "is:unread has:attachment" --max 10

# Read a specific email by ID
python3 scripts/gmail_utils.py read --id "19aa1e9c686d59b2"
```

## Workflow

When creating follow-up/reply emails:

1. Search for recent emails from the contact (in sent AND inbox)
2. Read the most recent thread to get the **message ID** and context
3. **Default: use `--reply-to MESSAGE_ID`** to create a properly threaded reply with quoted history
4. Review the draft in Gmail before sending

**Reply threading guidance:**
- Default to `--reply-to` with the message ID when replying to existing conversations
- This ensures proper threading and includes the quoted email chain automatically
- Alternative: use `--new` when the user specifies starting a fresh thread, or when clearly starting an unrelated conversation

## Email Body Formatting

**IMPORTANT: Use HTML, not Markdown.** Markdown does not render in Gmail - use HTML tags instead:

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
Stephen</p>
```

## Notes

- Credentials auto-refresh when expired
- Uses gmail.compose and gmail.readonly scopes
- Drafts are saved to your authenticated Gmail account
- First run opens browser for OAuth authorization
