# ADR-0520: An outlier is measured against its peers' interval, not their median

- **Status:** superseded by [ADR-0540](0540-peers-come-from-the-expected-entries.md)
- **Date:** 2026-09-05
- **Pull request:** _(not yet opened — branch `feat/eval-scoring`)_

## Context

`add-answer-evaluation` requires flagging a cited entry whose recorded value is a distant outlier
among the corpus's other entries for the same property and organism. The check reads only the
citation set and the corpus, never the answer's prose, which is what makes it cheap enough to keep in
a change that has no parser.

Two numbers had to be chosen, and the design recorded both as open questions: what comparison to
make, and how far outside is far enough. The design's starting form was a ratio against the peers'
median, with the note that these populations are small and skewed.

The case the check exists for is concrete. While writing specimen answers for a review page on
2026-09-04, one answer about yeast nuclear volume cited nine entries: eight between 1.76 and 3.3 µm³,
and one at 10.3. Noticing that took only reading the nine values side by side — and no automated
check in the project would have done it.

**An earlier draft of this ADR credited that observation to the biologist the page was written for.
He never saw the page.** The finding was the author's, made while assembling the specimens. The
correction matters beyond politeness: a decision recorded as resting on a domain expert's judgement
carries weight that a decision resting on the author reading a column of numbers does not, and a
later reader weighing whether to revisit this rule would have been misled about how well
established it is. Commit messages from 2026-09-07 carry the same misattribution and are left as
written, since history is not rewritten here.

That example rules out the obvious threshold. 10.3 is 3.1 times the peers' maximum, so an
order-of-magnitude rule — the factor `Entry.spans_implausibly` uses for a single entry's own bounds —
would miss the very answer that motivated the check.

It also exposes the problem with a median. Nine entries is a small population and this one is
skewed; the median is pulled toward whatever the outlier does, while the observed interval is not.
The pathological case is easy to state: peers at 1, 1, 1, 1 and 10 have a median of 1, so a value of
5 is five times the median while sitting well inside the range the corpus already records.

## Decision

Flag a cited entry when its representative value lies more than **twice** outside the interval its
peers occupy: above their maximum by more than that factor, or below their minimum by more than it.
Report the value, the interval, the number of peers, and the factor by which it lies outside.

Make no comparison at all where a property has fewer than **four** peers with a usable number, and
say in the report that the comparison could not be made — an absence that reads as a pass is the
failure this check exists to prevent.

The representative value is the entry's scalar where it has one, otherwise the midpoint of its
range. Zero and negative values are not judged, for the reason `Entry.spans_implausibly` already
gives: a ratio across zero is meaningless, and a mark firing on arithmetic rather than on evidence is
worse than no mark.

Report it, never score it. An outlier is a fact about the corpus rather than about the answer: the
entry may be measuring something its neighbours are not, which is exactly the yeast case. What the
check buys is that the figure appears in a list a person reads, beside the interval its peers occupy.

## Trade-off accepted

**A factor of two over a small interval flags freely.** Where peers cluster tightly — five entries
between 2.0 and 2.1 — anything above 4.2 is reported, and much of that will be legitimate
method-dependent variation. This is acceptable only because the output is a list rather than a score:
a false flag costs a line someone reads, and the alternative is missing a wrong headline figure that
looks entirely ordinary. Task 4.10 counts both directions against the first real run, and the
threshold is to be set from that measurement rather than defended from this reasoning.

**The interval is itself sensitive to one bad peer.** A single erroneous entry widens the range and
hides real outliers behind it. The median is the standard answer to that and is rejected here for
the reason above; what a wide interval does produce is the "too few peers" line and a visible range,
so a reader sees the population rather than a verdict about it.

**Four peers is a floor with no measurement behind it yet.** It was chosen so that the yeast case
(eight peers) is comfortably judged while a pair of entries is not, and it will silence the check on
the long tail of properties that have two or three entries — which is much of this corpus. That
silence is reported rather than implied.

**Both numbers are conventions, and naming them here is the point.** They are recorded so the next
reader can find what to re-measure, rather than inferring from the code that they were derived.
