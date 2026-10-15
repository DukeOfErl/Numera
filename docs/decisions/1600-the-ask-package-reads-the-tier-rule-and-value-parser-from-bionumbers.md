# ADR-1600: The ask package reads the tier rule and the value parser from `bionumbers`

- **Status:** accepted
- **Date:** 2026-10-15
- **Pull request:** not yet opened — branch `feat/ask-over-store` (`add-ask-over-store`)

## Context

The ask agent is being pointed at the harvest store, the validator's review database. Two things it
needs already exist in the validator package:

- **The trust-tier rule** — `bionumbers.tiers.trust_of` (ADR-0990): which tier an entry stands on and
  whether it is disputed. The review dashboard renders the same rule as a pie.
- **The value parser** — `bionumbers.readings.parse`: the numbers in a value the paper wrote as text
  (`7.1 ± 0.4`, `1,100–2,100`). The review page compares what a reviewer typed with it.

Until now the dependency ran one way only: `bionumbers.review` may import `scinumbers_ask`, and
`scinumbers_ask` imported nothing from `bionumbers`. Options considered:

1. **Copy both into `scinumbers_ask`.** No new direction, but two definitions of a tier: the stars in
   an answer and the pie on the dashboard would disagree the day either rule changed, and ADR-0990
   exists to stop exactly that. Two parsers would read the same value two ways.
2. **Move both into a shared third package.** The clean shape, and more than this change can carry:
   `tiers` reads the store's tables (`bionumbers.store`) and `readings` uses `bionumbers.quotes`, so
   the move drags most of the validator's data layer with it while another branch is editing it.
3. **Import them from `bionumbers`, confined to the store's loader.**

## Decision

Option 3. `scinumbers_ask` imports `bionumbers.tiers` and `bionumbers.readings` in one module, the
store's loader (`store_corpus`), and nowhere else. The code that draws stars reads a tier by its
name (`Tier` is a string enum), so the drivers never import `bionumbers` either. A run over a corpus
file never loads it, and a test asserts that in a fresh interpreter.

The footprint was measured on 2026-10-13 by importing both modules and listing what loaded: they
reach `bionumbers.store`, `curated`, `records` and `quotes`, which need SQLAlchemy and pydantic and
nothing else — no `anthropic`, `httpx`, `lxml`, `pint` or Streamlit. SQLAlchemy is already in the
`ask` extra; pydantic is now named there too, because the code imports it and a transitive
dependency is one a resolver may drop. The `ask` extra does not need the `validator` extra.

The reverse rule is untouched: `bionumbers` core still imports nothing from `scinumbers_ask`.

**Hosted tracing.** When `SCINUMBERS_TRACING=langfuse` is set (ADR-1010), everything the model sees
goes to the tracer, tool results included. Over the store that now includes paper passages, some
from papers licensed NC or ND — as BioNumbers text does today over the corpus file. Nothing is
changed for it; it is written here so the choice is visible rather than inherited. Reviewers' words
cannot reach the tracer, because they never reach the model.

## Trade-off accepted

The ask package now depends on the validator's data layer, and a change to `bionumbers.store`'s
tables can break the ask agent's loader. Accepted because the alternative is two tier rules, and the
coupling is confined to one module a corpus-file run never loads. If either package moves out of
this repository, option 2 is the way out, and this ADR names what has to move.
