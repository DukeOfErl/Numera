# ADR-0970: The value is withheld until the text is chosen, and the reviewer writes what they read

- **Status:** accepted
- **Date:** 2026-10-07
- **Pull request:** not yet opened — branch `feat/simulated-review`

## Context

The first review screen (ADR-0940) showed everything at once: the value, the paper's own name for
the quantity, the conditions with their quotes, and the two texts. The reviewer chose the text that
"better fits the value" and approved or disapproved.

Run with models in place of people (ADR-0960), that screen produced unanimity: on 35 and then 60
items, Haiku 4.5, Sonnet 5 and Nemotron Ultra each chose the supporting text on every item and
approved every item. Yoav's reading of this on 2026-10-07 was that the screen answers its own
question — a reviewer handed the value, the conditions and two texts has only to find the number,
"without reading the text and without exercising judgement (which is what they are there for)".

A scratch experiment on 60 seeded items with the value and conditions withheld — the reviewer saw
the quantity's name, the citation and the two texts, chose one and stated the value it gives —
changed the picture: the models disagreed where the entry's name did not identify it (the same
quantity under two conditions), the stronger ones raised an issue there rather than guessing, and
one entry was found doubtful ("F-actin binding dissociation constant", whose quote never ties the
value to F-actin). Whenever a model chose the supporting text, the value it read matched the stored
value, on all 190 such answers.

Options for the reveal: show the stored value and the conditions after the choice (chosen);
show them with the texts but ask the choice first on the same screen (nothing stops the eye
reading ahead); never show them (then the verdict — did this value come from this paper under
these conditions — has nothing to be about).

Options for the value the reviewer read: ask for it before the reveal (chosen); ask for it after
(it would be a copy of the stored value); not ask (the choice alone says which text, not whether
the reviewer read the same number from it).

Options for the two steps' record: two rows (every read has to join them); one row written twice
(chosen), with the first write leaving it *open* — a choice without a verdict — and the item
served first to its reviewer until the second write completes it.

## Decision

A decision has two steps on one row. The first step shows the quantity, the citation and the two
texts, and nothing of the stored entry; the reviewer chooses the text that states a value for the
quantity and writes that value as written, and both are recorded (`chosen_supporting`,
`value_read`). Only then are the stored value, the paper's own term and the condition rows shown,
and the reviewer approves or disapproves. An issue can be raised at either step, in place of what
remains; raised after the choice, the choice and the value read stay on the row. A reviewer who
leaves between the steps is brought back to the second.

The simulated review takes the same two steps as two model calls, the second carrying the first's
answer and the reveal, and records which model answered each (`answered_by`). An item cut off
between the steps gets only its second step on the next run. Agreement between the value read and
the stored value is tallied loosely by the run's summary and left to the reader of the rows for
anything finer.

## Trade-off accepted

Two writes where there was one: a half-finished row is now a state the store, the page and the
runner all have to handle, and a reviewer's time is split across two screens. The one-step
writer (`record_decision`) is kept for the rows already written and for a driver that chooses to
show everything at once.

Two model calls per decision instead of one, so a simulated run costs roughly twice what it did.
At the prices involved that is cents.

The first step cannot be answered for an entry whose name does not identify it among the paper's
values — the same quantity under two conditions, which is what the `ADJACENT_CONDITION`
distractor is built from. That is a defect of the entry's name, not of the review, and is fixed
at seeding (the harvest label carries the condition; `feat/harvest-prototype`, `a4fc1bf`). Until
the seeded items are re-extracted, such entries will draw issues of the form "cannot tell which
is meant", which is the correct reading of them.
