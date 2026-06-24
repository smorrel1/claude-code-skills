# 510(k) eCopy Section Structure

## Canonical numbered layout

Use this exact section numbering. FDA reviewers expect it; deviations cause RTA delays.

```
00.AdditionalInformation/
00.FDAComms/                              ContactInfo, SmallBusinessForm, FDA admin notes
00.TableOfContentsAndScreeningChecklist/
01.MedicalDeviceUserFeeCoverSheet/        Form 3601
02.CDRHPremarketReviewCoverSheet/         Form 3514 + Pre-Sub references
03.CoverLetter/
04.IndicationForUseStatement/             Form 3881 (one-page)
05.510kSummary/                           Per 21 CFR 807.92
06.TruthfulAndAccuracyStatement/
07.ClassIISummaryCertification/
08.[reserved]
09.DeclarationsOfConformitySummaryReports/
10.ExecutiveSummary/
11.DeviceDescription/
12.SubstantialEquivalenceDiscussion/      Plus predicate 510(k) Summary PDFs
13.ProposedLabelling/                     Operator Manual, IFU, label artwork
14.SterilisationAndShelfLife/             N/A for SaMD — include short justification
15.Biocompatibility/                      N/A for SaMD — include short justification
16.Software/                              Subdirectories below
17.ElectromagneticCompatibilityAndElectricalSafety/   N/A for SaMD
18.PerformanceTestingBench/
19.[reserved — animal testing]
20.PerformanceTestingClinical/
21.GlobalJurisdictions/                   Internal use; for global rollout planning
```

## Section 16 (Software) sub-layout

```
16.Software/
├── 10.LevelOfConcern/
├── 11.SoftwareDescription/
├── 12.DeviceHazardAnalysis/
├── 13.SRS/                               Software Requirements Spec
├── 14.Architecture/
├── 15.SDS/                               Software Design Spec
├── 16.TraceabilityMatrix/
├── 17.SSLCDP/                            Software Lifecycle Development Plan
├── 18.ValidationAndVerification/
├── 19.RevisionLevelHistory/
└── 20.UnresolvedAnomalies/
```

## eCopy technical packaging requirements

When zipping for upload to CDRH:

1. **Single ZIP at the top level** (no nested ZIPs)
2. **Folder names must match the section structure** (FDA's eCopy validator checks)
3. **File names must not contain**: spaces (use hyphens/underscores), special characters (& % $ # @), brackets, or pipe symbols
4. **PDF files preferred** — but the AI/ML AINN cycle is easier with .docx for reviewer markup
5. **No file >100MB** in any single PDF — split large performance reports
6. **Include a TOC at the root** as an HTML or PDF file with clickable links

## Section 00 — what goes in AdditionalInformation

The `00.AdditionalInformation/` folder is for cross-cutting content that doesn't fit a single section:

- Master referencing scheme document (how documents cross-reference each other)
- Template / style guide document
- 510(k)-specific questions sent to FDA pre-submission (with answers if any)
- Anything submitted in the AI request response cycle later goes in `00.AdditionalInformation/Additional Information Request/`

## Section 00.FDAComms — what to include

This is your record of all FDA interactions. Include:

- Contact information sheet (CEO + alternate + US Agent)
- Small Business Determination (Form 3602A) and FDA's decision letter
- Establishment Registration receipt
- Any pre-submission (Q-Sub) correspondence
- Acceptance Letter (after submission)
- Substantial Equivalence Letter (after clearance)

## Naming conventions inside each section

Use sequential prefixes within each section:

```
01.<DocumentName>-d<version>.docx       — primary document
02.<SupportingDocument>.pdf             — referenced material
03.<NextSupportingDocument>.pdf
```

Example for Section 12:
```
01.Substantial_Equivalence-d1.0.docx
02.K######_<PredicateName>.pdf            ← predicate's 510(k) Summary
03.Operator_Manual_<predicate>.pdf        ← predicate's Operator Manual
04.<author>_et_al.pdf                     ← supporting literature
05.<PatentRef>.pdf                        ← supporting IP / technology references
```

## Working folder vs submission folder

Keep two folders:

- **`Working/`** — drafts, redlines, AINN response drafts, Interactive Feedback iterations. Use .docx with tracked changes.
- **`eCopy/`** — frozen submission-ready PDFs only. Snapshot before submission and after each AI response.

Do not commingle. Reviewers receive only the eCopy.

## Required FDA forms (current as of 2024 — verify before each submission)

| Form | Purpose | Section |
|------|---------|---------|
| 3601 | Medical Device User Fee Cover Sheet | 01 |
| 3514 | CDRH Premarket Review Cover Sheet | 02 |
| 3881 | Indications for Use | 04 |
| 3602A | Small Business Determination (optional) | 00.FDAComms |
| 3654 | Premarket Tobacco Submission cover (N/A for medical devices unless dual) | — |

## Submission delivery

As of 2023, 510(k) submissions use the **CDRH Customer Collaboration Portal (CCP)** for eSubmitter / eCopy upload. The legacy CD/DVD physical submission has been deprecated for most use cases. Verify current channel at fda.gov/eCopy.
