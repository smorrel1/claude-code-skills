---
name: docx-editor
description: Word document (.docx) utilities including character normalization for fixing smart quotes, em dashes, and other special characters that break find-and-replace operations. Use when editing Word documents or when encountering "String not found" errors.
---

# DOCX Editor Utilities

Tools for working with Microsoft Word documents, particularly for fixing character encoding issues.

## Character Normalization

Word documents often contain special Unicode characters that look similar to standard ASCII but break text operations:

| Word Character | Replacement | Name |
|----------------|-------------|------|
| " " | " " | Smart double quotes |
| ' ' | ' ' | Smart single quotes |
| — – | - | Em/en dashes |
| → | -> | Arrow |
| … | ... | Ellipsis |

### Usage

```bash
# Normalize text with special characters
python3 scripts/fix_docx_chars.py "Text with "smart quotes" and — dashes"

# From stdin
echo "Text with — special chars" | python3 scripts/fix_docx_chars.py -
```

## When to Use

1. **Before editing .docx files**: Run text through normalizer before using in find-and-replace
2. **When Edit tool fails**: If you get "String not found" errors, the text likely has special characters
3. **Copying from Word**: Text pasted from Word often contains invisible special characters

## Workflow

1. Read the problematic text from the document
2. Run it through `fix_docx_chars.py` to get normalized version
3. Use the normalized text for search/replace operations

## Other Utilities

- `docx_utils.py`: General DOCX manipulation utilities
