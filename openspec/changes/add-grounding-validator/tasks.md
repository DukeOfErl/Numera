## 1. Scaffolding and corpus interface

- [x] 1.1 Create the `bionumbers` package under `src/` with the `uv` entry points, and add dependencies: `httpx`, `lxml`, `pint`, `anthropic`, `pytest`
- [x] 1.2 Define the corpus record shape (identifier, property, organism, value/range, units, source identifier, curator quotation fields) and a loader that reads JSONL from a supplied path
- [x] 1.3 Make the loader fail with an explanatory message when no corpus path is supplied, and add a test asserting no bundled data is used as a fallback
- [x] 1.4 Add a `.gitignore` entry for the corpus directory so the evaluation dataset cannot be committed

## 2. Source retrieval

- [ ] 2.1 Define the typed unavailability reasons (`NON_ARTICLE_SOURCE`, `UNRESOLVED_REFERENCE`, `NO_FULL_TEXT`, `NO_OPEN_ACCESS`) and the retrieval result type that carries either a document or a reason
- [ ] 2.2 Implement identifier resolution from a corpus record, recording a typed reason when no persistent identifier can be determined
- [ ] 2.3 Implement Europe PMC lookup for open-access full text, returning JATS XML for the version of record
- [ ] 2.4 Add preprint fallback when the version of record is not openly accessible, recording that the retrieved artifact is a preprint and its version
- [ ] 2.5 Add a disk cache keyed by identifier and version, and a test that a second retrieval makes no network call
- [ ] 2.6 Write tests covering each unavailability reason against recorded fixtures, asserting entries are retained rather than dropped

## 3. Document structure

- [ ] 3.1 Parse JATS XML into a tree of sections, paragraphs, tables, and captions
- [ ] 3.2 Attach a structural location reference plus character offsets to every text block, and settle the serialisation format (design.md open question)
- [ ] 3.3 Mark figure-image-only content as not machine-readable
- [ ] 3.4 Test that a value in a table resolves to a table-and-cell location and a value in body text to a section-and-paragraph location

## 4. Numeric extraction and comparison (stage one)

- [ ] 4.1 Implement the numeric mention parser covering every notation variant in the design's table: both micro-sign code points, hyphen/en-dash/`to` ranges, `±`/`+-`/`+/-` uncertainty, Unicode minus, and both scientific-notation forms
- [ ] 4.2 Write the parser's test corpus from that table, including the case that a negative exponent such as `1.5e-3` is never split as a range
- [ ] 4.3 Normalise units with Pint, handling both micro-sign encodings, and reject dimensionally incompatible comparisons
- [ ] 4.4 Implement tolerance-based comparison with a configurable default of 2% relative, reporting the applied tolerance
- [ ] 4.5 Implement range containment and range overlap relations, recording which relation was applied
- [ ] 4.6 Emit candidate mentions with their locations for a claimed quantity, and test recall against a fixture document with known matches

## 5. Semantic adjudication (stage two)

- [ ] 5.1 Define the adjudication request and the schema-validated response (does this mention describe the claimed property, organism, and conditions)
- [ ] 5.2 Implement the adjudicator against `claude-opus-5` using structured outputs, passing only the candidate span and its surrounding block
- [ ] 5.3 Record the adjudication basis on every verdict: deterministic, or model-assisted with the model identity
- [ ] 5.4 Test that a numerically matching mention describing a different property or organism is rejected as support

## 6. Verdicts

- [ ] 6.1 Implement the verdict vocabulary and the rules that select among `EXACT`, `EQUIVALENT`, `DERIVED`, `CONTRADICTED`, `NOT_FOUND`, `UNVERIFIABLE`
- [ ] 6.2 Carry the retrieval reason through into `UNVERIFIABLE`, and test that it is never reported as `NOT_FOUND`
- [ ] 6.3 Reject any evidence span that cannot be located in the retrieved document
- [ ] 6.4 Emit `CONTRADICTED` with both the claimed and the found value when a mention describes the claimed quantity at a different value

## 7. Benchmark

- [ ] 7.1 Implement subset selection: the cytoskeletal term list matched on word boundaries against the property field, the flagella/cilia/axoneme/pili/fimbriae exclusion, and the six curated keyword-only inclusions
- [ ] 7.2 Test that selection over an unchanged corpus is reproducible and yields the same identifiers twice
- [ ] 7.3 Classify entries as scorable (identifier, numeric value, and curator quotation all present) and retain the rest for coverage reporting
- [ ] 7.4 Derive gold evidence spans from curator quotations, marking entries whose quotation lacks the claimed value as having no gold evidence
- [ ] 7.5 Implement stratified failure-mode counting across the closed set of reasons
- [ ] 7.6 Report coverage and capability as separate figures with their denominators stated, and report any omitted entries
- [ ] 7.7 Compare verdicts and evidence spans against gold, reporting evidence agreement separately from verdict agreement
- [ ] 7.8 Run the benchmark end to end over the cytoskeleton subset and record the baseline figures

## 8. Documentation

- [ ] 8.1 Write `README.md`: what the validator does, how to supply a corpus, and how to run the benchmark
- [ ] 8.2 Create `docs/diagrams/DIAGRAMS.md` and an architecture diagram of the retrieval → candidates → adjudication → verdict flow, following the one-diagram-per-story principle
- [ ] 8.3 Record an ADR for the two-stage split (deterministic candidates, model adjudication) and the reasoning behind it
- [ ] 8.4 Record an ADR for the verdict vocabulary, in particular why `NOT_FOUND` and `UNVERIFIABLE` stay distinct
- [ ] 8.5 Start `CHANGELOG.md` with the validator under `## [Unreleased]`
- [ ] 8.6 Update the Architecture section of `CLAUDE.md` to describe the module layout
