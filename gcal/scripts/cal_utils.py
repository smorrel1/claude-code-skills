#!/usr/bin/env python3
"""Google Calendar CRUD operations using OAuth credentials."""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
except ImportError:
    print("Installing required packages...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q",
                          "google-auth", "google-auth-oauthlib", "google-api-python-client"])
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request

# Paths to OAuth credentials (use Gmail skill credentials)
GMAIL_SKILL_DIR = Path.home() / ".claude/skills/gmail"
CLIENT_SECRETS_PATH = GMAIL_SKILL_DIR / "credentials.json"
GCAL_SKILL_DIR = Path.home() / ".claude/skills/gcal"
TOKEN_PATH = GCAL_SKILL_DIR / "token.json"

# Scopes needed for Calendar API
CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar']


def get_credentials() -> Credentials:
    """Load and refresh OAuth credentials, re-authenticating if needed."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRETS_PATH.exists():
        raise FileNotFoundError(f"Client secrets not found at {CLIENT_SECRETS_PATH}")

    creds = None

    if TOKEN_PATH.exists():
        with open(TOKEN_PATH) as f:
            token_data = json.load(f)

        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes", CALENDAR_SCOPES)
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("Calendar API access required. Opening browser for authorization...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRETS_PATH), CALENDAR_SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else CALENDAR_SCOPES
        }
        with open(TOKEN_PATH, 'w') as f:
            json.dump(token_data, f)

    return creds


def get_service():
    """Get the Calendar API service."""
    creds = get_credentials()
    return build('calendar', 'v3', credentials=creds)


def list_calendars():
    """List all calendars."""
    service = get_service()
    calendars = service.calendarList().list().execute()

    print("Your calendars:")
    for cal in calendars.get('items', []):
        primary = " (primary)" if cal.get('primary') else ""
        print(f"  - {cal['summary']}{primary}")
        print(f"    ID: {cal['id']}")

    return calendars.get('items', [])


def list_events(calendar_id='primary', days=7, max_results=20, query=None):
    """List upcoming events."""
    service = get_service()

    now = datetime.utcnow()
    time_min = now.isoformat() + 'Z'
    time_max = (now + timedelta(days=days)).isoformat() + 'Z'

    params = {
        'calendarId': calendar_id,
        'timeMin': time_min,
        'timeMax': time_max,
        'maxResults': max_results,
        'singleEvents': True,
        'orderBy': 'startTime'
    }

    if query:
        params['q'] = query

    events_result = service.events().list(**params).execute()
    events = events_result.get('items', [])

    if not events:
        print(f"No events found in the next {days} days.")
        return []

    print(f"Events in the next {days} days:")
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))

        # Format datetime nicely
        if 'T' in start:
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            start_str = start_dt.strftime('%a %b %d, %I:%M %p')
        else:
            start_str = start

        summary = event.get('summary', '(No title)')
        location = event.get('location', '')
        event_id = event.get('id', '')

        print(f"\n  {start_str}: {summary}")
        if location:
            print(f"    Location: {location}")
        print(f"    ID: {event_id[:20]}...")

    return events


def get_event(event_id, calendar_id='primary'):
    """Get a specific event by ID."""
    service = get_service()
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

    print(f"Event: {event.get('summary', '(No title)')}")
    print(f"  Start: {event['start'].get('dateTime', event['start'].get('date'))}")
    print(f"  End: {event['end'].get('dateTime', event['end'].get('date'))}")
    if event.get('location'):
        print(f"  Location: {event['location']}")
    if event.get('description'):
        print(f"  Description: {event['description']}")
    if event.get('attendees'):
        print("  Attendees:")
        for att in event['attendees']:
            status = att.get('responseStatus', 'unknown')
            print(f"    - {att.get('email')} ({status})")

    return event


def create_event(summary, start, end=None, duration_mins=60, location=None,
                 description=None, attendees=None, calendar_id='primary'):
    """
    Create a new calendar event.

    Args:
        summary: Event title
        start: Start time (ISO format or 'YYYY-MM-DD HH:MM')
        end: End time (optional, uses duration if not provided)
        duration_mins: Duration in minutes (default 60)
        location: Event location
        description: Event description
        attendees: Comma-separated list of email addresses
        calendar_id: Calendar ID (default 'primary')
    """
    service = get_service()

    # Parse start time
    if ' ' in start and 'T' not in start:
        start = start.replace(' ', 'T')

    if 'T' in start:
        # DateTime event
        if not start.endswith('Z') and '+' not in start and '-' not in start[-6:]:
            start += '-08:00'  # Default to PST

        if end:
            if ' ' in end and 'T' not in end:
                end = end.replace(' ', 'T')
            if not end.endswith('Z') and '+' not in end and '-' not in end[-6:]:
                end += '-08:00'
        else:
            # Calculate end from duration
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            end_dt = start_dt + timedelta(minutes=duration_mins)
            end = end_dt.isoformat()

        start_body = {'dateTime': start, 'timeZone': 'America/Los_Angeles'}
        end_body = {'dateTime': end, 'timeZone': 'America/Los_Angeles'}
    else:
        # All-day event
        start_body = {'date': start}
        if end:
            end_body = {'date': end}
        else:
            # Single day event
            end_body = {'date': start}

    event = {
        'summary': summary,
        'start': start_body,
        'end': end_body,
    }

    if location:
        event['location'] = location
    if description:
        event['description'] = description
    if attendees:
        event['attendees'] = [{'email': e.strip()} for e in attendees.split(',')]

    created = service.events().insert(calendarId=calendar_id, body=event).execute()

    print(f"Event created: {created.get('summary')}")
    print(f"  Link: {created.get('htmlLink')}")
    print(f"  ID: {created.get('id')}")

    return created


def update_event(event_id, calendar_id='primary', summary=None, start=None,
                 end=None, location=None, description=None):
    """Update an existing event."""
    service = get_service()

    # Get existing event
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

    if summary:
        event['summary'] = summary
    if location:
        event['location'] = location
    if description:
        event['description'] = description
    if start:
        if ' ' in start and 'T' not in start:
            start = start.replace(' ', 'T')
        if 'T' in start:
            if not start.endswith('Z') and '+' not in start and '-' not in start[-6:]:
                start += '-08:00'
            event['start'] = {'dateTime': start, 'timeZone': 'America/Los_Angeles'}
        else:
            event['start'] = {'date': start}
    if end:
        if ' ' in end and 'T' not in end:
            end = end.replace(' ', 'T')
        if 'T' in end:
            if not end.endswith('Z') and '+' not in end and '-' not in end[-6:]:
                end += '-08:00'
            event['end'] = {'dateTime': end, 'timeZone': 'America/Los_Angeles'}
        else:
            event['end'] = {'date': end}

    updated = service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()

    print(f"Event updated: {updated.get('summary')}")
    print(f"  Link: {updated.get('htmlLink')}")

    return updated


def delete_event(event_id, calendar_id='primary'):
    """Delete an event."""
    service = get_service()
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    print(f"Event deleted: {event_id}")


def check_availability(date, calendar_id='primary'):
    """Check availability for a specific date."""
    service = get_service()

    # Parse date
    if len(date) == 10:  # YYYY-MM-DD
        day_start = datetime.fromisoformat(date)
        day_end = day_start + timedelta(days=1)
    else:
        day_start = datetime.fromisoformat(date.replace(' ', 'T'))
        day_end = day_start + timedelta(days=1)

    time_min = day_start.isoformat() + 'Z' if day_start.tzinfo is None else day_start.isoformat()
    time_max = day_end.isoformat() + 'Z' if day_end.tzinfo is None else day_end.isoformat()

    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])

    print(f"Events on {date}:")
    if not events:
        print("  No events - day is free!")
    else:
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            if 'T' in start:
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                start_str = start_dt.strftime('%I:%M %p')
            else:
                start_str = "All day"
            print(f"  {start_str}: {event.get('summary', '(No title)')}")

    return events


def main():
    parser = argparse.ArgumentParser(description="Google Calendar CRUD operations")
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # List calendars
    subparsers.add_parser('calendars', help='List all calendars')

    # List events
    list_parser = subparsers.add_parser('list', help='List upcoming events')
    list_parser.add_argument('--days', '-d', type=int, default=7, help='Days ahead to show')
    list_parser.add_argument('--max', '-m', type=int, default=20, help='Max events')
    list_parser.add_argument('--query', '-q', help='Search query')
    list_parser.add_argument('--calendar', '-c', default='primary', help='Calendar ID')

    # Get event
    get_parser = subparsers.add_parser('get', help='Get event details')
    get_parser.add_argument('event_id', help='Event ID')
    get_parser.add_argument('--calendar', '-c', default='primary', help='Calendar ID')

    # Create event
    create_parser = subparsers.add_parser('create', help='Create new event')
    create_parser.add_argument('--summary', '-s', required=True, help='Event title')
    create_parser.add_argument('--start', required=True, help='Start time (YYYY-MM-DD HH:MM or YYYY-MM-DD)')
    create_parser.add_argument('--end', help='End time')
    create_parser.add_argument('--duration', '-d', type=int, default=60, help='Duration in minutes')
    create_parser.add_argument('--location', '-l', help='Location')
    create_parser.add_argument('--description', help='Description')
    create_parser.add_argument('--attendees', '-a', help='Comma-separated emails')
    create_parser.add_argument('--calendar', '-c', default='primary', help='Calendar ID')

    # Update event
    update_parser = subparsers.add_parser('update', help='Update event')
    update_parser.add_argument('event_id', help='Event ID')
    update_parser.add_argument('--summary', '-s', help='New title')
    update_parser.add_argument('--start', help='New start time')
    update_parser.add_argument('--end', help='New end time')
    update_parser.add_argument('--location', '-l', help='New location')
    update_parser.add_argument('--description', help='New description')
    update_parser.add_argument('--calendar', '-c', default='primary', help='Calendar ID')

    # Delete event
    delete_parser = subparsers.add_parser('delete', help='Delete event')
    delete_parser.add_argument('event_id', help='Event ID')
    delete_parser.add_argument('--calendar', '-c', default='primary', help='Calendar ID')

    # Check availability
    avail_parser = subparsers.add_parser('availability', help='Check availability for a date')
    avail_parser.add_argument('date', help='Date to check (YYYY-MM-DD)')
    avail_parser.add_argument('--calendar', '-c', default='primary', help='Calendar ID')

    args = parser.parse_args()

    try:
        if args.command == 'calendars':
            list_calendars()
        elif args.command == 'list':
            list_events(args.calendar, args.days, args.max, args.query)
        elif args.command == 'get':
            get_event(args.event_id, args.calendar)
        elif args.command == 'create':
            create_event(
                summary=args.summary,
                start=args.start,
                end=args.end,
                duration_mins=args.duration,
                location=args.location,
                description=args.description,
                attendees=args.attendees,
                calendar_id=args.calendar
            )
        elif args.command == 'update':
            update_event(
                event_id=args.event_id,
                calendar_id=args.calendar,
                summary=args.summary,
                start=args.start,
                end=args.end,
                location=args.location,
                description=args.description
            )
        elif args.command == 'delete':
            delete_event(args.event_id, args.calendar)
        elif args.command == 'availability':
            check_availability(args.date, args.calendar)
        else:
            parser.print_help()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
