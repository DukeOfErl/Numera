# ADR-0160: Unit compatibility is three-valued, because complete classification is unavailable

- **Status:** accepted
- **Date:** 2026-08-26
- **Pull request:** _pending — `feat/ask-agent`_

## Context

The agent reports disagreement between entries — two values for one quantity,
with the conditions that distinguish them. Presenting a mass and a count as two
estimates of one quantity is an arithmetic error dressed as a range, and units are
the only machine-checkable signal the corpus carries against it.

The corpus holds **2,305 distinct unit strings**, and its 45 commonest cover only
64 per cent of entries. A complete classification is therefore not available at
any price — not by hand, and not by inference from strings that include free-text
qualifiers. Any design that assumes every unit can be classified is wrong from the
start.

## Decision

A hand-written table mapping units to what they measure — length, area, volume,
mass, time, concentration, count, dimensionless — with a **three-valued**
interface over it.

`dimension` returns `None` for a unit it does not recognise, and `comparable`
returns `None` when either side is unrecognised: **not comparable, not
incomparable, unknown**. An unknown pair is never presented as differing estimates
of one quantity, and never treated as dimensionless.

Where a search result spans more than one dimension, the answer names the kinds it
carries, and the entries table footnotes the same over the cited entries.

The table currently covers 45.6 per cent of the corpus's entries: measured over
all 14,294, `dimension` returns None for 7,775 of them. So `comparable` answers
`unknown` for the majority of pairs, which is the design working rather than
failing -- but it is now a counted figure rather than an estimate.

## Trade-off accepted

Most comparisons return `unknown`, so the check catches the mass-versus-count
error and declines to rule on the majority of pairs. It is a floor on
comparability, never a proof of it — two dimensionless figures may be a percentage
and a fold-change, which share a dimension and are still not each other's
alternative.

The alternative — treating unrecognised units as compatible, or guessing a
dimension from the string — would produce exactly the confident unsourced claim
this project exists to avoid. Silence about what is not known is the cost of not
inventing it.

The table is also permanent maintenance: it grows by hand as units are noticed,
and will never be finished.
