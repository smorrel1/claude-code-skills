#!/usr/bin/env python3
"""Gmail utility for reading, searching, drafting, and sending emails."""

import argparse
import base64
import json
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.application import MIMEApplication
from email import encoders
import mimetypes
import html as html_module
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
except ImportError:
    print("Installing required packages...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q",
                          "google-auth", "google-auth-oauthlib", "google-api-python-client"])
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# Paths to OAuth credentials
SKILL_DIR = Path(__file__).parent.parent
CREDENTIALS_PATH = SKILL_DIR / "credentials.json"
TOKEN_PATH = SKILL_DIR / "token_elaitra.json"

# Account-specific token paths
ACCOUNT_TOKENS = {
    'elaitra': SKILL_DIR / "token_elaitra.json",
    'gmail': SKILL_DIR / "token_gmail.json",
    'kcl': SKILL_DIR / "token_kcl.json",
}

# Current account (set by main() before any API calls)
CURRENT_ACCOUNT = 'elaitra'

# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.send'
]


def get_token_path():
    """Get the token path for the current account."""
    return ACCOUNT_TOKENS.get(CURRENT_ACCOUNT, TOKEN_PATH)


def get_credentials() -> Credentials:
    """Load and refresh OAuth credentials, or run auth flow if needed."""
    creds = None
    token_path = get_token_path()

    # Load existing token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_PATH}\n"
                    "Download OAuth credentials from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            print(f"Opening browser to authorize account ({CURRENT_ACCOUNT})...")
            creds = flow.run_local_server(port=0)

        # Save credentials
        with open(token_path, 'w') as f:
            f.write(creds.to_json())
        print(f"Token saved to {token_path}")

    return creds


def get_gmail_service():
    """Build and return Gmail API service."""
    creds = get_credentials()
    return build('gmail', 'v1', credentials=creds)


def get_email_for_reply(service, message_id: str):
    """Fetch email details needed for a reply."""
    msg_data = service.users().messages().get(
        userId='me', id=message_id, format='full'
    ).execute()

    headers = {h['name']: h['value'] for h in msg_data['payload']['headers']}
    body_text, body_html = extract_body_both(msg_data['payload'])

    return {
        'id': message_id,
        'threadId': msg_data['threadId'],
        'from': headers.get('From', 'Unknown'),
        'to': headers.get('To', ''),
        'subject': headers.get('Subject', '(No Subject)'),
        'date': headers.get('Date', ''),
        'message_id': headers.get('Message-ID', ''),
        'references': headers.get('References', ''),
        'body': body_text,
        'body_html': body_html
    }


def format_quoted_reply(original_email: dict) -> str:
    """Format the original email as a quoted reply (plain text fallback)."""
    quoted_lines = []
    quoted_lines.append(f"\n\nOn {original_email['date']}, {original_email['from']} wrote:\n")

    # Quote each line of the original body
    for line in original_email['body'].split('\n'):
        quoted_lines.append(f"> {line}")

    return '\n'.join(quoted_lines)


def format_quoted_reply_html(original_email: dict) -> str:
    """Format the original email as an HTML quoted reply, preserving formatting."""
    from_addr = html_module.escape(original_email['from'])
    date = html_module.escape(original_email['date'])

    # Use original HTML if available, otherwise convert plain text to HTML
    if original_email.get('body_html'):
        quoted_content = original_email['body_html']
    else:
        # Convert plain text to HTML, preserving line breaks
        escaped = html_module.escape(original_email['body'])
        quoted_content = escaped.replace('\n', '<br>\n')

    return f'''<br><br>
<div class="gmail_quote">
<div dir="ltr" class="gmail_attr">On {date}, {from_addr} wrote:<br></div>
<blockquote class="gmail_quote" style="margin:0px 0px 0px 0.8ex;border-left:1px solid rgb(204,204,204);padding-left:1ex">
{quoted_content}
</blockquote>
</div>'''


