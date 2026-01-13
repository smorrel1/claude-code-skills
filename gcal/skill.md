# Google Calendar Skill

CRUD operations for Google Calendar using OAuth credentials.

## Usage

```bash
python3 ~/.claude/skills/gcal/scripts/cal_utils.py <command> [options]
```

## Commands

| Command | Description |
|---------|-------------|
| `calendars` | List all calendars |
| `list` | List upcoming events |
| `get <event_id>` | Get event details |
| `create` | Create new event |
| `update <event_id>` | Update event |
| `delete <event_id>` | Delete event |
| `availability <date>` | Check availability for a date |

## Examples

```bash
# List calendars
python3 ~/.claude/skills/gcal/scripts/cal_utils.py calendars

# List events for next 7 days
python3 ~/.claude/skills/gcal/scripts/cal_utils.py list --days 7

# Search for events
python3 ~/.claude/skills/gcal/scripts/cal_utils.py list --query "JPM"

# Create an event
python3 ~/.claude/skills/gcal/scripts/cal_utils.py create \
  --summary "Coffee with Maggie" \
  --start "2026-01-13 10:00" \
  --duration 60 \
  --location "UCSF"

# Create all-day event
python3 ~/.claude/skills/gcal/scripts/cal_utils.py create \
  --summary "Conference Day" \
  --start "2026-01-15"

# Check availability
python3 ~/.claude/skills/gcal/scripts/cal_utils.py availability 2026-01-13

# Update event
python3 ~/.claude/skills/gcal/scripts/cal_utils.py update <event_id> \
  --summary "New Title" \
  --location "New Location"

# Delete event
python3 ~/.claude/skills/gcal/scripts/cal_utils.py delete <event_id>
```

## Notes

- Uses OAuth credentials from Gmail skill (`~/.claude/skills/gmail/credentials.json`)
- Calendar-specific token stored at `~/.claude/skills/gcal/token.json`
- First run will open browser for authorization
- Default timezone: America/Los_Angeles (PST)
