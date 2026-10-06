---
name: cmux
description: Manage Stephen's 30-50 Claude Code sessions running in cmux workspaces. Use when asked "which session/workspace handles X", to delegate a task to another session, foreground a workspace, prep for a call using another session's context, get a status roll-up across all sessions, or trace a running process to its owning session. Also invocable as /cmux with subcommands who-owns, delegate, status, brief.
---

# cmux Session Management

Binary: `CMUX=/Applications/cmux.app/Contents/Resources/bin/cmux`

## Who owns a topic / contact / process

Run `scripts/who_owns.py <keywords>` (or `--pid <pid>`). It searches `~/.claude/history.jsonl` (survives transcript deletion) plus transcript grep, and maps PIDs via `CLAUDE_CODE_SESSION_ID` env. Then:

1. Check `references/registry.md` first for an instant answer; update it with anything newly learned.
2. Map session -> workspace: transcript cwd/project narrows it; live processes give a tty; `$CMUX tree --all` maps tty -> workspace ref and title.
3. Verify by topic, not keyword density: read the candidate's first user message and last assistant message before asserting a match. Short substrings of a name or acronym produce false positives.
4. If no transcript exists, the session was auto-deleted; its prompts survive in history.jsonl. Say so explicitly.

## ALWAYS refer to workspaces by NAME, never by number (Stephen, 4 Sep 2026)

In all user-facing text, identify workspaces by their title ("Accountant", "my ai tools", "grant applications"), never "workspace:16". Numbers are for tool calls only; they drift across restarts and mean nothing to Stephen.

## Choosing the target: task NATURE beats topic ownership

Route by what kind of work it is, rather than by whose content it touches:

- **Content work** (drafts, briefs, analysis) -> the session with the richest topic context.
- **Debugging / tooling / pipeline failures** (broken attachments, corrupt PDFs, script errors) -> Stephen's tooling workspace ("my ai tools"), NOT the content owner. A session that has already failed to fix a bug several times has negative context - its failed assumptions travel with it. Fresh eyes + validation discipline beat topic familiarity.
- Also weigh queue load: do not stack tasks on an already-loaded critical session (e.g. Plan A during a round close) when the task is separable.
- **Technical/engineering issues (imaging formats, integrations, pipeline, transcription tooling) go to a session whose cwd is the relevant CODE repo**, NEVER to a session working in the documents folder (those are document and comms sessions). The user flagged a mis-route on 4 Sep 2026.
- Transcript sources: a meeting transcript may live in either of two accounts, a personal one reachable over MCP and a work one reachable only through local downloader scripts. Check both before saying a transcript does not exist.

## Delegate a task to another session

### 1. Pick an IDLE session (Stephen, 30 Sep 2026)

"In general choose delegates that are currently inactive for the last few hours if
possible, and check which one if any doubt. Try not to clash with live subjects."

```bash
python3 ~/.claude/skills/cmux/scripts/idle_rank.py --min-idle 2      # the shortlist
python3 ~/.claude/skills/cmux/scripts/idle_rank.py --match grant deck
python3 ~/.claude/skills/cmux/scripts/idle_rank.py --all --top 12    # busy ones too
```

It prints hours idle, a verified busy flag, the workspace name, its live
`workspace:` and `surface:` refs, the bound session id and the panel's cwd,
idlest first. Rows showing `?` have no Claude bound to the panel (a bare shell,
a fresh second pane) and are never candidates; they sort last and are counted in
a line under the table, so a handful of them cannot be mistaken for a total
failure.

- **Idleness** is the timestamp on the last entry INSIDE each panel's transcript,
  not the file's mtime. A bulk `restore_bindings.py` pass rewrites every
  transcript, so on 30 Sep 2026 sixty-one sessions all read as exactly 54h idle
  off mtime while their real last turns ran between 14 and 25 Sep.
- **Busy** is "esc to interrupt" on that panel's screen, checked per candidate at
  about 0.14s each (a whole sweep is ~8s). Do not trust the braille spinner in a
  cmux label: cmux paints it into the workspace TITLE, and some titles contain
  one already, so workspace:3 read as idle in the label while it was mid-task.
