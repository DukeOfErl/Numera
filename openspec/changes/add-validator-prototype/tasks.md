# Tasks

ADR block for this change: **`0900`–`0990`**, allocated in the table in `CLAUDE.md`, which is the
authority. Four decisions are already made in `design.md` and get their files in group 1, as stubs,
so the numbers are claimed before the code exists: 0900 (pipeline, not loop), 0910 (named states),
0920 (the second text), 0930 (the store fails closed). 0940–0990 are spare.

**Read this before picking up a task.** Group 2 is a **port of code nobody here has reviewed**. It ran
on another branch against a service that has since changed its behaviour; its tests pass because
they encode the same assumption the code does. Task 2.3 carries the known correction. Budget review
for the port as for new code.

**Reporting, for this change only** (`.claude/rules/validator-prototype.md`): do the tests, seeding
and mutation runs, but report them in one clause unless something fails. Yoav is deciding shape
and reviewer experience here, not verification depth.

Per-paper spend ceiling is **$2**, per the user's decision of 2026-09-18. Model is Opus 4.7 through
the Anthropic SDK; verify the model identifier and prices against the `claude-api` reference at the
time of writing `spend.py`, and record the date in its docstring.

## 1. Branch, allocation, scaffolding

- [x] 1.1 Add the row `add-validator-prototype` → `0900`–`0990` to the ADR table in `CLAUDE.md` (done at proposal time)
- [x] 1.2 Create ADR stubs `0900`, `0910`, `0920`, `0930` from the template, each with status
      *proposed* and the one-paragraph decision from `design.md`, and commit them
- [x] 1.3 Widen the `validator` extra with `streamlit`, `sqlalchemy` and `psycopg[binary]`, matching
      the floors the `ask` extra uses and saying in the comment why the review page needs both extras
- [x] 1.4 Create `src/bionumbers/__init__.py` and confirm `uv sync --extra ask --extra validator`
      resolves and `python -c "import bionumbers"` works
- [x] 1.5 Add `data/europepmc/` and `data/runs/` as the output locations in the code, and a test that
      both are ignored by git (`git check-ignore`), the way the probe README did by hand

## 2. Port the Europe PMC client (unreviewed code)

- [x] 2.1 Copy `europepmc.py`, `cache.py`, `retrieval.py`, `tests/europepmc_double.py`,
      `tests/test_europepmc.py`, `tests/test_europepmc_live.py`, `tests/test_cache.py` and
      `tests/fixtures/europepmc/` from `feat/grounding-validator-cytoskeleton` with
      `git checkout <branch> -- <paths>`. Do **not** take `corpus.py`, `cli.py`, `__main__.py`,
      `tests/test_retrieval.py` or `tests/fixtures/capture_europepmc.py` as they are
- [x] 2.2 Remove `resolve_identifier` and the `CorpusEntry` import from `retrieval.py`; keep the
      types. Confirm the offline tests import
- [x] 2.3 **Correct `_fetch_full_text` in the same commit that ports it**: "no XML" is any error
      status whose body does not start with `<article`, not `status == 404`. Re-record the
      no-XML fixture as a 500 and add the negative case the old suite lacked — a 500 with a
      non-article body yields `None`, a 500 with an article body is still an error. The negative
      must vary the *body*, which is the dimension the predicate now reads
- [x] 2.4 Read the ported module end to end as a reviewer would, and record findings in the commit
      message; fix what is found
- [x] 2.5 Bring `capture_europepmc.py` across, extended to record the two papers the research used
      (PMC13340094 with no `<back>`; PMC13248727 with XHTML tables and both micro signs)

## 3. Discovery

