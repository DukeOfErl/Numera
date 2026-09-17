# ADR-0540: An entry's peers come from the question's expected entries, not from a property string

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** [ADR-0520](0520-the-outlier-check-compares-an-interval.md)
- **Pull request:** _pending — feat/eval-baseline_

## Context

ADR-0520 defined an outlier's peers as the corpus's other entries recording **an identical property
string for the same organism**, compared against an interval with a factor of two and a floor of four
peers. Task 4.10 required both directions of every classifying rule to be counted against a real run
before any figure was trusted. That count has now been made, over the 2026-09-11 baseline.

**The rule has never judged anything.** Of the 91 cited entries in the baseline, **91 were
unjudgeable** and 0 were judged. Not most — all of them. The entry that motivated the check in the
first place, 106356 at 10.3 µm³ among yeast nuclear volumes of 0.28–3.3, is among the unjudgeable.

The cause is the same one that made the question set's expected lists too narrow twice over:
`property` is free text. `resolve_property("Nuclear volume")` selects `Nuclear volume (average)` and
`Nuclear volume of yeast spore cell`, but not `Volume of nucleus` or `Volume of nuclei during S
phase`, which record the same quantity. A peer pool keyed on property wording is a pool keyed on
coincidence.

Four candidate definitions were measured on the baseline, each judged by how many of the 91 citations
it could judge, how many it flagged, and whether it caught the known case:

| Peers are… | Judged | Flags | Catches 106356 |
|---|---:|---:|---|
| identical property string, same organism (ADR-0520) | **0** | 0 | no |
| what the question's property terms select, same organism | 78 | 3 | no |
| …and the same unit *dimension* | 55 | 1 | no |
| **the question's expected entries, same organism and unit** | **56** | **2** | **yes** |

The third row failed for an instructive reason, and the fourth's first attempt failed the same way in
miniature: a pool matched on dimension alone put `1.8e-15 Liter` beside `2.95 µm^3`. Both are
volumes; comparing them as numbers spans fifteen orders of magnitude and destroys the lower bound.
The project has dimensional *compatibility* (ADR-0160) but no unit *conversion*, so the pool is
restricted to an identical unit string instead.

## Decision

**An entry's peers are the question's own expected entries, restricted to the cited entry's organism
and to an identical unit string.** The factor of two and the floor of four peers are kept from
ADR-0520; only the definition of a peer changes.

The expected list is the right source because it is already what a peer pool needs: the set of
entries recording the asked property, resolved across every spelling of it by hand, against the
corpus rather than against a search. Building a second vocabulary-resolution mechanism for the
outlier check would be a second thing to get wrong, and the first one is already curated and
reviewed.

On the baseline this judges 56 of 91 citations and raises two flags, both of which survive
inspection: 106356, the yeast nucleus at 10.3 µm³ against peers of 0.28–3.3, and 103710, `Cell volume
average`, whose recorded range of 0.58–15.0 µm³ has a midpoint 2.6× above every peer.

## Trade-off accepted

**The check now depends on the question set, and inherits its faults.** A question whose expected
list is too narrow has too few peers and its citations go unjudged; a list that is wrong makes the
comparison wrong. That coupling is real, and it is the price of not building a second resolution
mechanism. It also has a defence the old rule lacked: the expected list is reviewed by a person,
and this change makes that review matter twice.

**An identical unit string is stricter than the project's own notion of sameness.** `µm^3` and
`um^3` are one quantity and two strings, and this rule treats them as different pools — which cost
six judgeable citations against the dimension-matched version (56 against 62). The alternative is a
unit converter, which does not exist and which ADR-0160 deliberately did not build. Accepted for now,
and the cheap direction: a split pool judges less, where a fused pool judges wrongly.

**Thirty-five of ninety-one citations remain unjudgeable**, mostly for want of four peers sharing a
unit. The report says so rather than leaving an absence that reads as a pass, which was already
ADR-0520's discipline and is kept.

**Only entries in the expected list can be flagged.** An entry cited from outside it — the
`unexpected` and `admissible` categories — has no pool and is never judged. That is a genuine blind
spot, and it is the opposite of where the risk was thought to be: an entry the set did not anticipate
is exactly the kind most likely to be wrong.
