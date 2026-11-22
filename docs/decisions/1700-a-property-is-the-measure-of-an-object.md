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
empty, or one part repeating the other, and no name is made. The claim is **kept**, labelled for
the review screen by the article's own term, with an empty property that `name-properties` fills
later; the run's summary counts the unnamed. (The first version of this decision, 2026-10-17
morning, dropped such a claim as it drops one with a failed quote. Yoav's objection the same day
reversed it: a verified value costs a paper's extraction to get back, a name a third of a cent, so
dropping was the expensive direction dressed as the cheap one.) A store loaded before the parts
were asked for is named by `numera-validator name-properties`, one call per entry over the entry's own
record and never the paper, and never into `item_json`, which stays what the reviewer saw.

## Trade-off accepted

Two fields would let a display choose its own phrasing and SQL group by measure; they would also
split a qualifier that does not split — "non-contracting" belongs to the object, "average" to the
measure, and a reader searches the whole phrase. The fixed "of" reads awkwardly now and then
("Number of ribosomes per cell" is fine; "Ratio of X to Y" leans on the object to carry "to Y"),
and that is accepted for a check that can be run both ways over the store rather than argued
about. The check over-refuses by design: a good name whose object happens to contain the
measure's word is left unnamed, where a vague name that passed would look like an entry. An
unnamed entry costs one backfill call; nothing is lost. The backfill asks the model without the paper, so it can
only sharpen what the extraction already recorded; a qualifier the extractor never quoted stays
missing until the paper is read again.