def find_latest_thread_message(service, email_address: str) -> str:
    """Find the most recent message ID in a thread with the given email address.

    Note: Gmail's OR operator prioritizes left-side matches, so we run separate
    queries for 'from:' and 'to:' and return the most recent across both.
    """
    # Run separate queries to avoid Gmail OR prioritization bug
    from_results = service.users().messages().list(
        userId='me', q=f"from:{email_address}", maxResults=1
    ).execute()

    to_results = service.users().messages().list(
        userId='me', q=f"to:{email_address}", maxResults=1
    ).execute()

    from_msgs = from_results.get('messages', [])
    to_msgs = to_results.get('messages', [])

    # If we have results from both, compare internal dates to find most recent
    if from_msgs and to_msgs:
        from_msg = service.users().messages().get(
            userId='me', id=from_msgs[0]['id'], format='metadata',
            metadataHeaders=['Date']
        ).execute()
        to_msg = service.users().messages().get(
            userId='me', id=to_msgs[0]['id'], format='metadata',
            metadataHeaders=['Date']
        ).execute()
        # Use internalDate (milliseconds since epoch) for comparison
        if int(from_msg.get('internalDate', 0)) > int(to_msg.get('internalDate', 0)):
            return from_msgs[0]['id']
        else:
            return to_msgs[0]['id']
    elif from_msgs:
        return from_msgs[0]['id']
    elif to_msgs:
        return to_msgs[0]['id']
    return None


def create_message(to: str, subject: str, body: str, cc: str = None, bcc: str = None,
                   reply_to_id: str = None, new_thread: bool = False, attachments: list = None):
    """Create an email message, automatically replying to existing thread unless --new is specified.

    Args:
        attachments: List of file paths to attach to the email.

    Returns:
        tuple: (raw_message, thread_id, to, subject, reply_to_id)
    """
    service = get_gmail_service()

    thread_id = None
    in_reply_to = None
    references = None
    use_html = False
    original = None

    # Check if body contains HTML tags
    body_has_html = '<a ' in body or '<b>' in body or '<ul>' in body or '<li>' in body or '<br>' in body

    # Auto-find prior thread if:
    # - Not explicitly starting a new thread (--new)
    # - No explicit reply-to ID provided
    # - We have a recipient email
    if not new_thread and not reply_to_id and to:
        # Extract email address from "Name <email>" format if needed
        email_addr = to
        if '<' in to:
            email_addr = to.split('<')[1].rstrip('>')

        auto_reply_id = find_latest_thread_message(service, email_addr)
        if auto_reply_id:
            reply_to_id = auto_reply_id
            print(f"Auto-replying to existing thread (use --new to start fresh thread)")

    # If replying to an existing message, fetch it and include quoted text
    if reply_to_id:
        original = get_email_for_reply(service, reply_to_id)
        thread_id = original['threadId']
        in_reply_to = original['message_id']
        references = f"{original['references']} {original['message_id']}".strip()
        use_html = True  # Use HTML for replies to preserve formatting

        # Use original sender as recipient if not specified
        if not to:
            # Extract email from "Name <email>" format
            from_addr = original['from']
            if '<' in from_addr:
                to = from_addr.split('<')[1].rstrip('>')
            else:
                to = from_addr

        # Ensure subject has Re: prefix
        if not subject.lower().startswith('re:'):
            subject = f"Re: {original['subject'].replace('Re: ', '').replace('RE: ', '')}"

    # Build the message body part
    if use_html and original:
        # Convert plain text body to HTML (preserving line breaks) unless body already has HTML
        if body_has_html:
            body_html = body  # HTML already has structure, don't add extra <br>
        else:
            body_escaped = html_module.escape(body)
            body_html = body_escaped.replace('\n', '<br>\n')

        # Add quoted reply
        quoted_html = format_quoted_reply_html(original)

        full_html = f'''<div dir="ltr">{body_html}</div>{quoted_html}'''

        # Create multipart message with both HTML and plain text
        body_part = MIMEMultipart('alternative')

        # Plain text version (fallback)
        plain_body = body + format_quoted_reply(original)
        part_plain = MIMEText(plain_body, 'plain')
        body_part.attach(part_plain)

        # HTML version (preferred)
        part_html = MIMEText(full_html, 'html')
        body_part.attach(part_html)
    elif body_has_html:
        # New thread with HTML content - send as HTML (don't add <br> since HTML already has structure)
        full_html = f'''<html><body><div dir="ltr">{body}</div></body></html>'''

        # Create multipart message with both HTML and plain text
        body_part = MIMEMultipart('alternative')

        # Plain text version (strip HTML tags for fallback)
        import re
        plain_body = re.sub(r'<[^>]+>', '', body)
        part_plain = MIMEText(plain_body, 'plain')
        body_part.attach(part_plain)

        # HTML version (preferred)
        part_html = MIMEText(full_html, 'html')
        body_part.attach(part_html)
    else:
        # Simple plain text message for new threads
        body_part = MIMEText(body)

    # If we have attachments, wrap in a mixed multipart
    if attachments:
        message = MIMEMultipart('mixed')
        message.attach(body_part)

        for filepath in attachments:
            filepath = os.path.expanduser(filepath)
            if not os.path.exists(filepath):
                print(f"Warning: Attachment not found: {filepath}")
                continue

            filename = os.path.basename(filepath)
            mime_type, _ = mimetypes.guess_type(filepath)
            if mime_type is None:
                mime_type = 'application/octet-stream'

            maintype, subtype = mime_type.split('/', 1)

            with open(filepath, 'rb') as f:
                attachment_data = f.read()

            attachment = MIMEBase(maintype, subtype)
            attachment.set_payload(attachment_data)
            encoders.encode_base64(attachment)
            attachment.add_header('Content-Disposition', 'attachment', filename=filename)
            message.attach(attachment)
            print(f"Attached: {filename}")
    else:
        message = body_part

    # Set headers
    message['to'] = to
    message['subject'] = subject
    if cc:
        message['cc'] = cc
    if bcc:
        message['bcc'] = bcc
    if in_reply_to:
        message['In-Reply-To'] = in_reply_to
    if references:
        message['References'] = references

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return raw, thread_id, to, subject, reply_to_id


