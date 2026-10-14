#!/usr/bin/env python3
"""Check an email body against the plain-English rules, before it is drafted.

Stephen's default for email from 14 Oct 2026: ASD-STE100 principles WITHOUT the
approved-word dictionary. Short sentences, one idea in each, active voice, the
same word for the same thing, no unglossed jargon. Contractions stay, so it
still sounds like him rather than like a maintenance manual.

The dictionary is deliberately not applied, so do NOT tell a recipient who asks
for the standard that the result is ASD-STE100 compliant. It is not.

    check_plain_english.py body.html          report
    check_plain_english.py body.html --quiet  exit code only

Exit 0 = ready to draft. Exit 1 = fix and re-run. Advice, not law: a long
sentence that reads well is a judgement call, which is why the output names the
sentence instead of rewriting it.
"""
import argparse
import re
import sys

SOFT, HARD = 20, 25

# "was sent", "is being reviewed", "has been completed". Deliberately narrow:
# a passive hunt with a wide net flags half of ordinary English.
PASSIVE = re.compile(
    r"\b(is|are|was|were|be|been|being|has been|have been|had been)\s+"
    r"(\w+ed|sent|done|made|given|taken|seen|known|shown|held|built|kept|"
    r"found|told|put|set|run|written|drawn|paid)\b", re.I)

# Pairs that must not both appear: the same thing under two names.
SYNONYMS = [
    ({"radiologist", "reader"}, "radiologist / reader"),
    ({"case", "study", "exam"}, "case / study / exam"),
    ({"overlay", "annotation", "marking"}, "overlay / annotation / marking"),
    ({"site", "customer", "account"}, "site / customer / account"),
    ({"call", "meeting", "chat"}, "call / meeting / chat"),
]

# Acronyms that need a gloss the first time, unless the recipient plainly knows
# them. Clinical and regulatory ones people outside the field will not know.
GLOSS = ["GSPS", "DBT", "CC", "MLO", "PACS", "SaMD", "510(k)", "UKCA", "EIS",
         "PPIE", "SoECAT", "IEC 62304", "DICOM", "QIDO", "BI-RADS"]


def sentences(text):
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    text = open(a.file).read()
    body = sentences(text)
    problems, notes = [], []

    for s in body:
        words = s.split()
        if len(words) > HARD:
            problems.append("%d words (ceiling %d): %s" % (len(words), HARD, s[:90]))
        elif len(words) > SOFT:
            notes.append("%d words, over the %d aim: %s" % (len(words), SOFT, s[:80]))
        m = PASSIVE.search(s)
        if m:
            notes.append("passive %r: %s" % (m.group(0), s[:80]))

    low = " ".join(body).lower()
    for group, label in SYNONYMS:
        present = [w for w in group if re.search(r"\b%s\b" % w, low)]
        if len(present) > 1:
            notes.append("two words for one thing (%s): pick one and keep it" % label)

    for term in GLOSS:
        if term.lower() in low and ("(" not in low.split(term.lower())[0][-80:]):
            notes.append("%s appears: gloss it on first use unless the reader "
                         "uses it daily" % term)

    if not a.quiet:
        print("%s  (%d sentence(s))" % (a.file, len(body)))
        for p in problems:
            print("  OVER THE CEILING  " + p)
        for n in notes[:12]:
            print("  consider          " + n)
        print("\nRESULT: %s" % ("FAIL, split the long sentences" if problems
                                else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
