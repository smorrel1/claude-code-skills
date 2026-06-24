# Substantial Equivalence Document Template

## Statutory framework

Quote FD&C §513(i) verbatim:

> (i)(1)(A) For purposes of determinations of substantial equivalence under subsection (f) and section 520(l), the term "substantially equivalent" or "substantial equivalence" means, with respect to a device being compared to a predicate device, that the device has the same intended use as the predicate device and that the Secretary by order has found that the device
> (i) has the same technological characteristics as the predicate device, or
> (ii)(I) has different technological characteristics and the information submitted that the device is substantially equivalent to the predicate device contains information, including appropriate clinical or scientific data if deemed necessary by the Secretary or a person accredited under section 523, that demonstrates that the device is as safe and effective as a legally marketed device, and (II) does not raise different questions of safety and effectiveness than the predicate device.

> (B) For purposes of subparagraph (A), the term "different technological characteristics" means, with respect to a device being compared to a predicate device, that there is a significant change in the materials, design, energy source, or other features of the device from those of the predicate device.

## SE document structure

Use these exact section names. FDA reviewers expect them.

1. **Introduction** (Statutory Background quote above)
2. **Scope** (one sentence: "This document describes Device X's substantial equivalence to the predicate device Y.")
3. **Applicable Documents / References** (table)
4. **Substantial Equivalence**
   - 4.1 Intended Use (comparison)
   - 4.2 Technological Characteristics (same? or different + supporting data?)
   - 4.3 Supporting Scientific Data (only if 4.2 is "different")
5. **Safety and Effectiveness Questions** (state explicitly: device does not raise different Q's)
6. **Conclusion** ("The requirements for Substantial Equivalence have been met.")

## The Comparison Table — canonical column layout

Use exactly five columns:

| Feature | Subject device | Predicate device (K######) | Comparison | Impact to Safety & Effectiveness |

Rows MUST include (at minimum):

- Regulation Description
- Device name and version (K number)
- Regulation Number (e.g. 21 CFR 892.2050)
- Classification Product Code
- Manufacturer
- Indications for Use (full verbatim text from both)
- Architecture (client/server, standalone, cloud, etc.)
- Display of 3rd party CAD markers (yes/no)
- Input data format compatibility (DICOM for imaging, HL7/FHIR for clinical data, proprietary formats where applicable)
- All device-specific technological features (one row each)
- Performance characteristics
- Supported image-generating manufacturers/models
- Display devices (monitors, resolution)

For each row, the "Comparison" cell is one of: **Same** | **Different (subject has fewer functions)** | **Different (subject has more functions)** | **Different — see [section]**

The "Impact to Safety & Effectiveness" cell is one of: **None** | **No detrimental impact** | **Subject has improved [X]** | **See discussion in Section [N]**

## Worked example excerpt (illustrative)

| Feature | Subject device v1.0 | Predicate (K######) | Comparison | Impact |
|---------|---------------------|---------------------|------------|--------|
| Regulation Number | 21 CFR 892.2050 | 21 CFR 892.2050 | Same | None |
| Product Code | LLZ | LLZ | Same | None |
| Core algorithm | [classical method] + [additional ML stage] | [classical method] only | Subject adds an ML stage which improves accuracy | No detrimental impact |
| Measurements | Distance only | Distance + angle | Subject excludes angle measurements | No detrimental impact (fewer functions) |
| Supported image sources | Specific OEM models listed | No restriction stated | Subject restricted to fewer | None (out-of-scope cases not processed) |

## When technological characteristics differ — "as safe and effective"

If your AI/ML adds capability the predicate lacks, you must show:

1. **The difference is significant** (acknowledge it openly — concealing differences triggers AI requests)
2. **The change does not raise different questions of safety and effectiveness** (state this explicitly)
3. **Supporting scientific data** demonstrates equivalent or better performance

Three valid scientific-data strategies:

| Strategy | When to use |
|----------|-------------|
| **Head-to-head benchmark** | Predicate's performance data is publicly disclosed in its 510(k) Summary or peer-reviewed literature |
| **Proxy benchmark** | Predicate's underlying technology is described in published literature but specific performance is not — substitute a published implementation of the same technology as the benchmark |
| **Standalone performance threshold** | Predicate is too dissimilar for either comparison; clinical justification of an absolute performance threshold instead |

The proxy benchmark approach typically yields a concrete numerical comparison (e.g. "subject device X mm mean error vs proxy Y mm"). FDA reviewers strongly prefer numerical, head-to-head comparisons over narrative arguments.

## Safety & Effectiveness Questions section — boilerplate

> Due to the substantially equivalent Intended Uses between [Subject] and [Predicate], and [Subject]'s [equivalent/superior] performance, it does not raise different questions of safety and effectiveness than the predicate device.

Optional risk-reduction additions (if applicable):

- Subject device is more explicit about the clinician's responsibility for diagnosis
- Subject device declares explicit precautions and special patient populations
- Subject device restricts itself to validated source data / input hardware

## Common mistakes to avoid

- **Claiming "same technological characteristics" when adding AI/ML.** Reviewers will catch this. Acknowledge difference, then argue equivalence.
- **Not citing the predicate's own predicate chain.** If your tech is closer to the predicate-of-predicate, name that too — it strengthens the SE argument.
- **Using marketing language for IFU.** The IFU should be clinical, not promotional.
- **Burying the Indications for Use comparison in prose.** It belongs in the Comparison Table, full verbatim, both columns.
- **Forgetting that "as safe and effective" is a legal term of art**, not a literal accuracy claim. You can be "as safe and effective" even with lower accuracy if the user-in-the-loop catches errors.
