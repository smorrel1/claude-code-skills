"""
Gmail Email Download Utility

Downloads emails matching specified queries and exports to markdown.
Requires OAuth credentials in credentials.json (see gmail skill for setup).
"""


import os.path
import base64
import email
import datetime
import markdown
import re
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Define scopes - read-only access is sufficient
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_service():
    """Get an authorized Gmail API service instance."""
    creds = None
    # Check if token.json exists (for saved credentials)
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If no valid credentials, let user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def get_messages(service, query):
    """Get list of messages matching query."""
    result = service.users().messages().list(userId='me', q=query).execute()
    messages = []
    if 'messages' in result:
        messages.extend(result['messages'])
    
    while 'nextPageToken' in result:
        page_token = result['nextPageToken']
        result = service.users().messages().list(
            userId='me', q=query, pageToken=page_token).execute()
        if 'messages' in result:
            messages.extend(result['messages'])
            
    return messages

def clean_html_text(html_content):
    """Remove HTML tags and return clean text."""
    if not html_content:
        return ""
    
    # Use BeautifulSoup to parse and extract text
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text()
    
    # Remove URLs - match http/https URLs
    text = re.sub(r'https?://[^\s\)]+', '[URL_REMOVED]', text)
    
    # Clean up extra whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)  # Replace multiple newlines with double newline
    text = re.sub(r'[ \t]+', ' ', text)      # Replace multiple spaces/tabs with single space
    
    return text.strip()

def remove_urls_from_text(text):
    """Remove URLs from plain text content."""
    if not text:
        return ""
    
    # Remove URLs - match http/https URLs
    text = re.sub(r'https?://[^\s\)]+', '[URL_REMOVED]', text)
    
    return text

def normalize_subject(subject):
    """Normalize email subject by removing prefixes and extra whitespace."""
    if not subject:
        return ""
    
    # Remove common email prefixes (case insensitive)
    subject = re.sub(r'^(re|fw|fwd|forward):\s*', '', subject, flags=re.IGNORECASE)
    
    # Remove extra whitespace
    subject = re.sub(r'\s+', ' ', subject).strip()
    
    return subject.lower()

def get_email_metadata(service, msg_id):
    """Get email metadata (subject, date, id) without full content."""
    msg = service.users().messages().get(userId='me', id=msg_id, format='metadata', metadataHeaders=['Subject', 'Date']).execute()
    
    headers = msg['payload']['headers']
    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
    date_str = next((h['value'] for h in headers if h['name'] == 'Date'), '')
    
    # Parse date
    try:
        date_obj = parsedate_to_datetime(date_str)
        # Make timezone-naive for comparison
        if date_obj.tzinfo is not None:
            date_obj = date_obj.replace(tzinfo=None)
    except:
        date_obj = datetime.datetime.now().replace(tzinfo=None)
    
    return {
        'id': msg_id,
        'subject': subject,
        'normalized_subject': normalize_subject(subject),
        'date': date_obj,
        'date_str': date_str
    }

def deduplicate_emails_by_subject(email_metadata_list):
    """Keep only the most recent email for each normalized subject."""
    subject_groups = {}
    
    # Group emails by normalized subject
    for email_meta in email_metadata_list:
        norm_subject = email_meta['normalized_subject']
        if norm_subject not in subject_groups:
            subject_groups[norm_subject] = []
        subject_groups[norm_subject].append(email_meta)
    
    # Keep only the most recent email from each group
    deduplicated = []
    for subject, emails in subject_groups.items():
        # Sort by date and take the most recent
        most_recent = max(emails, key=lambda x: x['date'])
        deduplicated.append(most_recent)
    
    return deduplicated

