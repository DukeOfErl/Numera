ADR numbers for this change are allocated `0200`–`0250`. `add-grounding-validator` holds `0040`–`0090`
and `add-ask-agent` holds `0100`–`0190`. Five are planned here — `0200`, `0210`, `0220`, `0230`,
`0240` — each written as part of the task that makes the decision, never batched into the docs group.
(The `CLAUDE.md` on this branch still records the older allocation; it is off `dev` and predates the
reallocation. Correcting it is task 10.4.)

The corpus contract is group **5**, not group 8, because every trap the consumer's loader punishes
is a *serialization* decision made in 4.1 — an absent scalar emitted as `""` rather than `null` blanks
out every range-only entry at the consumer, and keywords emitted as a string become one entry per
character. Verifying after provenance, reporting and the command would leave five groups between
causing such a bug and observing it, and none of those groups touches the contract: they add keys the
loader ignores. Groups 6 to 8 are provenance, reporting and the command, in that order.

Source material for the port: `~/Bionumbers-first/src/bionumbers/` and its `tests/`. Read that
repository's `README.md` first — it documents the data quirks each rule exists for. Its `pyarrow`
dependency and parquet output are dropped here.

## 1. Scaffolding and the licensing boundary

- [x] 1.1 Create `src/bionumbers_ingest/` with an `__init__.py`, as its own package parallel to `bionumbers` and `bionumbers_ask` — do not add modules to either
- [x] 1.2 Add an `ingest` extra to `pyproject.toml` (`pydantic>=2.6`) and a `bionumbers-ingest` console script, following the one-extra-per-work-package arrangement the file's comments describe; verify `uv sync --extra ingest` installs and that `--extra validator` and `--extra ask` still resolve
- [x] 1.3 Add `data/` to `.gitignore`, and verify the ignore rule with **empty placeholder files at the paths the run would write** — the corpus, the manifest, and the temporary name task 4.2 renames from — never with a real corpus. `git status` ignores by path, not by content, so a zero-byte file proves the same thing; producing an actual corpus here would put the unlicensed export's contents in the working tree to test the very rule meant to keep them out, and if the rule is wrong that file is then one `git add -A` away from being published irreversibly. Delete the placeholders afterwards. (No ingester exists at this point in the sequence anyway — a task that can only be done with real data is a task that gets deferred to when real data is lying around.)
- [x] 1.4 Record **ADR-0200**: ship an ingester rather than a prepared corpus — why the corpus is fetched by the reader and never redistributed, and what that costs (nobody can run the agent without doing the fetch)

## 2. Reading the source format

- [x] 2.1 Port the streaming HTML-table reader: first `<tr>` is the header row, every later one a record, cell content preserved as raw inner HTML so that cleaning can detect injected markup rather than have it dropped before anything can flag it
- [x] 2.2 Port `tests/fixtures/sample_table.html` and the reader's tests: header names, row count, raw markup surviving the read, the text-marker apostrophe surviving the read, and the row limit
- [x] 2.3 Verify against a locally-fetched export that the 14 header names and the row count match what the proposal states, and that memory stays flat across the file

## 3. Cleaning one row into one record

