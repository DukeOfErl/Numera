## Why

This project builds a database of useful biological numbers, assembled automatically from the
scientific literature rather than by hand. The hard part is not extraction — it is **trust**. A
number without verifiable provenance is worse than no number, and every downstream ambition (trust
rankings, human-in-the-loop review, contradiction detection, literature-gap mapping) rests on one
primitive: *given a claimed quantity and a source document, can we decide whether the document
actually supports it, and show exactly where?*

This change builds that primitive — a **grounding validator** — and establishes how to measure it.
The validator is not a throwaway experiment. It is the permanent verification component the trust
ladder will sit on, and its machinery (numeric mention extraction, unit normalisation, structural
location) is most of what automatic extraction will later need.

Measuring it requires ground truth: a body of quantities whose source documents are already known,
so the validator's verdicts can be scored rather than merely inspected. An existing curated
reference dataset serves this purpose. **BioNumbers** is the current candidate — it is well suited
because its curators recorded not just the value and its source, but frequently the location within
that source and a verbatim quotation containing the number. Another curated dataset could be
substituted; nothing in the validator's design depends on this particular choice.

A survey of the candidate corpus (14,294 entries, cleaned by a previous ingestion prototype) shows
how well it supports automatic scoring:

- **77%** of entries carry a PubMed ID on the reference; **80%** carry one on either the reference or
  the primary source.
- **75%** carry a curator-written location pointer inside the reference string
  (e.g. `p.1719 left column 2nd paragraph`, `p.37 table 1`).
- **49%** carry a **verbatim quotation** from the source.
- Within the cytoskeleton slice, of entries having both a quotation and a numeric value, **87%** have
  the value literally present inside the quoted text.

That last figure is the key enabler: for a large fraction of entries the gold evidence span already
exists in the data. Automatic gold labels are therefore available, and the validator can be scored
at scale rather than against a small hand-labelled sample.

## What Changes

- Introduce a **validator** (not merely a locator): given a candidate quantity and its claimed
  source, it emits a graded verdict plus the evidence that justifies it — `EXACT`, `EQUIVALENT`,
  `DERIVED`, `CONTRADICTED`, `NOT_FOUND`, `UNVERIFIABLE`. `NOT_FOUND` (checked, unsupported) and
  `UNVERIFIABLE` (could not check) are deliberately distinct; conflating them would misreport access
  gaps as falsified facts.
- Introduce **source retrieval** restricted to openly accessible full text (Europe PMC open-access
  subset and indexed bioRxiv/medRxiv preprints), which keeps this stage free of a PDF-scraping
  stack. Inaccessible sources are recorded with a typed reason, never silently dropped.
- Split grounding into two stages with independent metrics: deterministic, recall-oriented
  **candidate generation** (numeric mention extraction and unit normalisation) followed by
  precision-oriented **semantic adjudication** (does this span state *this* quantity, for *this*
  organism, under *these* conditions). Most entries should resolve without a model call; the split
  makes it diagnosable which half is failing.
- Introduce a **benchmark** over a themed subset of the reference corpus — the cytoskeleton slice
  (~680 entries by property and keyword match) — that derives gold labels from curator quotations
  and reports **coverage** and **capability** as two separate headline numbers, stratified by failure
  mode. A single blended accuracy figure is explicitly rejected: "we can attempt 55% of entries" and
  "we are 94% correct on what we attempt" point at completely different follow-on work.
- Record the artifact actually checked (preprint version vs version of record). Preprint/published
  value drift is expected and is a real signal, not a pipeline defect.

Not in scope: extraction of previously unknown numbers, the human-in-the-loop review interface,
trust-ranking mechanics, contradiction *reporting* beyond emitting the verdict, subject areas beyond
the cytoskeleton slice, and anything about monetisation.

## Capabilities

### New Capabilities
- `source-retrieval`: Resolve a quantity's claimed reference to openly accessible machine-readable
  full text, or report a typed reason it is unavailable. Covers identifier resolution, open-access
  and preprint lookup, structured (JATS) document access, and recording which artifact version was
  retrieved.
- `evidence-grounding`: Decide whether a retrieved document supports a claimed quantity and return a
  graded verdict with evidence spans. Covers numeric mention extraction, unit normalisation and
  tolerance-based comparison, semantic adjudication of candidates, and the verdict vocabulary.
- `grounding-benchmark`: Score the validator against a curated reference dataset. Covers evaluation
  corpus selection, the cytoskeleton subset definition, derivation of gold spans from curator
  quotations, stratification by failure mode, and separate reporting of coverage and capability.

### Modified Capabilities
<!-- None. This project has no existing specs under openspec/specs/. -->

## Impact

- **New code**: this repository currently contains only a `uv` scaffold and a placeholder
  `main.py`. Everything here is greenfield.
- **External dependencies**: Europe PMC REST API (articles, full-text XML, preprint index); a unit
  handling library; an LLM for the adjudication stage. Network access and rate limiting become real
  operational concerns.
- **Evaluation corpus**: depends on an ingested copy of the reference dataset. A prior prototype at
  `~/Bionumbers-first` already produces a cleaned canonical dataset (Parquet + JSONL, 18 fields)
  from the raw 27 MB HTML-masquerading-as-`.xls` export, handling range formats, micrometre
  encodings, and injected HTML junk. Whether to import that dataset as a fixture, port the ingester,
  or re-ingest is an open decision for `design.md` — it should not be settled silently here.
- **Open risk — licensing of the evaluation corpus**: no license terms have been located for the
  candidate dataset. Using it internally to score an algorithm, and citing it, is expected to be
  acceptable; redistribution is not established. Consequently the corpus must not be committed to
  this repository, and the benchmark must treat the corpus as a swappable input so that a different
  ground-truth source can be substituted if licensing requires it.
- **Documentation**: `README.md` is currently empty and will need to describe the validator; the
  `docs/` tree mandated by `CLAUDE.md` (diagrams, requirements, decision records) does not yet exist
  and will be created as this work lands.
