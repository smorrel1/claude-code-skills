# FDA AI/ML Deficiency Question Catalogue

FDA's AI/ML SaMD deficiency questions are highly stereotyped. Pre-empt them in your original submission to avoid the AINN (Additional Information — Not Needed) loop, which adds 3-6 months to a typical 510(k).

Each category names the question pattern, what FDA actually wants, and how to pre-empt.

## Category A — Device output and functional clarity

### A1. User interaction model

FDA pattern: any UI with continuous-versus-discrete query semantics (hover vs click, drag vs select) will be probed on exactly when the algorithm runs and what triggers an output update.

**Pre-empt with**: explicit pseudocode of the user interaction loop, including event types (hover, click, drag) and what each triggers.

### A2. Output bounds and uncertainty

FDA pattern: any spatial output (bounding box, oval, marker, mask) with a size or confidence dimension will be probed on whether the dimension reflects a minimum, maximum, or expected value, and what each means semantically.

**Pre-empt with**: define your output bounds as min, max, and typical, with explicit semantics of what each represents.

### A3. Multi-query / multi-output scenarios

FDA pattern: any UI that accepts multiple user queries (sequentially or in parallel) will be probed on the concurrency model and whether prior outputs persist or are replaced.

**Pre-empt with**: state the concurrency model (single query, queue, parallel) with screenshots.

### A4. Edge case output behaviour

FDA pattern: any input scenario where the algorithm has few or ambiguous features to work with (homogeneous tissue, low-contrast regions, out-of-distribution inputs) will be probed on what the output looks like and whether the user is warned.

**Pre-empt with**: a decision tree of "input case type → algorithm behaviour → displayed output" covering nominal cases, edge cases, no-match cases, and low-confidence cases. State the user-facing behaviour for each.

## Category B — Algorithm description

### B1. Detection vs. matching vs. classification

FDA pattern: any algorithm with multi-stage processing (e.g. detection + matching, or segmentation + measurement) will be probed on exactly what each stage does — and crucially what it does NOT do.

**Pre-empt with**: state explicitly what your algorithm does NOT do. Examples by domain: "The algorithm does not perform autonomous detection. It performs feature extraction only within a user-queried region" (imaging); "The algorithm does not produce a diagnosis. It surfaces relevant prior records for clinician review" (CDS); "The algorithm does not classify the rhythm. It identifies signal segments meeting predefined criteria" (signal processing).

### B2. Threshold justification

FDA pattern: any numerical threshold in a flowchart or warning trigger ("warn if predicted error >X") will be questioned on how the threshold was set and whether it was empirically derived.

**Pre-empt with**: every threshold/hyperparameter must be justified by either (a) empirical derivation from a held-out tuning set or (b) clinical literature reference. State the source.

### B3. Sub-output accuracy

FDA pattern: if your pipeline includes any internal processing step whose output surfaces (even indirectly) in the device output, FDA will ask for that sub-step's accuracy. Examples: an internal segmentation that defines a region the user sees (DICE coefficient expected); an internal classifier whose label appears in a downstream calculation (per-class precision/recall expected); an internal signal filter whose output affects a measurement (filter response curves expected).

**Pre-empt with**: for each internal step that contributes to a user-visible output, either (a) provide accuracy on a held-out set with the standard metric for that operation, or (b) explicitly argue that the step is internal-only and not part of the device output, so its accuracy doesn't need separate validation.

## Category C — CAD distinction

### C1. Diagnostic vs. aid distinction

FDA pattern: any AI/ML device will be probed on whether it constitutes a diagnostic device (or, in imaging, Computer-Aided Detection / Diagnosis — CAD). The answer materially changes which performance bar applies. For imaging CAD, a Multi-Reader Multi-Case (MRMC) study is typically required; non-CAD aids and most non-imaging clinical decision support tools have a lower bar.

**Pre-empt with**: explicit statement of the device's role up front. Example for an aid: "Subject device does not detect, diagnose, or triage findings. It does not produce probabilities or risk scores. It is a [function] aid only — the clinician makes the diagnosis."

For imaging, the CAD product codes are **MYN, QAS, QFM, QIH, OEB**. If you're explicitly trying to avoid CAD classification, do not let your IFU language drift into CAD territory. Equivalent traps exist in non-imaging domains (e.g. CDS that "recommends a diagnosis" vs CDS that "presents information for clinician interpretation") — the IFU framing decides which side of the line you sit on.

## Category D — Standard of care alignment

### D1. Is the output used in US standard workflows?

FDA pattern: any output not standard in US clinical workflow (e.g. a novel visualization, a non-standard measurement, an EU-typical view) will be questioned on US-workflow consistency.

**Pre-empt with**: explicit citation of US clinical practice guidelines (ACR, SBI, equivalent specialty body) or peer-reviewed US clinical studies showing the output is consistent with US workflow. Don't assume US workflow == European workflow.

### D2. Synthetic / derived / reconstructed inputs

FDA pattern: if your device processes inputs that are derived or reconstructed rather than originally acquired (e.g. synthetic 2D images from 3D imaging, reconstructed waveforms, downsampled signals, transformed features), FDA will require explicit US-specific labelling caution that the derived input is not intended as the primary diagnostic source.

**Pre-empt with**: bake US-specific labelling cautions into the IFU and Operator Manual from day 1 if your inputs are anything other than the originally acquired clinical data.

## Category E — Performance testing data

### E1. Case collection protocol

FDA pattern: any test dataset will be questioned on the case collection protocol, including inclusion/exclusion criteria, sampling method, source institutions, and case distribution.

