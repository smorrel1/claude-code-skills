#!/bin/bash
# Cron wrapper for zoom_notes_downloader.py.
# Resolves the script directory so the wrapper works wherever the skill lives.
# Optional: drop a .env file next to this script to set ZOOM_OUTPUT_DIR,
# ZOOM_OWNER_NAME, or any other env var the downloader honours.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/cron_log.txt"

echo "=== Job started at $(date) ===" >> "$LOG_FILE"

# Optional env file (key=value lines, no quoting required by this loader).
# Sourcing instead of `export $(...)` so values with spaces work.
if [ -f "${SCRIPT_DIR}/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "${SCRIPT_DIR}/.env"
    set +a
fi

# Prefer an explicit interpreter via $PYTHON_BIN, then a project venv, then python3 on PATH.
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ] && [ -x "${SCRIPT_DIR}/../venv/bin/python" ]; then
    PYTHON_BIN="${SCRIPT_DIR}/../venv/bin/python"
fi
if [ -z "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(command -v python3 || true)"
fi
if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: no Python interpreter found. Set PYTHON_BIN in .env." >> "$LOG_FILE"
    exit 1
fi

"$PYTHON_BIN" "${SCRIPT_DIR}/zoom_notes_downloader.py" "$@" >> "$LOG_FILE" 2>&1
status=$?

echo "=== Job ended at $(date) with status ${status} ===" >> "$LOG_FILE"
exit "$status"
