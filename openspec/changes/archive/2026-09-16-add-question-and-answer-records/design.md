## Context

See `proposal.md` — Why. The constraints that shape the approach:

- **The trail has two sinks and neither call site knows it.** `trace.py` writes to
  a logger; `trail_store.py` attaches to that logger as a second handler. Nothing
  here needs a new mechanism — `QuestionTrace.record` already takes arbitrary
  keyword fields and they land in the `detail` jsonb column.
- **The seams already exist.** `agent.ask` holds the question text from its first
  line. `AnswerEntries` is emitted with `cited`, `retrieved`, `matched`,
  `searches` and `question` already assembled. `question.answered` is recorded
  immediately before the `Answer` event is yielded.
- **The agent is the only place that can do this.** The drivers see the text too,
  but a record written by a driver exists only for that driver — the evaluation
  harness is the third adapter and would be missing from the data. Guards and
  records belong to the operation.
- **Recording fails open** (ADR-0710). Nothing added here may change that.

## Goals / Non-Goals

**Goals.** One record kind for the question, one for the answer, one for the
evidence set. Every one keyed on the existing `question_id`. No schema change.

**Non-Goals, at the design level:**

- **Not the displayed subset.** What the reader saw is `CITED_ROWS` and
  `UNCITED_ROWS` of a larger set, chosen by presentation. It is a legitimate
  thing to want — "they rated it down because the entry they wanted was cut" is a
  real hypothesis — but it is a driver-side record and a different decision.
- **Not redaction, retention or deletion.** Keeping a person's words raises all
  three. None is answered here, and the spec says only what is kept and why.
  Identity arrives in `add-user-identity`; that is the change where "whose words
  are these" becomes answerable and therefore where deletion becomes meaningful.
- **Not the answer's shape.** `add-answer-shape` is a separate open change.

## Decisions

### Three records, not one

The question is known at the start, the evidence in the middle, the answer at the
end. One combined record would have to be held and written last, which loses the
question whenever a run dies between — and a question that ended without an answer
is exactly the case worth having.

*Alternative considered:* a single `question.completed` record. Rejected for the
above, and because the trail's existing shape is one record per thing that
happened, not one row per question.

### The question is recorded when the question starts

Not at the end. A question that hits a spend ceiling, a missing key or a crash
still produces a record of what was asked. The spec makes this a scenario of its
own because the failing cases are the ones worth investigating, and they are
precisely the ones a write-at-the-end design drops.

### The evidence record rides the existing `AnswerEntries` seam

`cited` and `retrieved` are already computed there, together, at the moment the
answer resolved to them. Recording elsewhere would mean recomputing, and a
recomputation can disagree with what the answer was actually given — which is the
one thing this record exists to pin down.

`retrieved` is the whole retrieved set, not the displayed head of it.

### Cited and retrieved stay separable in the record

Not one merged list. The distinction is the difference between "the answer stood
on this" and "this was in front of it", and merging them cannot be undone by a
query. The entries table already treats them as different things.

### Answer text is recorded verbatim, not summarised or truncated

A truncated answer cannot be compared against the rating it received. Size is
discussed under Risks.

## Risks / Trade-offs

**Row size grows from ~100 bytes to ~1 KB** → Accepted, unmitigated. At alpha
scale — tens of questions a day — this is single-digit megabytes a year, well
inside Neon's free tier. Revisit if the corpus of questions ever outgrows it, not
before; a size guard added now would be speculation with a real cost (a truncated
answer is a useless one).

**A long answer meets the statement timeout** → `STATEMENT_TIMEOUT_MS` is 2000ms
and an insert of a kilobyte is nowhere near it. But the failure mode if it ever
happened is a *silent* dropped row, because recording fails open. The
`FAILURES_BEFORE_GIVING_UP` counter and the stderr complaint already exist for
this; no new mechanism, but worth a task that checks the count is still reported.

**The reader is not told their question is kept** → The spec requires they can
learn it from the interface. The prototype banner is the obvious place and it is
already pinned to the viewport. This is a real obligation, not a nicety: the
change stores what somebody typed.

**Something else starts writing the question** → If a driver later records the
question too, the same text lands twice under one identifier and a naive query
double-counts. The agent-side record is the one the spec requires; a task notes
that the driver must not add its own.

## Migration Plan

None. Additive event values in an append-only table; rows written before this
change are unchanged and still valid. Rollback is reverting the commit — the rows
already written remain readable and simply stop appearing for later questions.

There is no backfill and cannot be: the text of questions already asked was never
kept anywhere. That is the argument for doing this now rather than later.
