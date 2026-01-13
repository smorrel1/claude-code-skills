"""
File Consolidation Utility

This code consolidates text files based on their modification date.
It scans a directory for files modified after a start date and combines their
contents into a single text file, preserving file information and adding separators
between individual file contents.

The module contains:
- A main function `consolidate_files` that handles the consolidation process
- Error handling for file reading and directory scanning issues

The consolidated output file includes headers with the original filename and
modification timestamp, followed by the complete file content, and a horizontal
line separator between files.

Input: most text files incl .rtf

ISSUE: some files bulk up the output unnecessarily.  Add a filter for large files, or better yet remove graphics or whatever the cause is.
"""
import os
import sys
from datetime import datetime, timedelta
import pathlib

# Add script and parent directory to path for local imports
sys.path.insert(0, str(pathlib.Path(__file__).parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from rtf_consolidator import consolidate_minutes_files
from text_cleaner import detect_and_clean_content

# === LOAD CONFIG ===
try:
    from config import (
        WORKINGS_BASE,
        APPLE_NOTES_EXPORT,
        MINUTES_DIRS,
        FIREFLIES_DIR,
    )
    CONFIG_LOADED = True
except ImportError:
    CONFIG_LOADED = False
    WORKINGS_BASE = pathlib.Path.home() / "Dropbox/MonthlyReport/workings"
    APPLE_NOTES_EXPORT = pathlib.Path.home() / "Desktop/AppleNotesExport"
    MINUTES_DIRS = []
    FIREFLIES_DIR = None

def consolidate_files(folder_path, start_date, output_path, output_filename='consolidated_files.txt'):
    """
    Consolidate files modified after the start date into a single file.
    
    Args:
        folder_path (str): Path to the folder containing files
        start_date (datetime): Date to compare file modifications against
        output_filename (str): Name of the output consolidated file
    """
    try:
        # Convert folder path to Path object
        folder = pathlib.Path(folder_path)
        output_path =  pathlib.Path(output_path) / output_filename
        
        # Store consolidated content
        consolidated_content = []
        
        # Iterate through all files in the directory
        for file_path in folder.glob('**/*'):
            if file_path.is_file():
                # Skip binary and non-text files
                skip_extensions = {'.html', '.docx', '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mov', '.mp3', '.zip', '.DS_Store'}
                if file_path.suffix.lower() in skip_extensions or file_path.name == '.DS_Store':
                    continue
                    
                # Get file modification time
                mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                # Check if file was modified after start date
                if mod_time > start_date:
                    try:
                        # Read file content
                        with open(file_path, 'r', encoding='utf-8') as file:
                            raw_content = file.read()

                        # Clean the content to remove formatting tags
                        cleaned_content = detect_and_clean_content(raw_content)

                        if not cleaned_content.strip():
                            # Don't skip the file entirely - include with warning
                            print(f"⚠️  Warning: {file_path.name} produced no readable content after cleaning - including raw content")
                            cleaned_content = raw_content[:500] + "..." if len(raw_content) > 500 else raw_content

                        # Format header with file name and modification date
                        header = f"File: {file_path.name}\nModified: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}"

                        # Add to consolidated content with separator
                        consolidated_content.extend([
                            header,
                            cleaned_content,
                            '-' * 50  # Separator
                        ])
                    except Exception as e:
                        print(f"Error reading file {file_path}: {str(e)}")
        
        # Write consolidated content to output file
        if consolidated_content:
            try:
                with open(output_path, 'w', encoding='utf-8', errors='replace') as output_file:
                    output_file.write('\n\n'.join(consolidated_content))
                print(f"Successfully consolidated files into: {output_path}")
            except Exception as e:
                print(f"Error writing consolidated file: {str(e)}")
                # Try with different encoding as fallback
                try:
                    with open(output_path, 'w', encoding='utf-8', errors='ignore') as output_file:
                        output_file.write('\n\n'.join(consolidated_content))
                    print(f"Successfully consolidated files with encoding cleanup into: {output_path}")
                except Exception as e2:
                    print(f"Failed to write consolidated file even with fallback: {str(e2)}")
        else:
            print("No files found modified after the start date.")
            
    except Exception as e:
        print(f"Error processing files: {str(e)}")

def stash_old_context_files(context_dir):
    """
    Archive old consolidated files and gmail exports by adding run timestamp
    to prevent them from being included in the edited files search

    Args:
        context_dir: Path to context directory
    """
    print("\n🗄️  Stashing old context files...")

    context_path = pathlib.Path(context_dir)
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


def run_consolidation(start_date=None, skip_stash=False):
    """
    Run all consolidation tasks with the given start date.

    Paths are loaded from config.py. Copy config.example.py to config.py to customize.

    Args:
        start_date: datetime object, or None to use default
        skip_stash: bool, if True skip stashing old files (useful when called from generate_monthly_report.py)
    """
    if not CONFIG_LOADED:
        print("WARNING: config.py not found. Copy config.example.py to config.py and customize.")
        print("Using default paths which may not exist on your system.\n")

    if start_date is None:
        # Default to 2 months ago if no date provided
        start_date = datetime.now() - timedelta(days=60)
        print(f"No start date provided, using default: {start_date.strftime('%Y-%m-%d')}")
    else:
        print(f"Using provided start date: {start_date.strftime('%Y-%m-%d')}")

    date_str = start_date.strftime("%Y%m%d")
    context_name = f"context_{date_str}"
    output_path = WORKINGS_BASE / context_name

    # Check for existing context and handle gracefully
    if output_path.exists():
        existing_files = list(output_path.glob("consolidated_*.txt"))
        if existing_files and not skip_stash:
            print(f"⚠️  Context folder {context_name} already exists with {len(existing_files)} consolidated files")
            print(f"   Stashing old files before re-running...")
            stash_old_context_files(str(output_path))
        else:
            print(f"ℹ️  Using existing context folder: {context_name}")
    else:
        print(f"📁 Creating new context folder: {context_name}")

    # Ensure output directory and subdirs exist
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "summaries").mkdir(exist_ok=True)
    (output_path / "additional_notes").mkdir(exist_ok=True)

    output_path_str = str(output_path) + "/"

    # Notes - check AppleNotesExport first (from apple-notes skill)
    notes_found = False
    if APPLE_NOTES_EXPORT.exists():
        print(f"Consolidating notes from AppleNotesExport: {APPLE_NOTES_EXPORT}")
        consolidate_files(str(APPLE_NOTES_EXPORT), start_date, output_path_str, output_filename=f"consolidated_notes_{date_str}.txt")
        notes_found = True

    if not notes_found:
        print("⚠️  No AppleNotesExport found. Run the apple-notes skill first, or notes will be skipped.")
        print("   python3 ~/.claude/skills/apple-notes/scripts/export_notes.py --output " + str(APPLE_NOTES_EXPORT))

    # Fireflies transcripts
    if FIREFLIES_DIR and pathlib.Path(FIREFLIES_DIR).exists():
        print(f"Consolidating fireflies from {FIREFLIES_DIR}")
        consolidate_files(str(FIREFLIES_DIR), start_date, output_path_str, output_filename=f"consolidated_fireflies_{date_str}.txt")
    else:
        print("⚠️  FIREFLIES_DIR not configured or not found. Skipping fireflies consolidation.")

    # Consolidate each configured MINUTES_DIR
    for i, dir_path in enumerate(MINUTES_DIRS):
        if pathlib.Path(dir_path).exists():
            dir_name = pathlib.Path(dir_path).name
            print(f"Consolidating from {dir_name}")
            consolidate_files(str(dir_path), start_date, output_path_str, output_filename=f"consolidated_dir_{i+1}_{dir_name}_{date_str}.txt")
        else:
            print(f"⚠️  Directory not found: {dir_path}")

    # RTF minutes consolidation (uses MINUTES_DIRS from config)
    print(f"\n📄 Consolidating RTF minutes files...")
    consolidate_minutes_files(start_date, output_path_str)

    print(f"\n✅ All consolidation tasks completed!")
    print(f"   Period: {start_date.strftime('%Y-%m-%d')} onwards")
    print(f"   Output: {output_path}")

    return str(output_path)


def parse_date(date_str):
    """Parse date string in various formats."""
    formats = ["%Y-%m-%d", "%Y%m%d", "%d/%m/%Y", "%m/%d/%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {date_str}. Use YYYY-MM-DD format.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Consolidate files for monthly report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 consolidate_files.py --date 2025-11-11
  python3 consolidate_files.py --date 20251111
  python3 consolidate_files.py  # Uses default (60 days ago)
        """
    )
    parser.add_argument(
        "--date", "-d",
        help="Start date for consolidation (YYYY-MM-DD or YYYYMMDD)",
        default=None
    )
    parser.add_argument(
        "--no-stash",
        action="store_true",
        help="Don't stash existing files if re-running"
    )

    args = parser.parse_args()

    start_date = None
    if args.date:
        start_date = parse_date(args.date)

    run_consolidation(start_date, skip_stash=args.no_stash)
