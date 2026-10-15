# ADR-1530: Every paper, field and candidate ends in a named state, never a confidence score

- **Status:** accepted
- **Date:** 2026-09-18
- **Pull request:** not yet opened — branch `feat/validator-prototype`

## Context

The retrieval probe (ADR-0040) found that a model asked for a number it "knows" reports the
textbook figure at high confidence when the paper in front of it says something else: 40 min for
a paper stating 65. The loop-engineering brief says the same thing generally — self-scored
confidence is the least reliable exit condition there is. So a confidence field on a claim would be
the one column a downstream reader would trust and the one least worth trusting.

What the six papers inspected for this change showed instead is a small set of *situations*: a
value cited from other work rather than measured; a value used as a parameter; a compiled
literature table; a condition offloaded to a cited paper; a condition only in supplementary
material; a number stated only as a figure curve; a perspective essay under research-article
metadata.

Options:

1. A confidence score per claim (0–1), from the model.
2. Free-text "notes" per claim explaining doubts.
3. Closed enumerations per paper, per condition field and per candidate value, each member
   corresponding to an observed situation.

## Decision

Option 3, in `records.py`. Per paper: `CLAIMS_FOUND`, `NOTHING_TO_EXTRACT`,
`NOT_A_RESEARCH_ARTICLE`, `UNREADABLE`, `CEILING_REACHED`, `FAILED`. Per condition field:
`BESIDE_VALUE`, `FROM_METHODS`, `BY_REFERENCE`, `SUPPLEMENTARY_ONLY`, `NOT_STATED`. Per candidate:
`MEASURED`, `DERIVED` (claims), `CITED`, `PARAMETER`, `COMPILED` (rejected, kept for the second
text). The structured-output schema makes every field carry exactly one member, so absence is
always explicit. The decisive cue for cited-versus-measured is a bibliographic citation marker on
the clause holding the number, which is why the JATS reader keeps those markers as `[ref N]` tokens
in passage text and the review page shows them.

## Trade-off accepted

*Given up:* nuance inside a state. Two `NOTHING_TO_EXTRACT` papers may differ greatly (a figure-only
paper and an off-topic one); the `reason` string carries the model's sentence, but it is not
queryable. And `NOT_A_RESEARCH_ARTICLE` is a coarse rule — "no methods section" — that sets aside
brief reports whose methods live in supplementary material (PMC13340094 is one).

*Bought:* counts that mean what they say. A run summary of states is a measurement of the
literature and the extractor that a confidence histogram would not be, and the rebuild can add a
member when a new situation is observed rather than re-tune a threshold.
