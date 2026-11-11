#!/opt/anaconda3/bin/python3
"""Press "a" during a call and get an answer to the last question, fast.

The coach watches the transcript and speaks up when it has something worth
saying. This is the other direction: Stephen has just been asked something
and wants a prompt in the two or three seconds he would naturally take to
draw breath. Anything slower is useless, because the moment has gone.

    answer_key.py                     tail ~/live-transcript.jsonl, wait for a key
    answer_key.py --transcript PATH
    answer_key.py --once              answer the last question and exit (for tests)
    answer_key.py --benchmark 5       time five answers and report the spread

Keys: a or A answers the most recent question. q quits. Anything else is
ignored, so a stray keystroke during a call does nothing.

How the three seconds are met, in order of how much each one buys:
  - Haiku, not a bigger model. The job is recall and phrasing, not reasoning.
  - A hard cap on the answer length. Long answers are useless out loud anyway.
  - Streaming, so the first words land in well under a second and Stephen can
    start talking while the rest arrives.
  - A small context window, the last 40 utterances rather than the whole call.
  - A warm HTTP connection and a cached system prompt, so the second press is
    faster than the first.
"""

import argparse
import json
import os
import re
import select
import sys
import termios
import time
import tty

MODEL = "claude-haiku-4-5-20251001"   # the fast one; this is a recall task
MAX_TOKENS = 160                      # about 25 seconds of speech, read aloud
CONTEXT_LINES = 40                    # the last few minutes, not the whole call
DEFAULT_TRANSCRIPT = os.path.expanduser("~/live-transcript.jsonl")

# Who Stephen is, so the answer is in his world rather than generic. Kept
# short on purpose: every token here is latency on every press.
PERSONA = """You are prompting Stephen Morrell DURING a live call. He is CEO of
Elaitra (medical imaging AI, ViewFinder: contralateral CC and MLO position
mapping for mammography) and a visiting researcher at King's College London.

Someone has just asked him something. Give him what to say.

Rules, all of them about being usable out loud:
- Lead with the answer in the first sentence. No preamble.
- Two or three short sentences, maximum. He has to say this, not read it.
- Plain spoken English. No lists, no headings, no markdown.
- If the honest answer is that he does not know, say what he should say
  instead, for example what he will follow up with and by when.
- Never invent a number. If a figure is needed and you do not have it, tell
  him to give the range he is sure of or to promise the exact figure later.
- Never state a regulatory fact (device class, predicate, clearance, CE or
  UKCA status) unless it is in the transcript. If asked and it is not, tell
  him to say he will confirm it in writing.
- No em dashes. Use commas or full stops. Stephen never uses them."""

QUESTION = re.compile(r"\?\s*$")


def utterances(path, limit=CONTEXT_LINES):
    """The last `limit` transcript lines as (speaker, text)."""
    try:
        with open(path, "rb") as fh:
            # Read the tail only. These files reach megabytes over a long
            # call and parsing all of it would cost more than the API call.
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 64 * 1024))
            raw = fh.read().decode("utf-8", "ignore").split("\n")
    except OSError:
        return []
    out = []
    for line in raw:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        text = (d.get("text") or "").strip()
        if text and text not in (".", ".."):
            out.append((d.get("speaker") or "Unknown", text))
    return out[-limit:]


def last_question(lines):
    """The most recent question somebody else asked.

    Walks backwards for a line ending in a question mark that Stephen did not
    say himself. Falls back to the last thing anyone said, because people ask
    questions without the intonation surviving transcription ("so tell me
    about your regulatory path").
    """
    for speaker, text in reversed(lines):
        if "stephen" in speaker.lower():
            continue
        if QUESTION.search(text):
            return speaker, text
    for speaker, text in reversed(lines):
        if "stephen" not in speaker.lower():
            return speaker, text
    return None, None


def build_client():
    import anthropic
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY is not set, so there is nothing to ask.")
    # One client, reused. The TLS handshake alone is a few hundred
    # milliseconds, and paying it on every press would eat the budget.
    return anthropic.Anthropic(api_key=key, max_retries=1, timeout=20.0)


def answer(client, path, out=sys.stdout):
    """Stream an answer to the last question. Returns (seconds, first_token)."""
    lines = utterances(path)
    speaker, question = last_question(lines)
    if not question:
        out.write("\nNothing in the transcript yet.\n")
        out.flush()
        return None, None

    context = "\n".join("%s: %s" % (s, t) for s, t in lines)
    out.write("\n\033[1mQ (%s):\033[0m %s\n\033[33m" % (speaker, question[:160]))
    out.flush()

    t0 = time.time()
    first = None
    with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": PERSONA,
                     # Cached, so the persona is not re-read on every press.
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user",
                       "content": "Last few minutes of the call:\n\n%s\n\n"
                                  "They just asked: %s\n\nWhat does Stephen say?"
                                  % (context, question)}]) as stream:
        for chunk in stream.text_stream:
            if first is None:
                first = time.time() - t0
            out.write(chunk)
            out.flush()
    total = time.time() - t0
    out.write("\033[0m\n\033[2m%.1fs (first words %.1fs)\033[0m\n" % (total, first or 0))
    out.flush()
    return total, first


def wait_for_key():
    """One keypress, without waiting for Enter. None if stdin is not a tty."""
    if not sys.stdin.isatty():
        return None
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        if select.select([sys.stdin], [], [], 0.5)[0]:
            return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transcript", default=DEFAULT_TRANSCRIPT)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--benchmark", type=int, metavar="N")
    a = ap.parse_args()

    client = build_client()

    if a.benchmark:
        times = []
        for i in range(a.benchmark):
            total, first = answer(client, a.transcript)
            if total:
                times.append((total, first))
            time.sleep(0.5)
        if times:
            tot = sorted(t for t, _ in times)
            fst = sorted(f for _, f in times)
            print("\n%d run(s): total median %.1fs, worst %.1fs | "
                  "first words median %.1fs, worst %.1fs"
                  % (len(times), tot[len(tot) // 2], tot[-1],
                     fst[len(fst) // 2], fst[-1]))
            print("under 3s: %d of %d" % (sum(1 for t in tot if t <= 3.0), len(tot)))
        return 0

    if a.once:
        answer(client, a.transcript)
        return 0

    print("Meeting coach: press \033[1ma\033[0m to answer the last question, "
          "\033[1mq\033[0m to quit.")
    while True:
        k = wait_for_key()
        if k is None:
            print("Not a terminal, so there is no key to press. "
                  "Use --once or --benchmark.")
            return 1
        if k in ("a", "A"):
            try:
                answer(client, a.transcript)
            except Exception as exc:
                print("\nanswer failed: %s" % exc)
        elif k in ("q", "Q"):
            return 0


if __name__ == "__main__":
    sys.exit(main())
