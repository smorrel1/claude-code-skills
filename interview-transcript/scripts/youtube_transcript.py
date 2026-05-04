#!/usr/bin/env python3
"""
Interview Transcript Downloader

Downloads subtitles/transcripts from YouTube videos and X.com (Twitter) videos/Spaces.
Converts to plain text, HTML, or EPUB.
Uses yt-dlp for reliable subtitle/media extraction.
EPUB output includes thumbnail as cover image for Kindle.
"""

import argparse
import subprocess
import tempfile
import os
import re
import sys
import json
import urllib.request
from pathlib import Path
from datetime import datetime

# Jinja2 for templates (used with Calibre ebook-convert)
try:
    from jinja2 import Environment, FileSystemLoader
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False

import shutil


def detect_source(url: str) -> str:
    """Detect whether URL is YouTube, X.com/Twitter, or unknown.
    Returns 'youtube', 'x', or 'unknown'.
    """
    if any(domain in url for domain in ['youtube.com', 'youtu.be', 'youtube-nocookie.com']):
        return 'youtube'
    if any(domain in url for domain in ['x.com', 'twitter.com']):
        return 'x'
    return 'unknown'


def download_x_transcript(url: str, output_path: str = None) -> str:
    """Download and transcribe X.com video/Space audio using yt-dlp + whisper.

    For X.com videos with captions, extracts subtitles directly.
    For X.com videos/Spaces without captions, downloads audio and transcribes with whisper.cpp.

    Returns path to transcript text file.
    """
    if output_path is None:
        output_path = './x_transcript.txt'

    # First try subtitle extraction (same as YouTube)
    tmpdir = tempfile.mkdtemp()
    output_template = os.path.join(tmpdir, '%(title)s.%(ext)s')

    # Try to get subtitles first
    sub_cmd = [
        'yt-dlp', '--skip-download', '--write-subs', '--write-auto-subs',
        '--sub-lang', 'en', '--sub-format', 'srt/vtt/best',
        '--convert-subs', 'srt', '-o', output_template, url
    ]

    print("Attempting subtitle extraction from X.com...", file=sys.stderr)
    result = subprocess.run(sub_cmd, capture_output=True, text=True)

    # Check if subtitles were downloaded
    srt_file = None
    for f in os.listdir(tmpdir):
        if f.endswith('.srt') or f.endswith('.vtt'):
            srt_file = os.path.join(tmpdir, f)
            break

    if srt_file:
        print("Found subtitles, extracting text...", file=sys.stderr)
        with open(srt_file, 'r', encoding='utf-8') as f:
            srt_content = f.read()
        entries = parse_srt(srt_content)
        text = srt_to_plain_text(entries)
    else:
        # No subtitles available, download audio and transcribe with whisper.cpp
        print("No subtitles found. Downloading audio for whisper transcription...", file=sys.stderr)
        audio_path = os.path.join(tmpdir, 'audio.wav')
        dl_cmd = [
            'yt-dlp', '-x', '--audio-format', 'wav',
            '-o', audio_path, url
        ]
        result = subprocess.run(dl_cmd, capture_output=True, text=True)

        # yt-dlp may name the file differently
        wav_files = [f for f in os.listdir(tmpdir) if f.endswith('.wav')]
        if not wav_files:
            # Check for other audio formats that got downloaded
            audio_files = [f for f in os.listdir(tmpdir) if f.endswith(('.m4a', '.mp3', '.ogg', '.opus', '.webm'))]
            if audio_files:
                src = os.path.join(tmpdir, audio_files[0])
                # Convert to wav with ffmpeg
                subprocess.run(['ffmpeg', '-i', src, '-ar', '16000', '-ac', '1', audio_path],
                             capture_output=True, text=True)
                wav_files = [f for f in os.listdir(tmpdir) if f.endswith('.wav')]

        if not wav_files:
            print("Error: Could not download audio from X.com URL.", file=sys.stderr)
            print(f"yt-dlp stderr: {result.stderr}", file=sys.stderr)
            return None

        actual_audio = os.path.join(tmpdir, wav_files[0])

        # Transcribe with whisper.cpp
        whisper_cmd = shutil.which('whisper-cpp') or shutil.which('whisper')
        if whisper_cmd is None:
            # Try the common homebrew path
            whisper_cmd = '/opt/homebrew/bin/whisper-cpp'
            if not os.path.exists(whisper_cmd):
                print("Error: whisper-cpp not found. Install with: brew install whisper-cpp", file=sys.stderr)
                print("Alternatively, manually transcribe the audio at:", actual_audio, file=sys.stderr)
                return None

        print("Transcribing with whisper.cpp...", file=sys.stderr)
        txt_output = os.path.join(tmpdir, 'transcript.txt')
        whisper_result = subprocess.run(
            [whisper_cmd, '-m', '/opt/homebrew/share/whisper-cpp/models/ggml-large-v3-turbo-q5_0.bin',
             '-f', actual_audio, '--output-txt', '-of', os.path.join(tmpdir, 'transcript')],
            capture_output=True, text=True, timeout=600
        )

        if whisper_result.returncode != 0:
            print(f"Whisper error: {whisper_result.stderr}", file=sys.stderr)
            return None

        if os.path.exists(txt_output):
            with open(txt_output, 'r', encoding='utf-8') as f:
                text = f.read()
        else:
            print(f"Error: Whisper output not found at {txt_output}", file=sys.stderr)
            return None

    # Get metadata
    info = get_video_info(url)
    title = info.get('title', 'X.com Video')
    uploader = info.get('uploader', info.get('uploader_id', 'Unknown'))

    # Add header
    header = f"# {title}\n\nSource: {url}\nAuthor: @{uploader}\nDownloaded: {datetime.now().strftime('%Y-%m-%d')}\n\n---\n\n"
    text = header + text

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(text)

    print(f"Transcript saved to: {output_path}", file=sys.stderr)
    shutil.rmtree(tmpdir, ignore_errors=True)
    return output_path


