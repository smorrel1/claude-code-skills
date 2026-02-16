#!/usr/bin/env python3
"""
Fireflies.ai Transcript Downloader

Downloads meeting transcripts from Fireflies.ai to local storage.
Supports API-based access, live streaming, and browser automation for guest links.

Usage:
    # Set API key (get from Fireflies Settings > Developer Settings > API)
    export FIREFLIES_API_KEY="your_api_key"

    # List completed transcripts:
    python3 fireflies_transcript.py --api --list

    # Download specific completed transcript:
    python3 fireflies_transcript.py --api --id TRANSCRIPT_ID

    # Download ALL completed transcripts:
    python3 fireflies_transcript.py --api --all

    # List LIVE meetings in progress:
    python3 fireflies_transcript.py --api --live

    # Stream LIVE transcription (saves to file in real-time):
    python3 fireflies_transcript.py --stream MEETING_ID

    # Using guest link (browser automation, no API key needed):
    python3 fireflies_transcript.py --url "https://app.fireflies.ai/live/ID?ref=guestMode"
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Default output directory
DEFAULT_OUTPUT_DIR = Path.home() / "Desktop" / "fireflies_transcripts"


def get_api_key():
    """Get API key from environment or prompt user."""
    api_key = os.environ.get("FIREFLIES_API_KEY")
    if not api_key:
        api_key = input("Enter your Fireflies API key: ").strip()
    return api_key


def list_active_meetings(api_key: str):
    """List currently active/live meetings."""
    query = """
    query {
        active_meetings {
            id
            title
            meeting_link
            organizer_email
            start_time
            state
        }
    }
    """
    result = graphql_request(query, {}, api_key)
    return result.get("data", {}).get("active_meetings", [])


def graphql_request(query: str, variables: dict = None, api_key: str = None):
    """Make a GraphQL request to Fireflies API."""
    import requests

    url = "https://api.fireflies.ai/graphql"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def list_transcripts(api_key: str, limit: int = 50):
    """List available transcripts."""
    query = """
    query Transcripts($limit: Int) {
        transcripts(limit: $limit) {
            id
            title
            date
            dateString
            duration
            organizer_email
        }
    }
    """
    result = graphql_request(query, {"limit": limit}, api_key)
    return result.get("data", {}).get("transcripts", [])


def get_transcript(transcript_id: str, api_key: str):
    """Get full transcript details by ID."""
    query = """
    query Transcript($transcriptId: String!) {
        transcript(id: $transcriptId) {
            id
            title
            date
            dateString
            duration
            organizer_email
            participants
            transcript_url
            audio_url
            video_url
            summary {
                overview
                action_items
                keywords
            }
            speakers {
                id
                name
            }
            sentences {
                index
                speaker_id
                speaker_name
                text
                raw_text
                start_time
                end_time
            }
        }
    }
    """
    result = graphql_request(query, {"transcriptId": transcript_id}, api_key)
    return result.get("data", {}).get("transcript")


def format_transcript_text(transcript_data: dict) -> str:
    """Format transcript data into readable text."""
    lines = []

    # Header
    lines.append(f"# {transcript_data.get('title', 'Untitled Meeting')}")
    lines.append(f"Date: {transcript_data.get('dateString', 'Unknown')}")
    lines.append(f"Duration: {transcript_data.get('duration', 0)} minutes")
    lines.append(f"Organizer: {transcript_data.get('organizer_email', 'Unknown')}")

    participants = transcript_data.get('participants', [])
    if participants:
        lines.append(f"Participants: {', '.join(participants)}")

    lines.append("")

    # Summary
    summary = transcript_data.get('summary', {})
    if summary:
        if summary.get('overview'):
            lines.append("## Summary")
            lines.append(summary['overview'])
            lines.append("")

        if summary.get('action_items'):
            lines.append("## Action Items")
            for item in summary['action_items']:
                lines.append(f"- {item}")
            lines.append("")

        if summary.get('keywords'):
            lines.append(f"## Keywords: {', '.join(summary['keywords'])}")
            lines.append("")

    # Transcript
    lines.append("## Transcript")
    lines.append("")

    sentences = transcript_data.get('sentences') or []
    current_speaker = None

    if not sentences:
        lines.append("(Transcript not yet available - meeting may still be in progress)")
        return "\n".join(lines)

    for sentence in sentences:
        speaker = sentence.get('speaker_name', 'Unknown')
        text = sentence.get('raw_text') or sentence.get('text', '')
        start_time = sentence.get('start_time', 0)

        # Format timestamp as MM:SS
        minutes = int(start_time // 60)
        seconds = int(start_time % 60)
        timestamp = f"[{minutes:02d}:{seconds:02d}]"

        if speaker != current_speaker:
            lines.append("")
            lines.append(f"**{speaker}** {timestamp}")
            current_speaker = speaker

        lines.append(text)

    return "\n".join(lines)


def save_transcript(transcript_data: dict, output_dir: Path):
    """Save transcript to files."""
    # Create directory for this transcript
    date_str = transcript_data.get('dateString', 'unknown-date')
    title = transcript_data.get('title', 'Untitled')
    # Sanitize filename
    safe_title = re.sub(r'[^\w\s-]', '', title)[:50]
    safe_date = re.sub(r'[^\w-]', '', date_str)[:20]

    transcript_dir = output_dir / f"{safe_date}_{safe_title}"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON
    json_path = transcript_dir / "transcript.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(transcript_data, f, indent=2, ensure_ascii=False)
    print(f"  Saved JSON: {json_path}")

    # Save formatted text
    text_path = transcript_dir / "transcript.md"
    formatted_text = format_transcript_text(transcript_data)
    with open(text_path, 'w', encoding='utf-8') as f:
        f.write(formatted_text)
    print(f"  Saved Markdown: {text_path}")

    # Download audio if available
    audio_url = transcript_data.get('audio_url')
    if audio_url:
        try:
            import requests
            audio_path = transcript_dir / "recording.mp3"
            print(f"  Downloading audio...")
            response = requests.get(audio_url, stream=True)
            response.raise_for_status()
            with open(audio_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"  Saved Audio: {audio_path}")
        except Exception as e:
            print(f"  Warning: Could not download audio: {e}")

    return transcript_dir


def download_via_api(args):
    """Download transcripts using the Fireflies API."""
    api_key = get_api_key()
    if not api_key:
        print("Error: No API key provided")
        sys.exit(1)

    output_dir = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.live:
        print("Fetching active/live meetings...")
        meetings = list_active_meetings(api_key)
        if not meetings:
            print("\nNo active meetings found.")
            print("Note: Meetings appear here only while Fireflies bot is in them.")
        else:
            print(f"\nFound {len(meetings)} active meeting(s):\n")
            for m in meetings:
                title = m.get('title', 'Untitled')
                mid = m.get('id')
                organizer = m.get('organizer_email', '')
                link = m.get('meeting_link', '')
                start = m.get('start_time', '')
                state = m.get('state', '')
                print(f"  [{mid}] {title}")
                print(f"      Organizer: {organizer}")
                if start:
                    print(f"      Started: {start}")
                if state:
                    print(f"      State: {state}")
                if link:
                    print(f"      Link: {link}")
                print(f"      Stream with: --stream {mid}\n")
        return

    if args.list:
        print("Fetching transcript list...")
        transcripts = list_transcripts(api_key, limit=args.limit or 50)
        print(f"\nFound {len(transcripts)} transcripts:\n")
        for t in transcripts:
            date = t.get('dateString', 'Unknown date')
            title = t.get('title', 'Untitled')
            duration = t.get('duration', 0)
            tid = t.get('id')
            print(f"  [{tid}] {date} - {title} ({duration} min)")
        return

    if args.id:
        # Download specific transcript
        print(f"Fetching transcript {args.id}...")
        transcript = get_transcript(args.id, api_key)
        if transcript:
            save_path = save_transcript(transcript, output_dir)
            print(f"\nTranscript saved to: {save_path}")
        else:
            print(f"Error: Transcript {args.id} not found")
            sys.exit(1)

    elif args.all:
        # Download all transcripts
        print("Fetching all transcripts...")
        transcripts = list_transcripts(api_key, limit=args.limit or 500)
        print(f"Found {len(transcripts)} transcripts")

        for i, t in enumerate(transcripts, 1):
            tid = t.get('id')
            title = t.get('title', 'Untitled')
            print(f"\n[{i}/{len(transcripts)}] Downloading: {title}")

            try:
                full_transcript = get_transcript(tid, api_key)
                if full_transcript:
                    save_transcript(full_transcript, output_dir)
                time.sleep(0.5)  # Rate limiting
            except Exception as e:
                print(f"  Error: {e}")

        print(f"\nAll transcripts saved to: {output_dir}")


def stream_live_meeting(meeting_id: str, api_key: str, output_dir: Path):
    """Stream live transcription from an active meeting via Socket.IO."""
    try:
        import socketio
    except ImportError:
        print("Installing python-socketio[client]...")
        subprocess.run(["pip3", "install", "python-socketio[client]"], check=True)
        import socketio

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # YYYYMMDD_HHMMSS
    output_file = output_dir / f"live_{timestamp}.txt"

    print(f"Connecting to live meeting: {meeting_id}")
    print(f"Transcript will be saved to: {output_file}")
    print("Press Ctrl+C to stop streaming\n")

    # Socket.IO client with auth
    sio = socketio.Client()
    current_chunk = {'id': None, 'speaker': '', 'text': '', 'time': 0}

    def write_chunk():
        """Write the current chunk to file."""
        if current_chunk['text']:
            minutes = int(float(current_chunk['time']) // 60)
            seconds = int(float(current_chunk['time']) % 60)
            ts = f"[{minutes:02d}:{seconds:02d}]"
            line = f"{ts} {current_chunk['speaker']}: {current_chunk['text']}"
            print(line, flush=True)
            with open(output_file, 'a', encoding='utf-8') as f:
                f.write(line + "\n")
                f.flush()

    @sio.event
    def connect():
        print("Connected to Fireflies Realtime API", flush=True)

    @sio.event
    def disconnect():
        write_chunk()  # Write final chunk
        print(f"\nDisconnected. Transcript saved to: {output_file}", flush=True)

    @sio.on('auth.success')
    def on_auth_success(data):
        print("Authentication successful - listening for transcript...\n", flush=True)

    @sio.on('auth.failed')
    def on_auth_failed(data):
        print(f"Authentication failed: {data}", flush=True)
        sio.disconnect()

    @sio.on('connection.established')
    def on_connection_established(data=None):
        print("Connection established", flush=True)

    @sio.on('transcription.broadcast')
    def on_transcription(data):
        """Handle incoming transcription data."""
        try:
            payload = data.get('payload', data)
            chunk_id = payload.get('chunk_id', '')
            speaker = payload.get('speaker_name', 'Unknown')
            text = payload.get('text', '')
            start_time = payload.get('start_time', 0)

            # New chunk? Write the previous one first
            if chunk_id != current_chunk['id'] and current_chunk['id'] is not None:
                write_chunk()

            # Update current chunk (keep longest text for this chunk_id)
            if chunk_id != current_chunk['id'] or len(text) > len(current_chunk['text']):
                current_chunk['id'] = chunk_id
                current_chunk['speaker'] = speaker
                current_chunk['text'] = text
                current_chunk['time'] = start_time

        except Exception as e:
            print(f"Error processing transcription: {e}")
            print(f"Raw data: {data}")

    @sio.on('meeting.ended')
    def on_meeting_ended(data):
        print("\n--- Meeting ended ---")
        sio.disconnect()

    @sio.on('*')
    def catch_all(event, data):
        """Catch all other events for debugging."""
        if event not in ['transcription.broadcast', 'auth.success', 'connection.established']:
            print(f"Event '{event}': {data}")

    try:
        # Connect with Socket.IO - use https and force websocket transport
        sio.connect(
            'https://api.fireflies.ai',
            socketio_path='/ws/realtime',
            auth={
                'token': f'Bearer {api_key}',
                'transcriptId': meeting_id
            },
            transports=['websocket'],
            wait_timeout=10
        )
        sio.wait()
    except KeyboardInterrupt:
        print("\nStopping stream...")
        if sio.connected:
            sio.disconnect()
    except Exception as e:
        print(f"Connection error: {e}")

    return output_file


def download_via_browser(url: str, output_dir: Path):
    """Download transcript from guest link using browser automation."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Installing...")
        subprocess.run(["pip3", "install", "playwright"], check=True)
        subprocess.run(["playwright", "install", "chromium"], check=True)
        from playwright.sync_api import sync_playwright

    print(f"Opening URL in browser: {url}")
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headless=False for debugging
        context = browser.new_context()
        page = context.new_page()

        # Navigate and wait for content to load
        page.goto(url, wait_until="networkidle")
        print("Waiting for transcript to load...")
        time.sleep(5)  # Wait for JS to render

        # Try to find and extract transcript content
        # These selectors may need adjustment based on Fireflies UI
        transcript_selectors = [
            '[data-testid="transcript"]',
            '.transcript-container',
            '.meeting-transcript',
            '[class*="transcript"]',
            '[class*="Transcript"]',
        ]

        transcript_text = None
        for selector in transcript_selectors:
            try:
                element = page.query_selector(selector)
                if element:
                    transcript_text = element.inner_text()
                    break
            except:
                continue

        if not transcript_text:
            # Fallback: get all visible text
            print("Could not find specific transcript element, extracting page text...")
            transcript_text = page.inner_text('body')

        # Extract meeting title
        title = "Guest_Meeting"
        try:
            title_el = page.query_selector('h1, [class*="title"], [class*="Title"]')
            if title_el:
                title = title_el.inner_text()
        except:
            pass

        # Take screenshot for reference
        screenshot_path = output_dir / "page_screenshot.png"
        page.screenshot(path=str(screenshot_path))
        print(f"Saved screenshot: {screenshot_path}")

        # Save transcript
        safe_title = re.sub(r'[^\w\s-]', '', title)[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        text_path = output_dir / f"{timestamp}_{safe_title}.txt"
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(f"# {title}\n")
            f.write(f"Source: {url}\n")
            f.write(f"Downloaded: {datetime.now().isoformat()}\n\n")
            f.write(transcript_text)

        print(f"Saved transcript: {text_path}")

        browser.close()
        return text_path


def main():
    parser = argparse.ArgumentParser(
        description="Download Fireflies.ai meeting transcripts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("--api", action="store_true",
                        help="Use Fireflies API (requires API key)")
    parser.add_argument("--url", type=str,
                        help="Guest link URL to download")
    parser.add_argument("--id", type=str,
                        help="Specific transcript ID to download")
    parser.add_argument("--all", action="store_true",
                        help="Download all available transcripts")
    parser.add_argument("--list", action="store_true",
                        help="List available transcripts")
    parser.add_argument("--live", action="store_true",
                        help="List active/live meetings")
    parser.add_argument("--stream", type=str, metavar="MEETING_ID",
                        help="Stream live transcription from active meeting")
    parser.add_argument("--limit", type=int, default=50,
                        help="Maximum number of transcripts to list/download")
    parser.add_argument("--output", "-o", type=str,
                        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")

    args = parser.parse_args()

    # Track if we already fetched the API key
    cached_api_key = None

    # Default: auto-stream if there's an active meeting
    if not (args.api or args.url or args.stream or args.list or args.id or args.all or args.live):
        cached_api_key = get_api_key()
        meetings = list_active_meetings(cached_api_key)
        if meetings:
            # Auto-stream the first active meeting
            args.stream = meetings[0].get('id')
            print(f"Auto-streaming: {meetings[0].get('title', 'Untitled')}\n", flush=True)
        else:
            # No active meetings, show completed transcripts
            args.api = True
            args.list = True

    if args.api and not (args.list or args.id or args.all or args.live):
        args.live = True  # Default to --live when only --api specified

    output_dir = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR

    if args.stream:
        # Stream live meeting
        api_key = cached_api_key or get_api_key()
        stream_live_meeting(args.stream, api_key, output_dir)
    elif args.api:
        download_via_api(args)
    elif args.url:
        download_via_browser(args.url, output_dir)


if __name__ == "__main__":
    main()
