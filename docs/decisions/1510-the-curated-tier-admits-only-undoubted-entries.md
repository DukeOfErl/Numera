# ADR-1510: BioNumbers entries enter as the curated tier only where nothing marks them doubtful

- **Status:** accepted
- **Date:** 2026-10-07
- **Pull request:** not yet opened — branch `feat/harvest-prototype`, change `add-harvest-prototype`

## Context

The demo shows a store of numbers with a trust order: quote-verified by machine, then reviewed by
roles of rising expertise (simulated for now, ADR-0960). A BioNumbers entry was entered by a
curator from its paper, which is a review already, so it can stand at the top as a "curated" tier
and show what the harvested entries are working towards. Yoav asked for the entries "we are
confident about": no suspicion, no fused ranges, sound units, no rules of thumb.

The corpus already reports what the ingester could not repair (`range_fused`, `range_one_sided`,
`range_approximate`, ADR-0230 on the ingestion branch), and the ask agent judges one thing more,
the implausible span. Neither was written to decide trust. The demo's slice — yeast by organism,
the cytoskeleton by property or keyword, measured, with a method and a PubMed reference — holds 492
entries (counted 2026-10-03, and the same rule here).

## Decision

`bionumbers.curated.refusal` admits an entry only if none of ten signs applies, checked in order
and recorded by the first that fires: outside the slice; no value and no two-sided range; no method
or a method that reads as a calculation; no PubMed reference; a fused range; bounds more than a
millionfold apart; a one-sided bound; no unit; a unit holding a character the export garbled (the
multiplication sign arrives as a Cyrillic letter); or prose that says the value is unsure or a rule
of thumb. 423 of the 492 pass. `bionumbers curate` loads them into `curated_entry`, replacing the
table whole: no decision points at a curated entry.

An approximate value ("~60,000") is admitted and carries `approximate`: the hedge is the source's
own, recorded faithfully, and harvested entries carry the same hedges.

The guard is in `refusal`, and `store.load_curated` runs it itself on the corpus's own lines
(amended 2026-10-09: it first took built entries and trusted the type, which any caller can
construct). Before that amendment the sentence read: `store.load_curated` takes only `CuratedEntry`, which only
`curated.entry` builds and which refuses by the same rule — so a second caller cannot load an entry
that skipped it.

## Trade-off accepted

The rules lean to refusal, because the directions do not cost the same: an entry wrongly left out
costs one row of 423; one wrongly let in is a wrong value shown with the highest trust there is,
beside harvested values a reviewer is asked to doubt. The doubt words are deliberately narrow —
"crude" and "probably" were tried and fired on "crude extract" and on prose about something else —
so a curator's doubt phrased otherwise passes. Nothing here checks that a curated value is right;
it checks only that the record does not itself say it might not be.

The corpus is read as raw lines, not through `scinumbers_ask.corpus`, which this package's core may
not import; the span threshold is copied from there, and the two must move together.
