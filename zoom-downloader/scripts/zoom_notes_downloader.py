#!/usr/bin/env python3
"""
Zoom Notes Downloader
Downloads meeting transcripts from Zoom Docs (docs.zoom.us) and saves as markdown.
Uses cookies extracted from Chrome (no need to close Chrome) + headless Selenium for rendering.

Usage:
    python zoom_notes_downloader.py                  # Download all new notes
    python zoom_notes_downloader.py --all            # Re-download everything
    python zoom_notes_downloader.py --dry-run        # List notes without downloading
    python zoom_notes_downloader.py --visible        # Show browser window
    python zoom_notes_downloader.py --profile "Default"  # Specify Chrome profile
"""

import os
import re
import sys
import json
import time
import shutil
import sqlite3
import hashlib
import argparse
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_OUTPUT_DIR = os.path.expanduser(
    "~/Library/CloudStorage/GoogleDrive-stephen.morrell@elaitra.com"
    "/Shared drives/Elaitra_gc/agendas-minutes-notes"
)
CHROME_DIR = os.path.expanduser("~/Library/Application Support/Google/Chrome")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
ZOOM_DOCS_URL = "https://docs.zoom.us/recent"
PAGE_LOAD_WAIT = 8
DOC_LOAD_WAIT = 5


# ---------------------------------------------------------------------------
# Chrome cookie decryption (macOS)
# ---------------------------------------------------------------------------
def get_chrome_encryption_key():
    """Get Chrome's encryption key from macOS Keychain."""
    cmd = [
        "security", "find-generic-password",
        "-s", "Chrome Safe Storage",
        "-w",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "Could not retrieve Chrome Safe Storage key from Keychain. "
            f"Error: {result.stderr}"
        )
    return result.stdout.strip()


