"""
Monthly Report Configuration Template

Copy this file to config.py and customize paths for your environment.
config.py is in .gitignore and will not be committed.
"""

from pathlib import Path

# === BASE DIRECTORIES ===
# Primary Dropbox/cloud storage directory for your documents
DROPBOX_DIR = Path.home() / "Dropbox"

# Working directory for monthly report generation
WORKINGS_BASE = DROPBOX_DIR / "InvestorComms/MonthlyReport/workings"

# Where to export Apple Notes (used by apple-notes skill)
APPLE_NOTES_EXPORT = DROPBOX_DIR / "AppleNotesExport"

# === MINUTES/AGENDAS DIRECTORIES ===
# Add paths to directories containing meeting minutes, agendas, notes
# These will be scanned for .rtf, .md, .txt files
MINUTES_DIRS = [
    DROPBOX_DIR / "agendas-minutes",
    # Add more directories as needed:
    # Path.home() / "Documents/MeetingNotes",
    # Path.home() / "Library/CloudStorage/GoogleDrive/Shared drives/TeamDrive/minutes",
]

# === FIREFLIES TRANSCRIPTS ===
# Directory where Fireflies transcripts are downloaded
FIREFLIES_DIR = DROPBOX_DIR / "fireflies-transcripts"

# === OUTPUT DIRECTORIES ===
# Where final monthly reports are saved
MONTHLY_UPDATES_DIR = DROPBOX_DIR / "investor-comms/monthly-updates"
