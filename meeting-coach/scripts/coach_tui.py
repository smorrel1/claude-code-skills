#!/opt/anaconda3/bin/python3
"""The meeting coach, in one terminal window.

Stephen's call, 11 Nov 2026: one interactive window, not a Safari page plus
an Apple Note plus a terminal. Everything happens here:

  - type a question at the prompt and press Enter;
  - hotkeys for the things he needs mid-sentence, with the guide pinned to the
    bottom of the window so he never has to remember them;
  - coaching alerts at the top, newest first;
  - a red banner if Zoom's transcript stops, which on 11 Nov it did at 10:18
    with nobody told.

    coach_tui.py                    the live transcript at ~/live-transcript.jsonl
    coach_tui.py --transcript PATH

Hotkeys (Ctrl versions work on any keyboard):
    F1  / Ctrl-A   answer the last question somebody asked you
    F2  / Ctrl-S   summarise the last 45 seconds
    F3  / Ctrl-W   show the last few lines of transcript
    F4  / Ctrl-L   clear the answer pane
    F10 / Ctrl-Q   quit

Alerts arrive from the coach session through `coach_ui.py alert "<line>"`,
which now writes only to ~/.coach/ui-state.json; this window reads it.
"""

import argparse
import curses
import json
import os
import sys
import textwrap
import threading
import time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import answer_key as K  # noqa: E402

STATE = os.path.expanduser(os.environ.get("COACH_UI_STATE", "~/.coach/ui-state.json"))
STALE_SECS = 60

# Compact on purpose: the first version ran to 113 characters and an ordinary
# window cut off "F10 quit", the one key nobody can guess.
GUIDE = ["Enter ask", "F1 answer", "F2 last 45s", "F3 recent", "F4 clear", "F10 quit"]
CTRL = {1: "answer", 19: "summary", 23: "recent", 12: "clear", 17: "quit"}


class Coach:
    def __init__(self, transcript):
        self.transcript = transcript
        self.answer = ""          # streamed text in the middle pane
        self.title = "Ready."     # what the middle pane is showing
        self.busy = False
        self.input = ""
        self.client = None
        self.lock = threading.Lock()

    # -- data -------------------------------------------------------------
    def alerts(self):
        try:
            return json.load(open(STATE)).get("alerts", [])[:4]
        except Exception:
            return []

    def stalled(self):
        """Seconds of silence if a live meeting's transcript has stopped."""
        try:
            import coach_ui
            return coach_ui.feed_stalled()
        except Exception:
            return None

    def recent_lines(self, seconds=None, limit=8):
        lines = K.utterances(self.transcript, limit=200)
        if seconds is None:
            return lines[-limit:]
        # The transcript only carries wall-clock stamps, so read them back.
        cutoff = datetime.now() - timedelta(seconds=seconds)
        keep = []
        try:
            raw = open(self.transcript, errors="ignore").read().strip().split("\n")[-200:]
            for l in raw:
                d = json.loads(l)
                ts = datetime.fromisoformat(d.get("wall_ts", "1970-01-01T00:00:00"))
                if ts >= cutoff and (d.get("text") or "").strip(" ."):
                    keep.append((d.get("speaker") or "?", d["text"].strip()))
        except Exception:
            pass
        return keep or lines[-limit:]

    # -- model calls, in a thread so the window never freezes --------------
    def ask(self, title, prompt):
        if self.busy:
            return
        self.busy, self.title, self.answer = True, title, ""

        def run():
            t0 = time.time()
            try:
                if self.client is None:
                    self.client = K.build_client()
                with self.client.messages.stream(
                        model=K.MODEL, max_tokens=220,
                        system=[{"type": "text", "text": K.PERSONA,
                                 "cache_control": {"type": "ephemeral"}}],
                        messages=[{"role": "user", "content": prompt}]) as s:
                    for chunk in s.text_stream:
                        with self.lock:
                            self.answer += chunk
                with self.lock:
                    self.title += "   (%.1fs)" % (time.time() - t0)
            except Exception as exc:
                with self.lock:
                    self.answer = "Could not answer: %s" % exc
            finally:
                self.busy = False

        threading.Thread(target=run, daemon=True).start()

    def context(self):
        return "\n".join("%s: %s" % (s, t) for s, t in K.utterances(self.transcript))

    def answer_last(self):
        speaker, q = K.last_question(K.utterances(self.transcript))
        if not q:
            self.title, self.answer = "Nothing in the transcript yet.", ""
            return
        self.ask("Answer to %s: %s" % (speaker, q[:80]),
                 "Last few minutes of the call:\n\n%s\n\nThey just asked: %s\n\n"
                 "What does Stephen say?" % (self.context(), q))

    def summary(self):
        lines = self.recent_lines(seconds=45)
        text = "\n".join("%s: %s" % l for l in lines)
        self.ask("Last 45 seconds",
                 "Summarise what was just said, for Stephen to glance at "
                 "mid-call. Two sentences, plain English, no lists.\n\n%s" % text)

    def question(self, q):
        self.ask("You asked: %s" % q[:80],
                 "Last few minutes of the call:\n\n%s\n\nStephen asks you, "
                 "privately: %s\n\nAnswer him in at most three short sentences."
                 % (self.context(), q))

    def recent(self):
        self.title = "Recent transcript"
        self.answer = "\n".join("%s: %s" % l for l in self.recent_lines())


