# ADR-0930: The review store is its own tables and its writer fails closed

- **Status:** proposed
- **Date:** 2026-09-18
- **Pull request:** not yet opened — branch `feat/validator-prototype`

## Context

Stub. The ask app's trail (ADR-0700, ADR-0710) is an append-only event log written best-effort,
because a lost row there costs one row of telemetry beside a product. A reviewer's decision here
*is* the product: it is the one thing the prototype exists to collect, and it has a foreign key to
an item.

## Decision

Three tables in the existing Neon project — `review_paper`, `review_item`, `review_decision` —
through SQLAlchemy Core, separate from the trail. `record_decision` raises on failure; the page
tells the reviewer the decision was not saved and keeps the item open. See `design.md` D8.

## Trade-off accepted

To be completed with the options rejected (task 9.2).