- **Prefer 2+ hours idle** where the subject fits. Skip a busy owner unless no
  idle session has the context, and say so when you do.
- **Do not clash with a live subject.** If a busy session is working a topic, do
  not hand an idle session a task that would touch the same files or the same
  email thread, even when the idle session nominally owns it. The `CWD` column is
  the quick test for file overlap; two sessions in `2026 Round docs` will collide.
  On 30 Sep the user excluded two workspaces himself because both were live.
- **When the choice is unclear, ASK.** Two plausible idle candidates, or only a
  busy owner fits: put the ranked shortlist (name, hours idle, why each fits) to
  the Chief of staff or to Stephen and let them pick. Do not guess.

Then the nature rules above still apply: content to the richest context, tooling
and debugging to "my ai tools", code to a `~/code` session.

### 2. Resolve the target by NAME, at the moment of sending

Numbers are not identity. `cmux tree --all` reorders on every delegation, and on
29 Sep 2026 a brief meant for a grants session landed in a finance session off a number
cached minutes earlier. Never take a `workspace:N` from the registry table, from
notes, or from earlier in the conversation: re-read the tree (or re-run
`idle_rank.py`, which does) and match on the title, immediately before sending.

**Address the surface, not just the workspace, when a workspace has more than one
pane.** A send to a workspace lands in its focused pane, which may hold a
different Claude, or a bare shell. `idle_rank.py` prints `PANES`; where that is
greater than 1, pass the `surface:` ref of the idle panel.

### 3. Send it and prove it started

```bash
python3 ~/.claude/skills/cmux/scripts/send_task.py --workspace "grant applications" --file brief.md
python3 ~/.claude/skills/cmux/scripts/send_task.py --workspace "my ai tools" "one short instruction"
```

**Address a workspace by NAME, never by number** (Stephen, 30 Sep 2026). `send_task.py` now
refuses a bare number and resolves the name against the live tree. Numbers drift on every
reorder and have misrouted briefs twice: on 29 Sep a grants brief into a finance session, on
30 Sep an email-tooling report into "health personal". A name matching nothing, or several
workspaces, stops and lists the candidates instead of guessing.

`--workspace` takes a NAME, never a number, and refuses a numeric ref outright.
An unattended caller (the todo-agent job, any cron) must preflight with
`--dry-run`, which resolves the name and the bound session and types nothing:
without that, a change to this contract shows up as weeks of silent retries
rather than one loud failure. That is exactly what happened from 09:18 on
1 Oct 2026, when the todo-agent was still passing the number it had looked up.

Do not hand-roll `cmux send` + `send-key Enter`: that is what failed twice on
21 Sep 2026, leaving tasks sitting unsubmitted in the target's input box while the
sender reported success.

Anything multi-line or over 300 characters is written to
`state/tasks/<date>-<slug>-brief.md` and the target gets a one-line pointer to it
carrying a marker phrase (`--slug` names the file). One line submits on the first
Enter; a multi-line paste arrives with a "paste again to expand" hint, so the
first Enter only expands the block.

Exit codes, all three of which mean something different to Stephen:

| # | Exit | Meaning | What to do |
|---|------|---------|------------|
| 1 | 0 | CONFIRMED: the marker is in that session's own transcript and an assistant turn followed it | report it as running |
| 2 | 1 | not submitted, or never confirmed | report the failure and the screen; do not claim delivery |
| 3 | 2 | FAILED: it took the brief but cannot work it (usage limit, API error, /login) | re-route to the next idle candidate and tell the Chief of staff which session failed and why |

**Arrival is not work (Stephen, 30 Sep 2026).** The IUK session took a brief and
did nothing because its usage credits were exhausted, and the screen looked
delivered. So confirmation reads the TARGET'S OWN transcript:

- the marker phrase must appear in a real prompt entry there, which also catches a
  brief that landed in the wrong panel (a tool result quoting the marker does not
  count, or a session could confirm itself);
- an assistant turn, tool call or text, must follow that prompt;
- any `isApiErrorMessage` entry after it, or error wording on screen (usage limit
  reached, out of credits, credit balance is too low, rate limit exceeded,
  /login), is a FAILED delegation, not a slow one. This is only ever considered
  when the session is NOT visibly running: the screen shows the target's content
  as well as its state, and on 1 Oct 2026 a healthy session was called blocked
  while it was reading a report that discussed being out of credits. A session
  that is mid-task cannot be out of credits;
