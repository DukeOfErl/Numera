# Tasks

ADR block for this change: `0400`–`0450`. The table in `CLAUDE.md` is the authority and has been
reconciled. `0350`–`0390` is deliberately left unallocated -- reserving it here and nowhere else
would be exactly the drift `CLAUDE.md` describes, since no other branch can read this file.

Two branches, sequential. The rename is mechanical and has no behaviour change; keeping it separate
stops a 40-file diff from swamping the review of the citation work.

## Branch 1 — `chore/rename-to-scinumbers`

### 1. The package rename

- [x] 1.1 `git mv src/bionumbers_ask src/scinumbers_ask`; update imports across `src/`, `tests/`,
      `streamlit_app.py`, `pyproject.toml` (script and `known-first-party`), `README.md`,
      `CLAUDE.md`, `docs/diagrams/architecture.md`. Scope every substitution to an explicit path
      list — `src/bionumbers/`, `pyproject.toml`'s `bionumbers` script and `docs/decisions/0040`–`0090`
      belong to another branch
- [x] 1.2 `agent.py`'s `_origin` frame filter matches the package root computed from `__file__`, not
      a hardcoded string, so it cannot drift again
- [x] 1.3 The hyphenated forms: `cli.py`'s `prog=` and its `SystemExit` prefix, `trace.py`'s
      `LOGGER_NAME` and its tag list
- [x] 1.4 **Assert the trace tag.** Nothing covers `trace.py`'s tag list today; the rename is silent
      without a new assertion
- [x] 1.5 `web.py`'s session-state keys. Renaming drops in-flight sessions — intended, but noted

### 2. The environment prefix

- [x] 2.1 The seven `BIONUMBERS_ASK_*` reads become `SCINUMBERS_*`
- [x] 2.2 A retired name raises `NotConfigured` naming its replacement, for all seven plus the
      already-retired `WARN_USD`
- [x] 2.3 The refusal is called from both driver entry points, not from `Config.from_env` alone —
      three of the seven never pass through `Config`
- [x] 2.4 `tests/conftest.py`'s autouse fixture, the eight test files setting old names, the pytest
      marker help text, the README config table, `CLAUDE.md`, ADR-0170 and ADR-0180
- [x] 2.5 ADR-0400: the package is named for the question, not for one source

## Branch 2 — `feat/scinumbers-citation-form`

### 3. `bionumbers.py` owns the miner

- [x] 3.1 New `src/scinumbers_ask/bionumbers.py` carrying today's `PATTERN`, `MIN_DIGITS` and run
      logic **verbatim**, exposing `cross_references(text)` and `rewrite(text)`
- [x] 3.2 `repository.py` mines cross-references through it; `citations.py` is untouched in this group
- [x] 3.3 Relocate the mining assertions with byte-identical expectations, and update
      `test_spec_conformance.py`'s `COVERED` in the same commit
- [x] 3.4 A single module, not a `sources/` package — `test_driver_independence.py` builds its list
      from a top-level glob, so a subpackage would escape the dependency check entirely

### 4. The delimited form

- [x] 4.1 `citations()` parses `[[nnnnnn]]`, with no shape rules, and returns identifiers in order
- [x] 4.2 It also accepts BioNumbers' form, because a user's own question introduces it and a
      session's follow-ups inherit the conversation
- [x] 4.3 An unparsable bracket group is recorded to the trace, never dropped in silence
- [x] 4.4 The system prompt interpolates the form rather than restating it, and a test asserts it —
      the two have already drifted once
- [x] 4.5 An entry rendered to the model carries the delimited form in its prose and its `cites:`
      line; the corpus and the entries table keep BioNumbers' own words
- [x] 4.6 A real model emits the delimited form — a `-m network` probe, run **before** the old path
      is deleted
- [x] 4.7 ADR-0410 (the form, and why both are tolerated) and ADR-0420 (rewrite at render time,
      never in the corpus — argued against ADR-0230 and ADR-0190)

### 5. `entry_id`

- [x] 5.1 The field, the indexes, the events, the table column and the trace keys
- [x] 5.2 The corpus key, at both ends of the contract, hand-edited independently
- [x] 5.3 A corpus built by an older ingester is refused with a sentence saying what to do, not a
      `KeyError` repr. The app cannot rebuild it: an existing corpus is never rebuilt
- [x] 5.4 The ingester's internal vocabulary is left alone — those are BioNumbers' own words inside
      the BioNumbers adapter
- [x] 5.5 ADR-0430: why an integer, what the corpus key change costs, and the four places a widening
      to a string would touch

### 6. Specs and docs

- [x] 6.1 Spec deltas, body-only — no requirement heading is renamed, so the conformance map is
      unchanged
- [x] 6.2 README, the two coupled architecture diagrams, the `CLAUDE.md` module table, CHANGELOG

## Verification

- [x] V.1 Green at every group boundary; `-m corpus` against a rebuilt corpus and the old-corpus
      refusal exercised by hand
- [x] V.2 Fault seeding over `citations.py` and the render-time rewrite, into a copy
- [x] V.3 Mutation testing over `citations.py` and `bionumbers.py` only

## Archiving

- [ ] A.1 **Blocked on `add-ask-agent`, which has 16 open tasks.** Two of this change's deltas are
      `MODIFIED`, and openspec refuses a `MODIFIED` block whose target is not yet in
      `openspec/specs/`. `corpus-ingestion` was unblocked by archiving `add-corpus-ingestion` and
      `add-corpus-autobuild` (both complete); `grounded-answering` is added by `add-ask-agent` and
      so cannot be promoted before it. Do **not** reach for `--skip-specs`: that archives the change
      without promoting anything, which is the whole reason for archiving. Retry after
      `add-ask-agent` archives.
