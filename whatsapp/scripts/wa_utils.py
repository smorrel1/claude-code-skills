#!/usr/bin/env python3
"""
Access to the native macOS WhatsApp app's local message store.

Reading is from an unencrypted SQLite DB that syncs live while the WhatsApp
desktop app is running and linked to the phone:
  ~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite
Reads copy the .sqlite + -wal/-shm sidecars to a temp snapshot and query the
copy, so the live file is never touched and the newest messages are included.

Sending uses the WhatsApp URL scheme to open a 1:1 chat with the text
pre-filled. By default it STOPS there for you to review and press Return.
Pass --yes to also send (one message, explicit). There is no bulk send.

Commands:
  chats   [--query NAME] [--limit N]
  thread  --chat NAME|JID|ALIAS [--days N | --since YYYY-MM-DD | --limit N] [--md] [--media]
  search  --query TEXT [--days N] [--chat NAME] [--limit N]
  digest  [--days N]
  media   --chat NAME|JID|ALIAS [--days N] [--limit N] [--open]
  send    --to NAME|ALIAS|+E164 --text "..." [--yes]

Aliases: optional nickname map in whatsapp/aliases.json (gitignored, personal).
All times are Europe/London.
"""
import argparse, json, os, shutil, sqlite3, subprocess, sys, tempfile, time, datetime, urllib.parse
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/London")
except Exception:
    TZ = None

SHARED = os.path.expanduser(
    "~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared")
DB = os.path.join(SHARED, "ChatStorage.sqlite")
MEDIA_BASE = os.path.join(SHARED, "Message")  # ZMEDIALOCALPATH like "Media/<jid>/..." lives under Message/
HERE = os.path.dirname(os.path.abspath(__file__))
ALIAS_FILE = os.path.join(os.path.dirname(HERE), "aliases.json")
APPLE_EPOCH = datetime.datetime(2001, 1, 1)
SESSION_TYPE = {0: "1:1", 1: "group", 3: "status/broadcast"}


# ---------- aliases (personal, gitignored) ----------
def load_aliases():
    """nickname -> {"chat": str, "phone": str}. Values may be a bare string
    (treated as chat name) or an object with chat/phone keys."""
    out = {}
    if os.path.exists(ALIAS_FILE):
        try:
            raw = json.load(open(ALIAS_FILE))
            for k, v in raw.items():
                out[k.lower()] = ({"chat": v} if isinstance(v, str) else v)
        except Exception as e:
            print(f"(warning: could not read aliases.json: {e})", file=sys.stderr)
    return out


ALIASES = load_aliases()


def alias_lookup(name):
    return ALIASES.get((name or "").lower())


# ---------- db snapshot ----------
def connect():
    if not os.path.exists(DB):
        sys.exit("WhatsApp DB not found. Is the macOS WhatsApp app installed and "
                 "opened at least once?")
    d = tempfile.mkdtemp(prefix="wa_")
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(DB + suffix):
            shutil.copy2(DB + suffix, os.path.join(d, "ChatStorage.sqlite" + suffix))
    con = sqlite3.connect(os.path.join(d, "ChatStorage.sqlite"))
    con.row_factory = sqlite3.Row
    return con, d


def apple_to_local(ts):
    if ts is None:
        return None
    dt = (APPLE_EPOCH + datetime.timedelta(seconds=ts)).replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(TZ) if TZ else dt


def cutoff_apple(days=None, since=None):
    dt = None
    if days is not None:
        dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    elif since:
        dt = datetime.datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    if dt is None:
        return None
    return (dt - APPLE_EPOCH.replace(tzinfo=datetime.timezone.utc)).total_seconds()


def fmt(dt, with_date=True):
    return dt.strftime("%Y-%m-%d %H:%M" if with_date else "%H:%M") if dt else "?"


# ---------- lookups ----------
def find_chats(con, query=None, limit=25):
    sql = ("SELECT Z_PK, ZPARTNERNAME, ZCONTACTJID, ZSESSIONTYPE, "
           "ZLASTMESSAGEDATE, ZLASTMESSAGETEXT FROM ZWACHATSESSION ")
    args = []
    if query:
        sql += "WHERE ZPARTNERNAME LIKE ? OR ZCONTACTJID LIKE ? "
        args += [f"%{query}%", f"%{query}%"]
    sql += "ORDER BY ZLASTMESSAGEDATE DESC LIMIT ?"
    args.append(limit)
    return con.execute(sql, args).fetchall()


def resolve_chat(con, chat):
    al = alias_lookup(chat)
    if al and al.get("chat"):
        chat = al["chat"]
    rows = find_chats(con, query=chat, limit=50)
    if not rows:
        sys.exit(f"No chat matching '{chat}'.")
    exact = [r for r in rows if (r["ZPARTNERNAME"] or "").lower() == chat.lower()]
    return exact[0] if exact else rows[0]


