# ADR-0960: A simulated review says it is one, and a role is a label, not a persona

- **Status:** accepted
- **Date:** 2026-10-04
- **Pull request:** not yet opened — branch `feat/simulated-review`

## Context

The demonstration of 2026-10-17 has to show the review pipeline working: entries rated by reviewers
of rising seniority, a trust tier per entry (quote-verified → AI-reviewed → student → scientist →
senior scientist), contradicting reviews, and issues raised against entries. Recruiting reviewers
takes longer than the two weeks available, so Yoav decided on 2026-10-03 that models stand in for
them: each role played by a different model, each over its own subset of the items, the subsets
overlapping and shrinking as the model gets dearer.

That produces rows in `review_decision` that no person wrote, in the table whose whole purpose is
to hold what people decided. Four things had to be settled.

**How a row says who wrote it.** Options: encode it in the `reviewer` string alone (every query
has to parse a name); a boolean `simulated` (says nothing about which model, and a model reviewing
*as itself* — the AI-reviewed tier, a real product stage — is not simulated at all); a role column
and a model column (chosen).

**What "raise an issue" is.** Yoav's description gives a reviewer a third thing to do besides
approving and disapproving. Options: a closed `outcome` column beside the two booleans (two
encodings of one fact, free to disagree); an issue stored as a disapproval with a marker in the
comment (a verdict nobody gave, and unreportable); the two booleans made nullable and an `issue`
text column, each row shape with its own writer (chosen).

**What makes a model a "student".** Options: a persona in the instruction ("answer as a student
would"); the same instruction for every role, the role being only which model answers (chosen).

**Which items a role reviews.** Options: nested subsets, each role re-reviewing part of the one
below (every senior-reviewed entry is also student-reviewed, so "senior only" never occurs);
a random draw per run (not resumable, and a second run reviews a different subset); a draw fixed
by a hash of the role and the item id, independent between roles (chosen).

## Decision

`review_decision` gains `reviewer_role` (`AI`, `STUDENT`, `SCIENTIST`, `SENIOR_SCIENTIST`),
`reviewer_model` and `issue`. A row with a model and a role other than `AI` is a simulated review;
its `reviewer` name begins `simulated-`, and the run's printed summary carries `"simulated": true`.
**Every figure drawn from such rows must be labelled as simulated.**

An issue is a row whose `issue` holds the text and whose `chosen_supporting` and `approved` are
null. `store.record_issue` writes that shape and `store.record_decision` the other; there is no
check constraint, because one cannot be added to a deployed table idempotently and a rule only
fresh databases enforce reads as one they all do. An item a reviewer raised an issue on is not
offered to them again.

`bionumbers.simulated_review` is a second driver over the review task, beside the page. It builds
the screen from `bionumbers.review`'s own functions, so a model is shown what a person is shown —
never the second text's kind or type, never another reviewer's decision — and turns the model's
"A" into `chosen_supporting` through the page's own `first_step_from` (ADR-0970), which also
refuses a choice with no value read, as it does a person's. One instruction serves every
role and names none. `assigned` draws each role's subset from `sha256(role:item_id)` against the
role's share.

The trust tier is not stored. It is read off the roles of the decisions that approved an entry, by
whatever presents it.

## Trade-off accepted

The simulation measures models, not people. Agreement between simulated roles will be higher than
between real reviewers, and they share blind spots with the extractor; contradictions may be few,
and a thin report is shown as thin rather than padded. A persona would have produced livelier data
and none of it would have meant anything.

Because every item has a known supporting text, a run does yield one real figure per model — how
often it picked the supporting text over a distractor — which is the first measurement of whether
a model is usable as the AI-reviewed tier at all.

The review page offers the issue outcome too (two clicks, with a confirm), so issues come from
people and models alike. Independent subsets mean a small item set can leave a
role with very few items or an entry with no rating; that is the shape of real coverage and is
left visible.

Which model plays which role is configuration (`--reviewer ROLE=MODEL@SHARE`), not part of this
decision.
