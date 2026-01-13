#!/usr/bin/env python3
"""Gmail utility for reading, searching, and drafting emails."""

import argparse
import base64
import json
import os
import sys
from email.mime.text import MIMEText
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
TOKEN_PATH = SKILL_DIR / "token.json"

# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose'
]


def get_credentials() -> Credentials:
    """Load and refresh OAuth credentials, or run auth flow if needed."""
    creds = None

    # Load existing token
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

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
            creds = flow.run_local_server(port=0)

        # Save credentials
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())

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
    body = extract_body(msg_data['payload'])

    return {
        'id': message_id,
        'threadId': msg_data['threadId'],
        'from': headers.get('From', 'Unknown'),
        'to': headers.get('To', ''),
        'subject': headers.get('Subject', '(No Subject)'),
        'date': headers.get('Date', ''),
        'message_id': headers.get('Message-ID', ''),
        'references': headers.get('References', ''),
        'body': body
    }


def format_quoted_reply(original_email: dict) -> str:
    """Format the original email as a quoted reply."""
    quoted_lines = []
    quoted_lines.append(f"\n\nOn {original_email['date']}, {original_email['from']} wrote:\n")

    # Quote each line of the original body
    for line in original_email['body'].split('\n'):
        quoted_lines.append(f"> {line}")

    return '\n'.join(quoted_lines)


def find_latest_thread_message(service, email_address: str) -> str:
    """Find the most recent message ID in a thread with the given email address."""
    # Search for messages to/from this email address
    query = f"to:{email_address} OR from:{email_address}"
    results = service.users().messages().list(
        userId='me', q=query, maxResults=1
    ).execute()

    messages = results.get('messages', [])
    if messages:
        return messages[0]['id']
    return None


def create_draft(to: str, subject: str, body: str, cc: str = None, bcc: str = None,
                 reply_to_id: str = None, new_thread: bool = False):
    """Create a draft email, automatically replying to existing thread unless --new is specified."""
    service = get_gmail_service()

    thread_id = None
    in_reply_to = None
    references = None

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

        # Append quoted original message to body
        body = body + format_quoted_reply(original)

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

    message = MIMEText(body)
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
    draft_body = {'message': {'raw': raw}}

    # Include threadId to keep reply in same thread
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


def extract_body(payload):
    """Extract body text from email payload."""
    body = ""

    if 'body' in payload and payload['body'].get('data'):
        body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='replace')

    if 'parts' in payload:
        for part in payload['parts']:
            mime_type = part.get('mimeType', '')
            if mime_type == 'text/plain' and part['body'].get('data'):
                body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
                break
            elif mime_type == 'text/html' and part['body'].get('data') and not body:
                html = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
                if HAS_BS4:
                    soup = BeautifulSoup(html, 'html.parser')
                    body = soup.get_text(separator='\n', strip=True)
                else:
                    body = html
            elif mime_type.startswith('multipart/'):
                body = extract_body(part)
                if body:
                    break

    return body


def search_emails(query: str, max_results: int = 10, full_content: bool = False):
    """Search emails using Gmail query syntax."""
    service = get_gmail_service()

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
    parser = argparse.ArgumentParser(description="Gmail utility for reading, searching, and drafting emails")
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

    # Search command
    search_parser = subparsers.add_parser('search', help='Search emails')
    search_parser.add_argument('--query', '-q', required=True, help='Gmail search query')
    search_parser.add_argument('--max', '-m', type=int, default=10, help='Maximum results (default: 10)')
    search_parser.add_argument('--full', action='store_true', help='Include full email body')

    # Read command
    read_parser = subparsers.add_parser('read', help='Read a specific email')
    read_parser.add_argument('--id', required=True, help='Email message ID')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == 'draft':
            # Validate: need either --to or --reply-to
            if not args.to and not args.reply_to:
                print("Error: --to is required unless using --reply-to", file=sys.stderr)
                sys.exit(1)
            create_draft(args.to, args.subject or '', args.body, args.cc, args.bcc, args.reply_to, args.new)
        elif args.command == 'search':
            search_emails(args.query, args.max, args.full)
        elif args.command == 'read':
            read_email(args.id)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
