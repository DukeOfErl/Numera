# Validator prototype: from a property question to a reviewed number

## Why

Two probes have settled the questions that could have made a validator pointless. ADR-0040: given a
paper, an agent finds the number and quotes it verbatim, with zero fabricated quotes in fifteen.
ADR-0050: article full text is the reachable surface, `isOpenAccess` is the single pre-filter, and
no parsing project widens it. What has not been built is the thing those probes were for — a working
loop in which a **question** produces **candidate numbers with their evidence**, and a **person**
decides whether each number came from the text it is attributed to.

This change builds that loop as a prototype, end to end, so the next version can be designed against
observed reviewer behaviour and observed extraction failures rather than against guesses. It is
deliberately a prototype: it will be rebuilt or reworked with more care once it has run on real
papers and real reviewers. What it must get right is the contract with the reviewer and the record it
leaves behind, because those are what the rebuild will be measured against.

It differs from `add-grounding-validator` in direction. That change verifies a **claimed** entry
against its **cited** source. This one starts from a **question** and discovers sources, values and
conditions, then puts each value in front of a human. The two share the Europe PMC client and the
verbatim-quote discipline and nothing else; that change stays open and untouched.

## What Changes

- **Source discovery.** A property question ("doubling time of *E. coli*") is turned into an
  Europe PMC search restricted to open-access research articles with a PMCID, and each candidate's
  full text is fetched as JATS XML or recorded as unreachable with a typed reason. The licence is
  recorded per paper. Reviews, meta-analyses, editorials and preprints are excluded by metadata;
  perspective essays mis-tagged as research articles are caught by the absence of a Methods section.
- **Value extraction.** One paper produces zero or more **claims**: a value or range for the asked
  property, each with a verbatim quote and its location, the conditions under which it was measured
  (organism, strain, medium, temperature, growth phase, culture mode, normalisation basis) and the
  measurement method — each as a verbatim quote with its own provenance state. Every quote is checked
  mechanically against the paper before anything is kept. A paper that states nothing extractable is a
  first-class outcome, distinct from a paper that could not be read. Extraction is a **fixed
  pipeline**, one model call per paper with one bounded retry, under a per-paper spend ceiling of
  **$2** and a per-run budget.
- **The review task.** Each claim becomes one review item: the question, the value, the paper, a
  condition block, and **two texts** from the same paper — the supporting text and a second text
  that is either a distractor (similar in content, differing in a dimension the reviewer can see) or a
  second legitimate statement of the same value. The reviewer always chooses which text fits the
  value better, and separately approves or disapproves that the value came from the paper under those
  conditions. Which kind the second text was is stored, never shown.
- **The record.** Property, value, paper reference, both texts and their locations, the conditions,
  the reviewer's choice and verdict, who reviewed, and the fingerprint of what produced the item, all
  in the project's Postgres database, written **fail-closed** — a lost verdict is the loss of the one
  thing this prototype exists to collect.
- **A review page**, a second Streamlit script beside the ask app, reusing its sign-in door and
  identity conventions, showing one item at a time.
- **Reuse, marked as unreviewed.** The Europe PMC client, disk cache and retrieval types from
  `feat/grounding-validator-cytoskeleton` are ported into `src/bionumbers/` with one known defect
  corrected in the port itself: the service now answers HTTP 500, not 404, for an article without
  XML, and the client as written raises where it should report unavailability.

Not in scope: supplementary files and figure images (ADR-0050); PDF reading; verifying BioNumbers
entries (that is `add-grounding-validator`); any scoring of reviewer agreement beyond storing the
rows that make it computable; model routing below Opus; a public deployment.

## Capabilities

### New Capabilities
- `source-discovery`: From a property question to a set of open-access research articles with full
  text in hand or a typed reason it is not, each with its licence recorded.
- `value-extraction`: From one article to zero or more claims — value, verbatim quote, location,
  conditions and method with provenance states — every quote mechanically verified, under a spend
  ceiling, with "nothing to extract" and "could not read" kept distinct.
- `review-task`: What a reviewer is shown for one claim, what they must decide, how the second text
  is chosen and constrained, and what is recorded about the item and the decision.

### Modified Capabilities

None. The review page reuses the `user-identity` door as implemented and changes no requirement of
it; a deployment with no identity configured stays open, exactly as that spec already requires.

## Impact

- **New code**: `src/bionumbers/` becomes a real package (the `validator` extra and the
  `bionumbers` script already exist in `pyproject.toml` with no package behind them). A second
  Streamlit entry script at the repository root. New tables in the existing Neon database.
- **Ported code**: six modules and their fixture-backed tests from
  `feat/grounding-validator-cytoskeleton`, treated as new code for review purposes.
- **Dependencies**: the `validator` extra gains `streamlit`, `sqlalchemy` and `psycopg[binary]` for
  the review page and the store. The extraction call uses the `anthropic` SDK already in the extra.
  The review page also imports the ask package's sign-in door, so a deployment installs both extras.
- **External services**: Europe PMC (free, no documented rate limit, cached on disk); the Anthropic
  API at Opus 4.7 rates; the existing Neon project.
- **Documentation**: README, architecture diagrams, CLAUDE.md's architecture section and ADR table,
  the changelog, and the spec-conformance mapping — all in this change.
- **ADR block**: `0900`–`0990`, allocated in `CLAUDE.md`; `0900`–`0920` later renumbered `1520`–`1540` (collision with `dev`).
