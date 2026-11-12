# Investor-document style brief

Use this brief when revising the company’s documents for investors and the company data room. Follow it consistently across documents, while allowing their content to determine the appropriate structure.

## 1. Objective

Write for an intelligent investor who understands business but may know little about medical AI, clinical trials or the company’s technology.

The reader should understand:

- What the technology does.
- Why it matters in a practical setting.
- How its main components work together.
- What the evidence supports.
- What is in use, in development or still a proposed application.

The writing should feel considered, natural and informative. It should not sound like marketing copy, an academic abstract or an AI-generated summary.

Preserve the author’s meaning. Improve the explanation, sentence construction and organisation without inventing facts or strengthening claims.

## 2. The preferred voice

Use British English and a calm, direct tone. Write in connected paragraphs, with enough explanation to make technical material accessible.

Prefer concrete subjects and verbs:

> The product uses the imaging measurements alongside the clinical record to predict outcome.

Avoid abstract descriptions:

> Multimodal integration facilitates enhanced prognostic inference.

The objective is clarity, not maximum brevity. A few extra words are useful when they explain a relationship or introduce an unfamiliar idea.

### Too compressed

> One frozen checkpoint. No retraining. Missing values handled natively.

### Preferred

> The same trained model serves each task without being retrained for the dataset. It also accepts missing values directly, so they do not need to be estimated before prediction.

### Too elaborate

> The framework provides a comprehensive and sophisticated mechanism through which multiple heterogeneous sources of clinical information can be operationalised.

### Preferred

> The framework combines information from scans, blood tests and clinical records for use in the same analysis.

Use third person by default: “the company”, “the framework”, “the analyst” or “the model”. Use “we” or “our” only when the document deliberately adopts a company voice. Keep that choice consistent.

## 3. Take the reader through the explanation

Introduce the purpose of a system before its components. Introduce a component before describing where it runs or how it connects to other software.

A useful order is:

1. The practical question or problem.
2. What the company’s approach does.
3. How it works.
4. The evidence or example.
5. The implication and its limits.

This is a guide to the explanation, not a mandatory five-paragraph template.

### Abrupt

> The same pipeline runs on the company’s own GPU servers.

The reader has not yet been told what the pipeline does or why its location matters.

### Preferred

> The pipeline prepares mammograms for analysis and returns the result to the hospital’s image archive. The same processing runs on the company’s GPU servers for every site, so each hospital is read the same way.

Do not add technical details simply because they are available. Include them when they explain a capability, a constraint, a cost or an important distinction.

## 4. Introduce every substantial section

A section should begin with a sentence that establishes its subject and relevance. Avoid starting with an isolated fact, an unexplained technical principle or a colon followed by data.

### Abrupt

> The evidence base is 64 patients:

### Preferred

> The analysis uses a cohort of 64 patients to compare the adjustment methods. The table below reports the results.

### Abrupt

> Randomisation balances baseline covariates across treatment arms in expectation.

### Preferred

> To understand the purpose of adjustment, it helps to distinguish randomisation from the balance observed in an individual trial. Randomisation balances baseline characteristics on average, but differences can remain between treatment groups, particularly in smaller studies.

Use an introduction that adds understanding. Avoid empty preambles such as:

> In today’s rapidly changing healthcare environment…

> It is important to understand the significance of…

## 5. Connect paragraphs and ideas

Do not leave the reader to infer how a series of statements fits together.

Use transitions that describe the actual relationship:

- “This allows…” for a consequence.
- “The next step…” for a sequence.
- “For example…” for an illustration.
- “The same record…” when continuing a discussion.
- “However…” when introducing a material limitation.
- “First”, “second” and “finally” when several paragraphs develop a shared argument.

Do not insert a transition at the beginning of every paragraph. The connection should feel natural.

### Disjointed

> The method is prespecified. Imaging is available across sites. The analysis is reproducible. Model versions are recorded.

### Preferred

> The approach combines a prespecified analysis method with consistent use of imaging and a reproducible process. First, the team defines the adjustment method before analysing treatment outcomes. Second, the imaging workflow supports the data available across sites. Finally, the analysis records the model versions and processing steps so that the results can be reproduced.

Use this structure only where the underlying facts support it. Do not invent a sequence to make the prose smoother.

## 6. Sentence length and density

Vary sentence length. Use a shorter sentence to establish a point and a longer one to explain it where needed.

Avoid:

- Several short declarative sentences in succession.
- Sentences containing multiple unfamiliar concepts.
- Long strings of nouns.
- Semicolons used to compress an entire paragraph into one sentence.
- Repeated sentences with identical rhythm.

### Too short and dense

> The agent receives a reference. Endpoints read the record. Results return to it. Raw data stays local.

### Preferred

> The product receives a reference to the study in the hospital’s archive. It reads the images from there and writes its overlay back, while the images themselves stay inside the hospital’s own systems.

### Too many concepts at once