def draw(scr, c):
    scr.erase()
    h, w = scr.getmaxyx()
    width = max(20, w - 2)
    y = 0

    stalled = c.stalled()
    if stalled:
        msg = " TRANSCRIPT STOPPED %ds ago. Check the Zoom note: open, Transcript on. " % stalled
        scr.addnstr(y, 0, msg.ljust(w), w, curses.color_pair(1) | curses.A_BOLD)
        y += 2

    # Alerts: newest bold, older dim.
    alerts = c.alerts()
    if alerts:
        for line in textwrap.wrap(alerts[0]["text"], width)[:3]:
            scr.addnstr(y, 1, line, width, curses.A_BOLD | curses.color_pair(2))
            y += 1
        for a in alerts[1:4]:
            scr.addnstr(y, 1, ("%s  %s" % (a["at"], a["text"]))[:width], width, curses.A_DIM)
            y += 1
    else:
        scr.addnstr(y, 1, "No coaching alerts yet.", width, curses.A_DIM)
        y += 1
    y += 1
    scr.addnstr(y, 0, "─" * w, w, curses.A_DIM)
    y += 1

    # Answer pane.
    footer_h = 3
    with c.lock:
        title, body = c.title, c.answer
    scr.addnstr(y, 1, title + ("  …" if c.busy else ""), width, curses.A_BOLD)
    y += 1
    room = h - footer_h - y - 1
    wrapped = []
    for para in body.split("\n"):
        wrapped += textwrap.wrap(para, width) or [""]
    for line in wrapped[-room:] if room > 0 else []:
        scr.addnstr(y, 1, line, width, curses.color_pair(3))
        y += 1

    # Pinned footer: the input line and the hotkey guide.
    scr.addnstr(h - 3, 0, "─" * w, w, curses.A_DIM)
    prompt = "Ask: " + c.input
    scr.addnstr(h - 2, 1, prompt[-width:], width, curses.A_BOLD)
    guide = " " + "  ·  ".join(GUIDE)
    scr.addnstr(h - 1, 0, guide[:w - 1].ljust(w - 1), w - 1, curses.color_pair(4))
    scr.move(h - 2, min(w - 2, 1 + len(prompt)))
    scr.refresh()


def main_loop(scr, c):
    curses.raw()                 # so Ctrl-S and Ctrl-Q reach us, not the tty
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_RED)
    curses.init_pair(2, curses.COLOR_YELLOW, -1)
    curses.init_pair(3, curses.COLOR_WHITE, -1)
    curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_CYAN)
    scr.keypad(True)
    scr.timeout(150)
    while True:
        draw(scr, c)
        k = scr.getch()
        if k == -1:
            continue
        act = None
        if k == curses.KEY_F1:
            act = "answer"
        elif k == curses.KEY_F2:
            act = "summary"
        elif k == curses.KEY_F3:
            act = "recent"
        elif k == curses.KEY_F4:
            act = "clear"
        elif k == curses.KEY_F10:
            act = "quit"
        elif k in CTRL:
            act = CTRL[k]
        if act == "quit":
            return
        if act == "answer":
            c.answer_last()
        elif act == "summary":
            c.summary()
        elif act == "recent":
            c.recent()
        elif act == "clear":
            c.title, c.answer = "Ready.", ""
        elif k in (10, 13, curses.KEY_ENTER):
            if c.input.strip():
                c.question(c.input.strip())
            c.input = ""
        elif k in (127, 8, curses.KEY_BACKSPACE):
            c.input = c.input[:-1]
        elif k == 21:            # Ctrl-U clears the line, as in a shell
            c.input = ""
        elif 32 <= k < 127:
            c.input += chr(k)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transcript", default=K.DEFAULT_TRANSCRIPT)
    a = ap.parse_args()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Start this from a login shell.")
    curses.wrapper(main_loop, Coach(a.transcript))


if __name__ == "__main__":
    main()
