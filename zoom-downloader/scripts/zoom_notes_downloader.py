#!/usr/bin/env python3
"""
Zoom Notes Downloader (REST API edition)

Pulls AI-Companion meeting summaries via the Zoom REST API and writes them as
markdown files in the same transcripts folder used by Fireflies, so the
after-meeting skill keeps working.

This replaces the Selenium/CDP scraper that broke when Chrome 149 disabled
remote debugging on the default profile (see HANDOVER-fix-chrome149-cdp.md).

Setup
-----
1. At https://marketplace.zoom.us create a Server-to-Server OAuth app on the
   the personal-Gmail Zoom account (NOT the company one — Zoom meetings are
   hosted under the gmail account). Scopes:

       meeting:read:list_summaries:admin
       meeting:read:summary:admin
       meeting:read:list_past_instances:admin   (optional, richer metadata)
       user:read:user:admin                     (optional, for host email)

2. Activate the app, then copy Account ID, Client ID, Client Secret into
   ~/git/zoom_downloader/.env:

       ZOOM_ACCOUNT_ID=...
       ZOOM_CLIENT_ID=...
       ZOOM_CLIENT_SECRET=...
       ZOOM_OUTPUT_DIR=/Users/stephenmorrell/Library/CloudStorage/Dropbox/sm_elaitra/transcripts

3. python3 zoom_notes_downloader.py --dry-run    # list new summaries
   python3 zoom_notes_downloader.py              # download new summaries
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPT_DIR / "state.json"
TOKEN_CACHE = SCRIPT_DIR / ".token_cache.json"

ZOOM_OAUTH_URL = "https://zoom.us/oauth/token"
ZOOM_API_BASE = "https://api.zoom.us/v2"

DEFAULT_OUTPUT_DIR = os.environ.get(
    "ZOOM_OUTPUT_DIR",
    str(Path.home() / "Library/CloudStorage/Dropbox/sm_elaitra/transcripts"),
)
DEFAULT_LOOKBACK_DAYS = int(os.environ.get("ZOOM_LOOKBACK_DAYS", "30"))


class ZoomDownloaderError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# OAuth (server-to-server)
# ---------------------------------------------------------------------------
@dataclass
class OAuthCreds:
    account_id: str
    client_id: str
    client_secret: str

    @classmethod
    def from_env(cls) -> "OAuthCreds":
        missing = [
            k for k in ("ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET")
            if not os.environ.get(k)
        ]
        if missing:
            raise ZoomDownloaderError(
                "Missing env vars: " + ", ".join(missing) +
                f". Set them in {SCRIPT_DIR}/.env (see top of script)."
            )
        return cls(
            account_id=os.environ["ZOOM_ACCOUNT_ID"],
            client_id=os.environ["ZOOM_CLIENT_ID"],
            client_secret=os.environ["ZOOM_CLIENT_SECRET"],
        )


def get_access_token(creds: OAuthCreds) -> str:
    """Return a cached token if still valid, otherwise fetch a fresh one."""
    if TOKEN_CACHE.exists():
        try:
            cached = json.loads(TOKEN_CACHE.read_text())
            if cached.get("expires_at", 0) - 60 > time.time():
                return cached["access_token"]
        except Exception:
            pass

    basic = base64.b64encode(
        f"{creds.client_id}:{creds.client_secret}".encode()
    ).decode()
    resp = requests.post(
        ZOOM_OAUTH_URL,
        headers={"Authorization": f"Basic {basic}"},
        params={"grant_type": "account_credentials", "account_id": creds.account_id},
        timeout=30,
    )
    if resp.status_code != 200:
        raise ZoomDownloaderError(
            f"OAuth failed ({resp.status_code}): {resp.text[:300]}"
        )
    payload = resp.json()
    TOKEN_CACHE.write_text(json.dumps({
        "access_token": payload["access_token"],
        "expires_at": time.time() + payload.get("expires_in", 3600),
    }))
    try:
        os.chmod(TOKEN_CACHE, 0o600)
    except OSError:
        pass
    return payload["access_token"]


# ---------------------------------------------------------------------------
# Zoom API
# ---------------------------------------------------------------------------
class ZoomClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path: str, **params) -> dict:
        url = f"{ZOOM_API_BASE}{path}"
        resp = self.session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            time.sleep(int(resp.headers.get("Retry-After", "2")))
            resp = self.session.get(url, params=params, timeout=30)
        if resp.status_code >= 400:
            raise ZoomDownloaderError(
                f"GET {path} -> {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    def list_summaries(self, from_date: str, to_date: str):
        """Yield every summary in the [from_date, to_date] window."""
        next_token = None
        while True:
            params = {"from": from_date, "to": to_date, "page_size": 100}
            if next_token:
                params["next_page_token"] = next_token
            payload = self._get("/meetings/meeting_summaries", **params)
            for s in payload.get("summaries", []):
                yield s
            next_token = payload.get("next_page_token")
            if not next_token:
                return

    def get_summary(self, meeting_uuid: str) -> dict:
        # UUIDs that start with "/" or contain "//" must be double-URL-encoded
        # per Zoom's API rules.
        if meeting_uuid.startswith("/") or "//" in meeting_uuid:
            encoded = urllib.parse.quote(
                urllib.parse.quote(meeting_uuid, safe=""), safe=""
            )
        else:
            encoded = urllib.parse.quote(meeting_uuid, safe="")
        return self._get(f"/meetings/{encoded}/meeting_summary")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {"downloaded": {}}


def save_state(state: dict, path: Path) -> None:
    path.write_text(json.dumps(state, indent=2))


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------
SAFE_FILENAME_RE = re.compile(r"[^\w\s\-.]")
COLLAPSE_WS_RE = re.compile(r"\s+")


def slugify(text: str, fallback: str = "Zoom-Notes") -> str:
    cleaned = SAFE_FILENAME_RE.sub("", text or "").strip().rstrip(".")
    cleaned = COLLAPSE_WS_RE.sub("-", cleaned)
    return cleaned or fallback


def parse_zoom_time(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def make_filename(summary: dict) -> str:
    topic = summary.get("meeting_topic") or summary.get("summary_title") or "Zoom-Notes"
    start = parse_zoom_time(
        summary.get("meeting_start_time") or summary.get("summary_start_time")
    )
    if start:
        local = start.astimezone()
        return f"{local.strftime('%Y%m%d-%H%M')}-Zoom-{slugify(topic)}.md"
    short = (summary.get("meeting_uuid") or "")[:8] or "nouuid"
    return f"undated-{short}-Zoom-{slugify(topic)}.md"


def format_summary_md(summary: dict, detail: dict) -> str:
    topic = detail.get("meeting_topic") or summary.get("meeting_topic") or "Untitled"
    start = parse_zoom_time(detail.get("meeting_start_time"))
    end = parse_zoom_time(detail.get("meeting_end_time"))
    host_email = detail.get("meeting_host_email") or ""
    summary_title = detail.get("summary_title") or topic

    lines: list[str] = [f"# {summary_title}", ""]
    if start:
        local = start.astimezone()
        lines.append(f"**Date:** {local.strftime('%Y-%m-%d %H:%M %Z')}")
    if end:
        lines.append(f"**End:** {end.astimezone().strftime('%H:%M %Z')}")
    if host_email:
        lines.append(f"**Host:** {host_email}")
    lines.append(f"**Meeting UUID:** {detail.get('meeting_uuid', '')}")
    lines += ["", "---", ""]

    overview = (detail.get("summary_overview") or "").strip()
    if overview:
        lines += ["## Overview", "", overview, ""]

    for section in detail.get("summary_details") or []:
        label = (section.get("label") or "").strip() or "Section"
        body = (section.get("summary") or "").strip()
        if body:
            lines += [f"## {label}", "", body, ""]

    next_steps = detail.get("next_steps") or []
    if next_steps:
        lines += ["## Next Steps", ""]
        for step in next_steps:
            lines.append(f"- {step}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# .env loader (no python-dotenv dependency)
# ---------------------------------------------------------------------------
def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Zoom Notes Downloader (REST API)")
    p.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--all", action="store_true",
                   help="Re-download every summary in the window (ignore state).")
    p.add_argument("--dry-run", action="store_true",
                   help="List summaries without downloading.")
    p.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                   help="How far back to scan (default %(default)s).")
    p.add_argument("--from-date", default=None,
                   help="Explicit YYYY-MM-DD start (overrides --lookback-days).")
    p.add_argument("--to-date", default=None,
                   help="Explicit YYYY-MM-DD end (defaults to today).")
    p.add_argument("--state-file", default=str(STATE_FILE))
    return p.parse_args()


def main() -> int:
    args = parse_args()

    load_env_file(SCRIPT_DIR / ".env")

    try:
        creds = OAuthCreds.from_env()
    except ZoomDownloaderError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    today = datetime.now(timezone.utc).date()
    to_date = args.to_date or today.isoformat()
    from_date = args.from_date or (today - timedelta(days=args.lookback_days)).isoformat()
    print(f"Scanning AI-Companion summaries from {from_date} to {to_date}")

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    state_path = Path(args.state_file)
    state = load_state(state_path)
    if args.all:
        state["downloaded"] = {}

    try:
        token = get_access_token(creds)
    except ZoomDownloaderError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    client = ZoomClient(token)

    new_count = 0
    skip_count = 0
    error_count = 0

    for summary in client.list_summaries(from_date, to_date):
        uuid = summary.get("meeting_uuid")
        if not uuid:
            continue

        if not args.all and uuid in state["downloaded"]:
            skip_count += 1
            continue

        title = summary.get("meeting_topic") or summary.get("summary_title") or "(untitled)"
        print(f"  [{new_count + 1}] {title}  ({uuid[:12]}...)")

        if args.dry_run:
            new_count += 1
            continue

        try:
            detail = client.get_summary(uuid)
        except ZoomDownloaderError as e:
            print(f"      WARN: {e}", file=sys.stderr)
            error_count += 1
            continue

        content = format_summary_md(summary, detail)
        filename = make_filename({**summary, **detail})
        filepath = output_dir / filename
        if filepath.exists() and not args.all:
            stem = filepath.stem
            filepath = output_dir / f"{stem}-{uuid[:6]}.md"
        filepath.write_text(content, encoding="utf-8")

        state["downloaded"][uuid] = {
            "title": title,
            "filename": filepath.name,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "size": len(content),
        }
        save_state(state, state_path)
        new_count += 1
        print(f"      Saved: {filepath.name}  ({len(content)} chars)")

    print(f"\nSummary: new={new_count}  skipped={skip_count}  errors={error_count}")
    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
