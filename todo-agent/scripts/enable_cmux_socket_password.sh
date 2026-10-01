#!/bin/bash
# One-off, run by Stephen: let the launchd todo-agent talk to cmux again.
#
# cmux 0.64.23 ships with Socket Control Mode "cmux processes only". The todo-agent
# runs from launchd, outside cmux, so every @claude hand-off since the update was
# refused ("Access denied - only processes started inside cmux can connect").
#
# This switches the mode to "password": processes started inside cmux still connect
# as before, and anything outside must present the password. The password is random,
# kept in two 0600 files (cmux.json and the todo-agent state file), never printed.
# cmux.json is backed up first; if cmux stops answering afterwards the backup is
# restored automatically.
set -euo pipefail

CMUX=/Applications/cmux.app/Contents/Resources/bin/cmux
CONF="$HOME/.config/cmux/cmux.json"
PWF="$HOME/.claude/skills/todo-agent/state/cmux-socket-password"
BAK="$CONF.$(date +%Y%m%d-%H%M%S).bak"

umask 077
cp "$CONF" "$BAK"
[ -s "$PWF" ] || python3 -c "import secrets; print(secrets.token_urlsafe(32))" > "$PWF"
chmod 600 "$PWF" "$CONF"

python3 - "$CONF" "$(cat "$PWF")" <<'EOF'
import json, re, sys
path, pw = sys.argv[1], sys.argv[2]
raw = open(path).read()

# cmux rewrites this file itself when a setting changes in its UI, and its
# serializer drops the inline socketPassword (the password lives in its own
# store) and strips every comment. Seen twice on 24 Sep 2026, at 02:35 and
# 12:39, each time leaving password mode enabled with no password, which locks
# out every caller from outside cmux. So parse whatever shape the file is in
# now rather than splicing text into the commented template.
try:
    conf = json.loads(re.sub(r'^\s*//.*$', '', raw, flags=re.M))
except ValueError as e:
    sys.exit("cmux.json is not readable as JSON (%s). Fix it by hand." % e)

auto = conf.setdefault("automation", {})
auto["socketControlMode"] = "password"
auto["socketPassword"] = pw
open(path, "w").write(json.dumps(conf, indent=2) + "\n")
print("  mode=password, password set from the todo-agent's copy")
EOF
echo "cmux.json updated (backup: $BAK). Reloading cmux config..."
"$CMUX" reload-config >/dev/null 2>&1 || true
sleep 5

inside=$("$CMUX" ping 2>&1 || true)
outside=$(env -u CMUX_SOCKET_PASSWORD CMUX_SOCKET_PASSWORD="$(cat "$PWF")" "$CMUX" ping 2>&1 || true)
echo "  this terminal, no password : $inside"
echo "  with the job's password     : $outside"
if [ "$inside" != "PONG" ]; then
  cp "$BAK" "$CONF"
  echo "cmux stopped answering from inside cmux. Restored the backup; nothing changed."
  exit 1
fi

# The only verification that counts: launchd is genuinely outside cmux, so it
# exercises the path that has been failing. A ping from this terminal proves
# nothing, since a cmux pane is admitted by ancestry whatever the mode.
LOG="$HOME/.claude/skills/todo-agent/logs/todo-agent.log"
BEFORE=$(wc -l < "$LOG")
launchctl kickstart -k "gui/$(id -u)/com.stephen.todo-agent"
sleep 25
echo
echo "New todo-agent log lines (from launchd, outside cmux):"
tail -n +$((BEFORE + 1)) "$LOG" | tail -8
echo
echo "Success looks like no 'Access denied' above. If it still says so, open"
echo "cmux Settings > Automation > Socket Control Mode and pick Password there;"
echo "run.sh already sends the password."
