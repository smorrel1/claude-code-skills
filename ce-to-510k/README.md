# ce-to-510k

A Claude Code skill for porting CE Mark / UKCA medical device technical documentation into an FDA 510(k) submission package for AI/ML SaMD.

## What it does

Given an existing CE Mark, UKCA or MDR technical file for an AI/ML Software as a Medical Device, this skill helps produce:

1. A planning document for the 510(k) campaign
2. A predicate device research and analysis (using the FDA 510(k) database)
3. A pre-submission (Q-Sub) request when appropriate
4. A mapped 510(k) eCopy package structure with content gap list
5. A strategic recommendation on whether to pursue a Pre-Sub

## Coverage

The skill was distilled from a real (2023) AI/ML SaMD 510(k) clearance, including the full Additional Information Request and Interactive Feedback cycle. Patterns generalise across imaging, signal-processing, clinical decision support, digital pathology and other AI/ML SaMD; domain-specific examples are flagged inline.

The single highest-value reference is `references/06-fda-ai-ml-deficiencies.md` — a categorised catalogue of the AI/ML deficiency question patterns FDA actually uses, with a 16-item pre-empt checklist you can paste into your draft.

## Installation

Drop the `ce-to-510k/` directory into your Claude Code skills folder (typically `~/.claude/skills/`), then invoke via the Skill tool or by mentioning any of: 510(k), FDA submission, Q-Sub, pre-sub, predicate device, substantial equivalence, CE to FDA, MDR to FDA, AI/ML 510(k).

## Usage

Give Claude this prompt, with your device details substituted:

> Port my CE Mark / UKCA technical file at `<path>` into an FDA-compliant 510(k). Device: `<name>` v`<version>`. Indications for Use (current CE): `<text>`. Suspected predicate K-numbers: `<list or none>`. Identify and evaluate the predicate via the FDA 510(k) database. Draft the Pre-Sub if recommended. Produce a planning doc. End with a strategic recommendation on whether we should be doing a Pre-Sub.

The skill will work through eight phases (predicate research, SE drafting, CE-to-510k gap analysis, eCopy structure, Pre-Sub decision and drafting, AI/ML deficiency pre-empt, planning doc, strategic advice) and produce a working folder of deliverables on disk.

## Not suitable for

De Novo, PMA, IVD CLIA, EUA, IDE, drug applications, or CE/MDR-only work without FDA intent.

## Disclaimer

This skill provides procedural guidance based on FDA published guidance documents and recent 510(k) experience. It is not legal or regulatory advice and does not substitute for engagement with qualified FDA regulatory counsel. Verify all guidance citations against current FDA publications before submission. Regulatory requirements evolve; the maintainer makes no warranty that this skill reflects the current state of FDA practice.

## Licence

MIT. See LICENSE.
