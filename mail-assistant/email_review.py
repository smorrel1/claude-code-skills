#!/usr/bin/env python3
"""Midday email review: fetch, then render a decision page Stephen can act on.

Stephen's instruction, 9 Sep 2026: "every day at midday review my new emails
received since your last review and make an html page by priority with suggested
draft or guidance requests and let me give consolidated feedback for your action."

Three separate steps on purpose, so the model only does the part that needs
judgement and the page itself is deterministic:

  fetch   pull everything that arrived since the last review (48h on first run)
          and write inbox.json. No model, no judgement.
  page    turn a reviewed.json into the HTML. No model. The layout, the controls
          and the feedback format are fixed so they behave the same every day.
  mark    record that a review completed, which moves the "since" watermark.

Between fetch and page, `claude -p` reads inbox.json and writes reviewed.json:
priority, one-line summary, and either a suggested draft or a question for
Stephen. That is the only step with a model in it.

Nothing here dispatches mail. The page's one button sends Stephen's decisions
to the Claude session that made it (paste_back_server.py); copy is the fallback.
"""
import argparse
import html
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

SKILL = Path(__file__).resolve().parent
STATE = SKILL / "state"
LAST_REVIEW = STATE / "last-review.json"
EMAIL_SCRIPTS = Path.home() / ".claude" / "skills" / "email" / "scripts"

ACCOUNTS = ["work", "gmail"]
FIRST_RUN_HOURS = 48
MAX_PER_ACCOUNT = 120

PRIORITIES = [
    ("urgent", "Needs you today", "#b3261e"),
    ("reply", "Reply owed", "#8a5a00"),
    ("guidance", "Needs your steer", "#1a5fb4"),
    ("fyi", "Read only", "#5f6368"),
]


# ------------------------------------------------------------------- watermark

def since_iso():
    """When the last review finished. First ever run looks back 48 hours."""
    if LAST_REVIEW.exists():
        try:
            return json.loads(LAST_REVIEW.read_text())["at"]
        except (ValueError, KeyError):
            pass
    return (datetime.now() - timedelta(hours=FIRST_RUN_HOURS)).isoformat(timespec="seconds")