def decrypt_cookie_value(encrypted_value, key):
    """Decrypt a Chrome cookie value on macOS."""
    if not encrypted_value:
        return ""

    # Chrome cookies on macOS start with b'v10' or b'v11'
    if encrypted_value[:3] == b"v10" or encrypted_value[:3] == b"v11":
        encrypted_value = encrypted_value[3:]  # strip version prefix

        # Derive key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA1(),
            length=16,
            salt=b"saltysalt",
            iterations=1003,
        )
        derived_key = kdf.derive(key.encode("utf-8"))

        # AES-CBC with 16-byte IV of spaces
        iv = b" " * 16
        cipher = Cipher(algorithms.AES(derived_key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted_value) + decryptor.finalize()

        # Remove PKCS7 padding
        padding_len = decrypted[-1]
        if isinstance(padding_len, int) and 1 <= padding_len <= 16:
            decrypted = decrypted[:-padding_len]

        return decrypted.decode("utf-8", errors="replace")

    # Unencrypted cookie
    return encrypted_value.decode("utf-8", errors="replace")


def find_chrome_profile_with_zoom():
    """Find which Chrome profile has Zoom cookies."""
    for entry in os.listdir(CHROME_DIR):
        cookie_path = os.path.join(CHROME_DIR, entry, "Cookies")
        if not os.path.exists(cookie_path):
            continue
        try:
            # Copy to avoid locking issues with running Chrome
            tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            tmp.close()
            shutil.copy2(cookie_path, tmp.name)
            conn = sqlite3.connect(tmp.name)
            c = conn.cursor()
            c.execute(
                "SELECT count(*) FROM cookies WHERE host_key LIKE '%zoom.us%'"
            )
            count = c.fetchone()[0]
            conn.close()
            os.unlink(tmp.name)
            if count > 10:
                return entry
        except Exception:
            continue
    return None


def extract_zoom_cookies(profile_name):
    """Extract and decrypt Zoom cookies from Chrome's cookie database."""
    cookie_path = os.path.join(CHROME_DIR, profile_name, "Cookies")
    if not os.path.exists(cookie_path):
        raise FileNotFoundError(f"Cookie DB not found: {cookie_path}")

    # Copy to temp file to avoid locking
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    shutil.copy2(cookie_path, tmp.name)

    encryption_key = get_chrome_encryption_key()

    conn = sqlite3.connect(tmp.name)
    c = conn.cursor()
    c.execute(
        "SELECT host_key, name, encrypted_value, path, is_secure, is_httponly "
        "FROM cookies WHERE host_key LIKE '%zoom.us%'"
    )
    rows = c.fetchall()
    conn.close()
    os.unlink(tmp.name)

    cookies = []
    for host, name, enc_val, path, secure, httponly in rows:
        value = decrypt_cookie_value(enc_val, encryption_key)
        cookies.append({
            "domain": host,
            "name": name,
            "value": value,
            "path": path,
            "secure": bool(secure),
            "httpOnly": bool(httponly),
        })

    return cookies


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"downloaded": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Browser automation
# ---------------------------------------------------------------------------
def create_driver(headless=True):
    """Create a fresh Chrome driver (no profile needed, cookies injected)."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-extensions")
    options.add_argument("--window-size=1200,900")

    chromedriver_paths = [
        "/opt/homebrew/bin/chromedriver",
        "/usr/local/bin/chromedriver",
    ]
    service = None
    for path in chromedriver_paths:
        if os.path.exists(path):
            service = Service(path)
            break

    if service:
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)

    return driver


def inject_cookies(driver, cookies):
    """Navigate to zoom.us and inject cookies."""
    # Must visit the domain first before setting cookies
    driver.get("https://zoom.us")
    time.sleep(2)

    for cookie in cookies:
        try:
            # Selenium requires domain without leading dot for some cookies
            selenium_cookie = {
                "name": cookie["name"],
                "value": cookie["value"],
                "path": cookie["path"],
                "secure": cookie["secure"],
            }
            # Set domain - Selenium is picky about this
            domain = cookie["domain"]
            if domain.startswith("."):
                selenium_cookie["domain"] = domain
            else:
                selenium_cookie["domain"] = domain

            driver.add_cookie(selenium_cookie)
        except Exception:
            # Some cookies may fail (cross-domain, etc.) - that's OK
            pass

    # Also inject on docs.zoom.us
    driver.get("https://docs.zoom.us")
    time.sleep(2)
    for cookie in cookies:
        try:
            domain = cookie["domain"]
            if "docs.zoom.us" in domain or domain == ".zoom.us":
                selenium_cookie = {
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "path": cookie["path"],
                    "secure": cookie["secure"],
                }
                if domain.startswith("."):
                    selenium_cookie["domain"] = domain
                else:
                    selenium_cookie["domain"] = domain
                driver.add_cookie(selenium_cookie)
        except Exception:
            pass


def discover_docs(driver):
    """Discover all doc titles and URLs from the recent page."""
    driver.get(ZOOM_DOCS_URL)
    time.sleep(PAGE_LOAD_WAIT)

    if "signin" in driver.current_url.lower():
        print("ERROR: Cookie injection failed - Zoom requires login.")
        print("       Make sure you're logged into Zoom in Chrome.")
        return []

    docs = []
    seen_ids = set()
    last_count = 0
    stale_rounds = 0

    for scroll_round in range(30):
        # Find all clickable doc links
        links = driver.find_elements(By.CSS_SELECTOR, "a[href='#']")
        for link in links:
            title = link.text.strip()
            if not title or len(title) < 5:
                continue
            if "Welcome to Zoom Docs" in title:
                continue
            # Click to discover the URL
            try:
                link.click()
                time.sleep(2)
                url = driver.current_url
                if "/doc/" in url:
                    doc_id = url.split("/doc/")[-1].split("?")[0]
                    if doc_id not in seen_ids:
                        seen_ids.add(doc_id)
                        docs.append({
                            "title": title,
                            "url": url,
                            "doc_id": doc_id,
                        })
                        print(f"  [{len(docs)}] {title}")
                # Go back
                driver.get(ZOOM_DOCS_URL)
                time.sleep(3)
            except Exception as e:
                print(f"  WARN: Error with '{title[:40]}': {e}")
                driver.get(ZOOM_DOCS_URL)
                time.sleep(3)

        if len(docs) == last_count:
            stale_rounds += 1
            if stale_rounds >= 2:
                # Scroll down
                driver.execute_script("window.scrollBy(0, 400)")
                time.sleep(1)
                stale_rounds = 0
                # Check if we've scrolled past everything
                page_text = driver.find_element(By.TAG_NAME, "body").text
                if "Welcome to Zoom Docs" in page_text:
                    break
        else:
            stale_rounds = 0
            last_count = len(docs)

    return docs


def extract_transcript(driver, doc_url):
    """Navigate to a doc and extract the transcript text."""
    driver.get(doc_url)
    time.sleep(DOC_LOAD_WAIT)

    try:
        WebDriverWait(driver, 10).until(
            lambda d: len(d.find_element(By.TAG_NAME, "body").text) > 200
        )
    except TimeoutException:
        pass

    body_text = driver.find_element(By.TAG_NAME, "body").text
    title = driver.title

    # Find transcript start
    patterns = [
        "Speaker 1\n", "Stephen Morrell\n", "Unknown\n",
        "S1\n", "Sally\n", "motorola razr",
    ]
    start_idx = -1
    for p in patterns:
        idx = body_text.find(p)
        if idx > 0 and (start_idx == -1 or idx < start_idx):
            start_idx = idx

    # Find transcript end
    end_markers = ["Start typing or generate", "Generate summary"]
    end_idx = len(body_text)
    for marker in end_markers:
        idx = body_text.find(marker)
        if 0 < idx < end_idx:
            end_idx = idx

    if start_idx == -1:
        return title, ""

    return title, body_text[start_idx:end_idx].strip()


# ---------------------------------------------------------------------------
# File naming and formatting
# ---------------------------------------------------------------------------
def parse_datetime_from_title(title):
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})", title)
    if match:
        y, m, d, h, mi = match.groups()
        return f"{y}{m}{d}", f"{h}{mi}"
    return None, None


def make_filename(title, doc_id):
    date_str, time_str = parse_datetime_from_title(title)
    if date_str and time_str:
        clean = title
        clean = re.sub(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\(GMT[^)]*\)", "", clean)
        clean = re.sub(r"^\[My note\]\s*", "", clean)
        clean = re.sub(r"Stephen Morrell's\s*", "", clean)
        clean = clean.strip().rstrip(".")
        clean = re.sub(r"[^\w\s-]", "", clean)
        clean = re.sub(r"\s+", "-", clean.strip())
        if not clean:
            clean = "Zoom-Notes"
        return f"{date_str}-{time_str}-Zoom-{clean}.md"
    else:
        short_hash = hashlib.md5(doc_id.encode()).hexdigest()[:6]
        clean = re.sub(r"^\[My note\]\s*", "", title)
        clean = re.sub(r"Stephen Morrell's\s*", "", clean)
        clean = re.sub(r"[^\w\s-]", "", clean).strip()
        clean = re.sub(r"\s+", "-", clean)
        if not clean:
            clean = "Zoom-Notes"
        return f"undated-{short_hash}-Zoom-{clean}.md"


def format_transcript_md(title, transcript):
    date_str, time_str = parse_datetime_from_title(title)
    header = f"# {title}\n\n"
    if date_str:
        header += f"**Date:** {date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        if time_str:
            header += f" {time_str[:2]}:{time_str[2:]}"
        header += "\n"
    header += "\n---\n\n## Transcript\n\n"
    return header + transcript


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Download Zoom meeting notes")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--all", action="store_true",
                        help="Re-download all notes")
    parser.add_argument("--dry-run", action="store_true",
                        help="List notes without downloading")
    parser.add_argument("--visible", action="store_true",
                        help="Show browser window")
    parser.add_argument("--profile", default=None,
                        help="Chrome profile name (auto-detected if omitted)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    state = load_state()
    if args.all:
        state["downloaded"] = {}

    # Step 1: Extract cookies from Chrome
    profile = args.profile
    if not profile:
        print("Auto-detecting Chrome profile with Zoom cookies...")
        profile = find_chrome_profile_with_zoom()
        if not profile:
            print("ERROR: No Chrome profile found with Zoom cookies.")
            print("       Log into docs.zoom.us in Chrome first.")
            sys.exit(1)
    print(f"Using Chrome profile: {profile}")

    print("Extracting cookies from Chrome...")
    cookies = extract_zoom_cookies(profile)
    zoom_cookies = [c for c in cookies if "zoom" in c["domain"]]
    print(f"  Found {len(zoom_cookies)} Zoom cookies")

    # Step 2: Launch headless browser and inject cookies
    print("Starting browser...")
    try:
        driver = create_driver(headless=not args.visible)
    except WebDriverException as e:
        print(f"ERROR: Could not start Chrome: {e}")
        sys.exit(1)

    try:
        print("Injecting cookies...")
        inject_cookies(driver, cookies)

        # Step 3: Discover all docs
        print("\nDiscovering notes from docs.zoom.us/recent ...")
        docs = discover_docs(driver)
        print(f"\nDiscovered {len(docs)} notes total")

        if args.dry_run:
            print("\n--- DRY RUN ---")
            for doc in docs:
                s = "DONE" if doc["doc_id"] in state["downloaded"] else "NEW"
                print(f"  [{s}] {doc['title']}")
            return

        # Step 4: Download each new doc
        new_count = 0
        skip_count = 0

        for i, doc in enumerate(docs, 1):
            if doc["doc_id"] in state["downloaded"]:
                skip_count += 1
                continue

            print(f"\n[{i}/{len(docs)}] {doc['title']}")

            title, transcript = extract_transcript(driver, doc["url"])

            if not transcript:
                print(f"  SKIP: Empty transcript")
                state["downloaded"][doc["doc_id"]] = {
                    "title": doc["title"],
                    "downloaded_at": datetime.now().isoformat(),
                    "empty": True,
                }
                save_state(state)
                continue

            filename = make_filename(doc["title"], doc["doc_id"])
            filepath = output_dir / filename

            if filepath.exists():
                filepath = output_dir / f"{filepath.stem}-{doc['doc_id'][:6]}.md"

            content = format_transcript_md(title, transcript)
            filepath.write_text(content, encoding="utf-8")
            print(f"  Saved: {filepath.name} ({len(transcript)} chars)")
            new_count += 1

            state["downloaded"][doc["doc_id"]] = {
                "title": doc["title"],
                "filename": filename,
                "downloaded_at": datetime.now().isoformat(),
                "size": len(transcript),
            }
            save_state(state)

        print(f"\n--- Summary ---")
        print(f"  New: {new_count}  Skipped: {skip_count}")

    finally:
        driver.quit()
        print("Done.")


if __name__ == "__main__":
    main()
