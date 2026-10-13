# ADR-0990: One trust-tier rule, with a dispute as a flag beside the tier

- **Status:** accepted
- **Date:** 2026-10-13
- **Pull request:** not yet opened — branch `feat/simulated-review`

## Context

Two readers now want to say how far a harvested entry is trusted: the demo dashboards (a pie of
every entry by tier) and the ask agent on `feat/ask-over-store`, which will show a star tier
beside each citation it draws from the review store. ADR-0960 says a tier is read off the roles
of the decisions that approved an entry and stored nowhere; it did not say where the reading is
done, and each reader was about to do it itself.

The two readers also wanted different answers for a disputed entry. The dashboard rule Yoav gave
on 2026-10-09 was that any disapproval or issue makes the entry "issue raised", whatever else
approved it. For the ask agent he chose, on 2026-10-13, to keep the earned tier and add a caution:
a reader of an answer is better served by "a senior scientist approved this and a student
objected" than by a collapsed "issue raised". Two rules, one per reader, would drift the day either
changed.

Options: each reader computes its own (rejected: two definitions of one word); a `tier` column
written on every decision (rejected: ADR-0960 keeps it derived, so a changed rule re-reads every
row rather than migrating them); one function returning a tier with the dispute folded into it
(rejected: it cannot serve the ask agent); one function returning the tier and the dispute
separately (chosen).

## Decision

`bionumbers.tiers.trust_of(decisions)` returns a `Trust`: `tier` is `CURATED` for a curated entry,
otherwise the highest `ReviewerRole` among decisions with `approved` true and an empty `issue`,
otherwise `NONE`; `disputed` is true when any decision has `approved` false or a non-empty issue;
`simulated` is true when the decision that set the tier was a model's in a person's role. An open
row counts as nothing. `by_item(engine)` applies it to every item with a decision.

Rendering stays with each reader: the dashboard shows a disputed entry as "issue raised" and
`NONE` as "not yet reviewed"; the ask agent shows the tier as stars, a caution when disputed, no
stars for `NONE`. Both must label a simulated tier as simulated.

## Trade-off accepted

The dashboard's "issue raised" slice now hides a tier that the function knows and the ask agent
shows, so the two can state different-looking figures for the same entry; the pie's legend has to
say that "issue raised" entries also carry an earned tier. The rule is pure over rows rather than
a SQL view, so a reader with many entries pays one query and a Python pass; at the demo's scale
(hundreds of items) that is the cheaper side of keeping the rule in one testable place.
