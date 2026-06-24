---
name: ce-to-510k
description: Port CE Mark / UKCA medical device technical documentation into an FDA 510(k) submission package for AI/ML SaMD (Software as a Medical Device). Use when a user (typically a non-US medical device manufacturer with existing MDR / IVDR / UKCA technical files) wants to (1) plan a 510(k) submission, (2) identify and analyse a predicate device using FDA databases, (3) draft a Q-Submission (pre-sub) request, (4) map CE Mark documents to the FDA eCopy section structure, or (5) anticipate the AI/ML-specific deficiency questions FDA will ask. Built from real 510(k) clearance experience for an AI/ML imaging device, including the Additional Information / Interactive Feedback cycle. Triggers on "510k", "510(k)", "FDA submission", "pre-sub", "Q-sub", "predicate device", "substantial equivalence", "CE to FDA", "MDR to FDA", "AI/ML 510k".
---

# CE Mark → FDA 510(k) Conversion for AI/ML Medical Devices

## Purpose

Help a non-US manufacturer take an existing CE Mark / UKCA / MDR technical file for an AI/ML SaMD and produce: (1) a planning document, (2) a predicate device research and analysis, (3) a pre-submission (Q-Sub) request when appropriate, (4) a mapped 510(k) eCopy package structure with content gap list, (5) a strategic recommendation on whether to pursue a Pre-Sub.

This skill encodes lessons from a recent (2023) AI/ML SaMD 510(k) clearance, including the full Additional Information Request and Interactive Feedback cycle. Patterns generalise across imaging, signal-processing, clinical-decision-support and other AI/ML SaMD; domain-specific examples are flagged inline.

## When to use

Trigger when the user mentions any of: 510(k), FDA submission, Q-Sub / pre-sub, predicate search, substantial equivalence, converting MDR/CE/UKCA technical file to FDA, AI/ML 510(k), engaging an FDA regulatory consultant.

Do **not** use for: De Novo, PMA, IVD CLIA, EUA, IDE, drug applications, CE/MDR-only work without FDA intent.

## Inputs the user must supply

Before starting, get these from the user. If any are missing, ask before proceeding.

1. **Path** to their CE Mark / UKCA technical file root
2. **Device name** and version
3. **Intended use** statement (verbatim from current CE labelling)
4. **Candidate predicate K-numbers** if already suspected
5. **Trade-off context**: willing to revise the Indications for Use to better fit a predicate, or is the CE IFU fixed?
6. **Timeline pressure**: hard deadline vs. exploratory

## Workflow

### Phase 1 — Predicate research

**Use the `scientific-skills:fda-database` skill** to query the FDA 510(k) database. Search by:

- Product code (most reliable — narrows the universe quickly)
- Device classification / regulation number (e.g. `21 CFR 892.2050`)
- Trade name keywords
- Applicant name (for known competitors)
- Therapeutic area + modality keywords

Read [references/01-predicate-research.md](references/01-predicate-research.md) for the predicate ranking framework and a worked example.

**Deliverable**: a shortlist of 2–4 candidate K-numbers ranked by SE-likelihood, with 510(k) Summary PDFs downloaded to a `predicate-research/` working folder.

### Phase 2 — Substantial Equivalence drafting

Read [references/02-substantial-equivalence.md](references/02-substantial-equivalence.md) for the full SE template and a worked example.

Structural elements — do not skip:

1. Statutory background quote (FD&C 513(i))
2. Intended Use comparison
3. Technological Characteristics comparison (same vs. different)
4. Supporting Scientific Data (if technological characteristics differ)
5. Comparison Table (the centrepiece)
6. Conclusion Regarding Differences
7. Safety & Effectiveness Questions
8. Final SE Conclusion

### Phase 3 — CE Mark → 510(k) gap analysis

The CE Mark / MDR technical file gives ~70% of the 510(k) content. Read [references/03-ce-to-510k-gap.md](references/03-ce-to-510k-gap.md) for the mapping table and the FDA-specific content with no CE equivalent (510(k) Summary, IFU on Form 3881, Truthful & Accuracy Statement, Class II Special Controls certification).

### Phase 4 — eCopy section layout

The 510(k) is submitted as a numbered eCopy. Use the canonical layout in [references/04-ecopy-structure.md](references/04-ecopy-structure.md) — sections 00 through 21. Do not invent your own numbering; reviewers expect the standard order.