def cmd_mark(_):
    STATE.mkdir(exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")
    LAST_REVIEW.write_text(json.dumps({"at": now}, indent=1))
    print("Review watermark moved to %s" % now)
    return 0


# ----------------------------------------------------------------------- fetch

EXPECTED = {
    "work": "stephen.morrell@elaitra.com",
    "gmail": "stephen.morrell@gmail.com",
}


def gmail(account):
    """Build a Gmail service for one account, and PROVE it is that account.

    The switch is `CURRENT_ACCOUNT`, not `ACCOUNT`. Setting the wrong attribute
    fails silently: on 9 Sep 2026 the first run of this script fetched the work
    mailbox twice and labelled half of it "gmail", producing 54 duplicate items
    that looked like real personal mail. Reading the wrong mailbox is invisible
    unless something checks, so this checks.
    """
    sys.path.insert(0, str(EMAIL_SCRIPTS))
    import gmail_utils
    gmail_utils.CURRENT_ACCOUNT = account
    svc = gmail_utils.get_gmail_service()
    actual = svc.users().getProfile(userId="me").execute()["emailAddress"]
    want = EXPECTED.get(account)
    if want and actual.lower() != want.lower():
        raise RuntimeError("account switch failed: asked for %s (%s), got %s"
                           % (account, want, actual))
    return svc


def header(msg, name):
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def fetch_account(account, after_epoch):
    """Everything that ARRIVED in the inbox since the watermark.

    Deliberately `in:inbox`: mail already filed by the spam rules, or sent by
    Stephen, is not part of a review of what needs his attention.
    """
    svc = gmail(account)
    q = "in:inbox -in:chats after:%d" % after_epoch
    ids, page = [], None
    while True:
        r = svc.users().messages().list(userId="me", q=q, maxResults=100,
                                        pageToken=page).execute()
        ids += [m["id"] for m in r.get("messages", [])]
        page = r.get("nextPageToken")
        if not page or len(ids) >= MAX_PER_ACCOUNT:
            break

    out = []
    for mid in ids[:MAX_PER_ACCOUNT]:
        m = svc.users().messages().get(
            userId="me", id=mid, format="metadata",
            metadataHeaders=["From", "To", "Cc", "Subject", "Date", "Message-ID"]).execute()
        out.append({
            "account": account,
            "id": mid,
            "thread_id": m.get("threadId"),
            "from": header(m, "From"),
            "to": header(m, "To"),
            "cc": header(m, "Cc"),
            "subject": header(m, "Subject"),
            "date": header(m, "Date"),
            "snippet": m.get("snippet", "")[:600],
            "unread": "UNREAD" in m.get("labelIds", []),
            "labels": [l for l in m.get("labelIds", []) if not l.startswith("Label_")],
        })
    return out


def cmd_fetch(a):
    since = a.since or since_iso()
    after_epoch = int(datetime.fromisoformat(since).timestamp())
    all_msgs = []
    for acct in ACCOUNTS:
        try:
            got = fetch_account(acct, after_epoch)
            print("  %-6s %3d message(s) since %s" % (acct, len(got), since))
            all_msgs += got
        except Exception as exc:
            # One dead token must not sink the whole review.
            print("  %-6s FAILED: %s" % (acct, str(exc)[:120]))

    STATE.mkdir(exist_ok=True)
    out = Path(a.out)
    out.write_text(json.dumps({"since": since, "fetched_at": datetime.now().isoformat(
        timespec="seconds"), "messages": all_msgs}, indent=1))
    print("%d message(s) written to %s" % (len(all_msgs), out))
    return 0


# ------------------------------------------------------------------------ page

CSS = """
:root{--bg:#fff;--fg:#1b1b1f;--muted:#5f6368;--line:#e3e3e6;--card:#fafafa;--accent:#1a5fb4}
@media (prefers-color-scheme:dark){:root{--bg:#131316;--fg:#e6e6e9;--muted:#a0a0a8;--line:#2c2c31;--card:#1b1b20}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.wrap{max-width:920px;margin:0 auto;padding:28px 20px 120px}
h1{font-size:24px;margin:0 0 4px}
.sub{color:var(--muted);font-size:13px;margin-bottom:26px}
h2{font-size:13px;letter-spacing:.08em;text-transform:uppercase;margin:32px 0 12px;padding-bottom:6px;border-bottom:2px solid var(--line)}
.item{border:1px solid var(--line);border-left:4px solid var(--pc);border-radius:8px;background:var(--card);padding:14px 16px;margin-bottom:12px}
.hdr{display:flex;gap:10px;flex-wrap:wrap;align-items:baseline}
.who{font-weight:600}
.when{color:var(--muted);font-size:12px;margin-left:auto}
.subj{margin:2px 0 8px;font-size:14px}
.why{color:var(--muted);font-size:13px;margin-bottom:10px}
.ask{background:rgba(26,95,180,.09);border-left:3px solid var(--accent);padding:9px 12px;border-radius:4px;margin-bottom:10px;font-size:14px}
details{margin-bottom:10px}
summary{cursor:pointer;font-size:13px;color:var(--accent)}
pre.draft{white-space:pre-wrap;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:11px;font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;margin:8px 0 0;overflow-x:auto}
.acts{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;align-items:center}
label.opt{cursor:pointer;user-select:none}
textarea.note{width:100%;margin-top:9px;min-height:0;height:34px;padding:7px 9px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);font:13px/1.45 inherit;resize:vertical}
.tag{font-size:11px;color:var(--muted);border:1px solid var(--line);border-radius:20px;padding:1px 8px}
#bar{position:fixed;left:0;right:0;bottom:0;background:var(--bg);border-top:1px solid var(--line);padding:12px 20px;display:flex;gap:12px;align-items:center;justify-content:center}
button{font:600 14px inherit;padding:10px 20px;border-radius:8px;border:0;background:var(--accent);color:#fff;cursor:pointer}
button.sec{background:transparent;color:var(--accent);border:1px solid var(--accent)}
#out{position:fixed;inset:6% 8%;background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:18px;display:none;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.3)}
#out textarea{flex:1;width:100%;font:13px/1.5 ui-monospace,Menlo,monospace;border:1px solid var(--line);border-radius:8px;padding:12px;background:var(--card);color:var(--fg)}
.empty{color:var(--muted);padding:24px 0}
"""

JS = """
function collect(){
  const lines=[]; let n=0;
  document.querySelectorAll('.item').forEach(it=>{
    const pick=it.querySelector('input[type=radio]:checked');
    const note=it.querySelector('textarea.note').value.trim();
    const dec=pick?pick.value:'';
    if(!dec && !note) return;
    n++;
    lines.push('['+it.dataset.ref+'] '+it.dataset.who+' / '+it.dataset.subj);
    if(dec) lines.push('  DECISION: '+dec);
    if(note) lines.push('  NOTE: '+note);
    lines.push('');
  });
  const gen=document.getElementById('general').value.trim();
  if(gen){lines.push('GENERAL:'); lines.push('  '+gen);}
  const t=lines.length?lines.join('\\n'):'(no decisions marked)';
  document.getElementById('outtext').value=t;
  document.getElementById('count').textContent=n+' item(s) marked';
  document.getElementById('out').style.display='flex';
}
function copyOut(){
  const t=document.getElementById('outtext');
  t.select(); document.execCommand('copy');
  document.getElementById('copybtn').textContent='Copied';
  setTimeout(()=>document.getElementById('copybtn').textContent='Copy',1400);
}
function closeOut(){document.getElementById('out').style.display='none';}
async function sendBack(){
  if(document.getElementById('out').style.display!=='flex') collect();
  const t=document.getElementById('outtext').value;
  const b=document.getElementById('sendbtn'), s=document.getElementById('sendstat');
  b.disabled=true; s.textContent='Sending to "'+PB.workspace+'"...';
  try{
    const r=await fetch('http://127.0.0.1:8765/send',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({token:PB.token,workspace:PB.workspace,text:t})});
    const j=await r.json();
    if(j.ok){ s.textContent='Sent to "'+PB.workspace+'" and confirmed started.'; b.textContent='Sent'; return; }
    throw new Error(j.error||j.log||('status '+r.status));
  }catch(e){
    // Fallback: copy, so a paste into that workspace is all that is left.
    const ta=document.getElementById('outtext'); ta.select(); document.execCommand('copy');
    s.textContent='Could not send ('+String(e.message||e).slice(0,120)+'). Copied instead: paste into "'+PB.workspace+'".';
    b.disabled=false;
  }
}
"""


def reply_target(override=None):
    """The cmux workspace the decisions should go back to, by NAME.

    The calling workspace when the page is made inside cmux, else Chief of
    staff, which is where Stephen pastes them when the launchd run made it.
    """
    if override:
        return override
    import os, re, subprocess
    if os.environ.get("CMUX_WORKSPACE_ID"):
        cmux = "/Applications/cmux.app/Contents/Resources/bin/cmux"
        try:
            ref = json.loads(subprocess.run([cmux, "identify"], capture_output=True,
                             text=True, timeout=10).stdout)["caller"]["workspace_ref"]
            tree = subprocess.run([cmux, "tree", "--all"], capture_output=True,
                                  text=True, timeout=10).stdout
            m = re.search(r'workspace %s "([^"]+)"' % re.escape(ref), tree)
            if m:
                return m.group(1)
        except Exception:
            pass
    return "Chief of staff"


def render_item(m, ref):
    who = m.get("from_name") or m.get("from", "")
    subj = m.get("subject", "(no subject)")
    colour = dict((p[0], p[2]) for p in PRIORITIES).get(m.get("priority", "fyi"), "#5f6368")

    bits = ['<div class="item" style="--pc:%s" data-ref="%s" data-who="%s" data-subj="%s">'
            % (colour, ref, html.escape(who, True), html.escape(subj, True))]
    bits.append('<div class="hdr"><span class="who">%s</span>'
                '<span class="tag">%s</span><span class="when">%s</span></div>'
                % (html.escape(who), html.escape(m.get("account", "")),
                   html.escape(m.get("when", m.get("date", "")))))
    bits.append('<div class="subj">%s</div>' % html.escape(subj))
    if m.get("summary"):
        bits.append('<div class="why">%s</div>' % html.escape(m["summary"]))

    if m.get("question"):
        bits.append('<div class="ask"><b>Needs your steer:</b> %s</div>'
                    % html.escape(m["question"]))

    if m.get("draft"):
        bits.append('<details><summary>Suggested draft</summary>'
                    '<pre class="draft">%s</pre></details>' % html.escape(m["draft"]))

    opts = (["Send as drafted", "Amend as noted", "I will handle it", "No reply needed"]
            if m.get("draft") else
            ["Draft it as I note", "I will handle it", "No action needed"])
    radios = "".join(
        '<label class="opt"><input type="radio" name="d%s" value="%s"> %s</label>'
        % (ref, html.escape(o, True), html.escape(o)) for o in opts)
    bits.append('<div class="acts">%s</div>' % radios)
    bits.append('<textarea class="note" placeholder="your note, optional"></textarea>')
    bits.append("</div>")
    return "".join(bits)


def cmd_page(a):
    data = json.loads(Path(a.input).read_text())
    msgs = data.get("messages", [])
    stamp = datetime.now().strftime("%A %d %B %Y, %H:%M")
    since = data.get("since", "")

    body = ['<div class="wrap">', "<h1>Email review</h1>",
            '<div class="sub">%s &nbsp;·&nbsp; %d message(s) since %s</div>'
            % (html.escape(stamp), len(msgs), html.escape(since.replace("T", " ")))]

    ref = 0
    for key, label, colour in PRIORITIES:
        group = [m for m in msgs if m.get("priority") == key]
        if not group:
            continue
        body.append('<h2 style="color:%s">%s (%d)</h2>' % (colour, html.escape(label), len(group)))
        for m in group:
            ref += 1
            body.append(render_item(m, str(ref)))

    if not ref:
        body.append('<div class="empty">Nothing needing your attention since the last review.</div>')

    body.append('<h2>Anything else</h2>'
                '<textarea id="general" class="note" style="height:80px" '
                'placeholder="general instructions for the next run"></textarea>')
    body.append("</div>")
    target = reply_target(getattr(a, "reply_to", None))
    sys.path.insert(0, str(SKILL))
    import paste_back_server
    pb = json.dumps({"workspace": target, "token": paste_back_server.token()})
    body.append('<div id="bar"><button id="sendbtn" onclick="sendBack()">Send decisions to Claude</button>'
                '<button class="sec" onclick="collect()">Preview</button>'
                '<span class="sub" id="sendstat" style="margin:0">goes to cmux &ldquo;%s&rdquo;; no email is sent</span></div>'
                % html.escape(target))
    body.append('<div id="out"><div style="display:flex;align-items:baseline;gap:12px;margin-bottom:10px">'
                '<b>Paste this back to Claude</b><span class="sub" id="count" style="margin:0"></span>'
                '<span style="margin-left:auto;display:flex;gap:8px">'
                '<button id="copybtn" onclick="copyOut()">Copy</button>'
                '<button class="sec" onclick="closeOut()">Close</button></span></div>'
                '<textarea id="outtext"></textarea></div>')

    page = ("<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Email review %s</title><style>%s</style></head><body>%s"
            "<script>const PB=%s;%s</script></body></html>"
            % (html.escape(datetime.now().strftime("%d %b")), CSS, "".join(body),
               pb.replace("</", "<\\/"), JS))

    out = Path(a.out)
    out.write_text(page)
    print("Wrote %s (%d item(s))" % (out, ref))
    return 0


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch")
    f.add_argument("--since", help="ISO timestamp; defaults to the last review")
    f.add_argument("--out", default=str(STATE / "inbox.json"))
    f.set_defaults(func=cmd_fetch)

    g = sub.add_parser("page")
    g.add_argument("--input", default=str(STATE / "reviewed.json"))
    g.add_argument("--out", default=str(Path.home() / "Desktop" / "email-review.html"))
    g.add_argument("--reply-to", help="cmux workspace name the decisions go back to")
    g.set_defaults(func=cmd_page)

    sub.add_parser("mark").set_defaults(func=cmd_mark)
    sub.add_parser("since").set_defaults(func=lambda _: (print(since_iso()), 0)[1])

    a = p.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