- nothing at all within about 60 seconds counts as not started: check the screen
  rather than assuming.

Write the brief self-contained: the target lacks this conversation's context.
Names, emails, paths, deadlines, and the constraints that matter
("do NOT delete Stephen's existing draft"). 100% context in the target is OK (it
auto-compacts) but warn that detail may be lost. Prefer `SendMessage` to a peer
from `ListAgents` only when the peer's identity is certain; peer names (e.g.
"documents-32") often do not match workspace titles.

### 4. Housekeeping, all four, every time

```bash
$CMUX workspace-action --action pin --workspace workspace:N   # 1. pin it
$CMUX reorder-workspace --workspace workspace:N --index 0     # 2. move to top of queue
$CMUX select-workspace --workspace workspace:N                # 3. foreground it
# 4. inform Stephen: workspace NAME, what was sent, and which exit code came back
```

Reordering renumbers everything, so any `workspace:N` you were holding is stale
from this point. Re-resolve by name before the next send.

When delegating to several workspaces in one batch, pin+reorder each, foreground
the highest-priority one last, and report all by workspace title.

## A relaunch can leave a DUPLICATE window

Sometimes cmux restores the saved window AND rebuilds another for the resumed
sessions. The rebuilt one holds the live sessions; the restored one holds bare shells
printing "This agent session is already running in process N", and every session is
bound to two panels. On 6 Oct 2026 that was 74 duplicate workspaces and 142 double
bindings, which `restart_sessions.py` reports as DOUBLE BOUND.

```bash
python3 ~/.claude/skills/cmux/scripts/prune_twin_window.py --window window:2
python3 ~/.claude/skills/cmux/scripts/prune_twin_window.py --window window:2 --apply
```

It closes a workspace only when its screen, read at that moment, shows no running
Claude AND positively reads as a shell prompt AND no live claude process is bound to
its panel AND every session it carries is also bound in the window being kept. It
refuses the window that holds the live sessions outright.

Things that cost time on 6 Oct, now handled:

- **An unreadable surface reads as empty**, which looks exactly like a bare shell.
  Hence the positive shell test. To read one, `select-workspace` to materialise it,
  wait about 3 seconds, then read again.
- **The tree's tty for a twin is the SAME tty as the live original**, so checking
  `ps` by tty says every twin has a live claude. It does not. The screen is the
  ground truth; the tty is not.
- **Browser panes are content, not duplication.** Four workspaces held pages opened
  by hand (claude.ai settings, the website, an artifact, a PDF). The script closes
  only the duplicate terminal pane inside such a workspace and leaves the rest.
- **cmux refuses to close the last surface** in a workspace and spawns a fresh shell
  instead, which looks like a failure.
- **Pinned workspaces refuse to close.** Unpin first; the script does.

Move anything left into the keeping window (`move-workspace-to-window`), then
`cmux close-window --window window:2`. Afterwards `restart_sessions.py` should report
0 DOUBLE BOUND, which is also what stops the next relaunch from repeating it: the
duplication is restored FROM the saved state, so a state file carrying each session
once cannot produce it.

## Workspace ORDER does not survive a relaunch

cmux does not restore the order of workspaces. Measured 6 Oct 2026: the saved state
held one window of 78 workspaces, the relaunch produced two windows, one holding the
old order with only bare shells in it and the other holding all 79 live sessions in a
different order, a median of 4 places out and one workspace 50 places from where it
had been. An order built over weeks, most-used at the top, is lost every restart.

So it is snapshotted from outside, by title, every 30 seconds by the todo-agent job:

```bash
python3 ~/.claude/skills/cmux/scripts/workspace_order.py snapshot   # the job does this
python3 ~/.claude/skills/cmux/scripts/workspace_order.py restore    # dry run
python3 ~/.claude/skills/cmux/scripts/workspace_order.py restore --apply
python3 ~/.claude/skills/cmux/scripts/workspace_order.py list       # what is held
```

After a relaunch, do both halves:

```bash
python3 ~/.claude/skills/cmux/scripts/restart_sessions.py --order            # check
python3 ~/.claude/skills/cmux/scripts/restart_sessions.py --apply --order    # fix both
```

Three things worth knowing:

- **It restores from the last snapshot taken BEFORE cmux started**, never the newest.
  The job snapshots every 30 seconds, so by the time anyone notices a scrambled
  relaunch the newest snapshot is the scramble. With no snapshot older than the
  current cmux, it refuses rather than shuffling to a bad order.
- **Refs are resolved at the moment of each move.** Every reorder renumbers the
  workspaces after it, so a list of refs read up front is wrong by the second move.
- **Duplicate titles are handled by occurrence.** Many bare shells share one title
  ("user@host: ~/path"), and matching on title alone made them fight over one ref.

It preserves the recorded order exactly and does not re-sort pinned workspaces to the
top: cmux already shows them where the snapshot recorded them, and forcing pinned
first moved four workspaces that were where Stephen had put them.

## Foreground a workspace

```bash
$CMUX select-workspace --workspace workspace:N
```

## Reviving a dead workspace

**NEVER use bare `claude --continue` to revive a workspace.** Workspaces share cwds, and --continue attaches the newest conversation in the directory. On 9 Sep 2026 that bound seven conversations into two workspaces each. Always resume by session id.

**Restarting all sessions (after a cmux update, crash or reboot):** cmux 0.64.23+ does it natively. Each terminal panel stores its Claude `sessionId` and a `resumeBinding` (`claude --resume <id>`, `autoResume: true`), so relaunching cmux resumes every session into its own panel. Then verify:

```bash
python3 ~/.claude/skills/cmux/scripts/restart_sessions.py           # report
python3 ~/.claude/skills/cmux/scripts/restart_sessions.py --apply   # restore any NOT RUNNING by id
```

It compares cmux's per-panel binding with `~/.claude/sessions/<pid>.json` (the session each live process really is, tied to its panel via `CMUX_PANEL_ID`). Never judge from screen text: on 15 Sep a screen sweep called six workspaces dead and a process-env check called all 66 fine, and both were wrong in different ways. `--apply` types `cmux restore claude <id>` into the panel; cmux refuses to start a copy already running elsewhere, so it cannot collide.

**If the relaunch DROPPED bindings (report shows many LOST BINDING rows), `--apply` will not fix those**, because the current state file no longer knows what belonged where. Use the bulk restorer, which reads the previous state file and restores by session id:

```bash
python3 ~/.claude/skills/cmux/scripts/restore_bindings.py            # dry-run plan
python3 ~/.claude/skills/cmux/scripts/restore_bindings.py --apply    # execute (~2.5s per session)
```

It only touches panels that still exist, are unbound, whose session is not running anywhere, and whose transcript exists. A session previously bound to TWO panels is skipped unless you pass `--pick sid8="title substring"` after identifying the right home from the transcript's topic (first + recent user messages), e.g. `--pick 0fd5f37d="DeepLook negotiation"`. Panels occupied by a process (a fresh or wrongly-placed claude) are never touched: evict those by typing `/exit` into that panel, then `cmux restore claude <id>` there. First run 17 Sep 2026: 64 of 67 lost bindings restored in one pass; the leftovers were two live copies of one conversation squatting in the wrong panels.

A shell showing `Error: restore: this agent session is already running in process N` is a **fork leftover**: its conversation runs in a twin workspace. Do not force it. Either close the leftover, or stop the twin and run `cmux restore --surface` there, which is Stephen's call on which workspace should own the conversation.

Workspaces not viewed since a cmux restart have `in_window=false` surfaces (`$CMUX surface-health --workspace N`); read-screen/send fail with "Terminal surface not found". Fix: `select-workspace` to materialize it, wait ~4s. A dead Claude REPL usually auto-restores with a resume dialog (choose "Resume from summary": send-key Enter). Otherwise send `claude --resume SESSION_ID` in the right cwd.

## Call-prep briefs

Given a person/meeting: `who_owns.py <surname> <company>` + email search (email skill) to find the owning session and the actual relationship (verify who the person IS: "a VC" may turn out to be a founder). If the owning session is live, delegate the brief to it; if deleted or unreachable, build the brief here from its transcript file + history.jsonl + email. Brief = who they are, how introduced, what they already know, suggested angles, open items.

