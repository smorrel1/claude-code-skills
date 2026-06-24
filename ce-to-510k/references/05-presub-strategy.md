# Pre-Submission (Q-Sub) Strategy

## What a Q-Sub buys you

A Q-Submission (formerly "Pre-Sub") is a free, non-binding written FDA response to specific questions about your planned submission. The mechanism is described in FDA's "Requests for Feedback on Medical Device Submissions: The Q-Submission Program" guidance (latest 2023).

What you get:

- **Written FDA feedback** within ~70 days (binding-in-spirit, not in law)
- **Optional teleconference** with the assigned reviewer (~15 minutes per question is realistic)
- **A documented record** you can reference in the eventual 510(k)

What you do **not** get:

- A binding determination
- A clearance preview
- Guarantee the reviewer of your eventual submission is the same person

## Cost-benefit framework

A Pre-Sub adds ~60–90 calendar days plus internal authoring effort (~2 weeks for a focused 3-question Pre-Sub). It is worth it when:

| Situation | Pre-Sub? | Why |
|-----------|----------|-----|
| Clear predicate, same product code, same IFU subset | **No** | Don't add 90 days for predictable answers |
| Novel AI/ML claim not seen in predicate | **Yes** | Get FDA buy-in on test methodology before spending months on clinical study |
| Ambiguous predicate choice (2-3 candidates) | **Yes** | Have FDA confirm which they prefer |
| Special controls compliance uncertain | **Yes** | Avoid drafting against the wrong special controls |
| Indications language ambiguous (screening vs diagnostic) | **Yes** | Get FDA to lock the boundary |
| You can't afford a Refuse-to-Accept | **Yes** | RTA forces a 6-month restart |
| You have <6 months runway and confident in predicate | **No** | Submit, take the AI request hit if needed |
| You want FDA to comment on training data demographics | **Yes** | Demographics is a frequent AI/ML AINN trigger |

## The 3-5 question rule

Reviewers will meaningfully address **3 to 5 questions**. Beyond that, answers become generic. Choose questions that:

1. Are **binary or constrained** (not open-ended). "Do you agree that LLZ is the appropriate product code given the IFU below?" beats "What product code applies?"
2. **Force a position**. "Confirm that ground truth from a single fellowship-trained expert in [specialty] is acceptable if [conditions]" beats "What's acceptable ground truth?"
3. Are **decision-critical** for your plan. Don't waste a question on something you'll do anyway.
4. **Cite prior FDA positions** where possible. Reference cleared 510(k)s with similar issues; reviewers find it easier to extend a precedent.

## Q-Sub document structure

```
1. Cover Letter (one page)
2. Device Overview (1-2 pages)
   - Trade name, intended use, predicate(s)
   - Where in development you are
3. Specific Questions (numbered, with context per question)
   For each question:
   - Context (1 paragraph)
   - Our proposed approach (1-2 paragraphs)
   - Question (one sentence)
4. Appendices
   - Predicate 510(k) Summary
   - Draft IFU
   - Algorithm description
   - Proposed test protocol summary
```

Keep total length under 50 pages. Reviewers triage by length.

## Common Pre-Sub questions for AI/ML SaMD

The highest-yield AI/ML Pre-Sub questions are:

1. **Product code confirmation**: "Confirm product code [XXX] applies to a device with the indications below."
2. **Predicate acceptability**: "Confirm K###### is an acceptable predicate for the subject device."
3. **Ground truth methodology**: "Is a panel of N expert [specialty] clinicians with consensus-by-majority acceptable as reference standard for [specific endpoint]?" (NB: FDA strongly prefers panel of ≥2 + tiebreaker — see [06-fda-ai-ml-deficiencies.md](06-fda-ai-ml-deficiencies.md))
4. **Test set composition**: "Confirm a test set of N cases stratified by [relevant demographic and clinical axes] is adequate for the generalisation claim."
5. **OUS data acceptability**: "If 100% of test cases are OUS, confirm acceptable if demographic representativeness to US population is demonstrated." (Industry rule of thumb: 100% OUS typically accepted for non-diagnostic aids; FDA strongly prefers ≥50% US for diagnostic / CAD devices.)
6. **Performance goal justification**: "Confirm clinical acceptability of [X% accuracy] as the performance goal given the device is an aid (not autonomous)."
7. **Subgroup analysis scope**: "Confirm subgroup analysis stratified by [list] is sufficient; agree we do not need analysis on [excluded categories]."
8. **Special controls applicability**: "Confirm special controls listed in 21 CFR XXX.XXXX (b) apply / do not apply to this submission."

## Pre-Sub timeline (realistic)

| Day | Event |
|-----|-------|
| 0 | Submit Q-Sub via CCP |
| 5-10 | FDA acknowledges receipt, assigns lead reviewer |
| 30-45 | FDA may request clarification |
| 60-70 | Written response received |
| 75 | Optional teleconference scheduled |
| 75-90 | Teleconference held, follow-up email exchanges |

## Telecon best practice

If the Pre-Sub includes a teleconference:

- **Allocate 10 minutes per question maximum**
- **Lead with your proposed answer**, ask FDA to confirm. Don't ask open-ended.
- **Bring 2 people**: a regulatory lead and a clinical/technical lead. No more — meetings of 6+ lose focus.
- **Send a written summary within 24 hours** to FDA, asking for confirmation of action items
- **Minutes**: take detailed minutes. They become part of your 510(k) Section 00.FDAComms.

## The "we'll review with the submission" deflection

FDA reviewers often deflect specific questions with "we'll review that with the submission." If this happens, push politely:

- "We understand. Could you indicate whether the approach we've outlined is [acceptable / has obvious problems]? We're trying to avoid an RTA."
- "If our test protocol matches K###### which you cleared, can we treat that as a baseline?"

Sometimes the deflection is real (the reviewer doesn't have authority to bind), sometimes it's a soft signal you should restate the question.

## When NOT to do a Pre-Sub

- **Clear predicate + clear special controls + standard test methodology** — submit directly, use the AINN cycle if needed
- **You've already done extensive clinical work** — Pre-Sub feedback may force redesign you can't afford
- **The reviewer pool for your device type is small and known** — informal email may get faster informal feedback (but not a binding record)
- **Hard deadline within 6 months** — the Pre-Sub + 510(k) compound timeline is 9-12 months
