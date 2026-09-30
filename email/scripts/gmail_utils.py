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
import re
from datetime import datetime
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
# NOTE: Account keys below are user-defined. Rename them and their corresponding
# token_<key>.json files to match the accounts you configure in config.json.
SKILL_DIR = Path(__file__).parent.parent
CREDENTIALS_PATH = SKILL_DIR / "credentials.json"
TOKEN_PATH = SKILL_DIR / "token_work.json"

# Account-specific token paths
ACCOUNT_TOKENS = {
    'work': SKILL_DIR / "token_work.json",
    'gmail': SKILL_DIR / "token_gmail.json",
    'university': SKILL_DIR / "token_university.json",
}

# Current account (set by main() before any API calls)
CURRENT_ACCOUNT = 'work'

# Gmail API scopes.
# gmail.compose covers both draft creation AND messages.send per Google's docs,
# so the `send` subcommand works under this scope set. The default and preferred
# flow is still `draft` (user reviews and clicks Send in Gmail); `send` is used
# deliberately for cases like Send-to-Kindle where threading and a human-review
# step are not wanted.
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose',
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


def _html_to_plain(html: str) -> str:
    """Convert an HTML body to a plain-text fallback for the text/plain alternative.

    Preserves paragraph and list breaks; strips tags; unescapes entities.
    Intentionally simple: no inline images, no tables, no CSS.
    """
    import re
    text = html
    # Block-level closers and <br> become newlines
    text = re.sub(r'(?i)<\s*br\s*/?\s*>', '\n', text)
    text = re.sub(r'(?i)</\s*(p|div|li|h[1-6]|ol|ul|blockquote|tr)\s*>', '\n', text)
    # Opening list-item gets a bullet
    text = re.sub(r'(?i)<\s*li[^>]*>', '- ', text)
    # Drop all remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # Unescape entities (&amp;, &lt;, &nbsp; etc.)
    text = html_module.unescape(text)
    # Collapse 3+ consecutive newlines to two
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def validate_attachment_integrity(filepath: str, data: bytes) -> str:
    """Sanity-check an attachment's bytes before sending.

    Returns None if the file looks intact, or a human-readable reason string
    if it looks corrupt/truncated. Currently validates PDFs (the format that
    bit us: a PDF emailed mid-write is missing its trailer/xref/%%EOF and is
    unopenable by strict readers like Outlook/NHSmail, even though `file` and
    macOS Preview may still render it). Non-PDF types pass through.
    """
    lower = filepath.lower()
    is_pdf = lower.endswith('.pdf') or data[:5] == b'%PDF-'
    if not is_pdf:
        return None
    if data[:5] != b'%PDF-':
        return f"{os.path.basename(filepath)}: missing %PDF- header (not a valid PDF)"
    # A complete PDF ends with %%EOF; the spec tolerates a little trailing
    # whitespace/junk, so search the tail rather than the very last bytes.
    tail = data[-2048:]
    if b'%%EOF' not in tail:
        return (f"{os.path.basename(filepath)}: truncated PDF (no %%EOF marker "
                f"in the final bytes, {len(data)} bytes total). The file was "
                f"likely attached before it finished being written/exported. "
                f"Re-export or wait for the source to finish, then retry.")
    if b'startxref' not in tail:
        return (f"{os.path.basename(filepath)}: truncated PDF, missing "
                f"cross-reference table (no 'startxref' near end). Re-export the file.")
    # Stronger check when poppler's pdfinfo is available: it parses the xref
    # table and page tree, catching corruption that a tail %%EOF scan misses.
    # Best-effort only, skipped silently if pdfinfo isn't installed.
    import shutil, subprocess
    pdfinfo = shutil.which('pdfinfo')
    if pdfinfo:
        try:
            proc = subprocess.run([pdfinfo, filepath], capture_output=True,
                                  text=True, timeout=20)
            if proc.returncode != 0 or 'Pages:' not in proc.stdout:
                err = (proc.stderr or proc.stdout or 'unknown error').strip().splitlines()
                reason = err[0] if err else 'pdfinfo could not parse the file'
                return (f"{os.path.basename(filepath)}: PDF failed structural "
                        f"validation ({reason}). The file is corrupt or incomplete; "
                        f"re-export it.")
        except (subprocess.TimeoutExpired, OSError):
            pass  # don't block sending on a flaky/missing validator
    return None


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


# NOTE: full-thread quote assembly (get_thread_history / format_full_thread_quote_*)
# was REMOVED 2026-08-26. Quoting must use ONLY the --reply-to parent message body
# (format_quoted_reply*): the parent already embeds the history the correspondent
# has seen. Iterating the Gmail threadId duplicates Outlook-embedded chains
# (From:/Sent:/To: blocks survive any stripper) and is the documented BCC-broadcast
# privacy leak (SKILL.md thread-quoting rule 8). Do not reintroduce.