- [x] 3.1 Add `search_open_access(terms, *, since_year, limit, sections)` building
      `(<terms>) AND OPEN_ACCESS:Y AND (SRC:MED OR SRC:PMC) AND NOT PUB_TYPE:review AND NOT
      PUB_TYPE:"meta-analysis" AND NOT PUB_TYPE:editorial AND NOT PUB_TYPE:comment AND
      PUB_YEAR:[since TO now]`, `resultType=lite`, `cursorMark` paging, a project `User-Agent`,
      keeping only records with a `pmcid`; record the exact query with the run
- [x] 3.2 Fixture tests for the query string (punctuation escaping, every exclusion present), cursor
      iteration over two pages, the limit, and the exclusion reasons recorded per dropped record
- [x] 3.3 Fetch each kept candidate through the corrected client, into the disk cache; a
      `network`-marked test asserts that a known non-open-access PMCID yields "no XML" without
      raising, and that one fresh `OPEN_ACCESS:Y` record yields an `<article` body
- [x] 3.4 Licence: read `license` from a `core` lookup or the XML `permissions/license`
      (`ali:license_ref` and `license/@xlink:href`, both layouts in fixtures); a document with
      neither is `UNLICENSED` and its text is never written past the cache
- [x] 3.5 Add the two research fixtures to the double and test licence extraction from both layouts

## 4. The JATS reader and the quote checker

- [x] 4.1 `jats.py`: `read_jats(xml) -> Document` with `Passage(text, kind, section_path,
      element_id, row_headers, column_headers)`, citation markers kept as `[ref N]` tokens,
      `back` optional, supplementary-material references listed, `article-type` and the
      presence of a methods-titled section reported
- [x] 4.2 Fixture tests: a table cell resolves to headers plus cell; a paragraph resolves to its
      section path; the `back`-less paper reads; a `<sup>` inside a table header flattens to text;
      a paper with no methods section is reported so
- [x] 4.3 `quotes.py`: port the fold table from `probes/2026-09-09-retrieval/check_quote.py` as
      `\u` escapes, add the micro-sign fold, and implement `verify(quote, passage) -> Verified |
      Failed(reason)` checking the named passage first and the whole document second
- [x] 4.4 Turn the README canary into tests: a one-digit change to a real quote fails, in plain
      prose and across inline markup; a paraphrase fails; a whitespace-only difference passes
- [x] 4.5 Seed one defect into a copy of `quotes.py` (widen the fold to accept a changed digit) and
      confirm exactly the canary test fails; name the mutant in the commit message

## 5. Extraction

- [x] 5.1 `spend.py`: price table for the configured model (input, cached input, output), projection
      via the provider's token-count endpoint with output at `max_tokens`, actual cost from the
      usage block including cache reads; `Ceiling(per_paper=2.00, per_run=...)` checked before
      every call; a test that a projected crossing refuses the call
- [x] 5.2 `extraction.py`: the instruction (property and organism only, no unit, no expected value,
      `NOTHING_TO_EXTRACT` is correct when true, quote and name the passage id), the paper's
      passages in the system block with `cache_control`, one structured-output call returning
      claims, rejected candidates with category, condition fields with provenance states, and a
      paper state
- [x] 5.3 Verification pass: every quote through `quotes.verify`; failures returned to the model once
      with the failure named; a second failure drops the claim as unverifiable; nothing unverified
      reaches the output. A test that a fabricated quote never survives two rounds
- [x] 5.4 Terminal states per paper exactly as `design.md` D2, with `UNREADABLE` taken from
      discovery and `NOT_A_RESEARCH_ARTICLE` from the reader; a test per state
- [x] 5.5 Prior-knowledge test on the probe's case: the fixture paper stating 65 min yields no claim
      carrying 40 min, because no passage contains it
- [x] 5.6 Fingerprint: model id, instruction hash, article id, run id on every claim and state
- [x] 5.7 Write claims, rejected candidates, states and spend as JSONL under `data/runs/<run-id>/`,
      through `bionumbers_ingest.guard`; a test that a git-tracked path is refused
- [x] 5.8 Seed one defect into a copy of `extraction.py` (a quote that fails verification is kept)
      and confirm exactly the right test fails

