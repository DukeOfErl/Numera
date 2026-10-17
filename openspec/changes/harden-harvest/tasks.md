ADR block: `1700`–`1740` (reserved in `CLAUDE.md`).

## 1. The twenty-entry bound (was add-harvest-prototype 6.5, review finding 3)

- [ ] 1.1 Verified entries beyond the twentieth are dropped before the second-text call, inside the extraction operation; the article's record counts the drop
- [ ] 1.2 Tests: thirty in, twenty kept in order, no second-text call for the ten, the count recorded; twenty or fewer, nothing dropped

## 2. Repeat readings (was 6.6, review finding 1)

- [ ] 2.1 Decide D2 (derived at read time, or a recorded link) against a store holding one paper read twice; write the ADR
- [ ] 2.2 `next_item` serves one article's items together across runs
- [ ] 2.3 An entry shows its article's other readings, and which report the same property with a different value; nothing merged or dropped
- [ ] 2.4 Tests for the three scenarios in `review-task`

## 3. Small fixes (was 6.8, 6.9; review finding 8)

- [ ] 3.1 The review page keeps one engine across reruns when its database comes from `NUMERA_REVIEW_DB_URL`
- [ ] 3.2 A line whose first non-blank character is `#` is a comment in a PMCID file; test with an indented comment
- [ ] 3.3 The committable-run-folder guard lives in the operation that creates the run folder, called once

## 4. From the code review of 2026-10-15 (the five that let a wrong value or licence through were fixed on `add-harvest-prototype`)

- [ ] 4.1 A paper with no full text at discovery that `extract` fetches again has its licence read then, before any call; until it has one it is set aside with no spend (`cli._one_paper`)
- [ ] 4.2 A citation written as a superscript (`<sup><xref ref-type="bibr">`) folds away whole, caret included, so a quote with or without the marker verifies (10 of 130 cached papers)
- [ ] 4.3 A row whose label is a `<td rowspan>` carried down from the row above keeps that label as its row header (15 of 130 cached papers)
- [ ] 4.4 Re-extracting a run under the same id cannot mix two extractions on load: refuse, or load the run's items as one generation
- [ ] 4.5 Text and table cells on the review page are escaped for Markdown wherever they are shown (`>128` rendered as a blockquote), not only in `as_markdown`
- [ ] 4.6 A condition's quote is stored as the paper's text, reduced from a rendered table line as the claim's is
- [ ] 4.7 A second text may not be a fragment of the supporting text, nor a second occurrence identical to it
- [ ] 4.8 `extract` and `choose_second_text` take the model id from the client, so a caller other than the CLI cannot record and price the wrong model
- [ ] 4.9 One location mapping (`jats.Passage.location()`) and one superscript table, shared by the reader and the checker

## 6. A property names the measure and what it measures (Yoav, 2026-10-16; done on `feat/property-names`)

- [x] 6.1 The harvest asks for `measure` and `measured_object` in place of `property_name`; `naming.property_name` joins them; a claim whose parts make no name is dropped and recorded (ADR-1700)
- [x] 6.2 `review_item.property`, written on load; `store.fill_properties` and `bionumbers name-properties` for a store loaded earlier
- [x] 6.3 Tests: the join, the seven refusals, the three dropped drafts, the backfill's resume, failure and budget, the CLI
- [x] 6.4 Name the 452 entries of `harvest-demo.sqlite` and back it up; read the refusals both ways before trusting the rule (2026-10-17: 452 named, 0 refused, 3 duplicate names remain; median 14 words)
- [ ] 6.6 The names are long and three are duplicated (see `docs/roadmap.md`, deferred); a tighter instruction and a re-run, after the demo
- [ ] 6.5 A condition whose quote only points at another paper ("were described previously") is recorded as not stated in this paper, not as the condition (ask-DB session, 2026-10-16)

## 5. Before hand-over

- [ ] 5.1 Map the three requirements in `tests/test_spec_conformance.py` (recorded as gaps until then)
