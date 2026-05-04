---
name: interview-transcript
description: Download and transcribe interviews/talks from YouTube videos and X.com (Twitter) videos/Spaces. Clean transcripts with Claude (removing filler words and transcription errors while preserving facts), and send to Kindle with cover image and clickable table of contents. Use when user shares a YouTube or X.com URL and wants a transcript, or asks to transcribe a video interview.
---

# Interview Transcript Skill

Download transcripts from YouTube or X.com, clean them with AI, and send to Kindle with cover image and clickable TOC.

## Prerequisites

### Core (required for all transcripts)
- **yt-dlp**: `brew install yt-dlp` or `pip install yt-dlp` (subtitle/audio extraction)
- **jinja2**: `pip install jinja2` (EPUB template rendering)
- **Calibre**: `brew install calibre` (provides `ebook-convert` for EPUB creation)

### X.com fallback (only needed when no YouTube equivalent found)
- **ffmpeg**: `brew install ffmpeg` (resample audio to 16kHz mono for whisper)
- **whisper-cpp**: `brew install whisper-cpp` (audio transcription, binary at `/usr/local/opt/whisper-cpp/bin/whisper-cli`)
- **Whisper model**: e.g. `ggml-small.bin` from superwhisper app or [huggingface.co/ggerganov/whisper.cpp](https://huggingface.co/ggerganov/whisper.cpp/tree/main)

### Optional services
- **Gmail `email` skill** with OAuth credentials for Kindle delivery
- **Google Drive** OAuth token (`~/.claude/skills/email/token_drive.json`) for shareable link generation

## Supported Sources

| Source | URL Pattern | Method |
|--------|------------|--------|
| YouTube | `youtube.com/watch?v=...`, `youtu.be/...` | Subtitle extraction (SRT) |
| X.com / Twitter | `x.com/.../status/...`, `twitter.com/...` | Subtitles if available, otherwise audio download + whisper.cpp transcription |

## Usage

### Step 1: Download the transcript

**YouTube:**
```bash
python3 scripts/youtube_transcript.py --url "https://www.youtube.com/watch?v=VIDEO_ID"
```

**X.com:**
```bash
python3 scripts/youtube_transcript.py --url "https://x.com/user/status/123456"
```

The script auto-detects the source from the URL. For X.com, it first tries subtitle extraction, then falls back to downloading audio and transcribing with whisper.cpp.

Options:
| Option | Description |
|--------|-------------|
| `--url` | YouTube or X.com video URL (required) |
| `--lang` | Subtitle language code (default: en) |
| `--output` | Output file path (default: ./transcript.txt) |
| `--auto-subs` | Use auto-generated subtitles if manual unavailable |
| `--raw` | Output raw SRT instead of plain text |
| `--clean FILE` | Clean a transcript (remove filler words, add paragraphs) |

### Step 2: Clean filler words (Python script)

```bash
python3 scripts/youtube_transcript.py --clean transcript_raw.txt --output transcript_cleaned.txt
```

This removes filler words, duplicates, and adds paragraph breaks **without using LLM tokens**:
- Removes: um, uh, like, you know, basically, actually, literally, I mean, sort of, kind of, etc.
- Removes: [Music], [Applause], and other auto-caption artifacts
- Removes: stuttered/repeated words (e.g., "the the" -> "the")
- Adds paragraph breaks at ~500 character intervals

**Output shows reduction:** e.g., "Size: 45,000 -> 38,000 chars (15.6% reduction)"

### Step 3: Add section headers and fix transcription (LLM - use haiku model)

**IMPORTANT:** Use the Agent tool with `model: haiku`. The LLM adds `## Section Title` headers AND fixes transcription quality issues that the mechanical cleaning cannot catch.

The haiku agent should:
1. **Read** the pre-cleaned transcript file
2. **Add section headers** using `## Section Title` markdown:
   - **For interviews:** New section for each interviewer question/topic
   - **For lectures/talks:** New section at major concept transitions
   - Each section: 2-5 paragraphs (~1000 words max)
3. **Fix transcription quality** using contextual understanding:
   - **Misrecognized words:** Auto-captions often get proper nouns wrong (e.g., "Enthropic" -> "Anthropic", "quad code" -> "Claude Code", "Churnney" -> "Cherny")
   - **Punctuation:** Add missing sentence breaks, fix run-on sentences, add question marks to questions
   - **Speaker attribution:** Where `>>` markers exist, clarify who is speaking if obvious from context
   - **Garbled phrases:** Reconstruct phrases that were clearly misheard based on surrounding context
   - **Names and terms:** Correct technical terms, company names, product names, and people's names
4. **Write** the structured version with ONE Write tool call

**Why haiku does this better than the script:** The mechanical `--clean` step handles pattern-based fixes (filler words, duplicates). But contextual errors like "quad code" (should be "Claude Code") or missing punctuation require understanding the meaning, which only the LLM can do.

### Step 4: Convert to EPUB with cover

```bash
python3 scripts/youtube_transcript.py --to-epub transcript_structured.txt \
  --output "Video Title.epub" \
  --title "Video Title" \
  --author "Channel Name" \
  --youtube-cover "https://youtube.com/watch?v=VIDEO_ID"
```

For X.com videos, use `--cover` with a local image if you have one, or omit for no cover.

### Step 5: Send to Kindle

```bash
python3 ~/.claude/skills/email/scripts/gmail_utils.py --account gmail send \
  --to "<your-kindle-email>@kindle.com" \
  --subject "Convert" \
  --body "Transcript attached" \
  --attach "Video Title.epub" \
  --new
```

**Important:** Always use `--account gmail` and `--new` flags. Use subject "Convert" for Kindle-optimized formatting.

## Complete Workflow Example

```bash
# 1. Download transcript (auto-detects YouTube vs X.com)
python3 scripts/youtube_transcript.py --url "https://youtu.be/VIDEO_ID" \
  --output ~/Downloads/transcript_raw.txt --auto-subs

# 2. Clean filler words (Python - no LLM needed)
python3 scripts/youtube_transcript.py --clean ~/Downloads/transcript_raw.txt \
  --output ~/Downloads/transcript_cleaned.txt

# 3. (Claude haiku adds ## Section headers, saves to transcript_structured.txt)

# 4. Convert to EPUB with thumbnail as cover
python3 scripts/youtube_transcript.py --to-epub ~/Downloads/transcript_structured.txt \
  --output ~/Downloads/"Video Title.epub" \
  --title "Video Title" \
  --author "Channel Name" \
  --youtube-cover "https://youtu.be/VIDEO_ID"

# 5. Send to Kindle
python3 ~/.claude/skills/email/scripts/gmail_utils.py --account gmail send \
  --to "<your-kindle-email>@kindle.com" \
  --subject "Convert" \
  --body "Cleaned transcript attached." \
  --attach ~/Downloads/"Video Title.epub" \
  --new
```

## EPUB Options

| Option | Description |
|--------|-------------|
| `--to-epub FILE` | Convert text file to EPUB |
| `--title` | Book title for EPUB metadata |
| `--author` | Author name for EPUB metadata |
| `--cover IMAGE` | Use local image file as cover |
| `--youtube-cover URL` | Download YouTube thumbnail as cover |
| `--output` | Output file path |

## Workflow for Claude

When a user asks to download and clean a transcript:

1. **Extract URL** from user request, auto-detect source (YouTube or X.com)
2. **If X.com URL: Search YouTube first** (see X.com workflow below)
3. **Run the download script** to get raw transcript
4. **Run `--clean`** to remove filler words (Python, no LLM tokens)
5. **Add section headers + fix transcription using Agent tool with model=haiku**:
   - Launch a haiku agent that reads the pre-cleaned transcript
   - Add `## Section Title` headers at each topic change
   - Fix contextual transcription errors: misrecognized proper nouns, missing punctuation, garbled phrases, speaker attribution
   - **Write structured version with ONE Write tool call**
6. **Convert to EPUB with cover**:
   - Use `--to-epub` with `--youtube-cover URL` (YouTube) or `--cover FILE` (X.com)
   - The `## Section Title` headers become clickable TOC entries
7. **Send to Kindle** using gmail skill `send` command:
   - Use `--account gmail --new`
   - Use subject "Convert" for Kindle-optimized formatting
8. **Upload to Google Drive** and get shareable link:
   - Use the Python Google Drive API script with token at `~/.claude/skills/email/token_drive.json`
   - Set permissions to "anyone with link can view"
   - Return both view link and direct download link
9. **Generate a shareable post** for the user to copy/paste to YouTube comments or X.com:
   - Include: title, brief description of the transcript, EPUB download link (Google Drive), and a link to the interview-transcript skill on GitHub so others can run it themselves
   - Keep it concise and friendly, suitable for a YouTube comment or X post
   - Example format: "I made a cleaned-up Kindle-ready transcript of this interview with section headers and TOC. Download the EPUB here: [link]. Made with this open-source Claude Code skill: [github link]"

## X.com YouTube-First Search (IMPORTANT)

**Always try to find the same interview on YouTube before transcribing X.com audio.** YouTube videos have proper subtitles that extract instantly, while X.com requires downloading audio + whisper transcription (slow, lower quality).

### Search strategy (in order):

1. **Check the X post description** for links. Use `yt-dlp --dump-json --skip-download <x_url>` and look for URLs in the description field. Resolve any t.co shortened links with `curl -sIL`.
2. **Check the X post thread/replies** for YouTube links. The original poster or others often link to the full YouTube version.
3. **Search YouTube** using WebSearch with key details from the X post (speaker names, topic, podcast name). Filter to `youtube.com` domain.
4. **Match by duration.** Compare the X.com video duration (from yt-dlp metadata) to YouTube candidates. A close match (within ~5 min) strongly suggests the same content.

### If YouTube match found:
- Use the YouTube URL instead for subtitle extraction (instant, high quality)
- Still use YouTube thumbnail as cover via `--youtube-cover`

### If no YouTube match:
- Fall back to X.com audio download + whisper-cpp transcription
- whisper-cli binary is at `/usr/local/opt/whisper-cpp/bin/whisper-cli`
- Model file at `~/Library/Application Support/superwhisper/ggml-small.bin` (from superwhisper app)
- Resample to 16kHz mono first: `ffmpeg -i input.wav -ar 16000 -ac 1 output_16k.wav`

## X.com Specific Notes

- X.com videos/Spaces rarely have subtitles, so always try YouTube first
- X.com Spaces (live audio) are also supported via yt-dlp
- Transcription of long X.com Spaces may take several minutes with whisper

## Section Breaking Guidelines

Sections become clickable TOC entries in the EPUB. Use `## Section Title` markdown headers.

### For Interviews

Identify interviewer questions and use them as section titles:
- "So tell me about your background..." -> `## Background and Early Career`
- "How do you think about AI safety?" -> `## AI Safety Philosophy`

Look for cues:
- Direct questions ("What do you think about...", "How did you...")
- Topic shifts ("Let's talk about...", "Moving on to...")
- New themes introduced by either speaker

### For Lectures/Talks

Create sections at natural topic boundaries:
- Major concept introductions
- "Now let's look at..." transitions

### Section Length

Aim for 2-5 paragraphs per section. If a section gets too long (more than ~1000 words), look for natural subdivision points.

## Technical Details

### EPUB Creation (Calibre-based)

The skill uses Calibre's `ebook-convert` with OPF format for reliable Kindle compatibility:

- **book.opf**: Package format with `<EmbeddedCover>` tag
- **toc.html**: Clickable table of contents with hyperlinks
- **content.html**: Main content with section anchors
- **book.ncx**: Navigation control for Kindle's built-in nav
- **style.css**: Typography and formatting

### Send to Kindle Notes

- **Subject "Convert"**: Amazon converts to Kindle format with adjustable fonts, highlighting, notes
- **File size**: 50 MB max (Gmail: 25 MB)
- **Approved sender**: Your Gmail account (use `--account gmail`)
- **Filename = Book title**: Use descriptive filenames
