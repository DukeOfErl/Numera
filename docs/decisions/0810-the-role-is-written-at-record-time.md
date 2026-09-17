# ADR-0810: The role is a column written when the record is, never looked up afterwards

- **Status:** accepted
- **Date:** 2026-09-16
- **Pull request:** _pending — `feat/user-identity`_

## Context

The five roles exist for one purpose: the judgements testers give will later be
weighted by who gave them. A senior scientist's "wrong" and a student's "wrong"
are different evidence. So every record of a question, and every rating of an
answer, has to carry the role of the account that produced it — and the
question is *when* that role is fixed.

Two ways to attach it, and two places to put it:

- **Look it up at read time**, joining `trail.user_email` to `accounts.role`.
  One column fewer, and the role is always current. But "current" is the
  problem: an account promoted from student to scientist would retroactively
  change the weight of every rating it ever gave, and a rating's weight is
  the weight it carried when given.
- **Write it at record time**, beside `user_email`. Each row says what the role
  was at that moment; a later change touches nothing already written.

And within the second: a column, or a key inside the `detail` JSON. `detail` is
where each event's own fields go and would need no schema change. A column is
the first schema change since the table was created.

## Decision

**`user_role text` is a column, written at record time, beside `user_email`.**

The schema gains it in two places that both run on every start: in the `create
table if not exists`, for a fresh table, and as `alter table … add column if not
exists user_role text`, for the one that already exists. Both are idempotent;
`ensure_schema` executes them one statement at a time in one transaction, because
psycopg refuses several statements in one query once parameters are involved.
Rows written before the column exists carry NULL, which is truthful: nobody was
signed in.

The column rather than `detail`, because the role is a join key, not an event
field. Every weighting query the roles exist for groups or filters on it; a key
inside `jsonb` can be queried but is a different kind of thing from the row's
other identifiers, and `user_email` — the same kind of fact — already set the
precedent as a column.

**Written by the driver's filter, not threaded through the code that records.**
The web driver stamps `user_email` and `user_role` onto every record of a
signed-in session with a `logging.Filter` on the trail's logger, keyed by the
`session_id` every record already carries. `TrailHandler.emit` reads both off
the record as it always read `user_email`. `QuestionTrace`, `agent.py` and
`feedback._record` are unchanged and never hold the value; ADR-0820 says why
that matters beyond tidiness.

## Trade-off accepted

**A role change does not propagate to history, by design.** An operator who
corrects a mis-assigned role gets the correction from that moment on; earlier
rows keep the role that was in force, even where it was a mistake. That is the
same rule as for every other column in an append-only table, and a correction
that mattered can be applied in the query that weights the ratings, with the
reason written beside it.

**The first migration.** Until now the table had never changed shape, and the
`alter` is a second statement that has to stay in step with the `create`. The
live test creates a table in the old shape and runs `ensure_schema` twice
against real Postgres; the offline test asserts the statements exist. The
column stays if the change is rolled back, harmlessly NULL.

**The file sink does not carry it.** `trace.JsonLines` writes the record's
fields and identifiers, not the stamped attributes, so the developer's local
trail file shows no account. It never did, and on a developer's machine there is
no account to show; the durable store is what the operator reads. If the file
is ever wanted with identity, it is one line in the formatter.
