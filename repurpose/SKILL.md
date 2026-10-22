---
name: repurpose
description: Turn one long-form transcript or article into platform-native posts in one pass - an X thread, a LinkedIn post, and a newsletter section - each checked against AI-writing tells before delivery. Use when the user says "repurpose this", "turn this episode/transcript/post into content", "make a thread from this", or gives a transcript and asks for social posts. Pairs with interview-transcript (gets the transcript) and humanizer (removes AI tells).
---

# Repurpose

One recording becomes a week of posts. Input: a transcript, article, or notes file.
Output: three platform-native drafts the author can paste, each stripped of AI-writing tells.

## Why this exists

Solo creators record for an hour, then lose two or three more turning it into posts, and
most convert only a fraction of the potential reach. This skill does the conversion pass
locally, with no subscription, and refuses to ship text that reads machine-written.

## Workflow

1. **Read the source.** Accept a file path or pasted text. If the user has the
   companion `interview-transcript` skill, that is the natural upstream: video URL
   in, cleaned transcript out, then this skill takes over.

2. **Find the spine.** Identify the 3-5 strongest claims, stories, or numbers in the
   source. Quote them exactly; never invent statistics or soften attributed opinions.
   The author's own phrasing beats a summary of it.

3. **Write three assets**, saved as separate files next to the source
   (`<source>-thread.txt`, `<source>-linkedin.txt`, `<source>-newsletter.txt`):

   - **X thread** (5-8 posts): first post is a hook built from the single strongest
     claim, no hashtags, each post under 280 characters, last post points back to the
     full source. Plain text, one post per paragraph.
   - **LinkedIn post** (150-250 words): opens with the story or number, not a
     greeting; short paragraphs; one concrete takeaway; no emoji walls.
   - **Newsletter section** (200-350 words): a self-contained segment with a heading,
     written in the author's register from the source, closing with one link or ask.

4. **Voice match.** Before writing, sample the source's register (sentence length,
   formality, vocabulary) and match it. The drafts should read like the author on a
   good day, not like a different writer.

5. **Strip the AI tells.** If the `humanizer` skill is installed, apply its guidance
   and run its checker on each file until it passes:

   ```bash
   python3 ~/.claude/skills/humanizer/check_mannerisms.py <file>
   ```

   No em dashes, no "delve", no rule-of-three padding, no inflated symbolism. If the
   checker is absent, apply the same rules manually and say so.

6. **Deliver.** List the three files with a one-line description each. Never post
   anywhere; the author owns distribution.

## Rules

- Quote, never fabricate: every number and claim in the output must exist in the source.
- Keep the author's opinions theirs: no hedging added, no spice added.
- Plain text output files, no markdown syntax in the X thread (X renders none).
- One pass, three assets, under two minutes of the author's attention to review.
