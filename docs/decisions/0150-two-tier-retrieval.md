# ADR-0150: Retrieval is two-tier — capped summaries with an honest total, then bodies

- **Status:** accepted
- **Date:** 2026-08-26
- **Pull request:** _pending — `feat/ask-agent`_

## Context

The corpus holds 14,294 entries averaging ~1,400 characters, and a single-word
property search matches 300–1,600 of them. A search tool that returns what it
matched would produce a six-figure-token result for one tool call, bury the few
relevant entries among a thousand irrelevant ones, and spend most of a question's
budget before the agent had read anything.

Truncating is the obvious fix and introduces a subtler problem: an agent shown 50
rows cannot tell "50 results, that is all" from "50 of 1,656", and will summarise
the second as though it were the first.

## Decision

Two tiers, the **List/Detail** (coarse-to-fine) pattern:

- **Search** returns capped compact rows **plus the total match count**. A full
  entry averages roughly eight times a compact row.
- **Retrieval** fetches one complete entry by identifier.

The total is what makes truncation honest, and it is reported to the reader as
well as to the agent: an answer states how many entries matched when more matched
than were retrieved.

The reference column is not carried through search — it is looked up at display
time only, since including it would more than double what a search costs, and it
is never sent to the model.

## Trade-off accepted

An answer costs more round trips. What could have been one tool call is a search
followed by several retrievals, which is more latency and more model calls against
the per-question call bound.

Bought with that: the agent's **selection becomes an explicit, loggable, scorable
tool call** rather than an invisible step inside one forward pass. Which entries
it chose to open is recorded, so a citation can be checked against what it was
actually shown — which is what makes the citation check in `grounded-answering`
possible at all.