**Pre-empt with**: a written, dated case collection protocol filed BEFORE you select cases. State inclusion/exclusion criteria, source institution(s), sampling method (consecutive, stratified, enriched), and date range.

### E2. Generalisability to US population

FDA pattern: any test dataset (especially OUS-only) will be questioned on US-population representativeness, with explicit demographic stratification requested.

**Pre-empt with**: explicit comparison table — your test set demographic distribution vs. US population (or US disease-specific population per the relevant registry: BCSC and MQSA for breast imaging, NSDUH for mental health, NHANES for general health, NCDR for cardiology, NCI SEER for cancer, etc). Industry rule of thumb: for non-diagnostic aids, 100% OUS may be acceptable if demographic representativeness is demonstrated. For diagnostic / CAD devices, FDA strongly prefers ≥50% US data.

### E3. Ground truth methodology — panel of truthers

FDA pattern: ground truth methodology is the most predictable AI/ML deficiency. FDA's default expectation is a panel of at least 2 expert truthers plus a 3rd tiebreaker, with documented qualifications, instructions, and consensus mechanism.

**Pre-empt with**:

- **Panel of ≥2 truthers + 1 tiebreaker** is the FDA expectation
- State qualifications (years of experience, fellowship training, board certification)
- Document the instructions given to truthers
- Document the consensus mechanism
- If you used a single truther (cost-driven), be ready to defend with biopsy-confirmed outcomes or other "harder" ground truth

Workup-based ground truth (biopsy + multi-year follow-up) can be argued as stronger than panel consensus in some cases, but expect FDA to push back regardless. Have the defence ready in your protocol.

### E4. Subgroup analysis

FDA pattern: aggregate performance is never sufficient. Subgroup analysis stratified across clinical confounders is the default ask, formatted as a confusion matrix per subgroup.

**Pre-empt with**: subgroup analysis stratified by all relevant axes for your indication. Typical universal axes:

- Age bands appropriate to the indication
- Sex
- Race/ethnicity (per OMB 5-category minimum)
- Disease status (positive / negative ground truth)
- Severity / size / stage where clinically meaningful

Plus domain-specific axes — for breast imaging this includes BIRADS density (A-D) and lesion size; for dermatology, Fitzpatrick skin type; for cardiology, ejection fraction bands or rhythm type; for digital pathology, tissue source institution and slide scanner model. Mirror the equivalent demographic and clinical stratification expected for your specialty.

Format as confusion matrix per subgroup, plus an aggregated table of sample sizes per cell.

### E5. Performance goal justification

FDA pattern: any internal performance goal (e.g. "≥X% accuracy") will be questioned on clinical acceptability — not as a self-imposed target, but as a clinically meaningful threshold.

**Pre-empt with**: clinical reasoning — not just "this is our internal target". Cite literature on baseline performance for the same task, or argue the performance is acceptable given the user-in-the-loop nature.

### E6. Single-expert ground truth bias

FDA pattern: even with strong ground truth, single-reader annotations risk bias (different experts annotate differently — bigger/smaller regions, stricter/looser thresholds, different classification habits). FDA will probe whether the scoring metric is invariant to that variability.

**Pre-empt with**: see E3. If single-expert ground truth is unavoidable, design your scoring metric to be invariant to the dimension of variability (e.g. for spatial annotations: centre-point distance rather than overlap; for classification: well-calibrated binary outcomes rather than confidence scores), and explicitly argue this in the protocol.

## Category F — Literature applicability

### F1. Reused literature

FDA pattern: any cited publication will be questioned on whether the results applied to the final release version of the software.

**Pre-empt with**: every cited paper needs a paragraph mapping the paper's findings to the subject device version. State explicitly which version of the algorithm was used, whether identical to release, and what's changed.

## Category G — Labelling and UI visibility

### G1. Output visibility

FDA pattern: any usability study finding about output visibility (text size, contrast, position) will be probed on remediation.

**Pre-empt with**: usability study findings should already be addressed (in the operator manual or UI) BEFORE submission. Don't leave usability defects to be litigated in AINN.

### G2. Saving and persistence

FDA pattern: any output that can be saved (to PACS, to local cache, to the device database) will be probed on persistence behaviour — what is saved, when, where, and what user action is required.

**Pre-empt with**: operator manual must describe persistence behaviour explicitly — what is saved, when, where, and what user action is needed.

## Pre-empt checklist — paste into your draft 510(k)

Before submission, confirm the submission contains explicit answers to each of:

- [ ] A1 — User interaction model with event types
- [ ] A2 — Output bounds and semantics
- [ ] A3 — Concurrency / multi-query behaviour
- [ ] A4 — Edge case behaviour decision tree
- [ ] B1 — Explicit statement of what the algorithm does NOT do
- [ ] B2 — Justification for every threshold and hyperparameter
- [ ] B3 — Segmentation sub-accuracy (DICE) or explicit "internal only" argument
- [ ] C1 — Explicit non-CAD statement (if not CAD)
- [ ] D1 — US standard-of-care citation
- [ ] E1 — Dated case collection protocol
- [ ] E2 — Demographic comparison table vs. US population
- [ ] E3 — Panel of truthers OR strong defence of alternative
- [ ] E4 — Subgroup analysis stratified by all relevant demographic and clinical axes for the indication
- [ ] E5 — Clinical justification for performance goal
- [ ] F1 — Literature mapping paragraph per cited paper
- [ ] G1 — Usability defects already addressed in UI/manual
- [ ] G2 — Persistence behaviour in operator manual

If 12+ boxes ticked, you'll likely get cleared with a light AINN. If <8 boxes ticked, expect a 60+ day AINN cycle.
