# ADR-1700: A property is one name, the measure of an object, joined by the application

- **Status:** accepted
- **Date:** 2026-10-17
- **Pull request:** not yet opened — branch `feat/property-names`

## Context

The first live harvest named entries with one model-written label, "a short general name for the
quantity". The demo store shows what that produces: "average length" for two values that differ
only in which rings were measured, and "cytokinetic actin rings" for a diameter. Each says half of
what an entry needs — what was measured, or of what — and a reader cannot tell the two lengths
apart from anything on the row. Yoav's requirement (2026-10-16): a property always names both.

Three shapes were on the table. Two store fields, measure and object, formatted together at
display. One field written whole by the model and checked by a judgement. One field joined by the
application from two parts the model writes.

## Decision

One stored name, `review_item.property`, built by the application as `<measure> of
<measured_object>` from two labels the extraction asks for in place of `property_name`
(`naming.property_name`). The check that both halves are there is a string test: either part
empty, or one part repeating the other, and the name is refused. In the harvest a refused claim is
dropped and its id recorded, as a claim with a failed quote is; the article's own term is not a
fallback, because "average length" *was* the article's own term. A store loaded before the parts
were asked for is named by `bionumbers name-properties`, one call per entry over the entry's own
record and never the paper, and never into `item_json`, which stays what the reviewer saw.

## Trade-off accepted

Two fields would let a display choose its own phrasing and SQL group by measure; they would also
split a qualifier that does not split — "non-contracting" belongs to the object, "average" to the
measure, and a reader searches the whole phrase. The fixed "of" reads awkwardly now and then
("Number of ribosomes per cell" is fine; "Ratio of X to Y" leans on the object to carry "to Y"),
and that is accepted for a check that can be run both ways over the store rather than argued
about. The refusal over-refuses by design: a good name whose object happens to contain the
measure's word is lost, and recorded, where a vague name that passed would look like an entry.
One entry lost is the cheap direction. The backfill asks the model without the paper, so it can
only sharpen what the extraction already recorded; a qualifier the extractor never quoted stays
missing until the paper is read again.
