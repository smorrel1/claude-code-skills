"""
RTF File Consolidation Utility

This module consolidates RTF files with datestamps from specified directories.
It filters files by modification date and size, and combines them into consolidated text files.
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent))

from text_cleaner import detect_and_clean_content

# === LOAD CONFIG ===
try:
    from config import MINUTES_DIRS
except ImportError:
    MINUTES_DIRS = []

def extract_datestamp_from_filename(filename):
    """
    Extract datestamp from filename in YYYYMMDD format

    Args:
        filename (str): The filename to parse

    Returns:
        datetime or None: Parsed date if found, None otherwise
    """
    # Look for YYYYMMDD pattern at the start of filename
    date_match = re.search(r'^(\d{8})', filename)
    if date_match:
        try:
            return datetime.strptime(date_match.group(1), '%Y%m%d')
        except ValueError:
            pass

    # Look for YYMMDD pattern at the start
    date_match = re.search(r'^(\d{6})', filename)
    if date_match:
        try:
            # Assume 20XX for years
            year_prefix = "20"
            full_date_str = year_prefix + date_match.group(1)
            return datetime.strptime(full_date_str, '%Y%m%d')
        except ValueError:
            pass

    return None

def consolidate_rtf_files(directory_path, start_date, output_path, output_filename, max_file_size_kb=25):
    """
    Consolidate RTF files from a directory based on datestamp and size criteria

    Args:
        directory_path (str): Path to search for RTF files
        start_date (datetime): Start date filter
        output_path (str): Output directory
        output_filename (str): Output filename
        max_file_size_kb (int): Maximum file size in KB to include

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        directory = Path(directory_path)
        if not directory.exists():
            print(f"Directory not found: {directory_path}")
            return False

        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file_path = output_dir / output_filename

        # Find RTF files with datestamps
        rtf_files = []
        excluded_files = []

        print(f"Searching for RTF files in {directory_path}")

        # Search recursively for RTF files
        for rtf_file in directory.rglob('*.rtf'):
            # Skip if it's a hidden file or in hidden directory
            if any(part.startswith('.') for part in rtf_file.parts):
                continue

            # Extract datestamp from filename
            file_date = extract_datestamp_from_filename(rtf_file.name)

            if file_date and file_date >= start_date:
                # Check file size
                file_size_kb = rtf_file.stat().st_size / 1024

                if file_size_kb > max_file_size_kb:
                    excluded_files.append((rtf_file, file_size_kb))
                    print(f"⏭️  Skipping {rtf_file.name} ({file_size_kb:.1f}KB > {max_file_size_kb}KB limit)")
                else:
                    rtf_files.append((rtf_file, file_date, file_size_kb))

        # Sort by date
        rtf_files.sort(key=lambda x: x[1])

        if not rtf_files:
            print("No RTF files with datestamps found after start date")
            return True

        print(f"Found {len(rtf_files)} RTF files to consolidate")
        if excluded_files:
            print(f"Excluded {len(excluded_files)} files due to size limit")

        # Consolidate files
        consolidated_content = []

        for rtf_file, file_date, file_size_kb in rtf_files:
            try:
                print(f"Processing {rtf_file.name} ({file_size_kb:.1f}KB, {file_date.strftime('%Y-%m-%d')})")

                with open(rtf_file, 'r', encoding='utf-8') as f:
                    raw_content = f.read()

                # Clean the content to remove RTF/XML tags
                cleaned_content = detect_and_clean_content(raw_content)

                if not cleaned_content.strip():
                    print(f"⚠️  Warning: {rtf_file.name} produced no readable content after cleaning")
                    continue

                # Create header
                header = f"File: {rtf_file.name}"
                header += f"\nDate: {file_date.strftime('%Y-%m-%d')}"
                header += f"\nSize: {file_size_kb:.1f}KB"
                header += f"\nPath: {rtf_file.relative_to(directory)}"

                # Add to consolidated content
                consolidated_content.extend([
                    header,
                    cleaned_content,
                    '-' * 80  # Separator
                ])

            except Exception as e:
                print(f"Error reading {rtf_file.name}: {str(e)}")
                continue

        # Write consolidated file
        if consolidated_content:
            try:
                with open(output_file_path, 'w', encoding='utf-8', errors='replace') as f:
                    f.write('\n\n'.join(consolidated_content))
                print(f"✅ Successfully consolidated {len(rtf_files)} RTF files into: {output_file_path}")
                return True
            except Exception as e:
                print(f"Error writing consolidated file: {str(e)}")
                # Try with different encoding as fallback
                try:
                    with open(output_file_path, 'w', encoding='utf-8', errors='ignore') as f:
                        f.write('\n\n'.join(consolidated_content))
                    print(f"✅ Successfully consolidated files with encoding cleanup into: {output_file_path}")
                    return True
                except Exception as e2:
                    print(f"Failed to write consolidated file even with fallback: {str(e2)}")
                    return False
        else:
            print("No RTF content was successfully processed")
            return False

    except Exception as e:
        print(f"Error consolidating RTF files: {str(e)}")
        return False

def consolidate_minutes_files(start_date, output_path):
    """
    Consolidate RTF minutes files from directories specified in config.py

    Configure directories via config.py MINUTES_DIRS list.

    Args:
        start_date (datetime): Start date for filtering
        output_path (str): Output directory path

    Returns:
        bool: True if successful, False otherwise
    """
    date_str = start_date.strftime("%Y-%m-%d")
    all_success = True

    if not MINUTES_DIRS:
        print("\n⚠️  No MINUTES_DIRS configured in config.py")
        print("   Copy config.example.py to config.py and add your directories.")
        return False

    for i, directory in enumerate(MINUTES_DIRS):
        dir_path = Path(directory)
        if not dir_path.exists():
            print(f"\n⚠️  Directory not found: {dir_path}")
            continue

        dir_name = dir_path.name
        output_filename = f"consolidated_minutes_{i+1}_{dir_name}_{date_str}.txt"

        print(f"\n📄 Consolidating RTF files from {dir_name}...")
        success = consolidate_rtf_files(
            directory_path=str(dir_path),
            start_date=start_date,
            output_path=output_path,
            output_filename=output_filename
        )
        if not success:
            all_success = False

    return all_success

if __name__ == "__main__":
    # Test the consolidation
    from datetime import datetime
    from pathlib import Path

    try:
        from config import WORKINGS_BASE
        test_output_path = str(WORKINGS_BASE / "test_context")
    except ImportError:
        test_output_path = str(Path.home() / "Desktop/test_context")

    test_start_date = datetime(2025, 7, 2)
    Path(test_output_path).mkdir(parents=True, exist_ok=True)
    consolidate_minutes_files(test_start_date, test_output_path)