## 6. The second text

- [x] 6.1 `distractor.py`: the second call on the cached paper asking for candidates of each type;
      the mechanical exclusion (value, its roundings, its unit conversions via `pint`, and every
      recorded occurrence of the claim) applied to folded text; the type preference order;
      second-occurrence fallback; `NOT_REVIEWABLE` with reason when nothing survives
- [x] 6.2 Tests from the scientist report's examples: the adjacent-row distractor is admitted; a
      Discussion restatement "30–40 min" of a "39 ± 1 min" claim is rejected; a converted "0.76 h⁻¹"
      is rejected for a "55 min" claim; a second occurrence is used when no distractor survives
- [x] 6.3 A test that the kind and type are on the item and absent from anything the page renders

## 7. The store and the review page

- [x] 7.1 `sql/review.sql`: `review_paper`, `review_item`, `review_decision` with the columns in
      `design.md` D8; a `time_to_decide` column if it costs nothing more
- [x] 7.2 `store.py`: load a run's JSONL into `review_paper` and `review_item`; `next_item(reviewer)`
      returning an undecided item in a paper-interleaved order; `record_decision(...)` that raises
      on failure. Tests against SQLite for the queries; one `network`-marked test against the Neon
      `test` branch for the DDL
- [x] 7.3 `review.py` (presentation): the item as the page shows it — value highlighted in each
      text, citation markers visible, a table cell as headers plus cell, the condition block with
      provenance states, both texts in an order derived from the item id so it is stable but
      uninformative; tested without a browser
- [x] 7.4 `review_app.py`: the door via `web.admit` with `check_key=None`, one item per screen, the
      two-way choice and the verdict both required, the comment box, remaining count, the "nothing
      left" state, and the not-saved message when the store raises
- [x] 7.5 `AppTest` cases: open door, closed door, unconfigured deployment; verdict without a choice
      does not complete the item; a store failure leaves the item open and says so
- [x] 7.6 A source-parsing test that no core `bionumbers` module imports `streamlit` or
      `scinumbers_ask`, and that `review_app.py` and `bionumbers.review` are the only ones that do

## 8. The command

- [ ] 8.1 `cli.py`: `bionumbers discover "<question>" --since 2005 --limit 50`, `bionumbers extract
      <run-id> --ceiling 2 --budget 40`, `bionumbers load <run-id>` into the store, and
      `bionumbers status <run-id>` printing states, spend and the cached-token fraction
- [ ] 8.2 Run end to end on one question against real papers, for ten to twenty papers, and record
      the state distribution, the spend per paper and the fraction of claims that got an item, in
      the commit message and in ADR-0900's status

## 9. Conformance, documentation, changelog

- [x] 9.1 Add every requirement of the three specs to `tests/test_spec_conformance.py`'s `COVERED`
      map, naming the tests above; record any gap in `UNMAPPED` with its reason
- [x] 9.2 Fill in ADR-0900, 0910, 0920, 0930 from their stubs with the options rejected, not only the
      one taken; move status to *accepted* as each lands
- [ ] 9.3 `README.md`: what the prototype does, how to run the three commands and the review page,
      and the two-extra install
- [ ] 9.4 `docs/diagrams/architecture.md`: one sequence diagram for question → items and one for a
      review decision, following `DIAGRAMS.md`; no agent graph, because there is no agent
- [ ] 9.5 `CLAUDE.md` Architecture: the `bionumbers` package's module table and the dependency
      direction rule for it; mark the ADR block row with what was written
- [ ] 9.6 `CHANGELOG.md` under Unreleased: Added entries for discovery, extraction, the review page
      and the store
- [ ] 9.7 `docs/roadmap.md`: a line under separate lines of work pointing at this change
- [ ] 9.8 Run the full suite once, at the end (`pytest -m "not network and not corpus"`), then
      `pytest -m network` for the live cases; record both outputs