def resolve_phone(con, to):
    """Return an E.164-ish digit string for a 1:1 recipient."""
    al = alias_lookup(to)
    if al and al.get("phone"):
        return al["phone"]
    if to.lstrip("+").isdigit():
        return to
    chat = al["chat"] if (al and al.get("chat")) else to
    row = resolve_chat(con, chat)
    jid = row["ZCONTACTJID"] or ""
    if jid.endswith("@s.whatsapp.net"):
        return "+" + jid.split("@")[0]
    sys.exit(f"Cannot resolve a phone number for '{to}'. Add it to aliases.json "
             f"as {{\"{to}\": {{\"chat\": \"...\", \"phone\": \"+44...\"}}}} "
             f"(group chats cannot be sent to by URL).")


def sender_name(con, row, chat_row):
    if row["ZISFROMME"]:
        return "Me"
    gm = row["ZGROUPMEMBER"]
    if gm:
        m = con.execute("SELECT ZCONTACTNAME, ZFIRSTNAME, ZMEMBERJID FROM "
                        "ZWAGROUPMEMBER WHERE Z_PK=?", (gm,)).fetchone()
        if m:
            return (m["ZCONTACTNAME"] or m["ZFIRSTNAME"] or row["ZPUSHNAME"]
                    or (m["ZMEMBERJID"] or "").split("@")[0])
    return (chat_row["ZPARTNERNAME"] or row["ZPUSHNAME"]
            or (chat_row["ZCONTACTJID"] or "").split("@")[0])


def media_for(con, pk):
    return con.execute("SELECT ZTITLE, ZMEDIALOCALPATH FROM ZWAMEDIAITEM "
                       "WHERE Z_PK=?", (pk,)).fetchone()


def media_abspath(localpath):
    return os.path.join(MEDIA_BASE, localpath) if localpath else None


def body(con, row, show_media_path=False):
    if row["ZTEXT"]:
        return row["ZTEXT"]
    if row["ZMEDIAITEM"]:
        m = media_for(con, row["ZMEDIAITEM"])
        if m:
            label = m["ZTITLE"] or os.path.basename(m["ZMEDIALOCALPATH"] or "") or "file"
            ap = media_abspath(m["ZMEDIALOCALPATH"])
            if show_media_path and ap:
                exists = "" if os.path.exists(ap) else " (not downloaded)"
                return f"[media: {label}] {ap}{exists}"
            return f"[media: {label}]"
        return "[media]"
    return "[group event]" if row["ZGROUPEVENTTYPE"] else "[no text]"


# ---------- commands ----------
def cmd_chats(con, a):
    print(f"{'#':>3}  {'last':16}  {'type':16}  chat")
    for i, r in enumerate(find_chats(con, a.query, a.limit), 1):
        t = SESSION_TYPE.get(r["ZSESSIONTYPE"], str(r["ZSESSIONTYPE"]))
        print(f"{i:>3}  {fmt(apple_to_local(r['ZLASTMESSAGEDATE'])):16}  {t:16}  "
              f"{r['ZPARTNERNAME'] or r['ZCONTACTJID']}")


def thread_rows(con, chat_pk, days=None, since=None, limit=None):
    sql = "SELECT * FROM ZWAMESSAGE WHERE ZCHATSESSION=? "
    args = [chat_pk]
    co = cutoff_apple(days, since)
    if co is not None:
        sql += "AND ZMESSAGEDATE >= ? "; args.append(co)
    if limit:
        sql += "ORDER BY ZMESSAGEDATE DESC LIMIT ?"; args.append(limit)
        return list(reversed(con.execute(sql, args).fetchall()))
    sql += "ORDER BY ZMESSAGEDATE ASC"
    return con.execute(sql, args).fetchall()


def cmd_thread(con, a):
    chat = resolve_chat(con, a.chat)
    rows = thread_rows(con, chat["Z_PK"], a.days, a.since, a.limit)
    name = chat["ZPARTNERNAME"] or chat["ZCONTACTJID"]
    header = f"WhatsApp thread with {name} ({len(rows)} messages)"
    print((f"# {header}\n") if a.md else (header + "\n"))
    last = None
    for r in rows:
        dt = apple_to_local(r["ZMESSAGEDATE"])
        day = dt.strftime("%A %d %b %Y") if dt else "?"
        if day != last:
            print(("## " + day) if a.md else (f"--- {day} ---")); last = day
        print(f"{fmt(dt, False)}  {sender_name(con, r, chat)}: "
              f"{body(con, r, a.media).replace(chr(10), ' ')}")


