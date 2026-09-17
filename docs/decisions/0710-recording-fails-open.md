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

## Giving up was permanent, and that lost everything

Reported by the operator: the trail had stopped reaching the database. It had, for
every run, and nothing said so.

`install` attempted the schema once and, on failure, **returned without attaching
the handler at all**. It runs inside `web.resources`, which is
`@st.cache_resource` — once per container. So a single failed connection at
startup meant nothing was even trying to write for the life of the process, and
the database being reachable two seconds later changed nothing.

Neon's free tier suspends compute after minutes of inactivity, and a cold start
can outrun `CONNECT_TIMEOUT_S`. Opening the app after a break was therefore the
*ordinary* case and the failing one. It was silent by construction: recording
fails open, so the only evidence was one `complain()` line on stderr at startup,
and the file sink kept working — 292 records across 31 questions sat in
`logs/trace.jsonl` while the table stayed empty.

**Reproduced before it was fixed**, with an engine that refuses exactly one
connection and then behaves: handler attached `False`, rows written by ten later
records `0`. Against a healthy engine, `True` and 22.

### What was right about the old reasoning, and what was not

The cost argument holds and is kept: an unreachable database does not fail fast,
so paying a connection attempt per question to rediscover a known-dead
destination is exactly what this ADR's no-retry rule forbids. A reader would feel
it as a stall on every question.

The error was concluding "never retry" from "do not retry hard". A verdict about
a destination has a lifetime, and this one had none. `_reachable` now retries the
schema on a timed backoff — once a minute, doubling to a quarter of an hour, the
wait extended *before* each attempt so a failure cannot retry on the next record,
and reset on success so a recovered store keeps no punitive interval. One stalled
question per interval while the destination is down, bounded and shrinking.

Both routes to being unusable — the schema failing at install, and enough
consecutive write failures to conclude the destination died — now clear the same
flag and recover through the same path. The second had the identical defect: a
container that idled overnight while the database slept would have given up for
good.

### Two tests asserted the broken behaviour

`test_install_when_the_schema_cannot_be_created_adds_no_handler` and
`test_a_store_whose_schema_is_absent_does_not_connect_per_call` both passed
throughout, because both encoded the intent rather than the consequence. They are
rewritten to the new contract and say in their docstrings what they used to claim.

That is the lesson worth keeping: a test can be perfectly correct about what the
code does and still be the reason nobody looks. Neither was wrong about
behaviour — they were wrong about what the behaviour was *for*.