def create_draft(to: str, subject: str, body: str, cc: str = None, bcc: str = None,
                 reply_to_id: str = None, new_thread: bool = False, attachments: list = None):
    """Create a draft email."""
    service = get_gmail_service()
    raw, thread_id, to, subject, reply_to_id = create_message(
        to, subject, body, cc, bcc, reply_to_id, new_thread, attachments
    )

    draft_body = {'message': {'raw': raw}}
    if thread_id:
        draft_body['message']['threadId'] = thread_id

    draft = service.users().drafts().create(userId='me', body=draft_body).execute()
    print(f"Draft created successfully!")
    print(f"Draft ID: {draft['id']}")
    print(f"To: {to}")
    print(f"Subject: {subject}")
    if reply_to_id:
        print(f"In reply to: {reply_to_id}")
    return draft


def send_email(to: str, subject: str, body: str, cc: str = None, bcc: str = None,
               reply_to_id: str = None, new_thread: bool = False, attachments: list = None):
    """Send an email directly (not as draft)."""
    service = get_gmail_service()
    raw, thread_id, to, subject, reply_to_id = create_message(
        to, subject, body, cc, bcc, reply_to_id, new_thread, attachments
    )

    message_body = {'raw': raw}
    if thread_id:
        message_body['threadId'] = thread_id

    sent = service.users().messages().send(userId='me', body=message_body).execute()
    print(f"Email sent successfully!")
    print(f"Message ID: {sent['id']}")
    print(f"To: {to}")
    print(f"Subject: {subject}")
    if reply_to_id:
        print(f"In reply to: {reply_to_id}")
    return sent


def extract_body_both(payload):
    """Extract both plain text and HTML body from email payload.

    Returns: (text_body, html_body) tuple
    """
    text_body = ""
    html_body = ""

    def _extract_recursive(payload):
        nonlocal text_body, html_body

        if 'body' in payload and payload['body'].get('data'):
            mime_type = payload.get('mimeType', '')
            data = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='replace')
            if mime_type == 'text/plain':
                text_body = data
            elif mime_type == 'text/html':
                html_body = data

        if 'parts' in payload:
            for part in payload['parts']:
                mime_type = part.get('mimeType', '')
                if mime_type == 'text/plain' and part['body'].get('data'):
                    text_body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
                elif mime_type == 'text/html' and part['body'].get('data'):
                    html_body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
                elif mime_type.startswith('multipart/'):
                    _extract_recursive(part)

    _extract_recursive(payload)

    # If no plain text, derive from HTML
    if not text_body and html_body:
        if HAS_BS4:
            soup = BeautifulSoup(html_body, 'html.parser')
            text_body = soup.get_text(separator='\n', strip=True)
        else:
            text_body = html_body

    return text_body, html_body


def extract_body(payload):
    """Extract body text from email payload."""
    text_body, html_body = extract_body_both(payload)
    return text_body if text_body else html_body