def cmd_search(con, a):
    sql = ("SELECT m.*, s.ZPARTNERNAME chatname, s.ZCONTACTJID chatjid "
           "FROM ZWAMESSAGE m JOIN ZWACHATSESSION s ON m.ZCHATSESSION=s.Z_PK "
           "WHERE m.ZTEXT LIKE ? ")
    args = [f"%{a.query}%"]
    if a.chat:
        sql += "AND (s.ZPARTNERNAME LIKE ? OR s.ZCONTACTJID LIKE ?) "
        args += [f"%{a.chat}%", f"%{a.chat}%"]
    co = cutoff_apple(a.days)
    if co is not None:
        sql += "AND m.ZMESSAGEDATE >= ? "; args.append(co)
    sql += "ORDER BY m.ZMESSAGEDATE DESC LIMIT ?"; args.append(a.limit)
    for r in con.execute(sql, args).fetchall():
        who = "Me" if r["ZISFROMME"] else (r["chatname"] or r["ZPUSHNAME"] or "?")
        print(f"[{fmt(apple_to_local(r['ZMESSAGEDATE']))}] "
              f"{r['chatname'] or r['chatjid']} | {who}: {(r['ZTEXT'] or '')[:100]}")


def cmd_digest(con, a):
    co = cutoff_apple(a.days)
    rows = con.execute(
        "SELECT s.ZPARTNERNAME nm, s.ZCONTACTJID jid, COUNT(*) n, "
        "MAX(m.ZMESSAGEDATE) last FROM ZWAMESSAGE m "
        "JOIN ZWACHATSESSION s ON m.ZCHATSESSION=s.Z_PK "
        "WHERE m.ZMESSAGEDATE>=? GROUP BY m.ZCHATSESSION ORDER BY n DESC LIMIT 40",
        (co,)).fetchall()
    print(f"Activity in the last {a.days} day(s): {len(rows)} active chats")
    print(f"{'#':>3}  {'msgs':>5}  {'last':16}  chat")
    for i, r in enumerate(rows, 1):
        print(f"{i:>3}  {r['n']:>5}  {fmt(apple_to_local(r['last'])):16}  "
              f"{r['nm'] or r['jid']}")


def cmd_media(con, a):
    chat = resolve_chat(con, a.chat)
    rows = thread_rows(con, chat["Z_PK"], a.days, None, a.limit)
    n = 0
    for r in rows:
        if not r["ZMEDIAITEM"]:
            continue
        m = media_for(con, r["ZMEDIAITEM"])
        if not (m and m["ZMEDIALOCALPATH"]):
            continue
        ap = media_abspath(m["ZMEDIALOCALPATH"]); n += 1
        tag = "" if os.path.exists(ap) else "  (not downloaded)"
        print(f"{fmt(apple_to_local(r['ZMESSAGEDATE']))}  "
              f"{sender_name(con, r, chat)}: {ap}{tag}")
        if a.open and os.path.exists(ap):
            subprocess.run(["open", ap])
    if n == 0:
        print("No downloaded media in that window.")


def cmd_send(con, a):
    phone = resolve_phone(con, a.to)
    url = "whatsapp://send?phone=" + urllib.parse.quote(phone.lstrip("+")) \
          + "&text=" + urllib.parse.quote(a.text)
    subprocess.run(["open", url])
    print(f"Opened WhatsApp chat with {phone}, message pre-filled:")
    print(f"  {a.text}")
    if not a.yes:
        print("\nNOT SENT. Review it in WhatsApp and press Return to send, "
              "or re-run with --yes to send automatically.")
        return
    time.sleep(2.0)  # let the compose box focus
    script = ('tell application "WhatsApp" to activate\n'
              'delay 0.6\n'
              'tell application "System Events" to key code 36')  # Return
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode == 0:
        print("Sent.")
    else:
        print("Could not auto-press Return (grant Terminal/Claude Accessibility "
              "permission, or just press Return yourself). Detail: "
              + r.stderr.strip())


def main():
    p = argparse.ArgumentParser(description="macOS WhatsApp history reader and 1:1 sender")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("chats"); s.add_argument("--query"); s.add_argument("--limit", type=int, default=25)
    s = sub.add_parser("thread")
    s.add_argument("--chat", required=True); s.add_argument("--days", type=int)
    s.add_argument("--since"); s.add_argument("--limit", type=int)
    s.add_argument("--md", action="store_true"); s.add_argument("--media", action="store_true")
    s = sub.add_parser("search")
    s.add_argument("--query", required=True); s.add_argument("--days", type=int)
    s.add_argument("--chat"); s.add_argument("--limit", type=int, default=50)
    s = sub.add_parser("digest"); s.add_argument("--days", type=int, default=3)
    s = sub.add_parser("media")
    s.add_argument("--chat", required=True); s.add_argument("--days", type=int)
    s.add_argument("--limit", type=int, default=50); s.add_argument("--open", action="store_true")
    s = sub.add_parser("send")
    s.add_argument("--to", required=True); s.add_argument("--text", required=True)
    s.add_argument("--yes", action="store_true")
    a = p.parse_args()
    con, tmp = connect()
    try:
        {"chats": cmd_chats, "thread": cmd_thread, "search": cmd_search,
         "digest": cmd_digest, "media": cmd_media, "send": cmd_send}[a.cmd](con, a)
    finally:
        con.close(); shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