> Each versioned, calibrated and discoverable skill exposes schemas, lineage, an applicability envelope and governance metadata.

### Preferred

> Each skill describes its inputs and outputs, the model version and the data used to train it. It also states the conditions in which its results apply and the governance requirements for its use.

Do not shorten sentences at the expense of readability.

## 7. Explain technical language at first use

Use the technical term when precision requires it, but introduce it through a plain explanation.

### Preferred examples

> The model converts the scan into a numerical representation, called a latent.

> The product marks the same piece of tissue on both views of the breast. This is called tissue correspondence.

> A supercovariate summarises prognostic information from several baseline measurements into a score used in the trial analysis.

> An application programming interface, or API, gives other software a defined way to request an operation.

Once introduced, use the term consistently. Do not redefine it in every section.

Avoid replacing technical terms with vague language. “Numerical representation” is useful; “intelligent understanding of the patient” is not.

## 8. Remove AI-style constructions

### Slogans and punchlines

Remove sentences whose main purpose is to sound memorable.

Avoid:

> Five models stand behind that number, and the score means what it means because of them.

> The pattern is the point.

> One score, a better trial.

Prefer:

> The score combines outputs from five models. The following sections describe their contribution to the analysis.

Or delete the sentence if the surrounding text already explains the point.

### Artificial contrasts

Avoid:

> This is not just a model. It is a platform.

> The company sells certainty, not software.

Prefer:

> The product returns its result to the radiologist inside the reading software they already use.

Keep a contrast when it carries necessary information:

> The reported reduction concerns projected recruitment requirements, rather than a change to the size of the observed cohort.

### Vague emphasis

Avoid:

> The implications are significant.

> This changes everything.

> The reasons are structural.

Prefer a specific consequence supported by the document:

> The shared interface reduces the integration work required for each application.

### Forced lists and repeated patterns

Do not organise every argument into three points. Do not end each section with a summary slogan. Do not begin every paragraph with “This”.

## 9. Vocabulary and punctuation

Use British spellings such as:

> modelling, standardisation, randomisation, programme, centre, artefact, haematology, analysing

Do not use em dashes. Use commas, full stops or semicolons where appropriate.

Avoid rhetorical questions, metaphors, clichés, emojis and exclamation marks.

Avoid promotional or habitual AI vocabulary, including:

> unlock, harness, powerful, groundbreaking, cutting-edge, revolutionary, transformative, game-changer, seamless, holistic, synergy, delve, tapestry, landscape, ecosystem, pivotal, remarkable, boost, supercharge, world-class, best-in-class

Avoid “leverage” as a verb. Use “use”.

Do not replace a banned word with another promotional synonym. Replace the sentence with a concrete explanation.

### Promotional

> The platform unlocks powerful insights from a complex data landscape.

### Preferred

> The platform combines data from different clinical systems so that researchers can analyse it together.

## 10. Evidence and scientific meaning

Preserve:

- Every retained numerical result and its units.
- The dataset, cohort and evaluation conditions.
- Comparators and baselines.
- Confidence intervals and uncertainty.
- Distinctions between training, fine-tuning and frozen-model evaluation.
- Qualifications that affect interpretation.

A stylistic edit must not make the evidence appear stronger.

### Overstated

> The product clearly outperforms the competing product.

### Preferred when intervals overlap

> The product has the higher estimated score, but the confidence intervals overlap.

### Overstated

> The imaging representation proves that the model generalises across hospitals.

### Preferred

> The imaging representation improved prediction in the held-out hospital cohort.

### Incorrect implication

> The approach increases trial size.

### Preferred

> The approach reduces uncertainty around the treatment estimate, giving the existing trial the precision that would otherwise require more participants.

### Ambiguous projection

> The method reduces recruitment by 32%.

### Preferred

> Under the stated assumptions, the calculation projects 32% fewer participants for the same statistical power.

Distinguish association from causation. An adjusted treatment estimate changing does not mean the treatment became more effective.

Do not repeat a caveat after every sentence. Place it where it clearly governs the relevant result or section.

## 11. Development status and present tense

Use direct present tense to explain how the architecture and workflows operate:

> The agent selects a skill.

> The system proposes a protocol.

> The framework records the methods and results.

Avoid repeatedly writing:

> would select, could propose, might record, is being developed to

Place the development context in one concise status statement:

> The web viewer is in advanced development.

This lets the body explain the system clearly without repeating the same qualification.

Present-tense architectural descriptions must not imply evidence that does not exist. Do not invent completed deployments, approvals, validated performance or customer use.

If an underlying fact is uncertain, retain the distinction or raise it separately for the author. Do not resolve uncertainty by changing the tense.

Name a product the way the company does: its real product name, or a neutral term such as “the viewer”. Do not invent a codename in a document an investor will read.

## 12. Dates and language that ages quickly

Keep:

- The document date on the cover.
- The year in the copyright.
- Dates that are essential to interpreting evidence, where applicable.

Remove development chronology that adds little to the investment case:

