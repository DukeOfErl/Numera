# ADR-0930: The review store is its own tables and its writer fails closed

- **Status:** accepted
- **Date:** 2026-09-18
- **Pull request:** not yet opened — branch `feat/validator-prototype`

## Context

The ask app's durable trail (ADR-0700) is one append-only table with a JSON `detail` column, written
best-effort (ADR-0710): a lost row costs one row of telemetry beside a product that has already
answered. The obvious move was to write review decisions as `review.decision` events into that
table and reuse its writer.

But a decision here *is* the product — the one thing the prototype exists to collect — and it has a
foreign key to an item, a reviewer, a choice and a verdict that later analysis joins on. Both
properties argue against the trail: a fail-open writer would lose the product silently, and an
event log with a blob column is the wrong shape for rows that are queried by key.

Options:

1. Events in `trail`, fail-open, reuse `trail_store`.
2. Own tables, written through `trail_store`'s machinery with the failure policy flipped.
3. Own tables (`review_paper`, `review_item`, `review_decision`) in the same Neon database, SQLAlchemy
   Core, a writer that raises `DecisionNotSaved` on any failure; the page reports "not saved" and
   keeps the item open.

## Decision

Option 3. `store.py` and `sql/review.sql` declare the same columns and a test parses the DDL against
the Core tables so the two cannot drift silently. `record_decision` wraps every engine failure and
chains the cause; it never returns without a committed row. `next_item` serves a reviewer only
items they have not decided, interleaved across papers. The page gets its engine from the same
`st.connection` the ask app uses, so one secrets section serves both apps.

## Trade-off accepted

*Given up:* the trail's resilience. A Neon outage stops reviewing rather than degrading it, and a
reviewer meets an error they can do nothing about. Also given up: reuse of `trail_store`'s tested
writer; the timeouts and pool settings are borrowed by import, the writer is not.

*Bought:* no decision is ever silently lost, and the record is queryable by item, reviewer and
paper without parsing JSON. The JSON columns that do exist (`item_json`, `spend_json`, `fingerprint_json`) are copies for
reconstruction, not the record of anything analysis needs.
