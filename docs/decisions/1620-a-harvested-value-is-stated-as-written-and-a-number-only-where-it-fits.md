# ADR-1620: A harvested value is stated as the paper wrote it, and as a number only where the reading fits

- **Status:** accepted
- **Date:** 2026-10-15
- **Pull request:** not yet opened — branch `feat/ask-over-store` (`add-ask-over-store`)

## Context

A BioNumbers entry arrives with its value already numeric: `value`, or `range_low` and
`range_high`, with flags the ingester sets where the source hedged. A value harvested from a paper
arrives as the text the paper wrote — `488`, `7.1 ± 0.4`, `1,100–2,100`, `62 (40–100)`, `3.2∶1` —
with the extraction's own record of what kind of value it is (`SINGLE`, `WITH_UNCERTAINTY`,
`RANGE_OVER_CONDITIONS`).

The agent needs numbers for two things: presenting a range as a range, and the dimensional
comparison of values (ADR-0160). `bionumbers.readings.parse`, the review page's parser, reads all
452 values in the store without failing. It does not read all of them correctly: it reads
`0.89 and 1.16` as one number, `3.2∶1` as 3.2, and `62 (40–100)` as a range, losing the 62. And 21
values the extraction recorded as single are written as ranges (`10–20`), which may be the
parser's reading or the extraction's labelling.

Options considered:

1. **Text only.** Never wrong, but the agent loses ranges and unit comparison for every harvested
   value.
2. **Trust the parser.** Numbers everywhere, and about 38 of them stated with confidence where the
   reading is doubtful.
3. **Fix the parser first.** It belongs to the review session and its comparison of what a reviewer
   typed; changing its readings changes that comparison. Out of this change's reach.
4. **Keep the reading only where its shape fits the recorded kind.**

## Decision

Option 4. The value is always *shown* in the paper's words (`Entry.value_display` returns the text
for a harvested entry), so `7.1 ± 0.4 nm` keeps its uncertainty in the table and in the model's
view. The parsed numbers are kept only where their shape fits the kind the extraction recorded:

| Kind | Fits when |
|---|---|
| `SINGLE` | one number |
| `WITH_UNCERTAINTY` | one number and an uncertainty |
| `RANGE_OVER_CONDITIONS` | two numbers |

Anything else sets `reading_uncertain`: no number is stored, the model is told the value could not
be read with certainty and to give it in the paper's words, and the table marks it `?`. The entry is
still shown and still citable. Over the real store this cautions 38 of 452 values (counted
2026-10-15).

**Which direction is cheap.** A correct reading cautioned costs a sentence. A misread number stated
with confidence is a wrong answer that looks like a right one. So any disagreement cautions,
whichever side is wrong — the parser or the recorded kind — and the code says so where it decides.

## Trade-off accepted

About one harvested value in twelve loses its numbers, including some the parser read correctly and
the extraction mislabelled. Those values drop out of unit comparison and range display until the
parser or the labels improve; a reader still sees exactly what the paper wrote. A value the kind
check passes and the parser still misread (a `SINGLE` read as one wrong number) is not caught here —
the text shown beside it is the protection, not this rule.
