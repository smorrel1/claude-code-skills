#!/usr/bin/env python3
"""
Monthly Report Generation Automation Script

This script automates the entire monthly report generation process:
1. Exports Apple Notes using AppleScript
2. Downloads Gmail data
3. Finds all edited files (.rtf, .rtfd, .docx, .md, .text) since last report
4. Consolidates all data sources
5. Prepares context for report generation

Usage:
    python generate_monthly_report.py [start_date]

    start_date: Optional, format YYYY-MM-DD. If not provided, uses last report date.
"""

import os
import sys
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import shutil

# Add script and parent directory to path for local imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import existing modules
from EmailsDownload import main as download_emails
from consolidate_files import run_consolidation

# === LOAD CONFIG ===
# Try to import from config.py, fall back to defaults if not found
try:
    from config import (
        WORKINGS_BASE,
        APPLE_NOTES_EXPORT,
        MINUTES_DIRS,
        MONTHLY_UPDATES_DIR,
    )
except ImportError:
    print("WARNING: config.py not found. Copy config.example.py to config.py and customize.")
    print("Using default paths which may not exist on your system.\n")
    WORKINGS_BASE = Path.home() / "Dropbox/MonthlyReport/workings"
    APPLE_NOTES_EXPORT = Path.home() / "Desktop/AppleNotesExport"
    MINUTES_DIRS = []
    MONTHLY_UPDATES_DIR = Path.home() / "Dropbox/monthly-updates"

def run_apple_notes_export(output_dir):
    """
    Export Apple Notes using the apple-notes skill

    Args:
        output_dir: Directory to export notes to

    Returns:
        bool: True if successful, False otherwise
    """
    print("\n📝 Exporting Apple Notes using apple-notes skill...")

    # Path to the export script in the apple-notes skill
    export_script = Path.home() / ".claude/skills/apple-notes/scripts/export_notes.py"

    if not export_script.exists():
        print(f"⚠️  Warning: apple-notes skill not found at {export_script}")
        print("   Please install the apple-notes skill first.")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(export_script), "--output", str(APPLE_NOTES_EXPORT)],
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        print(f"✅ Apple Notes exported to {APPLE_NOTES_EXPORT}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Apple Notes export failed: {e}")
        if e.stdout:
            print(e.stdout)
        if e.stderr:
            print(e.stderr)
        return False
    except Exception as e:
        print(f"⚠️  Error running Apple Notes export: {e}")
        return False


def find_edited_files_since_date(directories, start_date, file_extensions):
    """
    Find all files with specified extensions edited since start_date

    Args:
        directories: List of directories to search
        start_date: datetime object for start date
        file_extensions: List of file extensions to search for (e.g., ['.rtf', '.md'])

    Returns:
        List of tuples: (file_path, modification_time)
    """
    print(f"\n🔍 Finding edited files since {start_date.strftime('%Y-%m-%d')}...")

    edited_files = []

    for directory in directories:
        dir_path = Path(directory)
        if not dir_path.exists():
            print(f"   ⚠️  Directory not found: {directory}")
            continue

        print(f"   Searching: {directory}")

        for file_path in dir_path.rglob('*'):
            # Skip hidden files and directories
            if any(part.startswith('.') for part in file_path.parts):
                continue

            if not file_path.is_file():
                continue

            # Check if file extension matches
            if file_path.suffix.lower() not in file_extensions:
                continue

            # Check modification time
            try:
                mod_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mod_time > start_date:
                    edited_files.append((file_path, mod_time))
            except Exception as e:
                print(f"   ⚠️  Error checking {file_path}: {e}")

    # Sort by modification time
    edited_files.sort(key=lambda x: x[1])

    print(f"   Found {len(edited_files)} edited files")

    return edited_files


def consolidate_edited_files(edited_files, output_path, start_date):
    """
    Consolidate edited files into a single text file

    Args:
        edited_files: List of (file_path, mod_time) tuples
        output_path: Path to output directory
        start_date: Start date for filename
    """
    if not edited_files:
        print("   No edited files to consolidate")
        return

    date_str = start_date.strftime("%Y-%m-%d")
    output_file = Path(output_path) / f"consolidated_edited_files_{date_str}.txt"

    print(f"\n📦 Consolidating {len(edited_files)} edited files...")

    consolidated_content = []

    for file_path, mod_time in edited_files:
        try:
            # Read file content based on type
            if file_path.suffix.lower() == '.docx':
                # Skip .docx for now - would need python-docx or similar
                print(f"   ⏭️  Skipping .docx (needs conversion): {file_path.name}")
                continue
            elif file_path.suffix.lower() == '.rtfd':
                # .rtfd is a package, skip for now
                print(f"   ⏭️  Skipping .rtfd package: {file_path.name}")
                continue
            else:
                # Plain text file
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                except Exception as e:
                    print(f"   ⚠️  Error reading {file_path.name}: {e}")
                    continue

            # Format header
            header = f"File: {file_path.name}"
            header += f"\nPath: {file_path}"
            header += f"\nModified: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}"
            header += f"\nType: {file_path.suffix}"

            consolidated_content.extend([
                header,
                content,
                '-' * 80
            ])

            print(f"   ✓ {file_path.name}")

        except Exception as e:
            print(f"   ⚠️  Error processing {file_path}: {e}")

    # Write consolidated file
    if consolidated_content:
        try:
            with open(output_file, 'w', encoding='utf-8', errors='replace') as f:
                f.write('\n\n'.join(consolidated_content))
            print(f"✅ Consolidated edited files saved to: {output_file}")
        except Exception as e:
            print(f"❌ Error writing consolidated file: {e}")


