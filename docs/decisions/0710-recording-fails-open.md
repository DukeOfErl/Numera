# ADR-0710: Recording fails open, and the spend gate fails closed

- **Status:** accepted
- **Date:** 2026-09-15
- **Pull request:** _pending — `feat/question-id-trail`_

## Context

Two places in this system write something that might not land, and they are one
`except` clause apart in shape:

- `SpendGate` refuses to proceed when it cannot establish that there is budget.
- The durable trail records what a question did.

Both are "a write that did not happen". Read side by side with no explanation,
they look inconsistent, and the natural instinct on noticing an inconsistency is
to make the two agree. One of the two directions is badly wrong, and which one is
not recoverable from the code.

If the trail were made to fail closed, an unreachable telemetry database would
stop the application answering questions — telemetry becoming an outage, which is
a worse version of the problem the durable trail was introduced to fix. If the
spend gate were made to fail open, a run would continue spending real money with
no bound.

This is why it is stated in `agent-session` as a requirement rather than left to
the code: a convention that exists only as an implementation detail is one the
next reader is entitled to tidy up.

## Decision

Recording fails **open**. A failure to record does not fail, delay or alter the
question being answered.

Four specifics, each a requirement rather than a tuning choice:

- **The swallow lives in the recording operation, not at any call site.** This is
  `guard.py`'s lesson with the polarity reversed. That guard had to move *out* of
  the CLI because a refusal in one driver protects one caller; a *tolerance*
  written into one driver leaves the next caller — a harness, a test, a second
  interface — holding an operation that raises.
- **One attempt, never a retry.** An unreachable database does not fail quickly,
  it hangs. A retry doubles the worst case on the render path to buy a row that
  by construction does not matter, and a question held open to record it is a
  worse outcome for the reader than the missing row.
- **Nothing is buffered to be flushed later.** Session state dies with the
  container, which is precisely the storage being escaped, so a buffer there is
  exactly as ephemeral as the file it replaces.
- **Silent toward the reader, noisy toward the operator.** The hazard of failing
  open is never the lost row; it is discovering in six weeks that the table has
  been empty the whole time. A failure is reported to stderr and counted.

`KeyboardInterrupt` and other `BaseException`s are deliberately *not* swallowed.
A person pressing Ctrl-C must not be absorbed by telemetry.

## Trade-off accepted

Records are lost silently from the reader's point of view, and the system cannot
tell the difference between "nothing happened" and "everything happened and
nothing was written". That is the cost of the policy, and it is why the counter
and the reported line exist at all.

The counter is per-process and in memory, so it answers "is this container
writing?" and not "has anything been recorded this month". The second question is
answered by querying the table for a gap in timestamps, which is the only form of
it that survives the restart this change exists to make survivable. Recording
that here because the first is easy to mistake for the second.
