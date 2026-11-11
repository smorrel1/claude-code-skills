#!/usr/bin/env python3
"""Zoom-native live transcript producer for the meeting-coach skill.

Reads the live meeting transcript that Zoom Workplace's "My notes"
(Zoom Docs) panel persists into its WebKit IndexedDB SQLite store, and
appends coach-compatible JSONL lines:

    {"wall_ts": "...", "meeting_ts": "mm:ss", "speaker": "...", "text": "..."}

Requirements at meeting time:
  - Stephen starts a Zoom note with Transcript on (the "My notes" panel
    shown during the meeting). The notes window must stay open (minimised
    is fine) - it is the process that writes the transcript locally.
  - No bot joins the call; nothing extra is visible to other participants.

How it works:
  - Zoom's notes webview stores each utterance as a record in the
    'notes:transcript:v1' object store of the IndexedDB database named
    'ZoomDocs:app:<userId>' under
    ~/Library/Application Support/zoom.us/data/UnifyWebView_Cache/WebKit/
    UnSigned/Default/MyNotes/Origins/*/*/IndexedDB/*/IndexedDB.sqlite3
  - Records are WebKit SerializedScriptValue blobs. We extract the string
    fields we need (messageId, message, timeStampContent, username) with a
    minimal reader for the string encoding (uint32le length, high bit set
    means 8-bit/Latin-1, else UTF-16LE; 0x10 = string tag).
  - Records are deleted from the local store when the meeting/note ends,
    so we poll while live and treat an emptied store as meeting end.

Usage:
    zoom_notes_live.py -o ~/live-transcript.jsonl [--interval 2] [--verbose]
"""

import argparse
import datetime as dt
import glob
import json
import os
import re
import sqlite3
import threading
import subprocess
import struct
import sys
import time

DB_GLOB = os.path.expanduser(
    "~/Library/Application Support/zoom.us/data/UnifyWebView_Cache/WebKit/"
    "UnSigned/Default/MyNotes/Origins/*/*/IndexedDB/*/IndexedDB.sqlite3"
)
STORE_NAME = "notes:transcript:v1"
FIELDS = ("messageId", "message", "timeStampContent", "username")


def log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", file=sys.stderr, flush=True)


def find_db():
    """Return path of the ZoomDocs:app:* IndexedDB, newest first."""
    candidates = []
    for db in glob.glob(DB_GLOB):
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
            row = con.execute(
                "SELECT value FROM IDBDatabaseInfo WHERE key='DatabaseName'"
            ).fetchone()
            con.close()
            if row and str(row[0]).startswith("ZoomDocs:app:"):
                wal = db + "-wal"
                mtime = max(
                    os.path.getmtime(p) for p in (db, wal) if os.path.exists(p)
                )
                candidates.append((mtime, db))
        except Exception:
            continue
    if not candidates:
        return None
    return max(candidates)[1]


def read_str(buf, pos):
    """Read a WebKit-serialized string at pos (after the 0x10 tag).
    Returns (string, next_pos) or None."""
    if pos + 4 > len(buf):
        return None
    (raw,) = struct.unpack_from("<I", buf, pos)
    length = raw & 0x7FFFFFFF
    if length > 100_000:
        return None
    pos += 4
    if raw & 0x80000000:  # 8-bit (Latin-1)
        if pos + length > len(buf):
            return None
        return buf[pos : pos + length].decode("latin-1"), pos + length
    else:  # UTF-16LE
        if pos + length * 2 > len(buf):
            return None
        return (
            buf[pos : pos + length * 2].decode("utf-16-le", "replace"),
            pos + length * 2,
        )


def field_pattern(name):
    nb = name.encode("latin-1")
    return struct.pack("<I", len(nb) | 0x80000000) + nb + b"\x10"


PATTERNS = {f: field_pattern(f) for f in FIELDS}


def parse_record(blob):
    """Extract known fields from a serialized transcript record."""
    out = {}
    for field, pat in PATTERNS.items():
        idx = blob.find(pat)
        if idx < 0:
            continue
        got = read_str(blob, idx + len(pat))
        if got:
            out[field] = got[0]
    return out


def wall_ts_from_content(hms):
    """'12:14:22' (local wall clock) -> ISO timestamp today."""
    try:
        t = dt.datetime.strptime(hms, "%H:%M:%S").time()
        return dt.datetime.combine(dt.date.today(), t).isoformat(timespec="seconds")
    except (ValueError, TypeError):
        return dt.datetime.now().isoformat(timespec="seconds")


def hms_to_secs(hms):
    try:
        h, m, s = (int(x) for x in hms.split(":"))
        return h * 3600 + m * 60 + s
    except Exception:
        return None