def determine_last_report_date():
    """
    Determine the date of the last monthly report

    Returns:
        datetime: Date of last report, or None if not found
    """
    # Look in the most recent context folder
    context_dirs = sorted(WORKINGS_BASE.glob("context_*"), reverse=True)
    context_dir = context_dirs[0] if context_dirs else WORKINGS_BASE

    # Look for monthly report files
    monthly_files = list(context_dir.glob("*monthly*.md"))
    monthly_files.extend(context_dir.glob("202*-monthly*.md"))

    if not monthly_files:
        print("⚠️  No previous monthly reports found in context/")
        return None

    # Get the most recent one
    monthly_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    latest_report = monthly_files[0]

    # Try to extract date from filename
    import re
    date_match = re.search(r'(\d{8})', latest_report.name)
    if date_match:
        try:
            date = datetime.strptime(date_match.group(1), '%Y%m%d')
            print(f"📅 Last monthly report found: {latest_report.name}")
            print(f"   Date: {date.strftime('%Y-%m-%d')}")
            return date
        except ValueError:
            pass

    # Fallback: use file modification time
    mod_time = datetime.fromtimestamp(latest_report.stat().st_mtime)
    print(f"📅 Last monthly report found: {latest_report.name}")
    print(f"   Using modification date: {mod_time.strftime('%Y-%m-%d')}")
    return mod_time