> The architecture was agreed in July…

> A demonstration was built in May…

> As of September, the team is starting…

Prefer:

> The architecture supports both a chat interface and a direct software endpoint.

Avoid “recently”, “currently”, “today”, “soon” and “in the coming months” unless the timing is necessary.

The document should remain broadly readable over the next few months without suggesting that incomplete work has already been completed.

## 13. Headings, subtitles and emphasis

Use descriptive headings in sentence case.

Preferred:

> What it is  
> Why it matters  
> What makes it different  
> How it is built  
> Applications  
> Status

For technical reports, use headings that name the evaluation:

> Outcome prediction in a held-out cohort

Rather than:

> Predict the future from any scan

Remove promotional subtitles beneath document titles. A useful introductory paragraph is welcome; a tagline is not.

Avoid bold phrases at the start of every paragraph. Use headings and paragraph structure to organise the explanation.

Retain a repeated structure such as “What we tested” and “Result” when it helps readers compare experiments in a full validation report.

## 14. Tables, figures and captions

Introduce a table or figure through its purpose.

### Weak

> The table compares adjustment methods.

### Preferred

> The table below compares the adjustment methods on the same patient cohort.

Explain the important result in the prose. Do not repeat every value.

Captions should identify:

- What is shown.
- The relevant cohort or conditions.
- How to interpret axes or metrics, where needed.
- A qualification essential to understanding the figure.

Avoid captions that simply restate a slogan.

### Weak

> One technology layer, used by anyone.

### Preferred

> One result, delivered where the work happens. The radiologist, the reporting software and the archive all receive the same overlay through the interface each already uses.

In short investor documents, avoid showing the same results as both an image table and a native table. Keep both only when they serve distinct purposes or the full technical report requires the detail.

## 15. Length and structure

Preserve the existing section order when it supports understanding. Do not force every document into an identical template.

When shortening, remove material in this order:

1. Repetition.
2. Slogans and vague conclusions.
3. Speculative commercial or technical claims.
4. Unnecessary implementation detail.
5. Examples that duplicate an earlier explanation.

Preserve useful introductions and connecting sentences. They are often what makes the document readable.

Do not meet a page target by shrinking the font, squeezing margins or turning paragraphs into fragments.

## 16. Worked example

### Before

> One model, every clinical question. The orchestration substrate exposes calibrated primitives over the model family. An agent could compose these to unlock insight. The system would retain analytical memory. This is not just automation; it is an AI clinician-scientist.

### After

> The product carries out the steps a radiologist would otherwise do by eye. It measures the breast in each view, matches the tissue between them, and marks the corresponding position of use. The agent selects the appropriate skills and records the methods and results so that the analysis can be reviewed.
>
> The same measurements support research. A researcher can compare matched positions across a cohort, and test whether the match holds on their own data.

The revised version explains the mechanism, connects the ideas and removes unsupported breadth. It does not replace the original slogans with new ones.

## 17. Editing workflow

Read the whole document before changing individual sentences.

Then make three passes:

### First pass: meaning and organisation

Identify the purpose, intended reader, main claims and evidence. Check whether concepts appear in a sensible order. Preserve the author’s edits and technical distinctions.

### Second pass: prose

Revise each paragraph for natural sentence construction, clear subjects, useful transitions and accessible language. Remove repetition, promotional wording and formulaic structures.

### Third pass: interpretation

Read the document as an investor unfamiliar with the company. Check whether a reader could misunderstand a result, confuse a projection with an achievement, or assume that a development capability is clinically deployed.

Resolve wording problems in the document. Keep factual questions separate rather than inserting editorial commentary into investor-facing text.

## 18. File and PDF delivery

When editing files:

- Save a backup before changing the source.
- Update the Markdown as the authoritative version.
- Preserve existing filenames, assets and user edits unless instructed otherwise.
- Use the existing the company document template, and the `md2docx` skill for Word output (narrow margins, page numbers at the foot).
- Regenerate the PDF from the revised Markdown.
- Inspect every rendered page.

Check for narrow table columns, cropped figures, orphaned headings, excessive blank space, awkward paragraph breaks, duplicated data and literal Markdown or HTML.

Keep the cover date and copyright year. Remove only development dates from the body unless instructed otherwise.

Report briefly what changed, where the files are and whether the requested page count was met.

## 19. Final acceptance checklist

Before delivery, confirm:

- A new investor can understand the opening without specialist knowledge.
- Each substantial section introduces its subject.
- Paragraphs connect rather than read as separate notes.
- Technical terms are explained when first needed.
- Sentence lengths vary without becoming choppy.
- There are no slogans, rhetorical questions or em dashes.
- Results and qualifications retain their original meaning.
- Architecture descriptions use direct present tense.
- Development status remains accurate and concise.
- Tables and figures have a clear purpose and do not repeat unnecessarily.
- The prose remains natural after shortening.
- The regenerated PDF has been checked page by page.