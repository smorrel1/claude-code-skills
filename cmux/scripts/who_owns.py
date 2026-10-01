#!/usr/bin/env python3
"""Find which Claude Code session / cmux workspace owns a topic, contact, or PID.

Usage:
  who_owns.py <keyword> [keyword2 ...]   # search topic/contact across history + transcripts
  who_owns.py --pid <pid>                # trace a running process to its session

Output: candidate sessions with sessionId, project, workspace tty (if live), and matching prompts.
"""
import json, os, re, subprocess, sys, glob

CLAUDE = os.path.expanduser("~/.claude")
CMUX = "/Applications/cmux.app/Contents/Resources/bin/cmux"


def pid_lookup(pid):
    out = subprocess.run(["ps", "eww", str(pid)], capture_output=True, text=True).stdout
    m = re.search(r"CLAUDE_CODE_SESSION_ID=([a-f0-9-]+)", out)
    if not m:
        print(f"PID {pid}: no CLAUDE_CODE_SESSION_ID in environment (not spawned by a Claude session)")
        return
    sid = m.group(1)
    print(f"PID {pid} -> session {sid}")
    for f in glob.glob(f"{CLAUDE}/projects/*/{sid}.jsonl"):
        print(f"  transcript: {f}")
    cpid = re.search(r"CMUX_CLAUDE_PID=(\d+)", out)
    if cpid:
        tty = subprocess.run(["ps", "-o", "tty=", "-p", cpid.group(1)], capture_output=True, text=True).stdout.strip()
        print(f"  claude PID {cpid.group(1)} tty={tty}")
        tree_tty(tty)


def tree_tty(tty):
    """Map a tty to its cmux workspace via `cmux tree --all`."""
    try:
        tree = subprocess.run([CMUX, "tree", "--all"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return
    ws = None
    for line in tree.splitlines():
        wm = re.search(r'workspace (workspace:\d+) "([^"]+)"', line)
        if wm:
            ws = wm.groups()
        if tty and f"tty={tty}" in line and ws:
            print(f"  cmux workspace: {ws[0]} \"{ws[1]}\"")


def keyword_search(keywords):
    kws = [k.lower() for k in keywords]
    hits = {}
    # 1. history.jsonl — survives transcript deletion
    hist = os.path.join(CLAUDE, "history.jsonl")
    if os.path.exists(hist):
        for line in open(hist, errors="ignore"):
            try:
                j = json.loads(line)
            except json.JSONDecodeError:
                continue
            d = (j.get("display") or "").lower()
            if any(k in d for k in kws):
                sid = j.get("sessionId")
                hits.setdefault(sid, {"project": j.get("project"), "prompts": []})
                hits[sid]["prompts"].append(j.get("display", "")[:110])
    # 2. transcript grep (catches assistant-side mentions)
    pat = "\\|".join(re.escape(k) for k in kws)
    g = subprocess.run(
        ["grep", "-ril", pat] + glob.glob(f"{CLAUDE}/projects/*") ,
        capture_output=True, text=True).stdout
    for f in g.splitlines():
        m = re.search(r"/([a-f0-9-]{36})\.jsonl$", f)
        if m and m.group(1) not in hits:
            hits[m.group(1)] = {"project": os.path.dirname(f), "prompts": ["(transcript mention only)"], "file": f}
    if not hits:
        print("No sessions found for:", " ".join(keywords))
        return
    for sid, info in hits.items():
        tf = glob.glob(f"{CLAUDE}/projects/*/{sid}.jsonl")
        alive = "transcript exists" if tf else "TRANSCRIPT DELETED (history.jsonl only)"
        mtime = ""
        if tf:
            import datetime
            mtime = " last-active " + datetime.datetime.fromtimestamp(os.path.getmtime(tf[0])).strftime("%Y-%m-%d %H:%M")
        print(f"\nsession {sid}  [{alive}]{mtime}")
        print(f"  project: {info.get('project')}")
        for p in info["prompts"][:4]:
            print(f"  prompt: {p}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(1)
    if args[0] == "--pid":
        pid_lookup(args[1])
    else:
        keyword_search(args)