## Status roll-up

Run `scripts/status_rollup.sh` for a WORKING / NEEDS INPUT / idle sweep of every workspace with last screen lines. Summarize for Stephen as: working on what, blocked on what, idle.

## Registry

Two files, one generated and one hand-written:

- **`references/registry.md`** is GENERATED. Read it, never edit it. It joins the live
  `cmux tree --all` (number, title, running/idle, tty, cmux queue order) onto the durable notes.
- **`references/registry-durable.md`** is hand-written and keyed on workspace **TITLE**. Topic,
  key contacts, session id, and anything hard-won. Add a row whenever a lookup resolves something
  new. Titles, not numbers, because cmux renumbers on every reorder.

```bash
python3 ~/.claude/skills/cmux/scripts/refresh_registry.py           # regenerate
python3 ~/.claude/skills/cmux/scripts/refresh_registry.py --check   # exit 1 if stale
```

**You no longer need to reconcile it by hand.** It regenerates automatically after any Bash
command containing a `cmux send`/`reorder`/`select-workspace`/`workspace-action` (PostToolUse hook
`~/.claude/hooks/refresh-cmux-registry.sh`, about 0.2s) and every five minutes from the todo-agent
job. The old standing instruction to re-run `tree --all` and fix the table before every delegation
existed because the file was keyed on numbers and was wrong by default: on 8 Sep 2026 it claimed
workspace:1 was "Plan A & Involvency" when workspace:1 was "Chief of staff" and Plan A had become
workspace:5.

A workspace whose title has durable notes but no live workspace drops into a "Not currently open"
section rather than being deleted. Reopen it before delegating; do not guess a number for it.

**If cmux is congested**, `cmux tree` stops answering and times out after about 15s (seen 8 Sep
2026: 0.18s at 14:16, timing out by 14:50). The generator then leaves the existing file alone
rather than truncating it, so a stale table is the worst case, never an empty one.

## Gotchas

- **Broken/ghosted pane rendering after a pane resize** (stacked duplicate status bars, stale
  separator rows over live content; seen 17 Sep 2026): fix with `$CMUX refresh-surfaces`, then
  `$CMUX send-key --workspace workspace:N ctrl+l` to make the Claude TUI clear-and-repaint. Both
  are safe on a running session. Verify visually (screencapture of the cmux display), not with
  read-screen, which shows the logical buffer, which is fine even when the paint is broken.
  Note `screencapture -x f1.png f2.png f3.png` captures one file per display; cmux usually lives
  on the ultrawide (second file).
- `ps lstart` times mislead; trust `ps eww` env vars for ownership.
- cmux state file (`~/Library/Application Support/cmux/session-com.cmuxterm.app.json`) records per panel: title, cwd, tty, and since 0.64.x the Claude `terminal.agent.sessionId` plus `resumeBinding`. `session-com.cmuxterm.app-previous.json` is the pre-relaunch copy.
- Transcript retention: `cleanupPeriodDays` in `~/.claude/settings.json` (set to 99999).
- `cmux rpc listSurfaces` does not exist; use `tree --all`.
- Avoid `===` in zsh compound commands (parse errors).

## Relaunch failure mode: double-bound sessions (16 Sep 2026)

If a session id is bound to TWO panels in the state file (fork leftovers from the 9 Sep bare
`claude --continue` incident, or a workspace opened twice on one conversation), a relaunch resumes
it in only one panel; the twin silently loses its binding (bare shell showing `Error: restore: this
agent session is already running in process N`) or gets a FRESH claude with no context. The plain
report then says "all CORRECT" because the orphaned panel is no longer bound. `restart_sessions.py`
now diffs against `session-com.cmuxterm.app-previous.json` and reports `LOST BINDING` (with which
workspace now holds the conversation) and `DOUBLE BOUND` (fix BEFORE the next relaunch: close the
twin). Deciding which workspace of a pair keeps the conversation is Stephen's call; then in the
loser send `/exit`, and in the keeper run `cmux restore --surface` if it is not already there.
