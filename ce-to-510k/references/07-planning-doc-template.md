# Planning Document Template

Use this as the on-disk `00-PLANNING.md` deliverable.

```markdown
# 510(k) Submission Plan — [Device Name] v[Version]

**Owner:** [Name, Role]
**Last updated:** YYYY-MM-DD
**Target submission date:** YYYY-MM-DD
**Target clearance date (realistic):** YYYY-MM-DD
**Target clearance date (optimistic):** YYYY-MM-DD

---

## 1. Device snapshot

- **Trade name:** [...]
- **Intended use (verbatim from CE Mark):** [...]
- **Proposed FDA Indications for Use:** [...]
- **Proposed product code:** [XXX]
- **Proposed classification regulation:** [21 CFR XXX.XXXX]
- **Device class:** Class II
- **Level of concern:** [Minor / Moderate / Major]
- **AI/ML?** [Yes — locked / Yes — adaptive (will require PCCP) / No]
- **CE Mark status:** [Class, NB number, date of first CE Mark]

## 2. Predicate decision

- **Chosen predicate:** K###### — [Tradename, Applicant, clearance date]
- **Backup predicate(s):** K######, K######
- **Predicate ranking summary:** [see 01-PREDICATE-RESEARCH.md]
- **SE risk areas:** [bulleted]

## 3. Pre-Sub decision

- **Pre-Sub: Yes / No**
- **Rationale:** [...]
- **If Yes**:
  - Pre-Sub target submission: YYYY-MM-DD
  - Questions: [list 3-5]
  - Expected response: YYYY-MM-DD (Pre-Sub + 70 days)
  - Effect on 510(k) timeline: +60-90 days
- **If No**:
  - Risk acknowledged: [list — most commonly AINN cycle of 60-180 days]

## 4. Work breakdown — Sections 00 through 21

| Section | Status | Owner | Est. days | Reuses CE? | Notes |
|---------|--------|-------|-----------|------------|-------|
| 00.FDAComms | Not started | | 2 | No | Need Establishment Reg, US Agent |
| 04.IFU | Not started | | 1 | Partial | Form 3881 — narrower than CE intended use |
| 05.510(k) Summary | Not started | | 5 | No | Public-facing |
| 10.Executive Summary | Not started | | 2 | No | |
| 11.Device Description | Draft | | 3 | Yes | Reformat from CE Tech File §3 |
| 12.SE Discussion | Not started | | 10 | No | The big one |
| 13.Labelling | Draft | | 5 | Yes | Reformat Operator Manual |
| 16.Software | Mostly ready | | 5 | Yes | Repackage IEC 62304 deliverables |
| 18.Bench Testing | Ready | | 2 | Yes | Reformat V&V reports |
| 20.Clinical Testing | Partial | | 15 | Partial | May need add'l US-rep argument |

## 5. AI/ML deficiency pre-empt checklist

[Paste the checklist from references/06-fda-ai-ml-deficiencies.md and mark progress]

## 6. Critical path

```
Predicate research ──┐
                     ├──> SE drafting ──> Internal review ──┐
CE Tech File audit ──┘                                       ├──> Pre-Sub (optional)
                                                             │
Clinical testing gaps ──> Test plan ──> Execute ─────────────┴──> 510(k) assembly ──> Submit
```

## 7. Timeline scenarios

### Optimistic (~6 months to clearance)

| Month | Milestone |
|-------|-----------|
| M+0 | Kickoff, predicate confirmed by consultant review |
| M+1 | CE → 510(k) gap analysis complete |
| M+2 | SE draft + IFU draft complete; pre-empt checklist run |
| M+3 | Internal review + remediation; submission package frozen |
| M+3.5 | Submit |
| M+4 | RTA acceptance |
| M+5 | Substantive review |
| M+6 | Clearance (no AINN) |

Requires: clear predicate, no AINN, no Pre-Sub, consultant already reviewed.

### Realistic (~9-12 months)

| Month | Milestone |
|-------|-----------|
| M+0 | Kickoff |
| M+1.5 | Predicate confirmed, CE gap analysis done |
| M+3 | SE + IFU drafts; additional clinical data identified as needed |
| M+4-5 | Additional clinical testing executed (subgroup analysis, density stratification) |
| M+6 | Submission package complete |
| M+6.5 | Submit |
| M+7 | RTA acceptance |
| M+9 | First AINN (60-day clock pause) — typical for AI/ML even with good pre-empt |
| M+10-11 | Interactive Feedback iteration(s) |
| M+12 | Clearance |

### Pessimistic (>15 months)

Triggers: predicate dispute, NSE finding, need to redesign IFU, need new clinical study to address subgroup gaps, transition to De Novo.

## 8. Budget rough

| Line | Cost (USD) |
|------|------------|
| FDA user fee (small business) | ~$5,400 |
| FDA user fee (standard) | ~$22,000 |
| Regulatory consultant (full submission) | $80-150k |
| Regulatory consultant (review only) | $15-30k |
| Clinical study (subgroup analysis on existing data) | $20-50k |
| Clinical study (new collection, panel of truthers) | $100-300k |
| US Agent annual | $1-3k |
| Establishment Registration | $7,653 (2024) |

## 9. Risks (top 5)

1. **AINN on subgroup analysis** — mitigated by pre-empt checklist
2. **Predicate disputed by reviewer** — mitigated by Pre-Sub for novel claims
3. **OUS test data rejected** — mitigated by US-representativeness table
4. **Ground truth panel insufficient** — mitigated by either panel-of-3 or biopsy-confirmed
5. **Reviewer turnover during AINN cycle** — mitigated by clean documentation in 00.FDAComms

## 10. Open questions to resolve

- [ ] Q1
- [ ] Q2
```
