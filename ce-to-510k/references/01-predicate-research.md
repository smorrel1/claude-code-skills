# Predicate Research Framework

## Why the predicate decision is THE decision

The 510(k) pathway hangs on Substantial Equivalence (SE) to a legally marketed predicate. Choose the wrong predicate and the entire downstream submission is mis-framed — at best a Refuse-to-Accept (RTA), at worst a "Not Substantially Equivalent" determination that pushes you to De Novo.

## Predicate ranking framework

Rank candidate predicates on five axes (1–5 each, higher = better). Take the highest aggregate.

| Axis | Question | Why it matters |
|------|----------|----------------|
| **Indications for Use overlap** | Is your IFU a subset, identical, or different from theirs? | Subset > identical > different. Different IFU usually defeats SE. |
| **Product code match** | Same FDA product code (e.g. LLZ, QIH)? | Same code = same classification regulation, almost automatic. |
| **Technological characteristics** | Same technology, or "different but as safe & effective"? | Same is trivial. Different requires extra scientific data. |
| **Predicate clearance recency** | Cleared within last 5 years? | Older predicates have been re-interpreted; recent predicates have already cleared a similar bar. |
| **Predicate disclosure quality** | Does the predicate's 510(k) Summary disclose performance data? | If yes, you can use it as a benchmark. If no, you need a proxy strategy. |

## Worked example (illustrative)

Score a candidate predicate against your subject device:

| Axis | Score | Note |
|------|-------|------|
| IFU overlap | 4 | Subject IFU is a subset of predicate's |
| Product code | 5 | Both same code, same regulation number |
| Tech characteristics | 3 | Same first-stage algorithm; subject adds an additional ML stage. "Different but improved" argued with proxy benchmark data. |
| Recency | 5 | Cleared within last 18 months |
| Disclosure quality | 2 | Predicate did not disclose performance data — required proxy |
| **Total** | **19/25** | Strong predicate despite disclosure gap |

## Searching the FDA 510(k) database

The FDA 510(k) database lives at the [Premarket Notification search](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPMN/pmn.cfm). Useful queries:

1. **Product code lookup**: start by mapping your CE Mark intended use to the most likely product code via the [FDA Product Classification database](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPCD/classification.cfm). Example AI/ML product codes by domain:
   - **Radiology / imaging**: `LLZ` (image management & processing), `QIH` / `OEB` (CAD for cancer detection), `QFM` (CADt triage), `QAS` (computer-assisted detection), `MYN` (pulmonary imaging)
   - **Cardiology**: `DPS` (ECG analysis), `MWJ` (cardiovascular monitoring)
   - **Clinical decision support**: `PYO` (clinical decision support software), `QPK` (drug interaction)
   - **Digital pathology**: `PSY` (whole slide image manager), `QKQ` (digital pathology image viewer)
   - **In vitro diagnostics**: many `J__` codes; check IVD classification separately

2. **Regulation number**: `21 CFR 892.2050` is the most common AI/ML imaging regulation. For non-imaging domains the regulation number tracks the device function (e.g. 21 CFR 870.2300 for cardiovascular monitors, 21 CFR 880.6315 for clinical decision support).

3. **Predicate-of-predicate trick**: pull the candidate predicate's own 510(k) Summary — it names its predicate. That predicate is also legally usable for your SE if the chain is intact.

4. **Tradename keywords + applicant**: confirms whether a competitor has cleared, and what indications they cleared on.

## What to extract from each candidate's 510(k) Summary

For each shortlisted candidate, record in a table:

- K-number, clearance date, applicant name
- Trade name(s) including any subsequent name changes
- Verbatim IFU statement
- Product code, regulation number, device class, level of concern
- Their predicate(s) and clearance date
- Technological characteristics summary (often a 3-column table — replicate it)
- Performance data disclosure (yes/no, what metric, what sample size)
- Any limitations / contraindications / special populations they declared

Save 510(k) Summary PDFs locally — the AI/ML deficiency loop will ask you to demonstrate you understood the predicate's technology.

## Red flags

- **No clear product code match** → almost certainly need De Novo, not 510(k)
- **Predicate cleared >7 years ago** → check whether FDA has issued newer guidance changing the special controls
- **Predicate withdrawn or recalled** → still legally usable IF clearance was not rescinded, but raises questions FDA will ask
- **Your IFU is broader than predicate's** → restate your IFU as subset, or accept the SE risk
- **Different intended user population (e.g. predicate cleared for diagnostic, you want screening)** → this is a "different question of safety and effectiveness" — very likely NSE

## Deliverable format

A markdown table ranking candidates, with for each one:

```markdown
## Candidate N: K######  ApplicantName  TradeName

**Clearance date:** YYYY-MM-DD
**Product code:** XXX
**Regulation:** 21 CFR XXX.XXXX

**IFU (verbatim):**
> ...

**Tech characteristics:** [bullets]

**Performance disclosure:** [yes/no, what]

**Score (axes 1-5):** IFU=_, Code=_, Tech=_, Recency=_, Disclosure=_ → Total /25

**SE risk areas:** [bullets]
```
