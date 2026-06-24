# CE Mark / UKCA / MDR → 510(k) Gap Analysis

## Reusability summary

Roughly 70% of a current MDR / UKCA technical file is reusable in a 510(k) with format changes only. The remaining 30% is FDA-specific and must be authored fresh.

## Mapping table

| 510(k) Section | CE Mark / MDR equivalent | Effort to convert | Notes |
|----------------|--------------------------|-------------------|-------|
| 00.TableOfContents & Screening Checklist | None | Author fresh | Mandatory — use FDA's RTA checklist |
| 00.FDAComms | None | Author fresh | Establishment Reg number, Small Business Determination |
| 01.Medical Device User Fee Cover Sheet | None | Author fresh | Form 3601 |
| 02.CDRH Premarket Review Cover Sheet | None | Author fresh | Form 3514 |
| 03.Cover Letter | Optional in MDR | Author fresh, short | Plain-text statement of submission type |
| 04.Indications for Use Statement | MDR intended purpose, EXPANDED | Author fresh | FDA Form 3881 — strict format. Distinct from "intended use". |
| 05.510(k) Summary | None | Author fresh | Required per 21 CFR 807.92. Will be publicly posted. |
| 06.Truthful & Accuracy Statement | None | Author fresh | One-page certification |
| 07.Class II Summary Certification | None | Author fresh | Required for Class II |
| 09.Declarations of Conformity | Largely reusable | Reformat | Subset of MDR standards apply (e.g. IEC 62304, ISO 14971) |
| 10.Executive Summary | None directly | Author fresh | 1-2 pages, written for non-technical reviewer |
| 11.Device Description | Reusable from MDR | Reformat, add 510(k)-specific framing | Add product code rationale |
| 12.Substantial Equivalence Discussion | None | Author fresh | The most important new section. See [02-substantial-equivalence.md](02-substantial-equivalence.md) |
| 13.Proposed Labelling | Reusable from CE labelling | Reformat to FDA conventions | Operator Manual, IFU, packaging labels |
| 14.Sterilisation & Shelf Life | Reusable | Reformat | N/A for SaMD |
| 15.Biocompatibility | Reusable | Reformat | N/A for SaMD |
| 16.Software | Largely reusable | Reformat to FDA structure | See sub-table below |
| 17.EMC & Electrical Safety | Reusable | Reformat | N/A for SaMD-only |
| 18.Performance Testing — Bench | Reusable from CE Performance Eval | Reformat | Verification & validation results |
| 20.Performance Testing — Clinical | Reusable from CE Clinical Evaluation | Reformat | Add US-representativeness argument |

## Section 16 (Software) sub-mapping

FDA expects the following sub-folders inside section 16. Use these exact names.

| Sub-folder | CE equivalent | Notes |
|------------|---------------|-------|
| 10.Level Of Concern | MDR Software Safety Class (IEC 62304 A/B/C) | Map MDR Class B → FDA Moderate. Class A → Minor. Class C → Major. |
| 11.Software Description | Reusable | High-level architecture document |
| 12.Device Hazard Analysis | Reusable (ISO 14971) | Same risk file works for both |
| 13.SRS (Software Requirements Spec) | Reusable | Reformat to IEC 62304 §5.2 |
| 14.Architecture | Reusable | Architecture diagrams + descriptions |
| 15.SDS (Software Design Spec) | Reusable | IEC 62304 §5.3 |
| 16.Traceability Matrix | Reusable | Requirements ↔ Design ↔ Test |
| 17.SSLCDP (Software Lifecycle Plan) | Reusable | Your IEC 62304 lifecycle plan |
| 18.Validation & Verification | Reusable | Test protocols + reports |
| 19.Revision Level History | Reusable | |
| 20.Unresolved Anomalies | New for FDA | Bug list with severity + workarounds |

## What's net-new for the FDA submission

The following have no CE Mark equivalent and must be authored:

1. **510(k) Summary** (Section 05) — Public-facing, 5-15 pages, per 21 CFR 807.92
2. **Substantial Equivalence Discussion** (Section 12) — Core legal argument
3. **Indications for Use Statement** (Section 04) — FDA Form 3881
4. **Cybersecurity documentation** — Per FDA "Content of Premarket Submissions for Management of Cybersecurity in Medical Devices" (October 2014, updated 2023). MDR is moving in this direction but format differs.
5. **Off-the-Shelf Software justification** — Per FDA OTS guidance (September 2019). Lists every 3rd-party library with version, vendor, validation status.
6. **AI/ML-specific content** — Algorithm description, training/test/validation data provenance and demographics, performance metrics by subgroup, ground truth methodology
7. **Establishment Registration & Listing** — Done outside the 510(k) but referenced. Foreign manufacturers also need a US Agent.
8. **Small Business Determination (Form 3602A)** — Optional but reduces user fees substantially. Eligibility: gross receipts <$100M.

## Pure formatting differences

The CE technical file → 510(k) mapping is mostly a reformatting exercise. Watch for:

- **Document numbering** — adopt a `<section>.<subsection>.<doc>.<version>` scheme
- **Date format** — FDA prefers Month DD, YYYY (e.g. "August 14th, 2022")
- **Units** — keep SI but add US imperial in parentheses where clinically relevant
- **Terminology** — "Indications for Use" not "Intended Purpose"; "Cleared" not "Approved" (510(k) is clearance, not approval); "Predicate" not "Equivalent device"
- **Standards** — MDR-cited standards are mostly recognized by FDA; check FDA's Recognized Consensus Standards database for the exact recognition number

## Anti-patterns

- **Don't copy MDR Technical Documentation index verbatim** — FDA's section numbering is different
- **Don't reuse CE Mark IFU verbatim** — CE intended purpose is broader; FDA IFU must be narrow and specific to the predicate-supported claims
- **Don't include MDR-only documents** (NB notes, EU Declaration of Conformity, MDR Annex II/III chapter mapping) — they confuse reviewers
- **Don't claim "CE Marked since YYYY" as a safety argument** — FDA does not consider CE Mark as evidence of safety or effectiveness. Mention CE Mark only in Regulatory History.
