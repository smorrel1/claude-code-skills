#!/usr/bin/env python3
"""Local listener that takes the email-review decisions straight to Claude.

Stephen, 12 Nov 2026: he had to copy the review page's output and paste it into
the Chief of staff session by hand. The page is a local file, so it cannot run
cmux itself; it POSTs here instead, and this hands the text to cmux's
send_task.py, which submits it and confirms it landed in that session's
transcript.

    POST http://127.0.0.1:8765/send   {"token", "workspace", "text"}
    GET  http://127.0.0.1:8765/ping

Only 127.0.0.1 is bound, and every send must carry the token written to
state/paste-back-token, which only pages made by email_review.py contain. So a
web page elsewhere cannot push text into a Claude session.

Runs under launchd (com.smorrell.email-review-paste-back).
"""
import json
import secrets
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SKILL = Path(__file__).resolve().parent
TOKEN_FILE = SKILL / "state" / "paste-back-token"
SPOOL = SKILL / "state" / "paste-back"
SEND_TASK = Path.home() / ".claude/skills/cmux/scripts/send_task.py"
PORT = 8765
MAX_BYTES = 200_000


def token():
    """The shared secret, created on first use."""
    if not TOKEN_FILE.exists():
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(secrets.token_urlsafe(24))
        TOKEN_FILE.chmod(0o600)
    return TOKEN_FILE.read_text().strip()


def deliver(workspace, text):
    """Spool the decisions to a file and send a one-line pointer via send_task."""
    SPOOL.mkdir(parents=True, exist_ok=True)
    f = SPOOL / ("%s-decisions.md" % time.strftime("%Y%m%d-%H%M%S"))
    f.write_text("Email review decisions from Stephen (sent from the review page). "
                 "Act on each one; drafts only, never send.\n\n" + text + "\n")
    p = subprocess.run([sys.executable, str(SEND_TASK), "--workspace", workspace,
                        "--file", str(f), "--slug", "email-review-decisions",
                        # The target is the session that made the page, chosen on
                        # purpose, so the comms-vs-tooling routing guard is skipped.
                        "--force"],
                       capture_output=True, text=True, timeout=180)
    return p.returncode, (p.stdout + p.stderr).strip()[-600:]


class H(BaseHTTPRequestHandler):
    def _reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        # The page is opened from file://, whose origin is "null".
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._reply(204, {})

    def do_GET(self):
        if self.path == "/ping":
            return self._reply(200, {"ok": True})
        self._reply(404, {"ok": False})

    def do_POST(self):
        if self.path != "/send":
            return self._reply(404, {"ok": False, "error": "unknown path"})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BYTES:
            return self._reply(400, {"ok": False, "error": "bad length"})
        try:
            body = json.loads(self.rfile.read(n))
        except ValueError:
            return self._reply(400, {"ok": False, "error": "bad json"})
        if not secrets.compare_digest(str(body.get("token", "")), token()):
            return self._reply(403, {"ok": False, "error": "bad token"})
        ws, text = str(body.get("workspace", "")).strip(), str(body.get("text", "")).strip()
        if not ws or not text:
            return self._reply(400, {"ok": False, "error": "workspace and text needed"})
        rc, log = deliver(ws, text)
        self._reply(200 if rc == 0 else 502,
                    {"ok": rc == 0, "rc": rc, "workspace": ws, "log": log})

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))


if __name__ == "__main__":
    token()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
