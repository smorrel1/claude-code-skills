---
name: todo-agent
description: Two-way channel between Stephen's Apple Notes To Do list and his cmux agents. Prepends follow-up actions near the top of the note, and every five minutes picks up any line starting with claude (the @ is optional) and hands it to the Chief of Staff to do or delegate. Use when writing to the To Do note, or when asked how the pickup works.
---

# To Do agent

Stephen's To Do note is 100KB long and he reads the first page. Two things follow from that:
work written to the bottom is invisible, and the note is the natural place for him to give
instructions, because it is already open.

## Inbound: he writes, agents act

Start any bullet in a To Do note with `claude` and then the instruction. The `@` is optional
(19 Sep 2026: dictation and the phone keyboard both swallow it):

```
@claude get me the costings from Annie and put them in the grant budget
Claude: get me the costings from Annie
claude get me the costings from Annie
```

Every five minutes the launchd job reads THE PINNED NOTE ONLY (Stephen, 21 Sep 2026:
`state/target-note.json`, currently "To Do 21st Sept 2026 Mac"), finds instructions it has
not seen, and hands
each one to the **Chief of staff** workspace with the section heading above it for context. The
Chief of Staff does it or delegates it, then records the result back on the line:

```
@claude get me the costings from Annie ✅ delegated to the grants workspace (16:20)
```

The trigger must **open** the bullet, after any list marker or number. Claude mid-sentence is
prose about the tool, not an instruction to it, which is what keeps the note's own "how to use
this" line from firing.

Dropping the `@` puts the trigger one word away from ordinary prose, so a bare `claude` has to be
corroborated: either punctuation straight after the word (`Claude: ...`, `Claude, ...`) or an
imperative verb next (`claude draft ...`, from `IMPERATIVES` in the script). A bare `claude`
followed by anything in `STOPWORDS` ("Claude Code is...", "claude sessions keep dying") never
fires. A line that opens with `@claude` is trusted whatever follows, exactly as before.

The cost of this is quiet, not noisy: a verb missing from `IMPERATIVES` means the line is
ignored rather than something wrong being run, so add the verb and it fires next time. Both
lists live at the top of `scripts/todo_agent.py`, and `tests/test_trigger.py` covers them:

```bash
python3 ~/.claude/skills/todo-agent/tests/test_trigger.py
```

## Outbound: agents write, he reads

```bash
cat > /tmp/items.json << 'JSON'
[
  {"bold_lead": "Send the costing to Raj: ", "text": "figures due Wed 16 Sep.",
   "children": ["Check the PPIE line with Alice first"]},
  {"text": "Review and send the Andy draft (drafted 7 Sep)."}
]
JSON
python3 ~/.claude/skills/todo-agent/scripts/todo_agent.py \
  prepend --heading "Clarity call follow-ups (added 8 Sep)" --items /tmp/items.json
```

New sections land immediately after the **Strategy** section, above `CLARITY`. `children` become
indented sub-bullets, which is how he organises subtopics so he can drag them around. Add
`--ordered` for a numbered list. `--dry-run` shows the insertion point and the HTML without
writing.

## Commands

| Command | What it does |
|---|---|
| `scan [--dry-run]` | Find new instructions and hand them over. Runs every 5 min |
| `list` | Show every trigger line and whether it has been picked up |
| `mark <id> "<outcome>"` | Put the tick and outcome on the line. The Chief of Staff calls this |
| `prepend --heading H --items F` | Insert a section below Strategy |
| `target` | Show which note writes go to |
| `use-note <id-fragment>` | Repin the target note, e.g. after starting a new month's list. This is also what the scan reads, so repinning moves pickups to the new note |
| `normalise [--cap 36]` | Pull runaway heading sizes back down after another writer inflated them |

## Four things about Apple Notes that this tool exists to handle

All measured on 8 Sep 2026, none of them documented by Apple.

**1. Every whole-body write multiplies font sizes by 1.2, and it compounds.** A 20px heading
becomes 24, then 29, then 35, then 42 across four writes. 16px is a fixed point and is left alone.
Stephen's note carries 158px headings because roughly eight past agent rewrites each inflated
everything already there. That is a large part of why the list feels overwhelming. `set_body()`
pre-deflates every size so a write is size-neutral; verified stable across five consecutive
rewrites of the real 100KB note. **Never call `set body of note` directly.** Doing so permanently
degrades the note every single time.

**2. A note's name comes from its first line.** Copy the To Do list and the copy is instantly also
called "To Do 8th Sept 2026." and, being newer, wins any "most recently modified" search. Two test
clones did exactly this. Writes therefore go to a note pinned by Core Data id
(`state/target-note.json`), and the tool refuses to guess when two candidates share a name.

**3. Discovery is slow, direct access is not.** Listing To Do notes takes about 14 seconds because
Notes walks the folder over Apple Events; reading the pinned note by id takes 0.4. So the
five-minute scan works from the pin, and discovery runs at most hourly (`state/discovered-notes.json`).
Scope any query to `notes of folder "Notes"`: an unscoped `every note` also walks Recently Deleted,
which returned three notes all called "To Do 8th Sept 2026." and is 60% slower.

**4. Notes fragments your markup.** An emoji written inside a span comes back in a span of its own,
so `@claude ✅` is not contiguous in the HTML even though it is in the text. Match markers against
`strip_tags()` output, never against raw HTML.

## What went wrong on 9 Sep 2026, and what changed