def get_video_info(url: str) -> dict:
    """Get video title and other metadata."""
    try:
        result = subprocess.run(
            ['yt-dlp', '--dump-json', '--skip-download', url],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        print(f"Warning: Could not fetch video info: {e}", file=sys.stderr)
    return {}


def list_subtitles(url: str) -> None:
    """List available subtitle tracks for a video."""
    print(f"Listing available subtitles for: {url}\n")
    result = subprocess.run(
        ['yt-dlp', '--list-subs', url],
        capture_output=True,
        text=True
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)


def download_subtitles(url: str, lang: str = 'en', auto_subs: bool = True, output_dir: str = None) -> str:
    """Download subtitles using yt-dlp and return the file path."""
    if output_dir is None:
        output_dir = tempfile.mkdtemp()

    output_template = os.path.join(output_dir, '%(title)s.%(ext)s')

    cmd = [
        'yt-dlp',
        '--skip-download',
        '--write-subs',
        '--sub-lang', lang,
        '--sub-format', 'srt/vtt/best',
        '--convert-subs', 'srt',
        '-o', output_template,
        url
    ]

    if auto_subs:
        cmd.insert(3, '--write-auto-subs')

    print(f"Downloading subtitles...", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        return None

    # Find the downloaded subtitle file
    for f in os.listdir(output_dir):
        if f.endswith('.srt') or f.endswith('.vtt'):
            return os.path.join(output_dir, f)

    print("Error: No subtitle file was downloaded.", file=sys.stderr)
    print("Try using --list-subs to see available languages.", file=sys.stderr)
    return None


def parse_srt(srt_content: str) -> list:
    """Parse SRT content and extract text with timestamps."""
    entries = []
    # Split by double newline (SRT block separator)
    blocks = re.split(r'\n\n+', srt_content.strip())

    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            # First line is index, second is timestamp, rest is text
            try:
                index = int(lines[0])
                timestamp = lines[1]
                text = ' '.join(lines[2:])
                # Clean HTML tags that may appear in auto-subs
                text = re.sub(r'<[^>]+>', '', text)
                if text.strip():
                    entries.append({
                        'index': index,
                        'timestamp': timestamp,
                        'text': text.strip()
                    })
            except (ValueError, IndexError):
                continue

    return entries


def srt_to_plain_text(entries: list) -> str:
    """Convert parsed SRT entries to plain text."""
    seen_lines = set()
    text_parts = []

    for entry in entries:
        text = entry['text']
        # Skip duplicates (common in auto-captions)
        if text.lower() not in seen_lines:
            seen_lines.add(text.lower())
            text_parts.append(text)

    # Join with spaces, then clean up
    full_text = ' '.join(text_parts)

    # Clean up common issues
    full_text = re.sub(r'\s+', ' ', full_text)  # Multiple spaces
    full_text = re.sub(r'\s([.,!?;:])', r'\1', full_text)  # Space before punctuation

    return full_text.strip()


def clean_transcript(text: str) -> str:
    """Clean transcript by removing filler words, duplicates, and formatting.

    This performs mechanical cleaning that doesn't require LLM intelligence:
    - Removes common filler words (um, uh, like, you know, etc.)
    - Removes auto-caption artifacts ([Music], [Applause], etc.)
    - Removes repeated/stuttered words
    - Cleans up punctuation and spacing
    - Adds paragraph breaks at sentence boundaries (~500 chars)

    Returns cleaned text ready for LLM section structuring.
    """
    # Preserve any existing markdown header
    header_match = re.match(r'^(#\s+[^\n]+\n+(?:Source:\s*[^\n]+\n)?(?:Downloaded:\s*[^\n]+\n)?(?:\s*-{3,}\s*\n)?)', text)
    header = header_match.group(1) if header_match else ''
    if header:
        text = text[len(header):]

    # Remove auto-caption artifacts
    text = re.sub(r'\[(?:Music|Applause|Laughter|Cheering|Inaudible|Background\s+noise)\]', '', text, flags=re.IGNORECASE)

    # Filler words/phrases to remove (with word boundaries)
    # Order matters - longer phrases first to avoid partial matches
    filler_patterns = [
        # Multi-word fillers (check these first)
        r'\byou know what I mean\b',
        r'\bif you will\b',
        r'\bso to speak\b',
        r'\bat the end of the day\b',
        r'\bto be honest\b',
        r'\bto be fair\b',
        r'\bI would say\b',
        r'\bI guess\b',
        r'\bI think\b',  # Often filler, but careful - sometimes meaningful
        r'\byou know\b',
        r'\bI mean\b',
        r'\bkind of\b',
        r'\bsort of\b',
        r'\bso yeah\b',
        r'\band yeah\b',
        r'\byeah so\b',
        r'\blike,\s*',  # "like," as filler (captures trailing space)
        r',\s*like,\s*',  # ", like," in middle of sentence
        r'\bbasically\b',
        r'\bactually\b',
        r'\bliterally\b',
        r'\bobviously\b',
        r'\bhonestly\b',
        r'\bclearly\b',
        r'\bessentially\b',
        # Single-word fillers
        r'\bum+\b',
        r'\buh+\b',
        r'\bah+\b',
        r'\beh+\b',
        r'\ber+\b',
        r'\bmm+\b',
        r'\bhmm+\b',
        r'\bhuh\b',
        r'\bright\?\s*',  # "right?" as filler question
    ]

    for pattern in filler_patterns:
        text = re.sub(pattern, ' ', text, flags=re.IGNORECASE)

    # Remove stuttered/repeated words (e.g., "the the", "I I I")
    text = re.sub(r'\b(\w+)(\s+\1){1,}\b', r'\1', text, flags=re.IGNORECASE)

    # Remove false starts (incomplete words followed by complete version)
    # e.g., "prob- probably" -> "probably"
    text = re.sub(r'\b(\w{2,})-\s+(\1\w*)\b', r'\2', text, flags=re.IGNORECASE)

    # Clean up punctuation
    text = re.sub(r'\s+', ' ', text)  # Multiple spaces to single
    text = re.sub(r'\s([.,!?;:])', r'\1', text)  # Space before punctuation
    text = re.sub(r'([.,!?;:])\s*([.,!?;:])', r'\1', text)  # Double punctuation
    text = re.sub(r',\s*,', ',', text)  # Double commas
    text = re.sub(r'\.\s*\.', '.', text)  # Double periods
    text = re.sub(r'\s+([\'"])', r'\1', text)  # Space before quotes
    text = re.sub(r',\s+that,', ' that', text)  # ", that," -> " that"
    text = re.sub(r'\s+,', ',', text)  # Space before comma
    text = re.sub(r',(\s*,)+', ',', text)  # Multiple commas
    text = re.sub(r'^,\s*', '', text)  # Leading comma
    text = re.sub(r'\s*,\s*\.', '.', text)  # ", ." -> "."
    text = re.sub(r',\s*([A-Z])', r'. \1', text)  # ", [Capital]" often means sentence break
    text = re.sub(r'(\w),\s+(\w)', r'\1, \2', text)  # Normalize "word, word" spacing

    # Capitalize after sentence endings
    def capitalize_after_period(match):
        return match.group(1) + match.group(2).upper()
    text = re.sub(r'([.!?]\s+)([a-z])', capitalize_after_period, text)

    # Add paragraph breaks at ~500 character intervals at sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    paragraphs = []
    current_para = []
    char_count = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        current_para.append(sentence)
        char_count += len(sentence)

        # Break paragraph at ~500 chars
        if char_count > 500:
            paragraphs.append(' '.join(current_para))
            current_para = []
            char_count = 0

    if current_para:
        paragraphs.append(' '.join(current_para))

    # Join paragraphs with double newlines
    cleaned_text = '\n\n'.join(paragraphs)

    # Re-add header if it existed
    if header:
        cleaned_text = header + '\n' + cleaned_text

    return cleaned_text.strip()


def text_to_html(text: str, title: str = "YouTube Transcript", url: str = None) -> str:
    """Convert plain text to HTML for Kindle.

    Follows Send to Kindle requirements:
    - Proper UTF-8 charset declaration (Content-Type format for Kindle compatibility)
    - Converts markdown-style headers to HTML
    - Clean paragraph formatting
    """
    # Remove markdown header that may have been added during cleaning
    # (e.g., "# Title\n\nSource: ...\nDownloaded: ...\n\n---")
    text = re.sub(r'^#\s+[^\n]+\n*', '', text)  # Remove # Title line
    text = re.sub(r'^Source:\s*[^\n]+\n*', '', text)  # Remove Source line
    text = re.sub(r'^Downloaded:\s*[^\n]+\n*', '', text)  # Remove Downloaded line
    text = re.sub(r'^\s*-{3,}\s*\n*', '', text)  # Remove --- separator (with surrounding whitespace)

    # Split into paragraphs (by double newline or long gaps)
    paragraphs = re.split(r'\n\n+', text)
    if len(paragraphs) == 1:
        # If no paragraph breaks, try to add them at sentence boundaries
        # every ~500 chars
        sentences = re.split(r'(?<=[.!?])\s+', text)
        paragraphs = []
        current = []
        char_count = 0
        for sentence in sentences:
            current.append(sentence)
            char_count += len(sentence)
            if char_count > 500:
                paragraphs.append(' '.join(current))
                current = []
                char_count = 0
        if current:
            paragraphs.append(' '.join(current))

    date_str = datetime.now().strftime("%Y-%m-%d")

    # Use Content-Type format for charset - Kindle may not recognize HTML5-style
    # charset declaration and default to ISO-8859-1, causing character issues
    # Dublin Core metadata helps Kindle recognize title/author
    html_parts = [
        '<!DOCTYPE html>',
        '<html lang="en" xmlns:dc="http://purl.org/dc/elements/1.1/">',
        '<head>',
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>',
        f'<meta name="dc.title" content="{title}"/>',
        '<meta name="dc.creator" content="YouTube Transcript"/>',
        f'<meta name="dc.date" content="{date_str}"/>',
        f'<title>{title}</title>',
        '<style>',
        'body { font-family: Georgia, serif; line-height: 1.6; margin: 2em; }',
        'h1 { font-size: 1.5em; margin-bottom: 0.5em; page-break-after: avoid; }',
        'h2 { font-size: 1.2em; margin-top: 1.5em; margin-bottom: 0.5em; page-break-after: avoid; }',
        '.meta { color: #666; font-size: 0.9em; margin-bottom: 2em; }',
        'p { text-indent: 1.5em; margin: 0.5em 0; text-align: justify; }',
        '</style>',
        '</head>',
        '<body>',
        f'<h1>{title}</h1>',
        f'<p class="meta">Downloaded: {date_str}',
    ]

    if url:
        html_parts.append(f'<br>Source: <a href="{url}">{url}</a>')

    html_parts.append('</p>')
    html_parts.append('<hr>')

    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        # Convert markdown headers to HTML
        if p.startswith('## '):
            html_parts.append(f'<h2>{p[3:]}</h2>')
        elif p.startswith('# '):
            html_parts.append(f'<h2>{p[2:]}</h2>')
        elif p == '---':
            html_parts.append('<hr>')
        else:
            html_parts.append(f'<p>{p}</p>')

    html_parts.extend(['</body>', '</html>'])

    return '\n'.join(html_parts)


def download_thumbnail(url: str, output_path: str = None) -> str:
    """Download YouTube video thumbnail. Returns path to downloaded image."""
    if output_path is None:
        output_path = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name

    try:
        # Get video info to find thumbnail URL
        result = subprocess.run(
            ['yt-dlp', '--dump-json', '--skip-download', url],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            # Try to get the best thumbnail
            thumbnail_url = info.get('thumbnail')
            if not thumbnail_url:
                thumbnails = info.get('thumbnails', [])
                if thumbnails:
                    # Get highest resolution thumbnail
                    thumbnails.sort(key=lambda x: x.get('width', 0) * x.get('height', 0), reverse=True)
                    thumbnail_url = thumbnails[0].get('url')

            if thumbnail_url:
                # Download the thumbnail
                urllib.request.urlretrieve(thumbnail_url, output_path)
                print(f"Thumbnail downloaded: {output_path}", file=sys.stderr)
                return output_path
    except Exception as e:
        print(f"Warning: Could not download thumbnail: {e}", file=sys.stderr)

    return None


def text_to_epub(text: str, title: str = "YouTube Transcript",
                 author: str = "YouTube Transcript", url: str = None,
                 cover_image: str = None, output_path: str = None) -> str:
    """Convert plain text to EPUB with optional cover image using Calibre.

    Uses OPF format with Jinja2 templates and Calibre's ebook-convert for
    proper Kindle compatibility with:
    - Cover image (from YouTube thumbnail)
    - Clickable table of contents
    - Proper metadata (title, author, date)
    """
    if not JINJA2_AVAILABLE:
        print("Error: jinja2 not installed. Install with: pip install jinja2", file=sys.stderr)
        return None

    # Check for ebook-convert (Calibre)
    if shutil.which('ebook-convert') is None:
        print("Error: ebook-convert not found. Install Calibre: brew install calibre", file=sys.stderr)
        return None

    # Create build directory
    build_dir = tempfile.mkdtemp(prefix='kindle_')
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(os.path.dirname(script_dir), 'templates')

    # Clean the text (remove markdown headers that may have been added)
    text = re.sub(r'^#\s+[^\n]+\n*', '', text)
    text = re.sub(r'^Source:\s*[^\n]+\n*', '', text)
    text = re.sub(r'^Downloaded:\s*[^\n]+\n*', '', text)
    text = re.sub(r'^\s*-{3,}\s*\n*', '', text)

    # Split into sections (by ## headers or large paragraph groups)
    sections = []
    current_title = None
    current_content = []

    paragraphs = re.split(r'\n\n+', text)
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if p.startswith('## '):
            # Save previous section
            if current_content:
                content_html = ''.join(f'<p>{para}</p>' for para in current_content)
                sections.append({'title': current_title or 'Introduction', 'content': content_html})
            current_title = p[3:]
            current_content = []
        elif p.startswith('# '):
            if current_content:
                content_html = ''.join(f'<p>{para}</p>' for para in current_content)
                sections.append({'title': current_title or 'Introduction', 'content': content_html})
            current_title = p[2:]
            current_content = []
        elif p == '---':
            continue
        else:
            current_content.append(p)

    # Add final section
    if current_content:
        content_html = ''.join(f'<p>{para}</p>' for para in current_content)
        sections.append({'title': current_title or 'Transcript', 'content': content_html})

    # If no sections created, make one big section
    if not sections:
        all_paras = [p.strip() for p in paragraphs if p.strip() and p.strip() != '---']
        content_html = ''.join(f'<p>{para}</p>' for para in all_paras)
        sections.append({'title': 'Transcript', 'content': content_html})

    date_str = datetime.now().strftime("%Y-%m-%d")

    # Copy cover image if provided
    cover_filename = None
    if cover_image and os.path.exists(cover_image):
        ext = os.path.splitext(cover_image)[1] or '.jpg'
        cover_filename = f'cover{ext}'
        shutil.copy(cover_image, os.path.join(build_dir, cover_filename))

    # Render templates
    env = Environment(loader=FileSystemLoader(template_dir))
    template_data = {
        'title': title,
        'author': author,
        'date': date_str,
        'source_url': url,
        'sections': sections,
        'cover_image': cover_filename,
    }

    for template_name in ['book.opf', 'toc.html', 'content.html', 'book.ncx', 'style.css']:
        try:
            template = env.get_template(template_name)
            output_content = template.render(**template_data)
            with open(os.path.join(build_dir, template_name), 'w', encoding='utf-8') as f:
                f.write(output_content)
        except Exception as e:
            print(f"Warning: Could not render {template_name}: {e}", file=sys.stderr)

    # Run ebook-convert
    if output_path is None:
        output_path = f'{title}.epub'

    opf_path = os.path.join(build_dir, 'book.opf')

    try:
        result = subprocess.run(
            ['ebook-convert', opf_path, output_path],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode != 0:
            print(f"ebook-convert error: {result.stderr}", file=sys.stderr)
            return None
    except subprocess.TimeoutExpired:
        print("Error: ebook-convert timed out", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error running ebook-convert: {e}", file=sys.stderr)
        return None

    # Cleanup build directory
    shutil.rmtree(build_dir, ignore_errors=True)

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description='Download transcripts from YouTube or X.com and convert to plain text, HTML, or EPUB'
    )

    subparsers = parser.add_subparsers(dest='command')

    # Default behavior: download
    parser.add_argument('--url', '-u', help='YouTube or X.com video URL')
    parser.add_argument('--lang', '-l', default='en', help='Subtitle language (default: en)')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--auto-subs', '-a', action='store_true', default=True,
                        help='Include auto-generated subtitles (default: True)')
    parser.add_argument('--no-auto-subs', action='store_true',
                        help='Only use manual subtitles')
    parser.add_argument('--raw', action='store_true',
                        help='Output raw SRT instead of plain text')
    parser.add_argument('--list-subs', action='store_true',
                        help='List available subtitle tracks')
    parser.add_argument('--to-html', metavar='FILE',
                        help='Convert a text file to HTML')
    parser.add_argument('--to-epub', metavar='FILE',
                        help='Convert a text file to EPUB (with cover image for Kindle)')
    parser.add_argument('--clean', metavar='FILE',
                        help='Clean a transcript file (remove filler words, duplicates, add paragraphs)')
    parser.add_argument('--title', '-t', help='Title for HTML/EPUB output')
    parser.add_argument('--author', help='Author for EPUB metadata (default: "YouTube Transcript")')
    parser.add_argument('--source-url', help='Source URL for metadata (used with --to-html/--to-epub)')
    parser.add_argument('--cover', metavar='IMAGE',
                        help='Cover image file for EPUB')
    parser.add_argument('--youtube-cover', metavar='URL',
                        help='Download cover from YouTube video URL')

    args = parser.parse_args()

    # Handle --clean (filler word removal, paragraph formatting)
    if args.clean:
        input_file = args.clean
        if not os.path.exists(input_file):
            print(f"Error: File not found: {input_file}", file=sys.stderr)
            sys.exit(1)

        with open(input_file, 'r', encoding='utf-8') as f:
            text = f.read()

        original_len = len(text)
        cleaned = clean_transcript(text)
        cleaned_len = len(cleaned)

        # Determine output path
        if args.output:
            output_path = args.output
        else:
            base, ext = os.path.splitext(input_file)
            output_path = f"{base}_cleaned{ext}"

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(cleaned)

        reduction = ((original_len - cleaned_len) / original_len) * 100 if original_len > 0 else 0
        print(f"Cleaned transcript saved to: {output_path}")
        print(f"Size: {original_len:,} → {cleaned_len:,} chars ({reduction:.1f}% reduction)")
        print(f"Ready for LLM section structuring (add ## Section headers)")
        sys.exit(0)

    # Handle --to-html conversion
    if args.to_html:
        input_file = args.to_html
        if not os.path.exists(input_file):
            print(f"Error: File not found: {input_file}", file=sys.stderr)
            sys.exit(1)

        with open(input_file, 'r') as f:
            text = f.read()

        title = args.title or Path(input_file).stem
        source_url = getattr(args, 'source_url', None)
        html = text_to_html(text, title=title, url=source_url)

        output_path = args.output or input_file.replace('.txt', '.html')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        # Check file size for Send to Kindle compatibility
        file_size = os.path.getsize(output_path)
        file_size_mb = file_size / (1024 * 1024)

        print(f"HTML saved to: {output_path}")
        print(f"File size: {file_size_mb:.2f} MB")

        if file_size_mb > 25:
            print("Warning: File exceeds Gmail's 25 MB attachment limit.", file=sys.stderr)
        if file_size_mb > 50:
            print("Warning: File exceeds Kindle's 50 MB limit. Consider using ZIP compression.", file=sys.stderr)

        sys.exit(0)

    # Handle --to-epub conversion
    if args.to_epub:
        if not JINJA2_AVAILABLE:
            print("Error: jinja2 not installed. Install with: pip install jinja2", file=sys.stderr)
            sys.exit(1)
        if shutil.which('ebook-convert') is None:
            print("Error: ebook-convert not found. Install Calibre: brew install calibre", file=sys.stderr)
            sys.exit(1)

        input_file = args.to_epub
        if not os.path.exists(input_file):
            print(f"Error: File not found: {input_file}", file=sys.stderr)
            sys.exit(1)

        with open(input_file, 'r') as f:
            text = f.read()

        title = args.title or Path(input_file).stem
        author = args.author or "YouTube Transcript"
        source_url = getattr(args, 'source_url', None)

        # Get cover image
        cover_image = None
        if args.cover and os.path.exists(args.cover):
            cover_image = args.cover
        elif args.youtube_cover:
            print("Downloading YouTube thumbnail for cover...", file=sys.stderr)
            cover_image = download_thumbnail(args.youtube_cover)

        output_path = args.output or input_file.replace('.txt', '.epub')
        epub_path = text_to_epub(
            text,
            title=title,
            author=author,
            url=source_url,
            cover_image=cover_image,
            output_path=output_path
        )

        if epub_path:
            file_size = os.path.getsize(epub_path)
            file_size_mb = file_size / (1024 * 1024)
            print(f"EPUB saved to: {epub_path}")
            print(f"File size: {file_size_mb:.2f} MB")
            if cover_image:
                print(f"Cover image: {cover_image}")
        else:
            print("Error: Failed to create EPUB", file=sys.stderr)
            sys.exit(1)

        # Cleanup temp cover if downloaded
        if args.youtube_cover and cover_image and cover_image.startswith(tempfile.gettempdir()):
            os.remove(cover_image)

        sys.exit(0)

    # Require URL for other operations
    if not args.url:
        parser.print_help()
        sys.exit(1)

    # Handle --list-subs
    if args.list_subs:
        list_subtitles(args.url)
        sys.exit(0)

    # Detect source and route accordingly
    source = detect_source(args.url)

    if source == 'x':
        # X.com path: download + transcribe via whisper if needed
        output_path = args.output or './x_transcript.txt'
        result_path = download_x_transcript(args.url, output_path)
        if not result_path:
            sys.exit(1)
        print(f"Transcript saved to: {result_path}")
        sys.exit(0)

    # YouTube path (default)
    # Get video info for title
    info = get_video_info(args.url)
    video_title = info.get('title', 'YouTube Video')

    # Download subtitles
    auto_subs = args.auto_subs and not args.no_auto_subs
    srt_path = download_subtitles(args.url, args.lang, auto_subs)

    if not srt_path:
        sys.exit(1)

    print(f"Downloaded: {srt_path}", file=sys.stderr)

    # Read and parse
    with open(srt_path, 'r', encoding='utf-8') as f:
        srt_content = f.read()

    if args.raw:
        output = srt_content
    else:
        entries = parse_srt(srt_content)
        output = srt_to_plain_text(entries)
        # Add header
        output = f"# {video_title}\n\nSource: {args.url}\nDownloaded: {datetime.now().strftime('%Y-%m-%d')}\n\n---\n\n{output}"

    # Write output
    if args.output:
        output_path = args.output
    else:
        ext = '.srt' if args.raw else '.txt'
        safe_title = re.sub(r'[^\w\s-]', '', video_title)[:50]
        output_path = f"./{safe_title}_transcript{ext}"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output)

    print(f"Transcript saved to: {output_path}")
    print(f"Video title: {video_title}")

    # Clean up temp files
    if srt_path.startswith(tempfile.gettempdir()):
        os.remove(srt_path)


if __name__ == '__main__':
    main()