### Phase 5 — Pre-Sub (Q-Submission) decision and drafting

A Pre-Sub is **not always indicated**. Read [references/05-presub-strategy.md](references/05-presub-strategy.md) for: when a Pre-Sub helps vs. just adds 60–90 days; Q-Sub template; the 3–5 question rule; how to frame questions to get a binding answer.

### Phase 6 — Anticipate AI/ML deficiencies

Highest-value content. CDRH has a stereotyped set of questions for AI/ML SaMD. Read [references/06-fda-ai-ml-deficiencies.md](references/06-fda-ai-ml-deficiencies.md) — categorised catalogue of the deficiency question patterns FDA uses during the Additional Information Request and Interactive Feedback rounds for AI/ML SaMD.

Pre-empt these in the original submission to avoid the AINN (Additional Information — Not Needed) loop, which adds 3–6 months.

### Phase 7 — Planning document

Produce a planning document covering timeline, dependencies, owner per section, predicate decision, Pre-Sub yes/no, gating risks, budget. Use [references/07-planning-doc-template.md](references/07-planning-doc-template.md).

### Phase 8 — Strategic advice

Give the user a clear recommendation on Pre-Sub yes/no, **with reasoning** based on:

- Predicate strength (clear LLZ/QIH-style match → skip Pre-Sub; novel claim → Pre-Sub)
- Clinical data availability (panel of truthers? US-representative cases?)
- Algorithm novelty vs. predicate
- Timeline tolerance for a 60–90 day Pre-Sub round
- Whether company can absorb a Refuse-to-Accept or AI request without runway risk

## Operating principles

- **Read the user's CE Mark file before writing anything.** Verify, do not assume.
- **Cite verbatim from FDA guidance documents** — never paraphrase regulatory language. References list in [references/08-fda-guidance-refs.md](references/08-fda-guidance-refs.md).
- **Comparison tables beat prose** for SE arguments. Reviewers scan tables first.
- **Acronyms spelled out on first use** in every document.
- **Pre-empt AI/ML deficiency questions** during initial submission, do not wait for the AI request.
- **Save predicate 510(k) Summary PDFs** to the working folder — reviewers check you actually read them.
- **The product code is the most powerful classification lever.** Same code as predicate = near-automatic same classification regulation.

## Output conventions

When producing 510(k) documents, follow these conventions:

- Document numbering: `<section>.<subsection>.<doc>.<version>` (e.g. `12.01.05.01`)
- Header table: Project name, Document number, Document revision, Issue Date, Filename
- Approvals table: Role, Name, Position, Date (Author + Reviewer/Approver minimum)
- Revision History table
- Abbreviations / Acronyms section
- Applicable Documents / References table
- Markdown for drafting; convert to .docx at submission time (use `scientific-skills:docx`)

## What to deliver

End state on disk:

```
<working-folder>/
├── 00-PLANNING.md
├── 01-PREDICATE-RESEARCH.md           + predicate-research/K######.pdf
├── 02-SUBSTANTIAL-EQUIVALENCE-DRAFT.md
├── 03-CE-TO-510K-GAP.md
├── 04-ECOPY-SKELETON/                 (folders 00 through 21 with stub README)
├── 05-PRESUB-Q-SUB-DRAFT.md           (only if Phase 5 recommended yes)
├── 06-AI-ML-DEFICIENCY-CHECKLIST.md
└── 07-STRATEGIC-RECOMMENDATION.md
```

## Reference index

| File | Use when |
|------|----------|
| [references/01-predicate-research.md](references/01-predicate-research.md) | Phase 1 |
| [references/02-substantial-equivalence.md](references/02-substantial-equivalence.md) | Phase 2 |
| [references/03-ce-to-510k-gap.md](references/03-ce-to-510k-gap.md) | Phase 3 |
| [references/04-ecopy-structure.md](references/04-ecopy-structure.md) | Phase 4 |
| [references/05-presub-strategy.md](references/05-presub-strategy.md) | Phase 5 + 8 |
| [references/06-fda-ai-ml-deficiencies.md](references/06-fda-ai-ml-deficiencies.md) | Phase 6 |
| [references/07-planning-doc-template.md](references/07-planning-doc-template.md) | Phase 7 |
| [references/08-fda-guidance-refs.md](references/08-fda-guidance-refs.md) | Verbatim citations |