- [x] 3.1 Port the record model, with `value`, `range_low` and `range_high` typed as number-or-absent so an empty string cannot be constructed — the trap that would otherwise blank out every range-only entry at the consumer
- [x] 3.2 Port the cleaning rules: whitespace collapsing, the text-marker apostrophe, keyword splitting, and the non-data row test. **Do not port the markup-and-entity function** — the source's `_clean_text` has the ordering bug 3.2a exists to fix, and copying it verbatim reintroduces a 71% corpus contamination that the ported tests pass over. Write that one from 3.2a instead
- [x] 3.2a Fix the ordering the source repository got wrong, do not port it: **unescape entities, then strip markup**, repeating until the text stops changing, and compute the markup flag from the unescaped text. Ported as-is, the tag pattern runs on a cell whose markup is escaped, matches nothing, and the unescape then manufactures a live tag into the output — which is why 10,206 of 14,294 records in the existing corpus carry `<IMG SRC="/WF_SQL_XSRF.html">` inside `keywords` and why `injected_html_removed` reports zero on a corpus that is 71% contaminated
- [x] 3.2b Test the escaped form specifically, because it is the only form the export contains: 20,411 occurrences of `&lt;IMG`, zero of `<IMG`. The existing test asserts the literal form, which is why the defect survived a passing suite — a fixture that exercises a shape the source never produces is the blind spot, not the test
- [x] 3.2c Assert over the whole emitted record that no field, and no keyword-list element, contains a `<` followed by a tag name. This is the second time markup has turned up somewhere nobody expected, so the guard belongs at the record boundary rather than per field. Credit: found by the ask session while building its entries panel
- [x] 3.2d Drive that assertion by injecting escaped markup into **each of the 14 columns in turn** and checking every emitted field, rather than asserting over a fixture that happens to carry it in one column. The export having it only in `Keywords` is an absence observed in one sample, which by 3.2a's own lesson is not an absence. Include the `Range` case explicitly: assert no digit from an escaped filename reaches a bound, a value, a unit, or `range_fused` — a manufactured tag there is indistinguishable from a genuine fusion, which is the two defect classes meeting
- [x] 3.2e Pin that all text reaches the output through the single cleaning boundary, so a later field path cannot bypass the ordering. A per-field fix is one refactor away from being half-applied
- [x] 3.2f Recognise a tag only by a real HTML element name, and leave every other angle-bracket token as text. The export holds exactly one HTML element and 85 content tokens across 49 records — `<D>`, `<Csat>`, `<Raf/cell>`, and the less-than sign in prose. A generic `<[^>]+>` consumes from a `<` to the next `>` and so deletes whole clauses from `Comments`, a key the consumer sends to a model. Do not raise the markup flag for a content token, or its count stops meaning anything. This defect is in the ported original and both measured figures were wrong until it was fixed
- [x] 3.3 Port value and range parsing across every notation in `specs/measurement-cleaning/spec.md`: hyphen, `to`, en/em dash, unicode minus, scientific notation, and the sign-versus-separator rule
- [x] 3.4 Port plus-or-minus handling: uncertainty around the value column, a whole-cell mean-and-deviation recovered when there is no value column, and a multi-measurement cell that must not collapse into one range
- [x] 3.5 Port link-only and link-plus-range rows: URL preserved, row kept, flagged, and no digit from the URL reaching a bound or a unit
- [x] 3.5a State at the preserved-range-text field itself that it is the source cell and retains any link URL, so it is not the string the bounds came from and a recomputation must strip the link first — the trap that made two branches measure the same population as 1,716 and 1,222. Pin it with a test asserting the URL is still there, so the semantics cannot drift silently in either direction
- [x] 3.6 Port unit normalization, and assert the direction explicitly — the Greek mu, with the micro sign absent — cross-checked against the identifier-free unit strings in the ask agent's own corpus fixture, since normalizing the other way makes every unit comparison miss while looking identical
- [x] 3.7 Port the cleaning tests, and add one test per remaining scenario in `specs/measurement-cleaning/spec.md` that the ported set does not already cover
- [x] 3.8 Add the two fused-range flags — `range_multi_number` and `range_prose_between_bounds` — leaving the computed bounds untouched, with tests including a plain two-number range that raises neither
- [x] 3.8a Derive the consumer-facing predicate `range_fused` from those flags and emit it as its own boolean on every record, `false` when clean. It is a field and not a rule over `parse_flags` because that list is a reporting vocabulary: eight names, five `range_`-prefixed, only two about fusion. Pin it with the negative tests, which are the point of the field — a plus-or-minus uncertainty range, a recovered mean and deviation, a link-only row and an unparsed cell each leave `range_fused` false while `parse_flags` is non-empty and `range_`-prefixed. Without those tests a later refactor can quietly widen the predicate from 1,445 records to 5,494
- [x] 3.9 Measure both flags over a full corpus and record the counts under task 9; narrow or drop `range_prose_between_bounds` if it fires on a large fraction of ordinary two-number ranges, rather than shipping a signal a consumer would learn to ignore. **DECIDED: keep both, and fix the tokenizer instead.** The false positives were not the heuristic being loose — they were `_extract_numbers` reading `2×10^5` as three numbers and `150,000` as two, which inflated *both* flags. Punctuation-only "prose between the bounds" fell from 347 records to 66 once notation was read correctly; the 66 residual is 0.5% of the corpus and does not meet the bar for dropping a signal. See 3.9b
- [x] 3.9b Read a caret exponent, a `×10^` mantissa and a thousands separator as part of one number. Settle a dash directly after a caret as that exponent's sign *before* the blanket dash-to-separator rule, or `10^–11` becomes `10^;11` and the exponent is stranded as its own number. This moved `range_multi_number` from 1,222 to **833** — 389 of the established figure were notation, not fused quantities — and `range_fused` from 1,740 to **1,445**. Both the earlier figures were wrong upward, and neither had shipped, so the corrected ones replace them in `proposal.md` and `design.md`
- [x] 3.9a Reconcile `range_multi_number`'s count against the 1,222 already established (see `proposal.md` — Deferred). A materially different figure means the flag is computed somewhere other than where bounds are taken as a minimum and maximum — most likely before the external-link URL is removed, where an escaped filename's digits inflate the count, or on a path the plus-or-minus branch should have returned from first. Two numbers for one population across two changes' documents is what this task exists to prevent. **RESOLVED: 1,222 exactly.** The cause was 3.2f — the generic tag pattern consumed part of one `Range` cell along with the digits in it, so the flag fired on 1,221 until angle-bracket content was preserved. `injected_html_removed` snapped to 10,206 at the same time, matching the ask session's independent count exactly
- [x] 3.10 Record **ADR-0230**: flag and count, never drop or silently correct — covering the link-only rows, the unparsed cells, and the two fused-range flags. State the contract with `add-ask-agent` as the **`range_fused` field**, with the flag names internal and changeable, so narrowing or dropping a flag is not a cross-branch change. Record why a name-matching rule over `parse_flags` was rejected and who refuted it: the counts in `design.md` (5,148 non-empty, 5,494 `range_`-prefixed, 1,445 meant), the contradiction in asking a consumer to recognise "a range concern" from a taxonomy declared internal, and that the observed vocabulary is not the emittable one — six names fired, eight can be raised — so a rule inferred from a corpus sample is not a contract at all