def find_latest_thread_message(service, email_address: str) -> str:
    """Find the most recent message ID in a thread with the given email address.

    Note: Gmail's OR operator prioritizes left-side matches, so we run separate
    queries for 'from:' and 'to:' and return the most recent across both.
    """
    # Run separate queries to avoid Gmail OR prioritization bug.
    # Exclude drafts and chats: a half-written draft to this person must never
    # become a reply target (its unsent content would leak into the quote).
    from_results = service.users().messages().list(
        userId='me', q=f"from:{email_address} -in:drafts -in:chats", maxResults=1
    ).execute()

    to_results = service.users().messages().list(
        userId='me', q=f"to:{email_address} -in:drafts -in:chats", maxResults=1
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


def _extract_email(addr_header: str) -> str:
    """Pull the first bare email address out of a From/To header value."""
    if not addr_header:
        return ""
    import re
    m = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', addr_header)
    return m.group(0).lower() if m else ""


_SELF_EMAIL_CACHE = {}


def _get_self_email(service) -> str:
    """Return the authenticated account's own email address (cached per account)."""
    key = CURRENT_ACCOUNT
    if key not in _SELF_EMAIL_CACHE:
        try:
            prof = service.users().getProfile(userId='me').execute()
            _SELF_EMAIL_CACHE[key] = (prof.get('emailAddress') or '').lower()
        except Exception:
            _SELF_EMAIL_CACHE[key] = ''
    return _SELF_EMAIL_CACHE[key]


def redirect_replyto_to_latest(service, reply_to_id: str) -> str:
    """Auto-correct a stale explicit --reply-to target.

    Given a reply-to message ID, find the most recent NON-DRAFT message
    exchanged with the same correspondent (inbound OR outbound, across all
    threads) and return that instead, so replying never lands on an old
    message when a newer one exists. Returns the original ID unchanged if it
    is already the latest, if the correspondent can't be determined, or for
    Kindle addresses.
    """
    try:
        meta = service.users().messages().get(
            userId='me', id=reply_to_id, format='metadata',
            metadataHeaders=['From', 'To', 'Subject', 'Date']
        ).execute()
    except Exception:
        return reply_to_id

    headers = {h['name']: h['value'] for h in meta.get('payload', {}).get('headers', [])}
    self_email = _get_self_email(service)
    from_email = _extract_email(headers.get('From', ''))
    to_email = _extract_email(headers.get('To', ''))

    # The correspondent is whichever party is not us.
    if from_email and from_email != self_email:
        correspondent = from_email
    elif to_email and to_email != self_email:
        correspondent = to_email
    else:
        correspondent = from_email or to_email
    if not correspondent or correspondent.endswith('@kindle.com'):
        return reply_to_id

    latest_id = find_latest_thread_message(service, correspondent)
    if not latest_id or latest_id == reply_to_id:
        return reply_to_id

    try:
        old_d = int(meta.get('internalDate', 0))
        new_meta = service.users().messages().get(
            userId='me', id=latest_id, format='metadata',
            metadataHeaders=['Subject', 'Date']
        ).execute()
        new_d = int(new_meta.get('internalDate', 0))
    except Exception:
        return reply_to_id

    if new_d <= old_d:
        return reply_to_id

    nh = {h['name']: h['value'] for h in new_meta.get('payload', {}).get('headers', [])}
    print(
        "Note: --reply-to pointed at an older message ("
        f"\"{headers.get('Subject', '')}\", {headers.get('Date', '')}). "
        f"Redirecting to the most recent traffic with {correspondent} ("
        f"\"{nh.get('Subject', '')}\", {nh.get('Date', '')}). "
        "Pass --keep-thread (force_thread=True) to reply in the original thread instead."
    )
    return latest_id



def internal_domains():
    """Domains treated as inside the organisation, from config.json.

    config.json is gitignored, so the company's own domains stay out of the
    public repo. Every address in accounts.work contributes its domain; with no
    config readable, nothing is internal and the warning always fires, which is
    the safe direction.
    """
    import json as _json
    try:
        cfg = _json.load(open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'config.json')))
    except (OSError, ValueError):
        return set()
    out = set()
    for acct in (cfg.get('accounts', {}).get('work') or {}).values():
        addr = (acct or {}).get('email', '')
        if '@' in addr:
            out.add(addr.rsplit('@', 1)[-1].lower())
    return out


def _attachment_part(filepath: str):
    """One attachment, with every integrity guard applied. None if missing.

    Shared by the ordinary and the inline modes so that neither can drift into
    sending a truncated file: the size-stability check, the structural PDF/docx
    check, and the sha256 recorded for the round-trip verification all live
    here rather than in the loop that happens to be running.
    """
    import hashlib as _hashlib
    filepath = os.path.expanduser(filepath)
    if not os.path.exists(filepath):
        print(f"Warning: Attachment not found: {filepath}")
        return None

    filename = os.path.basename(filepath)
    mime_type, _ = mimetypes.guess_type(filepath)
    if mime_type is None:
        mime_type = 'application/octet-stream'
    maintype, subtype = mime_type.split('/', 1)

    with open(filepath, 'rb') as f:
        attachment_data = f.read()

    # A file still being written/exported (or mid Dropbox sync) reads short. If
    # the on-disk size no longer matches what we read, the file is unstable:
    # refuse rather than email a truncated copy.
    if os.path.getsize(filepath) != len(attachment_data):
        raise RuntimeError(f"Refusing to attach {filename}: file changed size "
                           f"while being read (still being written or synced). "
                           f"Wait for it to finish, then retry.")

    problem = validate_attachment_integrity(filepath, attachment_data)
    if problem:
        raise RuntimeError(f"Refusing to attach corrupt file. {problem}")

    part = MIMEBase(maintype, subtype)
    part.set_payload(attachment_data)
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment', filename=filename)
    return part, filename, _hashlib.sha256(attachment_data).hexdigest(), len(attachment_data)


def split_body_for_inline(body: str, filenames: list, is_html: bool):
    """Cut the body after each filename so its attachment can follow it.

    Returns (segments, order) where segments[i] is the text that precedes
    attachment order[i], and segments[-1] is whatever is left over. A filename
    the body never mentions keeps its attachment, placed at the end, and says so.

    Matching is on the basename as written in the body. The files are numbered
    in the body ("1. 20260930-...docx"), so the cut goes after the end of that
    line, or after the closing tag of the list item in HTML.
    """
    segments, order, rest = [], [], body
    tail_tags = ('</li>', '<br>', '<br/>', '<br />', '</p>', '</div>')
    for name in filenames:
        idx = rest.find(name)
        if idx < 0:
            continue
        cut = idx + len(name)
        if is_html:
            # Take the smallest closing tag that follows, so the attachment
            # lands after the whole list item rather than inside it.
            ends = [rest.find(t, cut) + len(t) for t in tail_tags if rest.find(t, cut) >= 0]
            if ends:
                cut = min(ends)
        else:
            nl = rest.find('\n', cut)
            cut = len(rest) if nl < 0 else nl + 1
        segments.append(rest[:cut])
        order.append(name)
        rest = rest[cut:]
    segments.append(rest)
    return segments, order



def _segment_part(text: str, body_has_html: bool, use_html: bool):
    """One chunk of body between two attachments, in the same flavour as the whole.

    HTML bodies keep a text/plain twin, so Outlook and Exchange clients that
    fall back to plain text do not see raw tags (the reason the single-part
    path builds multipart/alternative too).
    """
    if not (body_has_html or use_html):
        return MIMEText(text)
    if body_has_html:
        html = f'<div dir="ltr">{text}</div>'
        plain = _html_to_plain(text)
    else:
        html = '<div dir="ltr">' + html_module.escape(text).replace('\n', '<br>\n') + '</div>'
        plain = text
    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText(plain, 'plain'))
    alt.attach(MIMEText(html, 'html'))
    return alt