def search_emails(query: str, max_results: int = 10, full_content: bool = False,
                  with_person: str = None):
    """Search emails using Gmail query syntax.

    Args:
        query: Gmail search query (ignored if with_person is provided)
        max_results: Maximum number of results to return
        full_content: If True, include full email body
        with_person: Email address or name to find all correspondence with.
                     Runs separate from:/to: queries and merges results to avoid
                     Gmail's OR operator prioritization bug.
    """
    service = get_gmail_service()

    if with_person:
        # Run separate queries for from: and to: to avoid OR prioritization bug
        # Request more results from each to ensure we get enough after deduping
        fetch_per_query = max_results * 2

        from_results = service.users().messages().list(
            userId='me', q=f"from:{with_person}", maxResults=fetch_per_query
        ).execute()

        to_results = service.users().messages().list(
            userId='me', q=f"to:{with_person}", maxResults=fetch_per_query
        ).execute()

        # Merge and dedupe by message ID
        seen_ids = set()
        all_messages = []

        for msg in from_results.get('messages', []):
            if msg['id'] not in seen_ids:
                seen_ids.add(msg['id'])
                all_messages.append(msg)

        for msg in to_results.get('messages', []):
            if msg['id'] not in seen_ids:
                seen_ids.add(msg['id'])
                all_messages.append(msg)

        # Fetch metadata to sort by date
        messages_with_dates = []
        for msg in all_messages:
            msg_meta = service.users().messages().get(
                userId='me', id=msg['id'], format='metadata',
                metadataHeaders=['Date']
            ).execute()
            messages_with_dates.append({
                'id': msg['id'],
                'internalDate': int(msg_meta.get('internalDate', 0))
            })

        # Sort by date descending (most recent first)
        messages_with_dates.sort(key=lambda x: x['internalDate'], reverse=True)

        # Limit to max_results
        messages = messages_with_dates[:max_results]
    else:
        results = service.users().messages().list(
            userId='me', q=query, maxResults=max_results
        ).execute()
        messages = results.get('messages', [])

    if not messages:
        print("No messages found.")
        return []

    print(f"Found {len(messages)} message(s):\n")

    emails = []
    for msg in messages:
        msg_data = service.users().messages().get(
            userId='me', id=msg['id'], format='full'
        ).execute()

        headers = {h['name']: h['value'] for h in msg_data['payload']['headers']}

        email_info = {
            'id': msg['id'],
            'threadId': msg_data['threadId'],
            'from': headers.get('From', 'Unknown'),
            'to': headers.get('To', ''),
            'subject': headers.get('Subject', '(No Subject)'),
            'date': headers.get('Date', ''),
            'snippet': msg_data.get('snippet', '')
        }

        if full_content:
            email_info['body'] = extract_body(msg_data['payload'])

        emails.append(email_info)

        print(f"ID: {email_info['id']}")
        print(f"From: {email_info['from']}")
        print(f"Subject: {email_info['subject']}")
        print(f"Date: {email_info['date']}")
        if full_content and email_info.get('body'):
            print(f"Body:\n{email_info['body'][:2000]}{'...' if len(email_info.get('body', '')) > 2000 else ''}")
        else:
            print(f"Snippet: {email_info['snippet']}")
        print("-" * 60)

    return emails


def delete_draft(draft_id: str):
    """Delete a draft email by ID."""
    service = get_gmail_service()

    try:
        service.users().drafts().delete(userId='me', id=draft_id).execute()
        print(f"Draft deleted successfully: {draft_id}")
        return True
    except Exception as e:
        # Try treating it as a message ID and finding the associated draft
        try:
            drafts = service.users().drafts().list(userId='me').execute()
            for draft in drafts.get('drafts', []):
                if draft.get('message', {}).get('id') == draft_id:
                    service.users().drafts().delete(userId='me', id=draft['id']).execute()
                    print(f"Draft deleted successfully (found by message ID): {draft['id']}")
                    return True
            print(f"No draft found with ID or message ID: {draft_id}")
            return False
        except Exception as e2:
            print(f"Error deleting draft: {e2}")
            return False


def read_email(message_id: str):
    """Read a specific email by ID."""
    service = get_gmail_service()

    msg_data = service.users().messages().get(
        userId='me', id=message_id, format='full'
    ).execute()

    headers = {h['name']: h['value'] for h in msg_data['payload']['headers']}
    body = extract_body(msg_data['payload'])

    print(f"ID: {message_id}")
    print(f"Thread ID: {msg_data['threadId']}")
    print(f"From: {headers.get('From', 'Unknown')}")
    print(f"To: {headers.get('To', '')}")
    print(f"Subject: {headers.get('Subject', '(No Subject)')}")
    print(f"Date: {headers.get('Date', '')}")
    print("-" * 60)
    print(f"Body:\n{body}")

    return {
        'id': message_id,
        'threadId': msg_data['threadId'],
        'from': headers.get('From', 'Unknown'),
        'to': headers.get('To', ''),
        'subject': headers.get('Subject', '(No Subject)'),
        'date': headers.get('Date', ''),
        'body': body
    }