## 4. Writing the corpus

- [x] 4.1 Write the JSONL writer: one record per line, absent scalars as JSON null, keywords as an array
- [x] 4.2 Write the corpus to a temporary file beside the destination and rename it into place after the last row, so a failed or interrupted run leaves the previous corpus or nothing — never a short corpus, which loads cleanly and is missing entries nobody can enumerate
- [x] 4.3 Test the failure path: a run that raises partway leaves no file at the output path
- [x] 4.4 Record **ADR-0220**: JSONL only — why the parquet output and `pyarrow` go, and that a second serialization path is a place the contract can drift unnoticed

## 5. The corpus contract

- [ ] 5.1 Write the contract test: the required keys and their accepted JSON types as one literal list in one place, with a comment naming its source (`bionumbers_ask.corpus.Entry`, on `feat/ask-agent`) and pointing at that module's docstring, which carries the reciprocal obligation to message this branch before the field set or the coercions change; asserted over every line of a real ingest of the fixture
- [ ] 5.2 Test the traps the consumer's loader documents — an absent scalar emitted as null and never as an empty string, keywords as an array and never a joined string, the identifier as a number — since each fails silently or corpus-wide rather than locally
- [ ] 5.3 Test that a corpus survives one unusable row: no line is emitted for it, and the remaining lines still form a loadable corpus
- [ ] 5.4 Add the round-trip test guarded on importing the consumer's loader, so it skips on this branch and becomes live the moment this lands on `dev` beside the agent
- [ ] 5.5 Verify once, by hand, against the real loader: extract it into the scratch directory with `git show feat/ask-agent:src/bionumbers_ask/corpus.py` — touching neither that branch nor the other checkout — load a produced corpus with it, and record the result below. Never commit the extracted copy
- [ ] 5.6 Record **ADR-0210**: verifying a contract whose owner is on another branch — the three layers, why the vendored-copy alternative was rejected, and what the merge makes live
- [ ] 5.7 Load a corpus built from the full locally-fetched export with that extracted loader — at real scale, not fixture scale — and record the entry count it returns. Drive the reader, cleaner and writer directly; the command does not exist yet and is not needed for this. Fixture scale cannot expose a trap that only some real row triggers, and this is the last cheap moment to find one

## 6. Provenance

