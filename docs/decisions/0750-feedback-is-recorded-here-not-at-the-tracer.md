# ADR-0750: Feedback is recorded in our own table; the tracer gets a copy

- **Status:** accepted
- **Date:** 2026-09-15
- **Pull request:** _pending — `feat/answer-feedback`_

## Context

A hosted LLM tracer has a first-class notion of feedback: a score attached to a
run, with a value and a comment, written in one call. It is the obvious place to
put a thumbs-up, and it is where someone debugging a single question is already
looking.

There is also `trail_store`, this project's own append-only table, which already
holds what each question retrieved and keyed to the same `question_id` a rating
would name.

## Decision

**`trail_store` is the record. The tracer receives a copy and is not relied on.**

Three findings, each checked on 2026-09-15, and the first alone is decisive:

- **Feedback dies with the trace.** It is a child object of the run. On the free
  tier a trace expires after fourteen days, at which point "traces are no longer
  accessible in the tracing project UI or via the API", and deleted traces are
  unrecoverable — no recycle bin, and support cannot restore them.
- **The vendor's own documentation contradicts itself** on whether attaching
  feedback extends a trace's retention: the support article says it auto-upgrades
  the trace, the billing page says the UI sends feedback *without* extending it
  and an upgrade requires an explicit API flag. Both first-party, both current.
  A system of record cannot rest on a question its supplier answers two ways.
- **Retention was re-cut from 400 days to 180 on 2026-09-14** — the day before
  this decision. Reading it back in bulk is worse: the export path became
  enterprise-only for new customers on 2026-08-03, and the remaining API is keyed
  by run id, which is gone once the trace expires, taking the join key with it.

The copy is still written, with the retention-extension flag set, because a
thumbs-down sitting beside the trace it refers to is worth three lines to
whoever is debugging that run.

## Trade-off accepted

The same judgement is written twice and the two can disagree — a failed write to
one leaves the other holding a rating the first does not. Tolerable because the
copy is a convenience and the table is the record: they are not two systems of
record, and only one is ever read back for analysis.

We also accept that the tracer's own feedback UI, if anyone uses it, writes
somewhere we do not read. Nothing prevents that; it is worth knowing.

## Where this leaves the data

Ratings land in the same table and on the same key as the trail of what the
question retrieved, so "this answer was rated down, and here is what it was
shown" is one join rather than an export from a third party. That is the query
the whole change exists to make possible, and it is the reason this decision goes
the way it does even though the tracer's API is easier.
