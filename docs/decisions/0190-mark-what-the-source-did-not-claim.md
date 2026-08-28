# ADR-0190: The table marks what the source did not claim, and never repairs it

- **Status:** accepted
- **Date:** 2026-08-28
- **Pull request:** _pending — `feat/ask-agent`_

## Context

The corpus stores a hedged value as a closed interval. `<8` arrives as
`[8.0, 8.0]`, `>100` as `[100, 100]`, `~5` as `[5, 5]`. Rendered by the rule that
collapses equal bounds to a single number — itself correct, and there for the
1,403 entries that store one measurement as a degenerate range — every one of
them printed as a bare figure.

This was not hypothetical. Asked *what is the minimal inhibitory concentration of
kanamycin for E. coli*, the agent answered:

> The minimal inhibitory concentration of kanamycin for *E. coli* **is 8.0 mg/L**
> (BNID 100763).

The source says `<8`. Both surfaces agreed — the table showed a bare `8.0` — so
nothing on the page contradicted anything, and the reader had no signal at all.
The failure is not that a number is imprecise. A bound and a measurement are
different claims: an MIC of `<8` means susceptible at or below 8, and stating it
as an equality asserts something the source never did.

Three of four questions in that live run landed on an entry carrying the flag.
2,233 records carry it — 15.6 per cent of the corpus — but they concentrate in
the well-known quantities people actually ask about, so the rate in the answered
population is higher than the stored rate suggests.

`add-corpus-ingestion` reports three things this project can read: `range_qualified`
(2,233), `range_fused` (1,461), and the bounds themselves. It deliberately makes
no judgement about whether a range is *plausible* — that is a presentation
concern (its ADR-0230) — so an implausibly wide range that parsed exactly as
written arrives unflagged. 46 entries in this corpus span more than a millionfold;
`range_fused` accounts for most, leaving five that are correctly parsed and still
unusable, `0.25-2.5e30` among them.

## Decision

**Mark, never repair, never withhold.** A marked entry is still returned, still
shown in full, and still citable: a citation claims provenance, and that stays
true of an entry whose value the source hedged. What changes is that the number
is no longer presented as something it is not.

**Three marks, three sentences.** `°` the source stated a bound or an
approximation; `≈` the two bounds may describe different quantities; `¡` the
bounds span more than a millionfold. Deliberately not one mark: a record can
carry any of them without the others, and BNID 100420 — `~160,000 (21,000 to
195,700)` — carries two, being wrong in two different ways that need two
different sentences.

**The model is told, not only the reader.** The prose is what people read, so a
caution goes into `get_entry`'s result as an instruction rather than as a field
name: `range_qualified: true` is a flag a model may act on, where *the source
stated a bound, do not report this as a measured quantity* is harder to round
away. Verified live: the same question now answers "a bounded estimate rather
than an exact measured value".

**The value itself says so.** A qualified degenerate interval renders as
`8.0 (bounded, not exact)` rather than `8.0`, because the table is read by people
who will not have read the legend.

**The span threshold is ours, and is a millionfold.** Not the ingester's to set:
`range_fused` is a statement about provenance, this is a judgement about the
number. A millionfold is far outside what a measurement of one quantity spans —
cell volumes across all life cover about 10^4 — and the entries above it here are
wrong on inspection rather than merely broad.

## Trade-off accepted

**A chosen constant with no principled derivation.** A millionfold is defensible,
not derived, and it will mark a genuinely broad measurement somewhere. It is
tested on both sides of the boundary so that changing it is a deliberate act, and
it says nothing where a ratio is meaningless — zero or negative bounds are not
judged, because a mark firing on arithmetic rather than evidence is worse than no
mark at all.

**A row can now carry four marks.** `†°≈¡` in front of a property is dense, and
the legend grows with it. Accepted because each says something a reader cannot
otherwise see, and because the legend is drawn only for marks that appear on a
shown row.

**Two fields whose meanings are close enough to be confused.** "The source stated
a bound" and "these bounds may be two quantities" will be conflated by some
readers. Collapsing them into one flag was rejected: it would say a single thing
about records that are wrong in two ways, and would redefine a term this project
already reads.

**The marks depend on fields a corpus may not emit.** Both default to `False`, so
a corpus without them loads and reports nothing rather than reporting wrongly —
which is the silent-failure shape this project has already met from the other
side. `tests/test_markers_against_corpus.py` counts each condition against a real
corpus, so a mark that can never fire fails a test instead of quietly reading zero.
