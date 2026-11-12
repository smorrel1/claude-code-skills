---
name: whatsapp
description: Access Stephen's WhatsApp from the native macOS app's local store. Reads are read-only from ChatStorage.sqlite (live while WhatsApp desktop is running and linked): search messages, pull a thread with a contact or group, list media, recent-activity digest, answer "what did X say about Y on WhatsApp". Can also send a single 1:1 message via the WhatsApp URL scheme, but only with explicit per-message confirmation (prepares and stops unless --yes). Also callable as /wa.
---

# whatsapp

Reads the native macOS WhatsApp app's local message DB (unencrypted SQLite,
protected by the Mac account), which syncs in near real time, so it is current
to the minute whenever the desktop app is running and linked. Reads copy the
`.sqlite` + `-wal`/`-shm` sidecars to a temp snapshot and query the copy, so the
live file is never touched and the last unflushed messages are included.

Source: `~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite`
Chat media: `.../group.net.whatsapp.WhatsApp.shared/Message/Media/<jid>/...`

## Commands

```bash
WA=~/.claude/skills/whatsapp/scripts/wa_utils.py
python3 $WA chats  [--query NAME] [--limit N]
python3 $WA thread --chat NAME|JID|ALIAS [--days N | --since YYYY-MM-DD | --limit N] [--md] [--media]
python3 $WA search --query TEXT [--days N] [--chat NAME] [--limit N]
python3 $WA digest [--days N]
python3 $WA media  --chat NAME|JID|ALIAS [--days N] [--limit N] [--open]
python3 $WA send   --to NAME|ALIAS|+E164 --text "..." [--yes]
```

Times are Europe/London. `thread --md` emits markdown; `thread --media` and the
`media` command resolve each attachment to its absolute file path.

## Sending (handle with care)

- There is no WhatsApp API for a personal number. `send` uses the
  `whatsapp://send?phone=...&text=...` URL scheme to open the 1:1 chat with the
  message pre-filled. By DEFAULT it stops there for review and does not send.
- Only `--yes` presses Return (via System Events; needs Accessibility
  permission). Treat every real send as an outbound message requiring Stephen's
  explicit go-ahead on that specific text and recipient. Never bulk send.
- Groups cannot be sent to this way; sending is 1:1 only. A phone number (in the
  alias or as +E164) is required.

## Aliases

Nicknames live in `whatsapp/aliases.json` (personal, gitignored). Each value is a
chat-name string, or an object `{"chat": "...", "phone": "+44..."}` (phone needed
to send). See `aliases.example.json`.

## Limits

- Needs the Mac logged in with WhatsApp desktop installed and linked.
- Media is stored as files on disk; the tool gives the path (and whether it is
  downloaded), not the content inline.
- Disappearing messages leave the DB when they expire.
- Private personal data: surface only what the task needs, as with the email skill.