def stash_old_context_files(context_dir):
    """
    Archive old consolidated files and gmail exports by adding run timestamp
    to prevent them from being included in the edited files search

    Args:
        context_dir: Path to context directory
    """
    print("\n🗄️  Stashing old context files...")

    context_path = Path(context_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stashed_count = 0

    # Patterns for files to stash
    stash_patterns = [
        'consolidated_*.txt',
        'gmail_export*.md',
        'BATCH_SUMMARIES*.md',
        '*-data-consolidation-summary.md',
    ]

    for pattern in stash_patterns:
        for file_path in context_path.glob(pattern):
            # Don't stash files that are already stashed (contain timestamp in name)
            if '_archive_' in file_path.name or '_stashed_' in file_path.name:
                continue

            # Create new filename with archive timestamp
            new_name = file_path.stem + f"_archive_{timestamp}" + file_path.suffix
            new_path = file_path.parent / new_name

            try:
                file_path.rename(new_path)
                print(f"   ✓ Stashed: {file_path.name} → {new_name}")
                stashed_count += 1
            except Exception as e:
                print(f"   ⚠️  Could not stash {file_path.name}: {e}")

    if stashed_count > 0:
        print(f"✅ Stashed {stashed_count} old context files")
    else:
        print("   No old context files to stash")


def main(start_date_str=None):
    """
    Main function to run the monthly report generation process

    Args:
        start_date_str: Optional start date string in format YYYY-MM-DD
    """
    print("=" * 80)
    print("MONTHLY REPORT GENERATION - AUTOMATION SCRIPT")
    print("=" * 80)

    # Determine start date
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            print(f"\n📅 Using provided start date: {start_date.strftime('%Y-%m-%d')}")
        except ValueError:
            print(f"❌ Invalid date format: {start_date_str}")
            print("   Expected format: YYYY-MM-DD")
            return
    else:
        # Try to determine from last report
        last_report_date = determine_last_report_date()
        if last_report_date:
            start_date = last_report_date
        else:
            # Default to 60 days ago
            start_date = datetime.now() - timedelta(days=60)
            print(f"\n📅 No previous report found, using default: {start_date.strftime('%Y-%m-%d')}")

    # Create context directory for this run
    date_str = start_date.strftime("%Y%m%d")
    output_dir = WORKINGS_BASE / f"context_{date_str}"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summaries").mkdir(exist_ok=True)
    (output_dir / "additional_notes").mkdir(exist_ok=True)
    output_dir_str = str(output_dir)

    # Step 0: Check for existing context and handle
    print("\n" + "=" * 80)
    print("STEP 0: Context Setup")
    print("=" * 80)
    existing_files = list(output_dir.glob("consolidated_*.txt"))
    if existing_files:
        print(f"⚠️  Context folder already has {len(existing_files)} consolidated files")
        stash_old_context_files(output_dir_str)
    else:
        print(f"📁 Created context folder: {output_dir.name}")

    # Step 1: Export Apple Notes
    print("\n" + "=" * 80)
    print("STEP 1: Export Apple Notes")
    print("=" * 80)

    # Check if notes are already exported and how fresh they are
    notes_exist = APPLE_NOTES_EXPORT.exists() and list(APPLE_NOTES_EXPORT.glob('**/*.md'))

    if notes_exist:
        # Check age of export
        newest_note = max(APPLE_NOTES_EXPORT.glob('**/*.md'), key=lambda p: p.stat().st_mtime)
        export_age_hours = (datetime.now() - datetime.fromtimestamp(newest_note.stat().st_mtime)).total_seconds() / 3600

        if export_age_hours < 24:
            print(f"✅ Apple Notes exported recently ({export_age_hours:.1f} hours ago)")
            print(f"   Location: {APPLE_NOTES_EXPORT}")
        else:
            print(f"⚠️  Apple Notes export is {export_age_hours:.0f} hours old, refreshing...")
            run_apple_notes_export(output_dir_str)
    else:
        print("📝 No Apple Notes export found, running export...")
        run_apple_notes_export(output_dir_str)

    # Step 2: Download Gmail data
    print("\n" + "=" * 80)
    print("STEP 2: Download Gmail Data")
    print("=" * 80)
    try:
        download_emails(start_date=start_date)
    except Exception as e:
        print(f"⚠️  Warning: Email download failed: {e}")
        print("   Continuing with other steps...")

    # Step 3: Find edited files in key directories
    print("\n" + "=" * 80)
    print("STEP 3: Find Edited Files")
    print("=" * 80)

    # Build search directories from config
    search_directories = [str(d) for d in MINUTES_DIRS if d.exists()]
    search_directories.append(str(output_dir))
    if APPLE_NOTES_EXPORT.exists():
        search_directories.append(str(APPLE_NOTES_EXPORT))

    file_extensions = ['.rtf', '.rtfd', '.docx', '.md', '.txt', '.text']

    edited_files = find_edited_files_since_date(
        search_directories,
        start_date,
        file_extensions
    )

    # Step 4: Consolidate edited files
    print("\n" + "=" * 80)
    print("STEP 4: Consolidate Edited Files")
    print("=" * 80)
    consolidate_edited_files(edited_files, output_dir_str, start_date)

    # Step 5: Run existing consolidation process
    print("\n" + "=" * 80)
    print("STEP 5: Run Standard Consolidation")
    print("=" * 80)
    try:
        run_consolidation(start_date=start_date, skip_stash=True)
    except Exception as e:
        print(f"❌ Error in consolidation: {e}")
        print("   You may need to run consolidate_files.py manually")

    # Step 6: Convert monthly report to DOCX if it exists
    print("\n" + "=" * 80)
    print("STEP 6: Convert Monthly Report to DOCX")
    print("=" * 80)

    monthly_updates_dir = str(MONTHLY_UPDATES_DIR)

    # Look for the monthly report markdown file
    date_str = datetime.now().strftime("%Y%m%d")
    monthly_report_md = Path(monthly_updates_dir) / f"{date_str}-monthly-report-DRAFT.md"

    if monthly_report_md.exists():
        print(f"📄 Found monthly report: {monthly_report_md.name}")
        monthly_report_docx = monthly_report_md.with_suffix('.docx')

        try:
            # Use pandoc to convert markdown to docx
            subprocess.run([
                'pandoc',
                str(monthly_report_md),
                '-o',
                str(monthly_report_docx)
            ], check=True, capture_output=True)

            print(f"✅ Converted to DOCX: {monthly_report_docx.name}")

        except subprocess.CalledProcessError as e:
            print(f"⚠️  Pandoc conversion failed: {e}")
            print("   You may need to install pandoc: brew install pandoc")
        except FileNotFoundError:
            print("⚠️  Pandoc not found - cannot convert to DOCX")
            print("   Install pandoc: brew install pandoc")
    else:
        print(f"ℹ️  No monthly report found at: {monthly_report_md}")
        print("   Expected filename format: YYYYMMDD-monthly-report-DRAFT.md")
        print("   Skipping DOCX conversion...")

    # Summary
    print("\n" + "=" * 80)
    print("✅ MONTHLY REPORT DATA COLLECTION COMPLETE")
    print("=" * 80)
    print(f"\nPeriod covered: {start_date.strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')}")
    print(f"\nConsolidated files saved to: {output_dir}")
    print("\nNext steps:")
    print("1. Review consolidated files in context/")
    print("2. Generate monthly report using the consolidated data")
    print("3. Monthly report will be auto-converted to DOCX if found in investor-comms/monthly-updates/")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()