def create_message(to: str, subject: str, body: str, cc: str = None, bcc: str = None,
                   reply_to_id: str = None, new_thread: bool = False, attachments: list = None,
                   force_thread: bool = False, inline_attachments: bool = False):
    """Create an email message, automatically replying to existing thread unless --new is specified.

    Args:
        attachments: List of file paths to attach to the email.
        inline_attachments: Place each attachment in the body immediately after
            the line naming it, instead of all of them after the whole body.

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
    body_has_html = '<a ' in body or '<b>' in body or '<ul>' in body or '<li>' in body or '<br>' in body or '<p>' in body or '<h' in body or '<ol>' in body or '<hr' in body or '<blockquote' in body

    # Auto-find prior thread if:
    # - Not explicitly starting a new thread (--new)
    # - No explicit reply-to ID provided
    # - We have a recipient email
    # - Recipient is not a Send-to-Kindle address (those should never be threaded:
    #   Amazon ingests each message independently, and threaded replies inherit
    #   "Re: (No Subject)" which is ugly in the Gmail Sent folder.)
    if not new_thread and not reply_to_id and to:
        # Extract email address from "Name <email>" format if needed
        email_addr = to
        if '<' in to:
            email_addr = to.split('<')[1].rstrip('>')

        if email_addr.lower().endswith('@kindle.com'):
            print("Recipient is a Kindle Send-to-Kindle address; skipping auto-thread.")
        else:
            auto_reply_id = find_latest_thread_message(service, email_addr)
            if auto_reply_id:
                reply_to_id = auto_reply_id
                print(f"Auto-replying to existing thread (use --new to start fresh thread)")

    # An explicitly supplied reply-to may be stale (an old message in an old
    # thread). Unless the caller forces the original thread or wants a new one,
    # redirect to the most recent non-draft traffic with the same correspondent.
    if reply_to_id and not new_thread and not force_thread:
        reply_to_id = redirect_replyto_to_latest(service, reply_to_id)

    # If replying to an existing message, fetch it and include quoted text
    if reply_to_id:
        original = get_email_for_reply(service, reply_to_id)
        thread_id = original['threadId']
        in_reply_to = original['message_id']
        references = f"{original['references']} {original['message_id']}".strip()
        use_html = True  # Use HTML for replies to preserve formatting

        # Use original sender as recipient if not specified.
        # Special case: if the reply target is a message WE sent (From == self),
        # using From: would address the reply back to ourselves. This happens when
        # the stale-reply redirect lands on our own most recent outbound to a
        # correspondent — including SENT-labeled stubs left behind by drafts that
        # were deleted via the API. Mirror Gmail's "Reply" behaviour on a sent
        # message: use the original To: header (the actual correspondent) instead.
        if not to:
            from_addr = original['from']
            from_email = _extract_email(from_addr)
            self_email = _get_self_email(service)
            if from_email and self_email and from_email == self_email and original.get('to'):
                source_addr = original['to']
            else:
                source_addr = from_addr
            # Extract email from "Name <email>" format
            if '<' in source_addr:
                to = source_addr.split('<')[1].rstrip('>')
            else:
                to = source_addr

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

        # Add quoted reply — quote this email's history as a mail client
        # would on Reply/Reply All/Forward: the parent message with the chain
        # already embedded in its own body. Never iterate the Gmail threadId:
        # a BCC broadcast collects every recipient's separate reply into one
        # thread here, and quoting the thread leaks other correspondents'
        # replies to the recipient.
        quoted_html = format_quoted_reply_html(original)

        full_html = f'''<div dir="ltr">{body_html}</div>{quoted_html}'''

        # Create multipart message with both HTML and plain text
        body_part = MIMEMultipart('alternative')

        # Plain text version (fallback) — strip HTML so Exchange/Outlook clients
        # that fall back to text/plain don't see raw <p>/<ol>/<li> tags.
        plain_text_body = _html_to_plain(body) if body_has_html else body
        plain_body = plain_text_body + format_quoted_reply(original)
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

        # Plain text version (strip HTML tags for fallback, preserve list/paragraph breaks)
        plain_body = _html_to_plain(body)
        part_plain = MIMEText(plain_body, 'plain')
        body_part.attach(part_plain)

        # HTML version (preferred)
        part_html = MIMEText(full_html, 'html')
        body_part.attach(part_html)
    else:
        # Simple plain text message for new threads
        body_part = MIMEText(body)

    # If we have attachments, wrap in a mixed multipart
    _LAST_ATTACHMENTS.clear()
    if attachments and inline_attachments:
        # Each attachment sits directly under the line that names it, so a
        # numbered list of files reads as "1. <name>", the file, "2. <name>",
        # the file. Ordinary mode puts every attachment after the whole body,
        # which for a pack of several documents leaves the reader matching
        # names to icons by hand.
        #
        # Deliberately NOT Content-ID/cid: these are documents, not images, and
        # a cid part without an <img> referencing it is hidden by some clients.
        #
        # INTERNAL USE ONLY. Field report the same day it was built: Apple Mail's
        # compose window shows blank gaps and a blue placeholder, and Outlook
        # renders only the FIRST body section and turns the rest into
        # ATT00001.htm attachments. The recipient sees a truncated email with
        # junk files. Warn whenever this leaves the company.
        _to_domain = (_extract_email(to or '') or '').rsplit('@', 1)[-1].lower()
        if _to_domain and _to_domain not in internal_domains():
            print("")
            print("  WARNING: --attach-inline with an external recipient (%s)." % (to,))
            print("  Outlook shows only the first section of the body and turns the rest")
            print("  into ATT00001.htm attachments; Apple Mail's compose view looks broken.")
            print("  Use plain --attach with a numbered list of filenames in the body instead.")
            print("")
        message = MIMEMultipart('mixed')
        parts, names = [], []
        for filepath in attachments:
            built = _attachment_part(filepath)
            if built is None:
                continue
            parts.append(built[0])
            names.append(built[1])
            _LAST_ATTACHMENTS.append((built[1], built[2], built[3]))
            print(f"Attached inline: {built[1]} ({built[3]} bytes, integrity OK)")

        segments, order = split_body_for_inline(body, names, body_has_html or use_html)
        by_name = dict(zip(names, parts))
        placed = set()
        for seg, name in zip(segments, order):
            message.attach(_segment_part(seg, body_has_html, use_html))
            message.attach(by_name[name])
            placed.add(name)
        # Whatever body is left, then any file the body never named.
        if segments[-1].strip() or use_html:
            tail = segments[-1] + (format_quoted_reply_html(original) if use_html and original else "")
            message.attach(_segment_part(tail, body_has_html, use_html))
        for name in names:
            if name not in placed:
                print(f"NOTE: the body never names {name}; attaching it at the end.")
                message.attach(by_name[name])
    elif attachments:
        message = MIMEMultipart('mixed')
        message.attach(body_part)

        for filepath in attachments:
            built = _attachment_part(filepath)
            if built is None:
                continue
            part, filename, sha, size = built
            message.attach(part)
            _LAST_ATTACHMENTS.append((filename, sha, size))
            print(f"Attached: {filename} ({size} bytes, integrity OK)")
    else:
        message = body_part

    # Set headers (RFC 5322 names are case-insensitive, but Gmail's web UI
    # draft view only populates the To/Cc/Bcc input fields when the headers
    # are in canonical case. Lowercase 'to:' parses fine for sending but
    # shows as an empty recipient field in the draft, which Stephen has to
    # re-fill before Send. Use canonical case to match Apple Mail/Gmail.)
    message['To'] = to
    message['Subject'] = subject
    if cc:
        message['Cc'] = cc
    if bcc:
        message['Bcc'] = bcc
    if in_reply_to:
        message['In-Reply-To'] = in_reply_to
    if references:
        message['References'] = references

    raw = encode_raw(message)
    return raw, thread_id, to, subject, reply_to_id


def encode_raw(message) -> str:
    """Serialize a MIME message for the Gmail API `raw` field. THE ONLY SAFE WAY.

    Never use base64.urlsafe_b64encode(msg.as_bytes()) for a message you upload:
    as_bytes() defaults to bare LF line endings. Gmail stores the bare LFs, API
    round-trips stay byte-identical (so API-side hash checks pass), but Apple
    Mail's IMAP fetch of the draft truncates the attachment (~1 byte per 78-byte
    base64 line; the PDF loses its xref/trailer/%%EOF and will not open). When
    Stephen then touches the draft in Mail.app, Mail re-saves the truncated copy
    to Gmail and the corruption becomes permanent everywhere, web UI included.
    Reproduced 28 Sep 2026 (Chandan/NYP draft). This serializes with CRLF and
    refuses to return anything containing a bare LF.
    """
    import email.policy
    crlf_policy = email.policy.compat32.clone(linesep='\r\n')
    data = message.as_bytes(policy=crlf_policy)
    bare_lf = data.count(b'\n') - data.count(b'\r\n')
    if bare_lf:
        raise RuntimeError(f"encode_raw: {bare_lf} bare LF line endings after CRLF "
                           f"serialization; refusing to upload (IMAP clients would "
                           f"truncate attachments).")
    return base64.urlsafe_b64encode(data).decode()


def raw_bare_lf_count(service, message_id: str) -> int:
    """Bare-LF count in the message as Gmail stores it (the IMAP-corruption proxy)."""
    m = service.users().messages().get(userId='me', id=message_id, format='raw').execute()
    data = base64.urlsafe_b64decode(m['raw'])
    return data.count(b'\n') - data.count(b'\r\n')


# Filled by create_message with (filename, sha256, size) per attachment so the
# post-save verifier can hash-compare what Gmail actually stored.
_LAST_ATTACHMENTS = []


def verify_stored_attachments(service, message_id: str):
    """Round-trip verify attachments on a just-saved draft/sent message.

    Downloads each attachment back from Gmail, sha256-compares it against the
    bytes read from disk at attach time, and structurally parses PDFs. Raises
    RuntimeError on any mismatch so a corrupt attachment can never be saved
    silently.
    """
    if not _LAST_ATTACHMENTS:
        return
    import hashlib
    expected = {fn: (digest, size) for fn, digest, size in _LAST_ATTACHMENTS}
    msg = service.users().messages().get(userId='me', id=message_id, format='full').execute()
    found = {}

    def walk(part):
        for p in part.get('parts', []):
            fn = p.get('filename')
            if fn and p['body'].get('attachmentId'):
                att = service.users().messages().attachments().get(
                    userId='me', messageId=message_id, id=p['body']['attachmentId']).execute()
                data = base64.urlsafe_b64decode(att['data'])
                found[fn] = data
            walk(p)

    walk(msg['payload'])
    problems = []
    # API sha256 is blind to line-ending damage: Gmail re-decodes server-side.
    # Bare LFs in the stored message are what makes Apple Mail truncate it.
    bare = raw_bare_lf_count(service, message_id)
    if bare:
        problems.append(f"stored message has {bare} bare LF line endings (Apple Mail will "
                        f"truncate the attachments); it was not serialized with encode_raw()")
    else:
        print("Verified in Gmail: stored MIME is pure CRLF (0 bare LF), safe for IMAP clients")
    for fn, (digest, size) in expected.items():
        data = found.get(fn)
        if data is None:
            problems.append(f"{fn}: missing from the saved message")
            continue
        got = hashlib.sha256(data).hexdigest()
        if got != digest:
            problems.append(f"{fn}: stored bytes differ from source ({len(data)} vs {size} bytes)")
            continue
        verdict = "sha256 match"
        if fn.lower().endswith('.pdf'):
            try:
                import io
                from pypdf import PdfReader
                verdict = f"sha256 match, PDF parses ({len(PdfReader(io.BytesIO(data)).pages)} pages)"
            except ImportError:
                verdict = "sha256 match (pypdf not installed, parse check skipped)"
            except Exception as e:
                problems.append(f"{fn}: stored PDF fails to parse: {e}")
                continue
        print(f"Verified in Gmail: {fn} ({verdict})")
    if problems:
        raise RuntimeError("Attachment verification FAILED after save: " + "; ".join(problems) +
                           ". Delete the draft and retry.")


def create_draft(to: str, subject: str, body: str, cc: str = None, bcc: str = None,
                 reply_to_id: str = None, new_thread: bool = False, attachments: list = None,
                 force_thread: bool = False, inline_attachments: bool = False):
    """Create a draft email."""
    service = get_gmail_service()
    raw, thread_id, to, subject, reply_to_id = create_message(
        to, subject, body, cc, bcc, reply_to_id, new_thread, attachments, force_thread,
        inline_attachments
    )

    draft_body = {'message': {'raw': raw}}
    if thread_id:
        draft_body['message']['threadId'] = thread_id

    draft = service.users().drafts().create(userId='me', body=draft_body).execute()
    verify_stored_attachments(service, draft['message']['id'])
    print(f"Draft created successfully!")
    print(f"Draft ID: {draft['id']}")
    print(f"To: {to}")
    print(f"Subject: {subject}")
    if reply_to_id:
        print(f"In reply to: {reply_to_id}")
    return draft


def send_email(to: str, subject: str, body: str, cc: str = None, bcc: str = None,
               reply_to_id: str = None, new_thread: bool = False, attachments: list = None,
               force_thread: bool = False, inline_attachments: bool = False):
    """Send an email directly (not as draft)."""
    service = get_gmail_service()
    raw, thread_id, to, subject, reply_to_id = create_message(
        to, subject, body, cc, bcc, reply_to_id, new_thread, attachments, force_thread,
        inline_attachments
    )

    message_body = {'raw': raw}
    if thread_id:
        message_body['threadId'] = thread_id

    sent = service.users().messages().send(userId='me', body=message_body).execute()
    verify_stored_attachments(service, sent['id'])
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
            'cc': headers.get('Cc', ''),
            'bcc': headers.get('Bcc', ''),
            'subject': headers.get('Subject', '(No Subject)'),
            'date': headers.get('Date', ''),
            'snippet': msg_data.get('snippet', '')
        }

        if full_content:
            email_info['body'] = extract_body(msg_data['payload'])

        emails.append(email_info)

        print(f"ID: {email_info['id']}")
        print(f"From: {email_info['from']}")
        if email_info.get('to'):
            print(f"To: {email_info['to']}")
        if email_info.get('cc'):
            print(f"Cc: {email_info['cc']}")
        print(f"Subject: {email_info['subject']}")
        print(f"Date: {email_info['date']}")
        if full_content and email_info.get('body'):
            print(f"Body:\n{email_info['body'][:2000]}{'...' if len(email_info.get('body', '')) > 2000 else ''}")
        else:
            print(f"Snippet: {email_info['snippet']}")
        print("-" * 60)

    return emails


def delete_draft(draft_id: str):
    """Archive a draft by moving to trash if possible, otherwise delete it."""
    service = get_gmail_service()

    def _remove_draft(actual_draft_id, message_id):
        """Try to trash the message (preserves content), fall back to delete."""
        try:
            service.users().messages().trash(userId='me', id=message_id).execute()
            print(f"Draft archived to Trash (preserved): {actual_draft_id}")
            return True
        except Exception:
            # Trash requires gmail.modify scope; fall back to delete
            service.users().drafts().delete(userId='me', id=actual_draft_id).execute()
            print(f"Draft deleted (trash unavailable, needs gmail.modify scope): {actual_draft_id}")
            return True

    try:
        # Try as a draft ID first
        draft = service.users().drafts().get(userId='me', id=draft_id).execute()
        msg_id = draft['message']['id']
        return _remove_draft(draft_id, msg_id)
    except Exception as e:
        # Try treating it as a message ID and finding the associated draft
        try:
            drafts = service.users().drafts().list(userId='me').execute()
            for draft in drafts.get('drafts', []):
                if draft.get('message', {}).get('id') == draft_id:
                    msg_id = draft['message']['id']
                    return _remove_draft(draft['id'], msg_id)
            print(f"No draft found with ID or message ID: {draft_id}")
            return False
        except Exception as e2:
            print(f"Error removing draft: {e2}")
            return False


def _resolve_draft(service, some_id: str):
    """Resolve a draft ID or message ID to (draft_id, full draft resource)."""
    try:
        d = service.users().drafts().get(userId='me', id=some_id, format='full').execute()
        return d['id'], d
    except Exception:
        try:
            drafts = service.users().drafts().list(userId='me', maxResults=200).execute()
            for item in drafts.get('drafts', []):
                if item.get('message', {}).get('id') == some_id:
                    d = service.users().drafts().get(userId='me', id=item['id'], format='full').execute()
                    return d['id'], d
        except Exception:
            pass
    return None, None


def _list_attachment_names(payload):
    """Collect attachment filenames from a message payload."""
    names = []

    def walk(part):
        if part.get('filename'):
            names.append(part['filename'])
        for p in part.get('parts', []) or []:
            walk(p)

    walk(payload)
    return names


def read_draft(draft_id: str):
    """Read the CURRENT server-side content of a draft (the ground truth,
    including any edits the user made in Gmail since the draft was created)."""
    service = get_gmail_service()
    did, d = _resolve_draft(service, draft_id)
    if not d:
        print(f"No draft found with ID or message ID: {draft_id}", file=sys.stderr)
        sys.exit(1)
    msg = d['message']
    headers = {h['name']: h['value'] for h in msg['payload']['headers']}
    text_body, html_body = extract_body_both(msg['payload'])
    attachments = _list_attachment_names(msg['payload'])

    print(f"Draft ID: {did}")
    print(f"Message ID: {msg['id']}")
    print(f"Thread ID: {msg.get('threadId', '')}")
    print(f"To: {headers.get('To', '')}")
    if headers.get('Cc'):
        print(f"Cc: {headers.get('Cc')}")
    if headers.get('Bcc'):
        print(f"Bcc: {headers.get('Bcc')}")
    print(f"Subject: {headers.get('Subject', '(No Subject)')}")
    if attachments:
        print(f"Attachments: {', '.join(attachments)}")
    print("-" * 60)
    print(f"Body (plain):\n{text_body}")
    if html_body:
        print("-" * 60)
        print(f"Body (html):\n{html_body}")
    return d


# ---------------------------------------------------------------- draft safety
#
# 22 Sep 2026: two draft updates in one morning rebuilt a draft from a locally
# cached body and wiped edits Stephen had made in the Gmail web UI between
# turns (the Sandra Badu-Poku costing draft; a near miss on a Keshthra draft).
# Gmail keeps no version history for drafts, so those edits were gone.
#
# Two defences below: a stamp of the body this tool last wrote, so a plain
# --body update refuses when the live body has moved on, and --replace, which
# edits the LIVE body server-side instead of resending a remembered one.

STAMPS_PATH = os.path.expanduser('~/.claude/skills/email/.draft-body-stamps.json')


def _body_sha(html: str, text: str) -> str:
    """Fingerprint of a draft body. HTML wins when present, as that is what
    Gmail stores for anything this tool composes."""
    import hashlib
    raw = (html or text or '')
    # Gmail rewrites whitespace between saves, so compare on content.
    raw = re.sub(r'\s+', ' ', raw).strip()
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


def _stamps() -> dict:
    try:
        return json.load(open(STAMPS_PATH))
    except Exception:
        return {}


def _stamp_key(draft_id: str) -> str:
    return f"{CURRENT_ACCOUNT}:{draft_id}"


def _save_stamp(draft_id: str, sha: str):
    st = _stamps()
    st[_stamp_key(draft_id)] = {'sha': sha, 'at': datetime.now().isoformat(timespec='seconds')}
    try:
        with open(STAMPS_PATH, 'w') as f:
            json.dump(st, f, indent=1)
        os.chmod(STAMPS_PATH, 0o600)
    except Exception:
        pass


def _live_body(msg) -> tuple:
    text_body, html_body = extract_body_both(msg['payload'])
    return text_body, html_body


def _download_attachments(service, msg, dest_dir: str) -> list:
    """Save a draft's attachments so an update can put them back.

    Gmail replaces the whole message on update, so anything not re-passed is
    dropped. Re-downloading is the only way to preserve a file Stephen added
    by hand, since the tool has no local copy of it.
    """
    saved = []

    def walk(part):
        fn = part.get('filename')
        body = part.get('body', {}) or {}
        if fn and (body.get('attachmentId') or body.get('data')):
            if body.get('attachmentId'):
                att = service.users().messages().attachments().get(
                    userId='me', messageId=msg['id'], id=body['attachmentId']).execute()
                data = att.get('data', '')
                expected = att.get('size')
            else:
                data = body['data']
                expected = body.get('size')
            blob = base64.urlsafe_b64decode(data)
            if expected and len(blob) != expected:
                raise RuntimeError(
                    f"attachment {fn}: got {len(blob)} bytes, Gmail reports {expected}. "
                    f"Refusing to update and risk a truncated file.")
            path = os.path.join(dest_dir, fn)
            with open(path, 'wb') as f:
                f.write(blob)
            saved.append(path)
        for p in part.get('parts', []) or []:
            walk(p)

    walk(msg['payload'])
    return saved


def _apply_replacement(body: str, old: str, new: str, replace_all: bool) -> str:
    n = body.count(old)
    if n == 0:
        raise SystemExit(
            "--replace: the OLD text does not appear in the live draft. Nothing written.\n"
            "Read the draft first (read-draft --id ...) and copy the exact text, including\n"
            "any HTML tags, since the stored body is HTML.")
    if n > 1 and not replace_all:
        raise SystemExit(
            f"--replace: the OLD text appears {n} times in the live draft, so the edit is "
            f"ambiguous. Nothing written.\nUse a longer, unique OLD, or pass --replace-all.")
    return body.replace(old, new)


def update_draft(draft_id: str, body: str = None, to: str = None, subject: str = None,
                 cc: str = None, bcc: str = None, attachments: list = None,
                 replace: tuple = None, replace_all: bool = False,
                 force_body: bool = False, expect_body_sha: str = None,
                 drop_attachments: bool = False):
    """Update an existing draft IN PLACE (same draft ID, same thread).

    Two ways to change the text:

      --replace OLD NEW   edits the LIVE body: the current server-side text is
                          fetched, the replacement applied to THAT, and the
                          result written back. Stephen's edits survive because
                          they were never overwritten. Preferred.
      --body TEXT         replaces the whole body. Guarded: it refuses unless
                          the live body still matches what this tool last
                          wrote, because anything else means he has edited the
                          draft since and the new text would erase that.

    Attachments are preserved by re-downloading and re-attaching them, since
    Gmail replaces the whole message on update. Recipients, subject, reply
    headers and threadId all default to the draft's current values.
    """
    import email as email_lib
    import tempfile

    if (body is None) == (replace is None):
        print("Error: give exactly one of --body or --replace OLD NEW.", file=sys.stderr)
        sys.exit(1)

    service = get_gmail_service()
    did, d = _resolve_draft(service, draft_id)
    if not d:
        print(f"No draft found with ID or message ID: {draft_id}", file=sys.stderr)
        sys.exit(1)
    msg = d['message']
    headers = {h['name']: h['value'] for h in msg['payload']['headers']}
    live_text, live_html = _live_body(msg)
    live_sha = _body_sha(live_html, live_text)
    stamp = _stamps().get(_stamp_key(did), {}).get('sha')

    if expect_body_sha and expect_body_sha != live_sha:
        print(f"REFUSED: the draft's live body is {live_sha}, not the {expect_body_sha} you "
              f"expected.\nIt has changed since you read it. Re-read it (read-draft --id "
              f"{did}) and redo the edit on the current text.", file=sys.stderr)
        sys.exit(2)

    if replace is not None:
        old, new = replace
        target = live_html or live_text
        body = _apply_replacement(target, old, new, replace_all)
    elif not (force_body or expect_body_sha):
        # A whole-body replacement is only safe when the live body is still the
        # one this tool wrote. Stephen edits drafts in Gmail between turns.
        if stamp is None:
            print(f"REFUSED: no record of this tool writing the current body of draft {did}, "
                  f"so a whole-body update could erase edits made in Gmail.\n"
                  f"Do one of:\n"
                  f"  1. read-draft --id {did}, then update-draft --replace 'OLD' 'NEW' "
                  f"(edits the live text, keeps his changes)\n"
                  f"  2. read-draft --id {did}, confirm the body is yours, then re-run with "
                  f"--expect-body-sha {live_sha}\n"
                  f"  3. --force-body, which overwrites whatever is there now. Drafts have no "
                  f"version history, so this cannot be undone.", file=sys.stderr)
            sys.exit(2)
        if stamp != live_sha:
            print(f"REFUSED: draft {did} has been edited since this tool last wrote it "
                  f"(live {live_sha}, last written {stamp}).\nThose are almost certainly "
                  f"Stephen's own edits, and --body would erase them.\n"
                  f"Use update-draft --replace 'OLD' 'NEW' to change the live text, or "
                  f"--force-body to overwrite it deliberately.", file=sys.stderr)
            sys.exit(2)

    existing_attachments = _list_attachment_names(msg['payload'])
    tmpdir = None
    if existing_attachments and not attachments and not drop_attachments:
        tmpdir = tempfile.mkdtemp(prefix='draft-attach-')
        attachments = _download_attachments(service, msg, tmpdir)
        print(f"Preserving {len(attachments)} attachment(s): {', '.join(existing_attachments)}")
    elif existing_attachments and drop_attachments:
        print(f"WARNING: dropping attachments as asked ({', '.join(existing_attachments)}).",
              file=sys.stderr)

    to = to or headers.get('To')
    subject = subject if subject is not None else headers.get('Subject', '')
    cc = cc or headers.get('Cc')
    bcc = bcc or headers.get('Bcc')

    # Build the new MIME with new_thread=True so create_message does not go
    # hunting for threads: we already know the thread from the draft itself.
    raw, _tid, to, subject, _r = create_message(
        to, subject, body, cc, bcc, None, True, attachments, False
    )

    # Preserve reply linkage headers from the existing draft.
    mime = email_lib.message_from_bytes(base64.urlsafe_b64decode(raw))
    for hdr in ('In-Reply-To', 'References'):
        if headers.get(hdr) and not mime.get(hdr):
            mime[hdr] = headers[hdr]
    # Must go through encode_raw (CRLF). A plain mime.as_bytes() here re-emits
    # bare LF and was the second route by which update-draft corrupted PDFs.
    raw = encode_raw(mime)

    body_obj = {'message': {'raw': raw}}
    if msg.get('threadId'):
        body_obj['message']['threadId'] = msg['threadId']

    updated = service.users().drafts().update(userId='me', id=did, body=body_obj).execute()
    verify_stored_attachments(service, updated['message']['id'])

    # Stamp what is now there, read back from the server rather than assumed,
    # so the next update can tell his edits from ours.
    try:
        fresh = service.users().drafts().get(userId='me', id=updated['id'], format='full').execute()
        ftext, fhtml = _live_body(fresh['message'])
        new_sha = _body_sha(fhtml, ftext)
    except Exception:
        new_sha = None
    if new_sha:
        _save_stamp(updated['id'], new_sha)

    print("Draft updated in place.")
    print(f"Draft ID: {updated['id']}")
    print(f"Message ID: {updated['message']['id']} (it changes on every update)")
    print(f"To: {to}")
    print(f"Subject: {subject}")
    if new_sha:
        print(f"Body sha: {new_sha}")
    return updated


def verify_draft(draft_id: str, sources: list = None) -> bool:
    """Audit a draft's attachments the way a recipient/IMAP client will see them.

    Checks, per attachment: size, sha256 (vs --source files when given), PDF
    %PDF/%%EOF/pypdf parse. Per message: bare-LF count in the stored raw MIME
    (>0 means Apple Mail will truncate on fetch), and whether Apple Mail has
    re-saved the draft (Apple-Mail boundary / x-unix-mode), which is how a
    client-side truncation becomes permanent server-side. Exit 1 on any problem.
    """
    import hashlib, io
    service = get_gmail_service()
    did, d = _resolve_draft(service, draft_id)
    if not d:
        print(f"No draft found with ID or message ID: {draft_id}", file=sys.stderr)
        return False
    msg = d['message']
    mid = msg['id']
    problems = []
    raw = base64.urlsafe_b64decode(service.users().messages().get(
        userId='me', id=mid, format='raw').execute()['raw'])
    bare = raw.count(b'\n') - raw.count(b'\r\n')
    print(f"Draft {did} (message {mid}, thread {msg.get('threadId')}): {len(raw)} raw bytes, {bare} bare LF")
    if bare:
        problems.append(f"{bare} bare LF in stored MIME (IMAP clients will truncate attachments)")
    if b'Apple-Mail=_' in raw or b'x-unix-mode' in raw:
        print("NOTE: last saved by Apple Mail (Apple-Mail boundary / x-unix-mode). Any attachment "
              "it re-uploaded is the copy Mail had cached, so check it against the source.")
    src = {}
    for sp in sources or []:
        sp = os.path.expanduser(sp)
        b = open(sp, 'rb').read()
        src[os.path.basename(sp)] = (hashlib.sha256(b).hexdigest(), len(b))

    found = []

    def walk(part, depth=0):
        hs = {h['name'].lower(): h['value'] for h in part.get('headers', [])}
        print(f"{'  ' * depth}- {part.get('mimeType')} {part.get('filename') or ''} "
              f"size={part['body'].get('size')} disp={hs.get('content-disposition', '')[:40]}")
        if part.get('filename') and part['body'].get('attachmentId'):
            att = service.users().messages().attachments().get(
                userId='me', messageId=mid, id=part['body']['attachmentId']).execute()
            found.append((part['filename'], base64.urlsafe_b64decode(att['data'])))
        for c in part.get('parts', []):
            walk(c, depth + 1)

    walk(msg['payload'])
    if not found:
        print("No attachments on this draft.")
    for fn, data in found:
        sha = hashlib.sha256(data).hexdigest()
        line = f"  {fn}: {len(data)} bytes sha256 {sha[:16]}"
        if fn in src:
            ok = src[fn][0] == sha
            line += f" | source {src[fn][1]} bytes: {'MATCH' if ok else 'MISMATCH'}"
            if not ok:
                problems.append(f"{fn}: stored {len(data)} bytes != source {src[fn][1]} bytes")
        if fn.lower().endswith('.pdf') or data[:5] == b'%PDF-':
            if data[:5] != b'%PDF-' or b'%%EOF' not in data[-2048:]:
                problems.append(f"{fn}: PDF truncated (no %PDF header or no %%EOF at end)")
                line += " | PDF TRUNCATED"
            else:
                try:
                    from pypdf import PdfReader
                    line += f" | PDF parses ({len(PdfReader(io.BytesIO(data)).pages)} pages)"
                except ImportError:
                    pass
                except Exception as e:
                    problems.append(f"{fn}: PDF fails to parse ({e})")
        print(line)
    for name in src:
        if name not in [f for f, _ in found]:
            problems.append(f"{name}: expected attachment is missing from the draft")
    if problems:
        print("VERIFY FAILED:\n  " + "\n  ".join(problems))
        return False
    print("VERIFY OK")
    return True


def thread_state(addr: str, days: int = 90, max_msgs: int = 12, no_cache: bool = False):
    """One-call thread state for a correspondent: replaces the 20-lookup
    verification loop. Returns and prints, for the given address:
      - every recent message classified SENT / DRAFT / SCHEDULED / INBOX
      - a summary: last outbound, last inbound, open drafts, scheduled sends
    Results are cached for 10 minutes per (account, addr) so repeated status
    checks within a task cost zero API calls (pass --no-cache to force).
    """
    import time as _time
    cache_path = os.path.expanduser('~/.claude/skills/email/.thread-state-cache.json')
    key = f"{CURRENT_ACCOUNT}:{addr.lower()}"
    cache = {}
    if os.path.exists(cache_path):
        try:
            cache = json.load(open(cache_path))
        except Exception:
            cache = {}
    ent = cache.get(key)
    if ent and not no_cache and _time.time() - ent['ts'] < 600:
        print(ent['report'] + "\n[cached %ds ago; --no-cache to refresh]" % int(_time.time() - ent['ts']))
        return ent['report']

    service = get_gmail_service()
    lines = []
    msgs = {}
    for q in (f"to:{addr} newer_than:{days}d", f"from:{addr} newer_than:{days}d",
              f"in:scheduled to:{addr}"):
        try:
            r = service.users().messages().list(userId='me', q=q, maxResults=max_msgs).execute()
            for mm in r.get('messages', []) or []:
                msgs[mm['id']] = None
        except Exception:
            pass
    addr_lc = addr.lower()

    def placement(h, status):
        """Where does addr sit on this message? Direct-ness matters:
        To = addressed, Cc = copied, from = they wrote it, thread = neither."""
        if addr_lc in h.get('From', '').lower():
            return 'from-them'
        if addr_lc in h.get('To', '').lower():
            return 'To-them' if status in ('SENT', 'DRAFT') else 'To'
        if addr_lc in h.get('Cc', '').lower():
            return 'Cc-them' if status in ('SENT', 'DRAFT') else 'Cc'
        return 'thread'

    detailed = []
    for mid in list(msgs)[: max_msgs * 2]:
        try:
            m = service.users().messages().get(
                userId='me', id=mid, format='metadata',
                metadataHeaders=['From', 'To', 'Cc', 'Subject', 'Date']).execute()
            h = {x['name']: x['value'] for x in m['payload']['headers']}
            L = m.get('labelIds', [])
            status = ('DRAFT' if 'DRAFT' in L else
                      'SENT' if 'SENT' in L else
                      'INBOX' if 'INBOX' in L else ','.join(L[:2]) or 'OTHER')
            detailed.append((int(m.get('internalDate', 0)), status, h, m['id'],
                             m.get('threadId'), placement(h, status)))
        except Exception:
            continue
    detailed.sort(reverse=True)

    from datetime import datetime as _dt
    last_out = last_in = last_cc = None
    drafts = []
    for ts, status, h, mid, tid, pl in detailed:
        if status == 'SENT' and pl == 'To-them' and last_out is None:
            last_out = (ts, h)
        if status == 'SENT' and pl == 'Cc-them' and last_cc is None:
            last_cc = (ts, h)
        if status == 'INBOX' and pl == 'from-them' and last_in is None:
            last_in = (ts, h)
        if status == 'DRAFT':
            drafts.append((ts, h, mid))

    def fmt(ts):
        return _dt.fromtimestamp(ts / 1000).strftime('%a %d %b %H:%M')

    lines.append(f"THREAD STATE with {addr} (account={CURRENT_ACCOUNT}, last {days}d)")
    lines.append(f"  last SENT To them:   " + (f"{fmt(last_out[0])}  {last_out[1].get('Subject','')[:60]}" if last_out else "none in window (direct To only)"))
    if last_cc and (not last_out or last_cc[0] > last_out[0]):
        lines.append(f"  last Cc'd them:      {fmt(last_cc[0])}  {last_cc[1].get('Subject','')[:60]}  (Cc, not addressed)")
    lines.append(f"  last FROM them:      " + (f"{fmt(last_in[0])}  {last_in[1].get('Subject','')[:60]}" if last_in else "none in window"))
    lines.append(f"  open DRAFTS to them: {len(drafts)}")
    for ts, h, mid in drafts:
        lines.append(f"    - DRAFT {fmt(ts)}  {h.get('Subject','')[:55]}  (msg {mid})")
    if last_out and last_in:
        lines.append(f"  ball in {'THEIR' if last_out[0] > last_in[0] else 'YOUR'} court "
                     f"({'awaiting their reply' if last_out[0] > last_in[0] else 'they wrote last - reply owed'})"
                     f" — judged on direct To-them sends only; Cc does not count as contacting them")
    elif last_in and not last_out:
        lines.append("  ball in YOUR court (they have written; you have never sent direct To them in window)")
    lines.append("  recent messages (placement = where they sit on that message):")
    for ts, status, h, mid, tid, pl in detailed[:max_msgs]:
        frm = h.get('From', '')[:28]
        lines.append(f"    {fmt(ts)}  {status:9} [{pl:9}] {frm:30} {h.get('Subject','')[:44]}  (msg {mid} thread {tid})")
    report = '\n'.join(lines)
    print(report)
    cache[key] = {'ts': _time.time(), 'report': report}
    try:
        json.dump(cache, open(cache_path, 'w'))
    except Exception:
        pass
    return report


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
    if headers.get('Cc'):
        print(f"Cc: {headers.get('Cc')}")
    if headers.get('Bcc'):
        print(f"Bcc: {headers.get('Bcc')}")
    print(f"Subject: {headers.get('Subject', '(No Subject)')}")
    print(f"Date: {headers.get('Date', '')}")
    print("-" * 60)
    print(f"Body:\n{body}")

    return {
        'id': message_id,
        'threadId': msg_data['threadId'],
        'from': headers.get('From', 'Unknown'),
        'to': headers.get('To', ''),
        'cc': headers.get('Cc', ''),
        'bcc': headers.get('Bcc', ''),
        'subject': headers.get('Subject', '(No Subject)'),
        'date': headers.get('Date', ''),
        'body': body
    }


def main():
    global CURRENT_ACCOUNT
    parser = argparse.ArgumentParser(description="Gmail utility for reading, searching, drafting, and sending emails")
    parser.add_argument('--account', '-a', choices=['work', 'gmail', 'university'], default='work',
                       help='Account to use. Rename these choices and their token_<name>.json files to match your config.json.')
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
    draft_parser.add_argument('--keep-thread', dest='keep_thread', action='store_true',
                              help='Reply in the exact --reply-to thread even if newer traffic with the contact exists (disables stale-reply auto-redirect)')
    draft_parser.add_argument('--attach', action='append', dest='attachments', metavar='FILE',
                             help='Attach a file (can be used multiple times)')
    draft_parser.add_argument('--attach-inline', dest='inline_attachments', action='store_true',
                             help='Place each attached file in the body immediately after the '
                                  'line that names it, instead of all of them at the end')

    # Send command
    send_parser = subparsers.add_parser('send', help='Send an email directly')
    send_parser.add_argument('--to', help='Recipient email address (auto-filled if --reply-to used)')
    send_parser.add_argument('--subject', help='Email subject (auto-filled with Re: if --reply-to used)')
    send_parser.add_argument('--body', required=True, help='Email body')
    send_parser.add_argument('--cc', help='CC recipients (comma-separated)')
    send_parser.add_argument('--bcc', help='BCC recipients (comma-separated)')
    send_parser.add_argument('--reply-to', dest='reply_to', help='Message ID to reply to (includes thread)')
    send_parser.add_argument('--new', action='store_true', help='Start a new thread (skip auto-reply to existing thread)')
    send_parser.add_argument('--keep-thread', dest='keep_thread', action='store_true',
                             help='Reply in the exact --reply-to thread even if newer traffic with the contact exists (disables stale-reply auto-redirect)')
    send_parser.add_argument('--attach', action='append', dest='attachments', metavar='FILE',
                             help='Attach a file (can be used multiple times)')
    send_parser.add_argument('--attach-inline', dest='inline_attachments', action='store_true',
                             help='Place each attached file in the body immediately after the '
                                  'line that names it, instead of all of them at the end')

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

    # Thread-state command (one-call correspondent status, cached 10 min)
    ts_parser = subparsers.add_parser('thread-state', help='One-call thread state for a correspondent (sent/draft/inbox/scheduled + ball-in-whose-court)')
    ts_parser.add_argument('--with', dest='with_addr', required=True, help='Correspondent email address')
    ts_parser.add_argument('--days', type=int, default=90)
    ts_parser.add_argument('--no-cache', action='store_true')

    # Read draft command (live server-side content, incl. user edits)
    read_draft_parser = subparsers.add_parser('read-draft', help='Read current content of a draft (ground truth incl. user edits)')
    read_draft_parser.add_argument('--id', required=True, help='Draft ID or message ID')

    # Update draft command (in-place revision preserving draft ID + thread)
    update_parser = subparsers.add_parser('update-draft', help='Update an existing draft in place (same draft ID/thread)')
    update_parser.add_argument('--id', required=True, help='Draft ID or message ID')
    update_parser.add_argument('--body', required=True, help='New email body (replaces current body)')
    update_parser.add_argument('--to', help='Override recipient (defaults to current)')
    update_parser.add_argument('--subject', help='Override subject (defaults to current)')
    update_parser.add_argument('--cc', help='Override CC (defaults to current)')
    update_parser.add_argument('--bcc', help='Override BCC (defaults to current)')
    update_parser.add_argument('--attach', action='append', dest='attachments', metavar='FILE',
                               help='Attach a file (must re-pass existing attachments or they are dropped)')

    verify_parser = subparsers.add_parser('verify-draft', help='Audit a draft attachment the way IMAP clients see it (sha, PDF parse, bare LF, Apple Mail rewrite)')
    verify_parser.add_argument('--id', required=True, help='Draft ID or message ID')
    verify_parser.add_argument('--source', action='append', metavar='FILE', help='Local source file to hash-compare (repeatable)')

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
            create_draft(args.to, args.subject or '', args.body, args.cc, args.bcc, args.reply_to, args.new, args.attachments, getattr(args, 'keep_thread', False), getattr(args, 'inline_attachments', False))
        elif args.command == 'send':
            # Validate: need either --to or --reply-to
            if not args.to and not args.reply_to:
                print("Error: --to is required unless using --reply-to", file=sys.stderr)
                sys.exit(1)
            send_email(args.to, args.subject or '', args.body, args.cc, args.bcc, args.reply_to, args.new, args.attachments, getattr(args, 'keep_thread', False), getattr(args, 'inline_attachments', False))
        elif args.command == 'search':
            if not args.query and not args.with_person:
                print("Error: Either --query or --with is required", file=sys.stderr)
                sys.exit(1)
            search_emails(args.query, args.max, args.full, args.with_person)
        elif args.command == 'read':
            read_email(args.id)
        elif args.command == 'delete-draft':
            delete_draft(args.id)
        elif args.command == 'thread-state':
            thread_state(args.with_addr, args.days, no_cache=args.no_cache)
        elif args.command == 'read-draft':
            read_draft(args.id)
        elif args.command == 'update-draft':
            update_draft(args.id, args.body, args.to, args.subject, args.cc, args.bcc, args.attachments)
        elif args.command == 'verify-draft':
            if not verify_draft(args.id, args.source):
                sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
