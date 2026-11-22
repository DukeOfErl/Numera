## Why

Everything the alpha records lands in one table, `trail`, and the only way to read
it is by pasting queries out of `sql/feedback.sql` and `sql/signin.sql` into Neon's
console one at a time. The questions the operator actually asks — are testers
using it, how are questions ending, what is it costing, what do readers think of
the answers, is anything failing silently — each need several of those queries
read side by side, and nobody does that on a quiet afternoon. The alpha has been
recording since 2026-09-15; the record is only worth keeping if someone looks at
it.

The hosted tracer (Langfuse) holds the other half — per-call latency, the span
tree, the prompt and response — and it already has its own dashboards. The
question this change settles is how the two are seen together without making the
tracer into a record it was decided it cannot be (ADR-0750, ADR-1000).

## What Changes

- **A local, read-only operator dashboard over the trail**, as a Streamlit page
  started by one command on the operator's machine. Not deployed; no sign-in of
  its own, because it never leaves the laptop.
- **A top row of health signals** for a chosen period: questions asked, active
  testers, how questions ended, spend, and limit endings — each a count, with the
  number it is a share of beside every rate.
- **A quality row**: readers' verdicts by `run_label`, ungrounded answers,
  unsupported citations, entries retrieved against entries cited.
- **A door row**: who is stuck at sign-in and who is waiting to be enrolled — the
  queries in `sql/signin.sql` and `pending.py`, shown rather than pasted.
- **A recording-health row**: whether the trail and the tracer are themselves
  working — gaps in the trail, tracing failures, cold-start writes.
- **A recent-questions table** that opens one question's whole trail, with a link
  to its Langfuse trace. The trace id is derived from `question_id`, so the link
  needs no lookup and no call to Langfuse.
- **Langfuse is linked, never queried.** Its own dashboards (latency, cost,
  units) are configured in Langfuse, documented here as an operator step. The
  local dashboard makes no call to Langfuse's API.
- **A database role that can read the trail and who is enrolled, and nothing
  else**, created by a committed SQL script. Of `accounts`, which holds testers'
  API keys, it can read only the address and whether the account is disabled.
  It cannot write anywhere.

## Capabilities

### New Capabilities

- `operator-monitoring`: what the operator can see about the alpha's use, cost,
  quality, sign-in queue and recording health; what the view is allowed to read
  and change (the trail only, never written); and how a question is followed
  from the view to its hosted trace.

### Modified Capabilities

None. The trail's schema, its events and the hosted tracer are read as they are;
no requirement on what is recorded changes.

## Impact

- **New package** `src/numera_monitor/`, outside `numera_ask`: a reader of
  the trail, not an adapter over the agent. It imports from `numera_ask` only
  `neon` (to resolve a branch name) and `hosted_trace.trace_id_for` (to derive
  the trace id); nothing in `numera_ask` imports it.
- **No new dependencies.** Runs on the `ask` extra, which already carries
  Streamlit, SQLAlchemy, psycopg and Langfuse (the last only for the trace-id
  derivation).
- **New console script** `numera-monitor`.
- **`neon.endpoint_host`**, a small addition to `numera_ask/neon.py`: a
  branch's host with no credential, so the view never fetches the owner's URL.
- **New console script** `numera-monitor-grant`: creates the read-only role
  (or rotates its password). Run once per Neon branch by the operator; the
  password is printed once and never written to the repository.
- **Neon**: a new role on the `alpha` branch (and `dev`, for development). No
  schema change. Reads wake a suspended compute, which the design accounts for.
- **Langfuse**: dashboards and up to two alerts configured in its UI — an
  operator step, no code.
- **Docs**: README (how to run it), architecture diagram, CLAUDE.md module table,
  CHANGELOG, roadmap (WP4's "usage-events table and its queries" is partly met by
  reading the trail instead), and ADRs in block `1950`–`1990`.