def get_message_content(service, msg_id):
    """Get the content of a message."""
    msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    
    # Get header info
    headers = msg['payload']['headers']
    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
    from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
    date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
    to_email = next((h['value'] for h in headers if h['name'] == 'To'), 'Unknown')
    
    # Get message body - prefer text/plain, fallback to text/html
    body = ""
    html_body = ""
    
    def extract_body_from_part(part):
        nonlocal body, html_body
        if part['mimeType'] == 'text/plain' and 'data' in part['body']:
            body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        elif part['mimeType'] == 'text/html' and 'data' in part['body']:
            html_body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        elif 'parts' in part:
            for subpart in part['parts']:
                extract_body_from_part(subpart)
    
    if 'parts' in msg['payload']:
        for part in msg['payload']['parts']:
            extract_body_from_part(part)
    elif 'body' in msg['payload'] and 'data' in msg['payload']['body']:
        if msg['payload']['mimeType'] == 'text/plain':
            body = base64.urlsafe_b64decode(msg['payload']['body']['data']).decode('utf-8')
        elif msg['payload']['mimeType'] == 'text/html':
            html_body = base64.urlsafe_b64decode(msg['payload']['body']['data']).decode('utf-8')
    
    # Use plain text if available, otherwise clean HTML
    if body:
        final_body = remove_urls_from_text(body)
    elif html_body:
        final_body = clean_html_text(html_body)
    else:
        final_body = "No content available"
    
    # Format as markdown
    md_content = f"""
# Email: {subject}
- **From:** {from_email}
- **To:** {to_email}
- **Date:** {date}

## Content
{final_body}

---
"""
    return md_content

def main(start_date=None, days_back=None):
    """
    Main function to download emails

    Args:
        start_date: datetime object for the start date, or None to use days_back
        days_back: number of days back to search, or None to use default
    """
    service = get_service()

    # Determine the search start date
    if start_date:
        # Use provided start date
        search_start = start_date
        print(f"Using provided start date: {search_start.strftime('%Y-%m-%d')}")
    elif days_back:
        # Use provided days back
        search_start = datetime.datetime.now() - datetime.timedelta(days=days_back)
        print(f"Using {days_back} days back: {search_start.strftime('%Y-%m-%d')}")
    else:
        # Default fallback
        NumberOfDaysAgo = 55
        search_start = datetime.datetime.now() - datetime.timedelta(days=NumberOfDaysAgo)
        print(f"Using default {NumberOfDaysAgo} days back: {search_start.strftime('%Y-%m-%d')}")

    # Format for Gmail API
    one_month_ago = search_start.strftime('%Y/%m/%d')
    
    # Search for emails containing @hologic.com
    hologic_query = f"@hologic.com after:{one_month_ago}"
    hologic_messages = get_messages(service, hologic_query)

    print(f"Found {len(hologic_messages)} emails containing '@hologic.com'")
    
    # Use hologic messages
    all_messages = hologic_messages
    print(f"Processing {len(all_messages)} emails containing '@hologic.com'")
    
    # Get metadata for all emails
    print("Getting email metadata for deduplication...")
    email_metadata = []
    for i, message in enumerate(all_messages):
        try:
            metadata = get_email_metadata(service, message['id'])
            email_metadata.append(metadata)
            if (i + 1) % 50 == 0:
                print(f"Processed metadata for {i+1}/{len(all_messages)} emails")
        except Exception as e:
            print(f"Error getting metadata for message {message['id']}: {str(e)}")
    
    # Deduplicate by subject
    deduplicated_emails = deduplicate_emails_by_subject(email_metadata)
    print(f"After deduplication: {len(deduplicated_emails)} unique emails (removed {len(all_messages) - len(deduplicated_emails)} duplicates)")
    
    # Write to markdown file
    with open('context/gmail_export_hologic.md', 'w', encoding='utf-8') as f:
        f.write("# Gmail Export\n\n")
        f.write(f"Exported {len(deduplicated_emails)} unique emails (deduplicated from {len(all_messages)} total)\n\n")
        
        # Process each deduplicated message
        for i, email_meta in enumerate(deduplicated_emails):
            try:
                content = get_message_content(service, email_meta['id'])
                f.write(content)
                print(f"Processed email {i+1}/{len(deduplicated_emails)}: {email_meta['subject']}")
            except Exception as e:
                print(f"Error processing message {email_meta['id']}: {str(e)}")
    
    print(f"Export complete! {len(deduplicated_emails)} deduplicated emails exported to context/gmail_export_hologic.md")

if __name__ == '__main__':
    # Search emails from 2 years ago
    import datetime
    two_years_ago = datetime.datetime.now() - datetime.timedelta(days=730)
    main(start_date=two_years_ago)