def main():
    global CURRENT_ACCOUNT
    parser = argparse.ArgumentParser(description="Gmail utility for reading, searching, drafting, and sending emails")
    parser.add_argument('--account', '-a', choices=['elaitra', 'gmail', 'kcl'], default='elaitra',
                       help='Account to use: elaitra (stephen.morrell@elaitra.com), gmail (stephen.morrell@gmail.com), or kcl (stephen.morrell@kcl.ac.uk)')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Draft command
    draft_parser = subparsers.add_parser('draft', help='Create a draft email')
    draft_parser.add_argument('--to', help='Recipient email address (auto-filled if --reply-to used)')
    draft_parser.add_argument('--subject', help='Email subject (auto-filled with Re: if --reply-to used)')
    draft_parser.add_argument('--body', required=True, help='Email body')
    draft_parser.add_argument('--cc', help='CC recipients (comma-separated)')
    draft_parser.add_argument('--bcc', help='BCC recipients (comma-separated)')
    draft_parser.add_argument('--reply-to', dest='reply_to', help='Message ID to reply to (includes thread)')
    draft_parser.add_argument('--new', action='store_true', help='Start a new thread (skip auto-reply to existing thread)')
    draft_parser.add_argument('--attach', action='append', dest='attachments', metavar='FILE',
                             help='Attach a file (can be used multiple times)')

    # Send command
    send_parser = subparsers.add_parser('send', help='Send an email directly')
    send_parser.add_argument('--to', help='Recipient email address (auto-filled if --reply-to used)')
    send_parser.add_argument('--subject', help='Email subject (auto-filled with Re: if --reply-to used)')
    send_parser.add_argument('--body', required=True, help='Email body')
    send_parser.add_argument('--cc', help='CC recipients (comma-separated)')
    send_parser.add_argument('--bcc', help='BCC recipients (comma-separated)')
    send_parser.add_argument('--reply-to', dest='reply_to', help='Message ID to reply to (includes thread)')
    send_parser.add_argument('--new', action='store_true', help='Start a new thread (skip auto-reply to existing thread)')
    send_parser.add_argument('--attach', action='append', dest='attachments', metavar='FILE',
                             help='Attach a file (can be used multiple times)')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search emails')
    search_parser.add_argument('--query', '-q', help='Gmail search query')
    search_parser.add_argument('--with', '-w', dest='with_person',
                              help='Find all emails with a person (name or email). '
                                   'Runs separate from:/to: queries and merges results '
                                   'to avoid Gmail OR operator bug. Overrides --query.')
    search_parser.add_argument('--max', '-m', type=int, default=10, help='Maximum results (default: 10)')
    search_parser.add_argument('--full', action='store_true', help='Include full email body')

    # Read command
    read_parser = subparsers.add_parser('read', help='Read a specific email')
    read_parser.add_argument('--id', required=True, help='Email message ID')

    # Delete draft command
    delete_parser = subparsers.add_parser('delete-draft', help='Delete a draft email')
    delete_parser.add_argument('--id', required=True, help='Draft ID or message ID')

    args = parser.parse_args()

    # Set the account before any API calls
    CURRENT_ACCOUNT = args.account

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == 'draft':
            # Validate: need either --to or --reply-to
            if not args.to and not args.reply_to:
                print("Error: --to is required unless using --reply-to", file=sys.stderr)
                sys.exit(1)
            create_draft(args.to, args.subject or '', args.body, args.cc, args.bcc, args.reply_to, args.new, args.attachments)
        elif args.command == 'send':
            # Validate: need either --to or --reply-to
            if not args.to and not args.reply_to:
                print("Error: --to is required unless using --reply-to", file=sys.stderr)
                sys.exit(1)
            send_email(args.to, args.subject or '', args.body, args.cc, args.bcc, args.reply_to, args.new, args.attachments)
        elif args.command == 'search':
            if not args.query and not args.with_person:
                print("Error: Either --query or --with is required", file=sys.stderr)
                sys.exit(1)
            search_emails(args.query, args.max, args.full, args.with_person)
        elif args.command == 'read':
            read_email(args.id)
        elif args.command == 'delete-draft':
            delete_draft(args.id)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
