"""
Text Cleaning Utility

This module provides functions to clean RTF, XML, and other formatted text
to make it more digestible for LLM processing.
"""

import re
from striprtf.striprtf import rtf_to_text

def clean_rtf_content(rtf_content):
    """
    Clean RTF content by removing RTF control codes and formatting

    Args:
        rtf_content (str): Raw RTF content

    Returns:
        str: Cleaned plain text
    """
    try:
        # First try using striprtf library for proper RTF parsing
        try:
            cleaned_text = rtf_to_text(rtf_content)
            if cleaned_text and cleaned_text.strip():
                return clean_text_content(cleaned_text)
        except:
            pass

        # Fallback to manual RTF cleaning if striprtf fails
        text = rtf_content

        # Remove RTF header and document structure
        text = re.sub(r'\\rtf\d+.*?\\deftab\d+', '', text, flags=re.DOTALL)

        # Remove RTF control words and groups
        text = re.sub(r'\\[a-zA-Z]+\d*\s?', '', text)  # Control words like \f0, \fs26
        text = re.sub(r'\\[^a-zA-Z]', '', text)        # Control symbols like \{, \}
        text = re.sub(r'\{[^{}]*\}', '', text)         # Remove grouped content

        # Remove remaining braces
        text = text.replace('{', '').replace('}', '')

        # Clean up the resulting text
        return clean_text_content(text)

    except Exception as e:
        print(f"Warning: RTF cleaning failed, using raw text: {str(e)}")
        return clean_text_content(rtf_content)

def clean_xml_content(xml_content):
    """
    Clean XML/HTML tags from content

    Args:
        xml_content (str): Content with XML/HTML tags

    Returns:
        str: Cleaned plain text
    """
    # Remove XML/HTML tags
    text = re.sub(r'<[^>]+>', '', xml_content)

    # Decode common XML entities
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&amp;', '&')
    text = text.replace('&quot;', '"')
    text = text.replace('&apos;', "'")
    text = text.replace('&#39;', "'")
    text = text.replace('&#x27;', "'")

    return clean_text_content(text)

def clean_text_content(text):
    """
    General text cleaning for better LLM consumption

    Args:
        text (str): Raw text content

    Returns:
        str: Cleaned and formatted text
    """
    if not text:
        return ""

    # Fix common RTF artifacts
    text = text.replace("\\'92", "'")  # RTF apostrophe
    text = text.replace("\\'93", '"')  # RTF left double quote
    text = text.replace("\\'94", '"')  # RTF right double quote
    text = text.replace("\\'96", '–')  # RTF en dash
    text = text.replace("\\'97", '—')  # RTF em dash
    text = text.replace("\\'85", '…')  # RTF ellipsis

    # Clean up excessive whitespace
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Multiple blank lines to double
    text = re.sub(r'[ \t]+', ' ', text)             # Multiple spaces/tabs to single space
    text = re.sub(r'^\s+', '', text, flags=re.MULTILINE)  # Leading whitespace
    text = re.sub(r'\s+$', '', text, flags=re.MULTILINE)  # Trailing whitespace

    # Remove lines that are mostly formatting artifacts
    lines = text.split('\n')
    cleaned_lines = []

    for line in lines:
        line = line.strip()
        # Skip lines that are mostly control characters or very short
        if len(line) > 2 and not re.match(r'^[\s\\\{\}]+$', line):
            cleaned_lines.append(line)

    # Rejoin and final cleanup
    text = '\n'.join(cleaned_lines)
    text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 consecutive newlines

    return text.strip()

def detect_and_clean_content(content):
    """
    Auto-detect content type and apply appropriate cleaning

    Args:
        content (str): Raw content

    Returns:
        str: Cleaned content
    """
    if not content or not isinstance(content, str):
        return ""

    content = content.strip()

    # Detect RTF content
    if content.startswith('{\\rtf') or '\\rtf1' in content[:100]:
        return clean_rtf_content(content)

    # Detect XML/HTML content
    elif content.startswith('<?xml') or content.startswith('<') or re.search(r'<[^>]+>', content):
        return clean_xml_content(content)

    # Default text cleaning
    else:
        return clean_text_content(content)

if __name__ == "__main__":
    # Test with a sample RTF string
    test_rtf = """{\\rtf1\\ansi\\ansicpg1252\\cocoartf2822
\\f0\\b\\fs40 \\cf0 20250703-BoD1-Phil\\
\\f1\\b0\\fs26 \\cf0 what\\'92s the motive\\
funding round. \\
}"""

    print("Original:")
    print(test_rtf)
    print("\nCleaned:")
    print(clean_rtf_content(test_rtf))