Stephen wrote an `@claude` instruction at 11:00. It was never delivered, and the
job reported "nothing new" for two hours afterwards while looking perfectly
healthy. Four separate defects, all now fixed:

1. **cmux's socket was returning "Broken pipe" all morning**, so every delivery
   attempt failed. That was the trigger, not the bug.
2. **Three retries in fifteen minutes, then it gave up and filed the instruction
   as delivered.** From that moment the instruction was invisible: no log line,
   no reminder, nothing in the note. Retries now run for two hours, then back off
   to hourly and continue forever, and a stuck instruction is printed on EVERY
   run. A failed delivery is never recorded as delivered.
3. **Instruction ids were hashed on the note's NAME.** Stephen retitled the note
   from "To Do 8th Sept" to "To Do 9th Sept" and every id in it changed. The pin
   file also cached the old name, so the same instruction had two identities.
   Ids now hash on the note's Core Data id, and the pin refreshes its cached name.
4. **It fired on a half-typed line.** At 10:59 it picked up the single word "eve"
   while he was still typing "every day at midday...". A note edited in the last
   two minutes is now left to settle.

Lesson worth keeping: a scheduled job that says "nothing new" is indistinguishable
from one that is quietly broken. Anything it gives up on has to keep shouting.

## 15-17 Sep 2026: "Access denied" after the cmux 0.64.23 update

cmux 0.64.23 defaults Socket Control Mode to "cmux processes only". This job runs from
launchd, outside cmux, so every hand-off was refused for two days while `@claude` lines
piled up. Fix: switch the mode to Password (`scripts/enable_cmux_socket_password.sh`,
run by Stephen). `run.sh` exports `CMUX_SOCKET_PASSWORD` from
`state/cmux-socket-password` (0600). Sessions inside cmux connect without it. If
"Access denied" returns after a cmux update, check that setting first.

Other To Do notes are ignored, including the phone list. Reading every recent one meant the
17 Sep phone/Mac merge delivered three instructions twice, once per copy, because ids hash on
the note id. Renaming a note is safe: the pin follows the Core Data id, so "To Do 9th Sept 2026
Mac" becoming "To Do 21st Sept 2026 Mac" re-fired nothing.

## 19 Sep 2026: edit this script on a copy

The @ was made optional here while the launchd job was running the same file every 30
seconds. It ran a half-saved version, crashed in `find_instructions`, and re-delivered an
instruction that had been done on 14 Sep. Edit a copy, run `scan --dry-run` against it, and
only then move it into place. The 30-second cadence leaves no safe window.

The same day, `mark` put an outcome on the wrong bullet: it fell back to the stored line
index, and the note had been edited since delivery. `mark` now finds the line by its own
words, prefers the unticked copy when the merge left two, and refuses to write at all
rather than guess.

## 21 Sep 2026: a send is not a submit

Twice today a task was sent to a workspace and never submitted: `cmux send` fills the input
box, Enter submits it, except that a multi-line paste arrives as a block and the first Enter
only expands it. The sender saw no error. Delivery now goes through
`~/.claude/skills/cmux/scripts/send_task.py`, shared with every other delegation: the brief is
written to `state/pickups/` and the workspace is sent one short line pointing at it, then Enter
up to three times, with the screen re-read between each. A delivery that cannot be seen running
is reported, never recorded as done.

## It now says so out loud

A shut channel used to show up only in the log. On 24 Sep 2026 cmux's socket mode changed and
every hand-off was refused for most of a day, while two of Stephen's instructions sat
undelivered through 25 and 29 retries. `run.sh` now posts a macOS notification, at most one an
hour, when the log or the scan shows a lockout ("Access denied", "no socket password",
"auth_required") or any STUCK instruction. Verified firing from launchd, not just from a
terminal. The hourly timer is `state/last-alert`; delete it to be nagged again at once.

The lockout itself: cmux owns `~/.config/cmux/cmux.json` and rewrites it whenever a setting
changes, in its own style, comments stripped. `socketPassword` is meant to leave that file,
since cmux moves it into `~/.local/state/cmux/socket-control-password`. Switching the mode away
from Password DELETES that store, so switching back leaves password mode with no password.
Cure: re-run `scripts/enable_cmux_socket_password.sh`, which reads the file in whatever shape
it is in and sets both keys.

## Safety

- Every write backs the previous body up to `backups/` first, timestamped.
- Headings are capped at 36px, Stephen's stated ceiling.
- A delivery that cannot be confirmed as started is **not** recorded as done. It retries every run
  for two hours, then hourly forever, and is reported on every single run until it goes through.
  An instruction must never vanish silently.
- cmux's socket goes unresponsive when sessions are busy (`cmux tree` answered in 0.18s at 14:16
  on 8 Sep and was timing out at 15s by 14:50). Every cmux call tolerates that and the job still
  exits 0.
- The Chief of Staff prompt says drafts only. The global send guard applies to anything it
  delegates.

## Where things live

```
~/.claude/skills/todo-agent/
  scripts/todo_agent.py     the tool
  run.sh                    launchd entry point: refresh registry, then scan
  state/target-note.json    the pinned note
  state/seen-instructions.json
  backups/                  every prior body, timestamped
  logs/todo-agent.log       quiet ticks logged hourly, anything else every time
~/Library/LaunchAgents/com.stephen.todo-agent.plist    every 300s
```

Check it is running: `launchctl list | grep todo-agent`.