- [ ] 6.1 Compute the source file's SHA-256 and size while reading it, without a second pass over 27 MB
- [ ] 6.2 Stamp each record with the first 12 characters of that digest as the join key to its manifest
- [ ] 6.3 Write the manifest beside the corpus — full digest, source size, source modification time named as such rather than as a fetch time, ingest date, ingester version, the run's counts, and the row limit if one applied — renamed into place after the corpus, so a corpus with no manifest is a run that did not finish
- [ ] 6.4 Test that two corpora from different sources carry different digests, that each record's stamp matches its own manifest, and that a limited run records its limit
- [ ] 6.5 Record **ADR-0240**: stamp every ingest with source identity and dates — that the export carries no temporal information at all, that the loss is unrecoverable afterwards, why the fetch time can only ever be a proxy, and why the stamp is on the record as well as in the manifest

## 7. Integrity reporting

- [ ] 7.1 Port the validation report: records, rows skipped as non-data, duplicate identifiers, link-carrying records, records with no scalar, and a count per parse flag — plus the `range_fused` count stated separately, so the predicate's population is read off the run rather than inferred from the flags behind it
- [ ] 7.2 Test that records written plus rows skipped equals rows read, and that a clean run states its zeroes rather than omitting them
- [ ] 7.3 Test that duplicate identifiers are reported and both records kept
- [ ] 7.4 Test that flags appear on the emitted record as well as in the report, and that `range_fused` appears on every record and in the report's counts

## 8. The command

- [ ] 8.1 Implement `bionumbers-ingest <file>`, with an output path option, defaulting inside the ignored `data/` directory
- [ ] 8.2 Make the whole file the default and the row limit an explicit request, inverting the source repository's 200-row default, and have the report state when a limit was applied
- [ ] 8.3 Fail on a missing or unreadable source with a message naming the path, a non-zero exit, and no output file
- [ ] 8.4 Test the command end to end over the fixture: corpus, manifest and report, with the expected line count

## 9. Testing the tests, and the full run

- [ ] 9.1 Fault-seed the cleaning module per `CLAUDE.md`: copy the source to a scratch directory, seed one realistic defect there, assert the module under test resolved inside the copy, abort any injection whose search string does not match exactly once, and check that exactly the right test fails. Seed at least an `and`/`or` swap in the sign-versus-separator test, a dropped `lstrip` of the text marker, and the wrong bound returned from the plus-or-minus branch
- [ ] 9.2 Run the `mutation-test-module` skill over the cleaning module and the writer, and record what survived and what was fixed
- [ ] 9.3 Run the command over a locally-fetched full export and record here: rows read, records written, rows skipped, duplicate identifiers, the count per flag including the two new ones (see task 3.9), and the `range_fused` count. Check every zero among the flag counts against the source before accepting it — `injected_html_removed` reporting zero is what hid a 71% contamination, and a flag whose condition is unreachable is indistinguishable from a clean corpus. Expect this flag near 10,206. Sanity-check that last figure against the flags that raise it — a `range_fused` population anywhere near the 5,148 or 5,494 that the rejected rules would have selected means the predicate has been widened by mistake
- [ ] 9.4 Re-run the round-trip of 5.5 against the corpus the *command* produced in 9.3, and record the entry count. 5.7 already proved the loader accepts a full-scale corpus built by calling the pipeline directly; this confirms the command's own output path did not diverge from it

## 10. Documentation

- [ ] 10.1 Write `README.md` (empty on this branch): what the ingester does, where to obtain the export and how to cite BioNumbers, that the corpus is never committed and why, how to install the `ingest` extra, how to run the command, what the corpus and manifest contain, what the parse flags mean, and that `range_fused` — not any flag name — is the field a consumer reads
- [ ] 10.2 Add a pipeline diagram to `docs/diagrams/architecture.md` following `docs/diagrams/DIAGRAMS.md` — a short left-to-right flowchart of source file → rows → records → corpus and manifest, within the 7±2 box budget — and reference it from `README.md`
- [ ] 10.3 Add this change's entries under `## [Unreleased]` in `CHANGELOG.md`
- [ ] 10.4 Update `CLAUDE.md`'s Architecture section for the new package and its module layout, name the pipeline shape, and correct the stale ADR allocation note to `0040`–`0090` / `0100`–`0190` / `0200`–`0250`
- [ ] 10.5 Before merging, run `/code-review` over the branch, then propose a retro