class Emitter:
    """Dedupe + finalize logic. Zoom rewrites a line in place while ASR
    refines it, so emit a message only once it is stable for one extra
    poll or a newer message has appeared after it."""

    def __init__(self, out_path):
        self.out_path = out_path
        self.emitted = {}  # messageId -> text already written out
        self.pending = {}  # messageId -> (text, speaker, tsc, stable_count)
        self.t0 = None  # meeting start (secs since midnight)

    def observe(self, records):
        # records: list of dicts with FIELDS, in DB order
        ids_in_order = [r["messageId"] for r in records if r.get("messageId")]
        latest = ids_in_order[-1] if ids_in_order else None
        for r in records:
            mid = r.get("messageId")
            text = (r.get("message") or "").strip()
            if not mid or not text:
                continue
            # Zoom keeps appending to a record while the same person keeps
            # talking, so an already-emitted messageId can grow; re-queue it
            # and emit the added text later.
            if mid in self.emitted and text == self.emitted[mid]:
                continue
            prev = self.pending.get(mid)
            stable = prev[3] + 1 if prev and prev[0] == text else 0
            self.pending[mid] = (
                text,
                r.get("username") or "Unknown",
                r.get("timeStampContent"),
                stable,
            )
        # finalize: stable for >=1 extra poll, or not the newest message
        for mid in list(self.pending):
            text, speaker, tsc, stable = self.pending[mid]
            if stable >= 1 or (latest is not None and mid != latest):
                self.emit(mid, text, speaker, tsc)
                del self.pending[mid]

    def flush_all(self):
        for mid, (text, speaker, tsc, _) in list(self.pending.items()):
            self.emit(mid, text, speaker, tsc)
        self.pending.clear()

    def emit(self, mid, text, speaker, tsc):
        prev = self.emitted.get(mid)
        out_text = text
        if prev:
            if text.startswith(prev):
                out_text = text[len(prev):].strip()
                if not out_text:
                    self.emitted[mid] = text
                    return
            # non-append rewrite (ASR correction): emit full new text
        secs = hms_to_secs(tsc) if tsc else None
        if secs is not None and self.t0 is None:
            self.t0 = secs
        if secs is not None and self.t0 is not None:
            rel = max(0, secs - self.t0)
            meeting_ts = f"{rel // 60:02d}:{rel % 60:02d}"
        else:
            meeting_ts = "00:00"
        line = {
            "wall_ts": wall_ts_from_content(tsc) if tsc else
                dt.datetime.now().isoformat(timespec="seconds"),
            "meeting_ts": meeting_ts,
            "speaker": speaker,
            "text": out_text,
        }
        with open(self.out_path, "a") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        self.emitted[mid] = text


def audio_devices():
    """(input, output) default device names, or (None, None).

    Zoom's notes transcribe one input device. On 11 Nov 2026 the transcript
    stopped at 10:19:29 while the meeting ran to 10:31, and the best guess was
    an audio switch (AirPods connecting, or an output change). Without the
    device in the log, that guess could not be tested.
    """
    try:
        out = subprocess.run(["system_profiler", "SPAudioDataType", "-json"],
                             capture_output=True, text=True, timeout=10).stdout
        items = json.loads(out)["SPAudioDataType"][0]["_items"]
    except Exception:
        return None, None
    inp = next((d["_name"] for d in items
                if d.get("coreaudio_default_audio_input_device") == "spaudio_yes"), None)
    outp = next((d["_name"] for d in items
                 if d.get("coreaudio_default_audio_output_device") == "spaudio_yes"), None)
    return inp, outp


def front_app():
    """The frontmost app. The other hypothesis for 11 Nov was Zoom's notes
    webview pausing behind a full-screen Teams window."""
    try:
        out = subprocess.run(["lsappinfo", "info", "-only", "name",
                              subprocess.run(["lsappinfo", "front"], capture_output=True,
                                             text=True, timeout=5).stdout.strip()],
                             capture_output=True, text=True, timeout=5).stdout
        return out.split("=", 1)[-1].strip().strip('"') or None
    except Exception:
        return None


class Watchdog(threading.Thread):
    """Every 60s: log audio devices and front app when they CHANGE, and the
    transcript record count while a meeting is live, so the log shows the
    minute Zoom stopped adding lines and what changed around it."""

    def __init__(self):
        super().__init__(daemon=True)
        self.records = None      # set by the main loop
        self.live = False
        self.last = (None, None, None)
        self.last_count = None

    def run(self):
        while True:
            inp, outp = audio_devices()
            app = front_app()
            if (inp, outp) != self.last[:2] and inp:
                log(f"audio: input={inp} output={outp}")
            if app and app != self.last[2]:
                log(f"front app: {app}")
            self.last = (inp or self.last[0], outp or self.last[1], app or self.last[2])
            if self.live and self.records is not None:
                if self.records == self.last_count:
                    log(f"no new transcript records in 60s ({self.records} total)")
                self.last_count = self.records
            time.sleep(60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    emitter = Emitter(args.output)
    db_path = None
    store_id = None
    con = None
    seen_any = False
    log("zoom_notes_live starting; waiting for a Zoom note transcript...")
    dog = Watchdog()
    dog.start()

    while True:
        try:
            if con is None:
                db_path = find_db()
                if not db_path:
                    time.sleep(args.interval)
                    continue
                con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
                row = con.execute(
                    "SELECT id FROM ObjectStoreInfo WHERE name=?", (STORE_NAME,)
                ).fetchone()
                if not row:
                    con.close()
                    con = None
                    time.sleep(args.interval)
                    continue
                store_id = row[0]
                log(f"reading {db_path} (store {store_id})")

            rows = con.execute(
                "SELECT rowid, value FROM Records WHERE objectStoreID=? ORDER BY rowid",
                (store_id,),
            ).fetchall()
            records = [parse_record(v) for _, v in rows if v]
            records = [r for r in records if r.get("messageId")]

            if records:
                if not seen_any:
                    log(f"transcript live: {len(records)} record(s)")
                seen_any = True
                dog.live, dog.records = True, len(records)
                emitter.observe(records)
                if args.verbose:
                    log(f"{len(records)} records, {len(emitter.emitted)} emitted")
            elif seen_any:
                # store cleared -> meeting/note ended
                emitter.flush_all()
                log("transcript store cleared (meeting ended); still watching")
                seen_any = False
                dog.live, dog.records, dog.last_count = False, None, None
                emitter.t0 = None

        except sqlite3.Error as e:
            log(f"sqlite error ({e}); reconnecting")
            try:
                con.close()
            except Exception:
                pass
            con = None
        except KeyboardInterrupt:
            emitter.flush_all()
            log("stopped")
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
