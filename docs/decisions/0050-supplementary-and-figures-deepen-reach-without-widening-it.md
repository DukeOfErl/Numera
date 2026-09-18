# ADR-0050: Supplementary files and figures deepen reach without widening it

- **Status:** proposed — findings and a recommendation, like [ADR-0040](0040-what-the-validator-feasibility-probe-established.md). It narrows that ADR's "Next probes" list rather than settling the validator's scope.
- **Date:** 2026-09-18
- **Pull request:** — (not yet opened)

## Context

ADR-0040 named three next probes and called the first — supplementary files and
figure images — "the only open question that could still make the validator
infeasible at useful scale". Its coverage survey had found roughly 22% of the
*favourable* corpus slice reachable as machine-readable text, and located the
missing material in two structural places: supplementary files (every
quantitative table for BNID 108345 and 108346) and figure images (the per-depth
values for BNID 115327).

The implied hope was that those two paths would recover a large part of the
missing ~78%. The probe of 2026-09-18 tested it. Evidence and method are in
`probes/2026-09-18-reach/`.

## Decision

**Treat article full text as the reachable surface, and stop counting on
supplementary files to extend coverage.** Specifically:

- **Keep `isOpenAccess` as the single reachability pre-filter.** It gates the
  supplementary bundle exactly as it gates article XML — both endpoints returned
  empty for every non-open-access paper tested. Nothing about supplementary
  material changes ADR-0040's recommendation to filter on it, or its rule that an
  unreachable source is *out of scope* rather than *unconfirmed*.
- **Do not build supplementary-file ingestion for the sake of coverage.** Across
  a random sample of 250 entries, supplementary material supplied a value the
  article text did not in **one** case. Of 27 values found anywhere, 26 were in
  the article text.
- **If reach is extended, extend it by reading figures first, then PDFs.** The
  ordering is now measured rather than assumed: across 46 reachable papers,
  images appear in 41, PDF in 16, binary `.xls` in 5. The readable modern format
  `.xlsx` appears in 5, so the spreadsheet support this probe already has covers
  about a tenth of papers.
- **Record "reachable" and "readable" as different facts.** 42 of 46 reachable
  papers carried material no text reader could open (median 15 files, one with
  280). A validator that reports "not stated in the source" after reading only
  what parses is making a claim it has not earned.

## Trade-off accepted

**We give up the hope that a parsing project fixes coverage.** ADR-0040 left open
that the missing 78% might be recoverable with enough format support; it is not.
Whole-corpus reach measured 19.2% on a random sample — consistent with ADR-0040's
prediction that the whole corpus would fall below the favourable slice's 22% —
and supplementary parsing moves it by a fraction of a percent. The constraint is
open-access status and unresolvable PMIDs, not file formats.

**In exchange, the scope question gets simpler.** There is no large engineering
effort standing between the validator and its true addressable set, because there
is no large engineering effort that would help. The 54% of sampled entries whose
reference does not resolve to a PMC record at all is now the largest single
bucket and is entirely uninvestigated — that, not format support, is where the
next coverage question lives.

**We accept that the recipe gap remains unmeasured.** The probe set out to size
it and could not: only 4 of 46 papers were fully readable, which is too few. What
it did establish is that the gap is real and not merely theoretical — BNID 108345
is reachable, its source table parses cleanly to exactly the 413 rows the paper
claims, and the recorded value 46429.8 g/mole is reproducible from it by no
obvious recipe (plain mean 44897.97, abundance-weighted 42850.42, the implied row
count 399.37). Positive controls fire on the same files, so the absence is real.
Reaching the data is not confirming the number, and a validator must be able to
say so.

**We accept that no figure-reading rate is claimed here.** One figure was read
accurately enough (depths within ~1 mbsf of the supplementary table), but by a
reader that had already seen the article sentence describing it — and the largest
error, reading 9.57 as 10.5, is pulled toward that sentence. This is ADR-0040's
contamination problem appearing inside a measurement rather than between arms,
and it is why its protocol correction about fresh agents binds the figure work
too.

## A note on how these numbers were obtained

Two earlier answers were produced and discarded, both flattering, and
`probes/2026-09-18-reach/METHOD.md` records them because the second is a trap
worth naming. A 43.8% "recipe gap" turned out to be mostly a count of unreadable
formats. A 96% hit rate on "fully read" papers was **circular**: the harness
fetched a supplementary bundle only when the article match had already failed, so
every matched entry had no supplementary statistics and passed the "fully read"
test by construction. The partition separated found from not-found by definition
and could not have returned anything else.

The general shape: **a covariate collected only on the failing branch will
partition the outcome perfectly, and the resulting table looks clean.** Neither
wrong answer would have been caught by rerunning the same code.

The finder itself is calibrated against the six 2026-09-09 entries and four
canaries that must not match, and it aborts rather than print a table if a canary
fires. That earned its place on the first run: the finder generated rescaled and
rounded surface forms, so the value 19043 produced the form `"19"` and 87654321
produced `"88"`, both of which occur in any paper. No calibration case would have
caught it. Calibration is n = 7 — enough to catch a broken finder, nowhere near
enough to quote a false-negative rate, and no figure above should be read as
precise.
