# ADR-0230: Flag and count; never drop, never silently correct

- **Status:** accepted
- **Date:** 2026-08-28
- **Pull request:** _(not yet opened — branch `feat/corpus-ingestion`)_

## Context

The published export contains rows the ingester cannot fully interpret, and they are not rare:

- **4,259 rows (29.8%)** carry a "Table link" URL to an external PDF where a scalar should be.
- **3,234 rows (22.6%)** carry no scalar at all.
- **21 rows** hold range text from which no number can be read.
- **1,445 rows (10.1%)** carry bounds that may fuse two quantities: bounds are taken as the lowest
  and highest number in the range cell, so a cell naming a second quantity contributes a bound to
  the first, and the result reads as one measurement while spanning two.

Three responses were available for each class: drop the row, repair it, or keep it and say what is
wrong with it. Dropping produces a corpus that is silently missing entries nobody can enumerate.
Repairing means inventing a value the source does not contain — the unsourced correction this
project exists to avoid — and for a fused range there is no rule that separates a second quantity
from a genuinely wide range without reading the comment text.

The consuming change, `add-ask-agent`, needs to know which ranges are not usable as measurements so
it does not present one as a figure. The question was how to tell it.

## Decision

**Keep every row, and carry the reason on the record.** Nothing is dropped and no value is invented.
Each cleaning outcome that is not a clean parse appends a name to `parse_flags`, the run report states
a count per flag, and the manifest records those counts alongside the source digest.

**The contract with `add-ask-agent` is a dedicated boolean field, `range_fused`, not a flag name.**
`true` when the stored bounds may fuse numbers from more than one quantity. The consumer reads that
field directly and forwards it without interpretation; `parse_flags` stays internal to cleaning, and
its names may be renamed, split, merged or dropped without a cross-branch change. Cleaning may not
retire or redefine `range_fused` without telling that change.

A rule over `parse_flags` was **rejected**, on the ask session's evidence. That list is a reporting
vocabulary of eight names, five of them beginning with `range_`, and only two concern fusion:
`range_plus_minus` and `range_mean_sd_embedded` mark *successful* parses, `range_is_link` and
`no_scalar` mark rows with no scalar at all. On the corpus, "non-empty `parse_flags`" selects 5,148
records and a `range_` prefix selects 5,494, against the 1,445 meant — either rule would mark
thousands of correctly parsed entries in a user-visible marking, which teaches a reader to ignore it.
A name-matching rule also contradicts declaring the names internal: a consumer cannot evaluate "names
a range concern" without the taxonomy.

Two further facts decided it, and both generalise past this case:

- **The observed vocabulary is not the emittable one.** Six flag names fired on the corpus; the
  cleaner can raise eight. A rule derived from the six breaks the first time the seventh fires, with
  nothing having changed and no version to blame. A contract inferred from a data sample is not a
  contract.
- **An absence inferred from a data sample is not an absence.** `injected_html_removed` reported zero
  on a corpus where 10,206 of 14,294 records carried injected markup, because its condition was
  computed before entities were unescaped and so was unreachable. A zero needs an argument from the
  code, not only from data. Every flag this change defines is therefore shown to fire on the export.

## Trade-off accepted

**The corpus contains rows a reader must not treat as measurements, and nothing stops them.** The
flag and the predicate are advisory: a consumer that ignores `range_fused` presents a fused range as
a figure, and the corpus gives it no protection. Dropping those rows would have made misuse
impossible. We accept the weaker guarantee because a missing row is unfalsifiable — no reader can
enumerate what is not there — while a marked row is at worst ignored.

**The flag counts are only as good as the tokenizer beneath them, and ours was wrong twice.** The
fused-range population was measured at 1,716, then 1,222, before landing at 833 for the flag and
1,445 for the predicate. The first error read digits out of an escaped link filename; the second read
`2×10^5` as three numbers and `150,000` as two. Nearly a third of the 1,222 was notation rather than
fused quantities. Both figures had been written into two changes' documents before being corrected.
Anything derived from counting is exposed to the same class of error, and the mitigation is that the
run reports each count every time rather than quoting a figure recorded once.

**A residual 66 records** are flagged as having prose between their bounds where the "prose" is only
punctuation — a ratio colon, a percent sign, a bracket. That is 0.5% of the corpus, and it survives
deliberately: narrowing the heuristic further would start suppressing genuine second quantities, and
the measurement that mattered — punctuation-only false positives, down from 347 to 66 — came from
fixing the tokenizer rather than the heuristic.
