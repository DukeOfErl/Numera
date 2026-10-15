## Context

Four findings from the 2026-10-07 review of `add-harvest-prototype` (its tasks 6.5, 6.6, 6.8 and
6.9), moved here on 2026-10-15 so that change could close before the presentation. Three are
small and settled; one (repeat readings) needs a design decision before code.

## Goals / Non-Goals

**Goals:** the bound holds in code; a repeat reading of an article is visible as one, to a
reviewer and to a reader; the two small CLI defects go.

**Non-Goals:** choosing which reading is right (that is what review is for); the ask agent's
citation labels (`add-ask-over-store`'s D3); re-extracting anything.

## Decisions

### D1. The bound is applied after verification, before the second-text call

Verified entries are cut to the first twenty in the model's own order — the instruction asks for
the most reusable first — and the number dropped goes on the article's record. Applied before the
second-text call because that call is the spend the bound exists to cap. The guard lives in the
extraction operation, not in `harvest`'s driver, so any caller of `extract` gets it.

### D2. Repeat readings: to be decided when the work starts

Open. Two shapes, to be measured against the store when a paper has actually been read twice:

- **Derived at read time:** readings are grouped by `(pmcid, property)` with no new table. Cheap
  and never stale; depends on the property name matching across runs, which the harvest does not
  guarantee (labels are model-written).
- **A recorded link:** a `reading_link` row written at load, pairing items across runs once a
  matching rule (or a reviewer) says they are the same property. Survives relabelling; needs a
  rule, and a rule that classifies things moves records in both directions.

`add-ask-over-store` (its D3, confirmed by that session on 2026-10-15) constrains neither shape:
each reading is its own entry, anything saved is keyed by `item_id`, and its `-n.2` suffix is
display order by run creation time within one load, not a relation between readings. With a
recorded link the agent could later say "also read in run X"; with a derived one nothing there
changes.

Serving together is independent of the choice: `next_item` partitions by `(run_id, pmcid)` today
and partitions by `pmcid` afterwards. Record the decision as an ADR from the `1700`–`1740` block.

### D3. The run-path guard moves into the operation

`_refuse_a_committable_run_dir` is called by `discover` and `harvest` separately. It moves into the
function that creates the run folder, so a third command inherits it.

## Risks / Trade-offs

- Serving by `pmcid` across runs changes the order a reviewer sees items in; the simulated review
  runner's measurements were taken under the old order. Low cost: no paper has two runs yet.
